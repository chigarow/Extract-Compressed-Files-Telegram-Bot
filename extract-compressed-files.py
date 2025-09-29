"""Telethon-based implementation to download large compressed archives via a user account,
extract media (images & videos) and forward them to a target user.

Workflow:
1. Run this script (Termux / PC). First run will ask for phone + code + (optional) 2FA password.
2. Send (or forward) a compressed archive (zip/rar/7z/tar/...) to the logged-in user account (A) via any chat (private, saved messages, etc.).
3. The script listens for new messages containing a document whose filename extension matches supported archive formats.
4. It downloads the file (Telethon has higher limits than Bot API), extracts media, and sends media files to target account B (configured in secrets).

New Features:
1. Direct media upload: Send images/videos directly to the user account and they will be re-uploaded to the target user as media.
2. Proper video attributes: Videos now have correct duration and thumbnail for proper display in Telegram.
3. Media tab support: Files are uploaded as native media types (photos/videos) instead of documents to appear in the Media tab.

Notes:
* Credentials loaded from secrets.properties: APP_API_ID, APP_API_HASH, ACCOUNT_B_USERNAME
* Session is persisted in data/session.session (Telethon default if session name is path) to avoid re-login.
"""

import os
import asyncio
import time
import sys
from datetime import datetime
from telethon import events
from telethon.errors import FloodWaitError, FileReferenceExpiredError

# Add the script's directory to the Python path to ensure modules can be found
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import utility modules
from utils import (
    # Constants
    ARCHIVE_EXTENSIONS, MEDIA_EXTENSIONS, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS,
    MAX_ARCHIVE_GB, DATA_DIR, LOG_FILE, MIN_PCT_STEP, MIN_EDIT_INTERVAL,
    FAST_DOWNLOAD_ENABLED, FAST_DOWNLOAD_CONNECTIONS, WIFI_ONLY_MODE,
    
    # Utility functions
    human_size, format_eta, setup_logger,
    
    # File operations
    compute_sha256, extract_with_password, is_password_error, extract_archive_async,
    
    # Media processing
    is_ffmpeg_available, is_ffprobe_available, validate_video_file,
    is_telegram_compatible_video, needs_video_processing,
    compress_video_for_telegram, get_video_attributes_and_thumbnail,
    
    # Cache and persistence
    CacheManager, ProcessManager, FailedOperationsManager,
    
    # Queue management
    get_queue_manager, get_processing_queue,
    
    # Telegram operations
    get_client, ensure_target_entity, TelegramOperations, create_download_progress_callback,
    
    # FastTelethon downloads
    fast_download_to_file,
    
    # Command handlers
    handle_password_command, handle_max_concurrent_command, handle_set_max_archive_gb_command,
    handle_toggle_fast_download_command, handle_toggle_wifi_only_command, 
    handle_toggle_transcoding_command, handle_help_command, handle_battery_status_command,
    handle_status_command, handle_queue_command, handle_cancel_password,
    handle_cancel_extraction, handle_cancel_process
)

# Bot start time
start_time = datetime.now()

# Initialize logging
logger = setup_logger('extractor', LOG_FILE)

# Log FastTelethon availability
try:
    from utils.fast_download import fast_download_to_file
    FAST_DOWNLOAD_AVAILABLE = True
    logger.info("FastTelethon module available - download acceleration enabled")
except ImportError:
    FAST_DOWNLOAD_AVAILABLE = False
    logger.warning("FastTelethon module not available - download acceleration disabled. Run: pip install cryptg for better performance.")

# Initialize global managers
cache_manager = CacheManager()
process_manager = ProcessManager()
failed_ops_manager = FailedOperationsManager()
queue_manager = get_queue_manager()
processing_queue = get_processing_queue()

# Get Telegram client
client = get_client()

# Global state variables
pending_password = None
current_processing = None
semaphore = asyncio.Semaphore(1)  # Will be updated with config
cancelled_operations = set()


async def save_current_processes():
    """Save current processes to file periodically to persist across restarts"""
    while True:
        try:
            await asyncio.sleep(60)  # Save every minute
            await process_manager.save_current_processes()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error saving current processes: {e}")


