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

# Update the global client reference in telegram_operations
import utils.telegram_operations as telegram_ops_module
telegram_ops_module.client = client

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


# Archive and media processing is now handled by the queue system


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
                # Add archive to download queue
                temp_archive_path = os.path.join(DATA_DIR, filename)
                
                download_task = {
                    'type': 'archive_download',
                    'message': msg,
                    'event': event,
                    'filename': filename,
                    'temp_path': temp_archive_path,
                    'size_bytes': msg.file.size or 0
                }
                
                # Check size limit
                size_gb = (msg.file.size or 0) / (1024 ** 3)
                if size_gb > MAX_ARCHIVE_GB:
                    await event.reply(f'❌ Archive too large ({human_size(msg.file.size or 0)}). Limit is {MAX_ARCHIVE_GB} GB.')
                    return
                
                # Check if already processed
                if cache_manager.is_processed(filename, msg.file.size or 0):
                    await event.reply(f'⏩ Archive {filename} was already processed. Skipping.')
                    return
                
                await queue_manager.add_download_task(download_task)
                
                # Check queue position
                queue_position = queue_manager.download_queue.qsize()
                if queue_position > 0:
                    await event.reply(f'📋 {filename} added to download queue (position: {queue_position})')
                else:
                    await event.reply(f'⬇️ Starting download: {filename}')
            # Check if it's direct media
            elif file_ext in MEDIA_EXTENSIONS:
                # Add direct media to download queue instead of processing immediately
                temp_path = os.path.join(DATA_DIR, filename)
                
                download_task = {
                    'type': 'direct_media_download',
                    'message': msg,
                    'event': event,
                    'filename': filename,
                    'temp_path': temp_path
                }
                
                await queue_manager.add_download_task(download_task)
                
                # Check queue position
                queue_position = queue_manager.download_queue.qsize()
                if queue_position > 0:
                    await event.reply(f'📋 {filename} added to download queue (position: {queue_position})')
                else:
                    await event.reply(f'⬇️ Starting download: {filename}')
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
            await asyncio.sleep(5 * 60)  # Check every 5 minutes for retries
            
            # Process retry queue from queue manager
            await queue_manager.process_retry_queue()
            
            # Also check legacy failed operations
            failed_ops = failed_ops_manager.get_failed_operations()
            current_time = time.time()
            
            for op in failed_ops:
                if op.get('retry_after', 0) <= current_time:
                    logger.info(f"Retrying legacy failed operation: {op}")
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