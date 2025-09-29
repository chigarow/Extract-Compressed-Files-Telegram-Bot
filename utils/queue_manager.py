"""
Queue management module for the Telegram Compressed File Extractor.
Handles download and upload queues with concurrency control.
"""

import asyncio
import logging
import os
import time
from .constants import DOWNLOAD_SEMAPHORE_LIMIT, UPLOAD_SEMAPHORE_LIMIT
from .cache_manager import PersistentQueue
from .constants import DOWNLOAD_QUEUE_FILE, UPLOAD_QUEUE_FILE

logger = logging.getLogger('extractor')


class QueueManager:
    """Manages download and upload queues with persistent storage and concurrency control."""
    
    def __init__(self):
        # Create queues
        self.download_queue = asyncio.Queue()
        self.upload_queue = asyncio.Queue()
        
        # Semaphores for concurrency control
        self.download_semaphore = asyncio.Semaphore(DOWNLOAD_SEMAPHORE_LIMIT)
        self.upload_semaphore = asyncio.Semaphore(UPLOAD_SEMAPHORE_LIMIT)
        
        # Persistent storage
        self.download_persistent = PersistentQueue(DOWNLOAD_QUEUE_FILE)
        self.upload_persistent = PersistentQueue(UPLOAD_QUEUE_FILE)
        
        # Processing tasks
        self.download_task = None
        self.upload_task = None
        
        # Load existing items from persistent storage
        self._restore_queues()
    
    def _restore_queues(self):
        """Restore queues from persistent storage."""
        # Restore download queue
        for item in self.download_persistent.get_items():
            try:
                self.download_queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("Download queue full, skipping item")
        
        # Restore upload queue
        for item in self.upload_persistent.get_items():
            try:
                self.upload_queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("Upload queue full, skipping item")
    
    async def add_download_task(self, task: dict):
        """Add a download task to the queue."""
        await self.download_queue.put(task)
        self.download_persistent.add_item(task)
        
        # Start processor if not running
        if self.download_task is None or self.download_task.done():
            self.download_task = asyncio.create_task(self._process_download_queue())
    
    async def add_upload_task(self, task: dict):
        """Add an upload task to the queue."""
        await self.upload_queue.put(task)
        self.upload_persistent.add_item(task)
        
        # Start processor if not running
        if self.upload_task is None or self.upload_task.done():
            self.upload_task = asyncio.create_task(self._process_upload_queue())
    
    async def _process_download_queue(self):
        """Process download queue with concurrency control."""
        logger.info("Starting download queue processor")
        
        while True:
            try:
                # Get next download task
                task = await self.download_queue.get()
                
                # Remove from persistent storage
                self.download_persistent.remove_item(task)
                
                # Process with semaphore
                async with self.download_semaphore:
                    await self._execute_download_task(task)
                
                self.download_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Download queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in download queue processor: {e}")
                continue
    
    async def _process_upload_queue(self):
        """Process upload queue with concurrency control."""
        logger.info("Starting upload queue processor")
        
        while True:
            try:
                # Get next upload task
                task = await self.upload_queue.get()
                
                # Remove from persistent storage
                self.upload_persistent.remove_item(task)
                
                # Process with semaphore
                async with self.upload_semaphore:
                    await self._execute_upload_task(task)
                
                self.upload_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Upload queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in upload queue processor: {e}")
                continue
    
    async def _execute_download_task(self, task: dict):
        """Execute a download task with retry mechanism."""
        from .telegram_operations import TelegramOperations, create_download_progress_callback
        from .constants import MAX_RETRY_ATTEMPTS, RETRY_BASE_INTERVAL
        import time
        
        filename = task.get('filename', 'unknown')
        message = task.get('message')
        event = task.get('event')
        temp_path = task.get('temp_path')
        retry_count = task.get('retry_count', 0)
        
        if not message or not event or not temp_path:
            logger.error(f"Download task missing required data: {filename}")
            return
            
        try:
            logger.info(f"Executing download task for {filename} (attempt {retry_count + 1})")
            
            # Initialize telegram operations
            telegram_ops = TelegramOperations()
            
            # Create progress callback (only for active downloads, not queued ones)
            start_time = time.time()
            status_msg = await event.reply(f'⬇️ Downloading {filename}...')
            
            progress_callback = create_download_progress_callback(status_msg, {
                'filename': filename,
                'start_time': start_time
            }, start_time)
            
            # Execute download
            await telegram_ops.download_file_with_progress(message, temp_path, progress_callback)
            
            # Success - update status
            elapsed = time.time() - start_time
            size_mb = os.path.getsize(temp_path) / (1024 * 1024) if os.path.exists(temp_path) else 0
            logger.info(f'Download completed: {filename} ({size_mb:.2f} MB) in {elapsed:.1f}s')
            await status_msg.edit(f'✅ Download completed: {filename}')
            
            # Process the downloaded file based on task type
            task_type = task.get('type', 'unknown')
            
            if task_type == 'archive_download':
                # Add to processing queue for extraction
                processing_task = {
                    'type': 'extract_and_upload',
                    'temp_archive_path': temp_path,
                    'filename': filename,
                    'event': event
                }
                
                from . import queue_manager as qm
                processing_queue = qm.get_processing_queue()
                await processing_queue.add_processing_task(processing_task)
                
            elif task_type == 'direct_media_download':
                # Add directly to upload queue
                upload_task = {
                    'type': 'direct_media',
                    'event': event,
                    'file_path': temp_path,
                    'filename': filename,
                    'size_bytes': os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                }
                
                await self.add_upload_task(upload_task)
            
        except Exception as e:
            retry_count += 1
            logger.error(f"Download failed for {filename} (attempt {retry_count}): {e}")
            
            if retry_count < MAX_RETRY_ATTEMPTS:
                # Schedule retry with exponential backoff
                retry_delay = RETRY_BASE_INTERVAL * (3 ** (retry_count - 1))
                logger.info(f"Scheduling retry for {filename} in {retry_delay}s (attempt {retry_count + 1})")
                
                # Add to retry queue
                retry_task = task.copy()
                retry_task['retry_count'] = retry_count
                retry_task['retry_after'] = time.time() + retry_delay
                
                await self._add_to_retry_queue(retry_task)
                
                if event:
                    await event.reply(f'⚠️ Download failed for {filename}. Retrying in {retry_delay}s... (attempt {retry_count + 1}/{MAX_RETRY_ATTEMPTS})')
            else:
                # Max retries reached
                logger.error(f"Download permanently failed for {filename} after {MAX_RETRY_ATTEMPTS} attempts")
                if event:
                    await event.reply(f'❌ Download permanently failed for {filename} after {MAX_RETRY_ATTEMPTS} attempts')
                
                # Clean up
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass
    
    async def _execute_upload_task(self, task: dict):
        """Execute an upload task."""
        from .telegram_operations import TelegramOperations, ensure_target_entity, get_client
        from .media_processing import needs_video_processing, compress_video_for_telegram
        from .cache_manager import CacheManager
        from .utils import human_size
        from .file_operations import compute_sha256
        from .constants import VIDEO_EXTENSIONS
        import os
        import asyncio
        import time
        
        filename = task.get('filename', 'unknown')
        file_path = task.get('file_path')
        event = task.get('event')
        
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Upload task file not found: {file_path}")
            if event:
                await event.reply(f"❌ File not found: {filename}")
            return
            
        try:
            logger.info(f"Executing upload task for {filename}")
            
            # Initialize components
            client = get_client()
            telegram_ops = TelegramOperations(client)
            cache_manager = CacheManager()
            
            # Notify start of upload (only for active uploads)
            upload_msg = await event.reply(f'📤 Uploading {filename}...')
            
            # Get target entity
            target = await ensure_target_entity(client)
            
            # Check if video needs processing
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in VIDEO_EXTENSIONS:
                if needs_video_processing(file_path):
                    # Compress video - fix path generation to avoid corrupting directory structure
                    base_path, ext = os.path.splitext(file_path)
                    if file_ext != '.mp4':
                        compressed_path = base_path + '_compressed.mp4'
                    else:
                        compressed_path = base_path + '_compressed' + ext
                    
                    await event.reply(f"🎬 Processing video: {filename}...")
                    
                    success = await compress_video_for_telegram(file_path, compressed_path)
                    if success and os.path.exists(compressed_path):
                        # Replace original with compressed
                        try:
                            os.remove(file_path)
                            os.rename(compressed_path, file_path)
                            logger.info(f"Video compression completed: {filename}")
                        except Exception as e:
                            logger.error(f"Error replacing compressed video: {e}")
                    else:
                        logger.warning(f"Video compression failed for {filename}, uploading original")
            
            # Upload the media file with progress tracking
            progress_callback = telegram_ops.create_progress_callback(upload_msg, filename)
            
            # Add archive name to caption if it's from an archive
            archive_name = task.get('archive_name')
            if archive_name:
                caption = f"📎 {filename}\n📦 From: {archive_name}"
            else:
                caption = f"📎 {filename}"
            
            await telegram_ops.upload_media_file(
                target, file_path, 
                caption=caption,
                progress_callback=progress_callback
            )
            
            # Update cache
            file_hash = task.get('file_hash')
            if not file_hash:
                file_hash = compute_sha256(file_path)
            
            size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else task.get('size_bytes', 0)
            await cache_manager.add_to_cache(file_hash, {
                'filename': filename,
                'size': size_bytes,
                'timestamp': time.time(),
                'uploaded': True
            })
            
            await upload_msg.edit(f"✅ Upload completed: {filename}")
            logger.info(f"Upload completed successfully: {filename}")
            
        except Exception as e:
            retry_count = task.get('retry_count', 0) + 1
            logger.error(f"Upload failed for {filename} (attempt {retry_count}): {e}")
            
            if retry_count < MAX_RETRY_ATTEMPTS:
                # Schedule retry with exponential backoff
                retry_delay = RETRY_BASE_INTERVAL * (3 ** (retry_count - 1))
                logger.info(f"Scheduling upload retry for {filename} in {retry_delay}s")
                
                # Add to retry queue
                retry_task = task.copy()
                retry_task['retry_count'] = retry_count
                retry_task['retry_after'] = time.time() + retry_delay
                
                await self._add_to_retry_queue(retry_task)
                
                await event.reply(f'⚠️ Upload failed for {filename}. Retrying in {retry_delay}s... (attempt {retry_count + 1}/{MAX_RETRY_ATTEMPTS})')
            else:
                # Max retries reached
                logger.error(f"Upload permanently failed for {filename} after {MAX_RETRY_ATTEMPTS} attempts")
                await event.reply(f"❌ Upload permanently failed for {filename} after {MAX_RETRY_ATTEMPTS} attempts")
        finally:
            # Clean up file
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up file {file_path}: {e}")
    
    def get_queue_status(self) -> dict:
        """Get current queue status."""
        return {
            'download_queue_size': self.download_queue.qsize(),
            'upload_queue_size': self.upload_queue.qsize(),
            'download_semaphore_available': self.download_semaphore._value,
            'upload_semaphore_available': self.upload_semaphore._value,
            'download_task_running': self.download_task and not self.download_task.done(),
            'upload_task_running': self.upload_task and not self.upload_task.done(),
        }
    
    async def stop_all_tasks(self):
        """Stop all processing tasks."""
        if self.download_task and not self.download_task.done():
            self.download_task.cancel()
            try:
                await self.download_task
            except asyncio.CancelledError:
                pass
        
        if self.upload_task and not self.upload_task.done():
            self.upload_task.cancel()
            try:
                await self.upload_task
            except asyncio.CancelledError:
                pass
    
    def clear_all_queues(self):
        """Clear all queues and persistent storage."""
        # Clear in-memory queues
        while not self.download_queue.empty():
            try:
                self.download_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        while not self.upload_queue.empty():
            try:
                self.upload_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Clear persistent storage
        self.download_persistent.clear()
        self.upload_persistent.clear()
    
    async def _add_to_retry_queue(self, task: dict):
        """Add a failed task to the retry queue."""
        from .constants import RETRY_QUEUE_FILE
        from .cache_manager import make_serializable
        import json
        
        # Load existing retry queue
        retry_queue = []
        if os.path.exists(RETRY_QUEUE_FILE):
            try:
                with open(RETRY_QUEUE_FILE, 'r') as f:
                    retry_queue = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load retry queue: {e}")
        
        # Add new task (make it serializable)
        serializable_task = make_serializable(task)
        retry_queue.append(serializable_task)
        
        # Save updated retry queue
        try:
            with open(RETRY_QUEUE_FILE, 'w') as f:
                json.dump(retry_queue, f, indent=2)
            logger.info(f"Added task to retry queue: {task.get('filename')}")
        except Exception as e:
            logger.error(f"Failed to save retry queue: {e}")
    
    async def process_retry_queue(self):
        """Process tasks from the retry queue."""
        from .constants import RETRY_QUEUE_FILE
        import json
        import time
        
        if not os.path.exists(RETRY_QUEUE_FILE):
            return
        
        try:
            with open(RETRY_QUEUE_FILE, 'r') as f:
                retry_queue = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load retry queue: {e}")
            return
        
        current_time = time.time()
        remaining_tasks = []
        
        for task in retry_queue:
            retry_after = task.get('retry_after', 0)
            
            if retry_after <= current_time:
                # Time to retry this task
                task_type = task.get('type', 'unknown')
                filename = task.get('filename', 'unknown')
                
                logger.info(f"Retrying {task_type} for {filename}")
                
                try:
                    if 'download' in task_type or 'message' in task:
                        await self.add_download_task(task)
                    elif 'upload' in task_type or 'file_path' in task:
                        await self.add_upload_task(task)
                    else:
                        # Processing task
                        from . import queue_manager as qm
                        processing_queue = qm.get_processing_queue()
                        await processing_queue.add_processing_task(task)
                        
                except Exception as e:
                    logger.error(f"Failed to retry task {filename}: {e}")
                    remaining_tasks.append(task)
            else:
                # Not ready to retry yet
                remaining_tasks.append(task)
        
        # Update retry queue file
        try:
            with open(RETRY_QUEUE_FILE, 'w') as f:
                # Make sure remaining tasks are serializable
                from .cache_manager import make_serializable
                serializable_tasks = make_serializable(remaining_tasks)
                json.dump(serializable_tasks, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to update retry queue: {e}")


class ProcessingQueue:
    """Manages the main processing queue for extracted files."""
    
    def __init__(self):
        self.processing_queue = asyncio.Queue()
        self.processing_task = None
        self.current_processing = None
        
    async def add_processing_task(self, task: dict):
        """Add a task to the processing queue."""
        await self.processing_queue.put(task)
        
        # Start processor if not running
        if self.processing_task is None or self.processing_task.done():
            self.processing_task = asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """Process the main processing queue."""
        logger.info("Starting main processing queue")
        
        while True:
            try:
                # Get next processing task
                task = await self.processing_queue.get()
                self.current_processing = task
                
                # Execute the task
                await self._execute_processing_task(task)
                
                self.current_processing = None
                self.processing_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Processing queue cancelled")
                break
            except Exception as e:
                logger.error(f"Error in processing queue: {e}")
                self.current_processing = None
                continue
    
    async def _execute_processing_task(self, task: dict):
        """Execute a processing task (extraction and upload) with retry mechanism."""
        from .file_operations import extract_archive_async, compute_sha256
        from .media_processing import needs_video_processing, compress_video_for_telegram
        from .telegram_operations import TelegramOperations, ensure_target_entity
        from .cache_manager import CacheManager
        from .constants import MAX_RETRY_ATTEMPTS, RETRY_BASE_INTERVAL, MEDIA_EXTENSIONS, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
        import os
        import shutil
        import asyncio
        import time
        
        task_type = task.get('type')
        filename = task.get('filename', 'unknown')
        retry_count = task.get('retry_count', 0)
        
        try:
            logger.info(f"Executing processing task: {task_type} for {filename} (attempt {retry_count + 1})")
            
            if task_type == 'extract_and_upload':
                await self._process_archive_extraction(task)
            elif task_type == 'process_downloaded_file':
                await self._process_downloaded_file(task)
            else:
                logger.warning(f"Unknown processing task type: {task_type}")
                
        except Exception as e:
            retry_count += 1
            logger.error(f"Processing failed for {filename} (attempt {retry_count}): {e}")
            
            if retry_count < MAX_RETRY_ATTEMPTS:
                # Schedule retry with exponential backoff
                retry_delay = RETRY_BASE_INTERVAL * (3 ** (retry_count - 1))
                logger.info(f"Scheduling processing retry for {filename} in {retry_delay}s")
                
                # Add to retry queue
                retry_task = task.copy()
                retry_task['retry_count'] = retry_count
                retry_task['retry_after'] = time.time() + retry_delay
                
                await self._add_to_retry_queue(retry_task)
                
                event = task.get('event')
                if event:
                    await event.reply(f'⚠️ Processing failed for {filename}. Retrying in {retry_delay}s... (attempt {retry_count + 1}/{MAX_RETRY_ATTEMPTS})')
            else:
                # Max retries reached
                logger.error(f"Processing permanently failed for {filename} after {MAX_RETRY_ATTEMPTS} attempts")
                event = task.get('event')
                if event:
                    await event.reply(f'❌ Processing permanently failed for {filename} after {MAX_RETRY_ATTEMPTS} attempts')
    
    async def _process_archive_extraction(self, task: dict):
        """Process archive extraction and media upload."""
        from .file_operations import extract_archive_async
        from .utils import human_size
        import tempfile
        
        temp_archive_path = task.get('temp_archive_path')
        filename = task.get('filename')
        event = task.get('event')
        
        if not temp_archive_path or not os.path.exists(temp_archive_path):
            raise FileNotFoundError(f"Archive file not found: {temp_archive_path}")
        
        # Create extraction directory
        extract_path = os.path.join(os.path.dirname(temp_archive_path), f'extracted_{filename}_{int(time.time())}')
        os.makedirs(extract_path, exist_ok=True)
        
        try:
            # Update status
            await event.reply(f'📦 Extracting {filename}...')
            
            # Extract archive
            loop = asyncio.get_event_loop()
            success, error_msg = await loop.run_in_executor(None, extract_archive_async, temp_archive_path, extract_path, filename)
            
            if not success:
                raise RuntimeError(f"Extraction failed: {error_msg}")
            
            # Find media files
            media_files = []
            for root, dirs, files in os.walk(extract_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file)[1].lower()
                    if file_ext in MEDIA_EXTENSIONS:
                        media_files.append(file_path)
            
            if not media_files:
                await event.reply(f'ℹ️ No media files found in {filename}')
                return
            
            await event.reply(f'📤 Found {len(media_files)} media files. Starting upload...')
            
            # Process and upload media files
            for media_file in media_files:
                media_filename = os.path.basename(media_file)
                
                # Add each media file to upload queue
                upload_task = {
                    'type': 'extracted_media',
                    'event': event,
                    'file_path': media_file,
                    'filename': media_filename,
                    'archive_name': filename,
                    'size_bytes': os.path.getsize(media_file)
                }
                
                await self.add_upload_task(upload_task)
            
            await event.reply(f'✅ Queued {len(media_files)} media files from {filename} for upload')
            
        finally:
            # Clean up
            try:
                if os.path.exists(temp_archive_path):
                    os.remove(temp_archive_path)
                shutil.rmtree(extract_path, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Cleanup error for {filename}: {e}")
    
    async def _process_downloaded_file(self, task: dict):
        """Process a downloaded file (direct media)."""
        file_path = task.get('file_path')
        filename = task.get('filename')
        event = task.get('event')
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Downloaded file not found: {file_path}")
        
        # This is a direct media file, add to upload queue
        upload_task = {
            'type': 'direct_media',
            'event': event,
            'file_path': file_path,
            'filename': filename,
            'size_bytes': os.path.getsize(file_path)
        }
        
        await self.add_upload_task(upload_task)
    
    def get_current_processing(self):
        """Get currently processing task."""
        return self.current_processing
    
    def get_queue_size(self) -> int:
        """Get current processing queue size."""
        return self.processing_queue.qsize()
    
    async def cancel_current_processing(self):
        """Cancel current processing task."""
        if self.processing_task and not self.processing_task.done():
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
            self.current_processing = None


# Global instances
queue_manager = None
processing_queue = None


def get_queue_manager() -> QueueManager:
    """Get or create the global queue manager instance."""
    global queue_manager
    if queue_manager is None:
        queue_manager = QueueManager()
    return queue_manager


def get_processing_queue() -> ProcessingQueue:
    """Get or create the global processing queue instance."""
    global processing_queue
    if processing_queue is None:
        processing_queue = ProcessingQueue()
    return processing_queue