async def process_archive_event(event):
    """Process an incoming archive file event."""
    global pending_password, current_processing
    
    message = event.message
    filename = message.file.name or 'file'
    size_bytes = message.file.size or 0
    size_gb = size_bytes / (1024 ** 3)
    
    if size_gb > MAX_ARCHIVE_GB:
        await event.reply(f'❌ Archive too large ({human_size(size_bytes)}). Limit is {MAX_ARCHIVE_GB} GB.')
        return

    # Check if already processed
    if cache_manager.is_processed(filename, size_bytes):
        await event.reply(f'⏩ Archive {filename} with size {human_size(size_bytes)} was already processed. Skipping download and extraction.')
        return

    logger.info(f'Received archive: {filename} size={human_size(size_bytes)}')
    temp_archive_path = os.path.join(DATA_DIR, filename)
    start_download_ts = time.time()
    
    # Update current processing status for download phase
    download_status = {
        'filename': filename,
        'status': 'downloading',
        'start_time': start_download_ts,
        'size': size_bytes,
        'progress': 0,
        'event': event,
        'temp_archive_path': temp_archive_path,
        'message': message
    }
    
    current_processing = download_status
    await process_manager.update_download_process(download_status)
    
    status_msg = await event.reply(f'⬇️ Download 0% | ETA -- | 0.00 / {human_size(size_bytes)}')
    
    # Create progress callback
    progress_callback = create_download_progress_callback(status_msg, download_status, start_download_ts)
    
    try:
        # Initialize Telegram operations
        telegram_ops = TelegramOperations(client)
        
        # Download file with progress
        await telegram_ops.download_file_with_progress(
            message, temp_archive_path, progress_callback
        )
        
        # Update status
        await status_msg.edit(f'✅ Download completed! Starting extraction...')
        logger.info(f'Download completed for {filename}')
        
        # Add to processing queue
        await queue_manager.add_processing_task({
            'type': 'extract_and_upload',
            'download_status': download_status,
            'temp_archive_path': temp_archive_path,
            'filename': filename,
            'event': event
        })
        
        # Clear download process
        await process_manager.clear_download_process()
        
    except FloodWaitError as e:
        logger.warning(f"Rate limited during download, need to wait {e.seconds} seconds")
        await event.reply(f'⏸️ Rate limited. Retrying in {e.seconds} seconds...')
        # Add to failed operations for retry
        failed_ops_manager.add_failed_operation({
            'type': 'download',
            'event_data': {'filename': filename, 'size': size_bytes},
            'retry_after': time.time() + e.seconds
        })
    except FileReferenceExpiredError:
        logger.error("File reference expired during download")
        await event.reply('❌ File reference expired. Please send the file again.')
    except Exception as e:
        logger.error(f'Download error for {filename}: {e}')
        await event.reply(f'❌ Download failed: {e}')
        
        # Clean up
        try:
            if os.path.exists(temp_archive_path):
                os.remove(temp_archive_path)
        except Exception:
            pass
    finally:
        current_processing = None


async def process_direct_media_upload(event, file_path: str, filename: str):
    """Process direct media upload."""
    try:
        size_bytes = os.path.getsize(file_path)
        
        # Check if already processed
        if cache_manager.is_processed(filename, size_bytes):
            await event.reply(f'⏩ Direct media {filename} with size {human_size(size_bytes)} was already processed. Skipping upload.')
            try:
                os.remove(file_path)
                logger.info(f'Cleaned up already processed file: {file_path}')
            except Exception as e:
                logger.warning(f'Failed to clean up already processed file {file_path}: {e}')
            return
        
        # Check hash
        file_hash = None
        try:
            file_hash = compute_sha256(file_path)
            if cache_manager.is_hash_processed(file_hash):
                await event.reply('⏩ Media file already processed earlier (hash match). Skipping upload.')
                try:
                    os.remove(file_path)
                    logger.info(f'Cleaned up already processed file: {file_path}')
                except Exception as e:
                    logger.warning(f'Failed to clean up already processed file {file_path}: {e}')
                return
        except Exception as e:
            logger.warning(f'Hashing failed (continuing): {e}')
        
        # Add to upload queue
        upload_task = {
            'type': 'direct_media',
            'event': event,
            'file_path': file_path,
            'filename': filename,
            'file_hash': file_hash,
            'size_bytes': size_bytes
        }
        
        await queue_manager.add_upload_task(upload_task)
        await event.reply(f'📋 Queue: Media {filename} added to upload queue.')
        
    except Exception as e:
        logger.error(f'Error queuing media upload {filename}: {e}')
        await event.reply(f'❌ Error queuing upload for {filename}: {e}')


