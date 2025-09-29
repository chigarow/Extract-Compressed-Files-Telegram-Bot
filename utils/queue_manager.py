"""
Queue management module for the Telegram Compressed File Extractor.
Handles download and upload queues with concurrency control.
"""

import asyncio
import logging
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
        """Execute a download task."""
        # This will be implemented with the actual download logic
        # For now, it's a placeholder
        logger.info(f"Executing download task for {task.get('filename', 'unknown')}")
        # TODO: Implement actual download logic
        pass
    
    async def _execute_upload_task(self, task: dict):
        """Execute an upload task."""
        # This will be implemented with the actual upload logic
        # For now, it's a placeholder
        logger.info(f"Executing upload task for {task.get('filename', 'unknown')}")
        # TODO: Implement actual upload logic
        pass
    
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
        """Execute a processing task (extraction and upload)."""
        # This will be implemented with the actual processing logic
        # For now, it's a placeholder
        logger.info(f"Executing processing task for {task.get('filename', 'unknown')}")
        # TODO: Implement actual processing logic
        pass
    
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