@client.on(events.NewMessage(incoming=True))
async def watcher(event):
    """Main message watcher for handling incoming files and commands."""
    global pending_password
    
    try:
        msg = event.message
        text = msg.message or ''
        
        # Handle commands
        if text.startswith('/'):
            parts = text.split()
            command = parts[0].lower()
            
            if command == '/help':
                await handle_help_command(event)
            elif command == '/status':
                await handle_status_command(event)
            elif command == '/battery-status':
                await handle_battery_status_command(event)
            elif command in ['/q', '/queue']:
                await handle_queue_command(event)
            elif command == '/pass' and len(parts) > 1:
                password = ' '.join(parts[1:])
                await handle_password_command(event, password)
            elif command == '/cancel-password':
                await handle_cancel_password(event)
            elif command == '/cancel-extraction':
                await handle_cancel_extraction(event)
            elif command == '/cancel-process':
                await handle_cancel_process(event)
            elif command == '/max_concurrent' and len(parts) > 1:
                try:
                    value = int(parts[1])
                    await handle_max_concurrent_command(event, value)
                except ValueError:
                    await event.reply('❌ Invalid number format. Usage: /max_concurrent <number>')
            elif command == '/set_max_archive_gb' and len(parts) > 1:
                try:
                    value = float(parts[1])
                    await handle_set_max_archive_gb_command(event, value)
                except ValueError:
                    await event.reply('❌ Invalid number format. Usage: /set_max_archive_gb <number>')
            elif command == '/toggle_fast_download':
                await handle_toggle_fast_download_command(event)
            elif command == '/toggle_wifi_only':
                await handle_toggle_wifi_only_command(event)
            elif command == '/toggle_transcoding':
                await handle_toggle_transcoding_command(event)
            else:
                await event.reply(f'❌ Unknown command: {command}\n\nUse /help to see available commands.')
            return
        
        # Handle file messages
        if msg.file:
            filename = msg.file.name or 'file'
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Check if it's an archive
            if file_ext in ARCHIVE_EXTENSIONS:
                await process_archive_event(event)
            # Check if it's direct media
            elif file_ext in MEDIA_EXTENSIONS:
                # Download and process as direct media
                temp_path = os.path.join(DATA_DIR, filename)
                
                try:
                    telegram_ops = TelegramOperations(client)
                    await telegram_ops.download_file_with_progress(msg, temp_path)
                    await process_direct_media_upload(event, temp_path, filename)
                except Exception as e:
                    logger.error(f'Error processing direct media {filename}: {e}')
                    await event.reply(f'❌ Error processing media: {e}')
                    # Clean up on error
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except Exception:
                        pass
            else:
                # Not a supported file type
                await event.reply(f'ℹ️ File type not supported: {file_ext}')
    
    except Exception as e:
        logger.error(f'Error in message watcher: {e}')
        await event.reply(f'❌ An error occurred: {e}')


async def retry_failed_operations():
    """Retry failed operations periodically."""
    while True:
        try:
            await asyncio.sleep(30 * 60)  # Check every 30 minutes
            
            failed_ops = failed_ops_manager.get_failed_operations()
            current_time = time.time()
            
            for op in failed_ops:
                if op.get('retry_after', 0) <= current_time:
                    logger.info(f"Retrying failed operation: {op}")
                    # TODO: Implement retry logic based on operation type
                    failed_ops_manager.remove_failed_operation(op)
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in retry failed operations: {e}")


async def schedule_retry_task():
    """Schedule the retry task."""
    retry_task = asyncio.create_task(retry_failed_operations())
    return retry_task


async def main_async():
    """Main async function."""
    logger.info('Starting Telegram Compressed File Extractor...')
    
    try:
        await client.start()
        logger.info('Telegram client started successfully')
        
        # Ensure target entity can be resolved
        await ensure_target_entity()
        
        # Start background tasks
        save_task = asyncio.create_task(save_current_processes())
        retry_task = asyncio.create_task(retry_failed_operations())
        
        logger.info('Bot is running. Send compressed files to extract and forward media!')
        
        # Keep the client running
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info('Received keyboard interrupt, shutting down...')
    except Exception as e:
        logger.error(f'Error in main async: {e}')
    finally:
        # Clean up
        try:
            save_task.cancel()
            retry_task.cancel()
            await queue_manager.stop_all_tasks()
            logger.info('Cleanup completed')
        except Exception as e:
            logger.error(f'Error during cleanup: {e}')


def main():
    """Main entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')


if __name__ == '__main__':
    main()