"""
Command handlers module for the Telegram Compressed File Extractor.
Contains functions to handle user commands and interactions.
"""

import os
import json
import shutil
import subprocess
import asyncio
import logging
import time
from datetime import datetime
import psutil
from .constants import (
    MAX_ARCHIVE_GB, MAX_CONCURRENT, FAST_DOWNLOAD_ENABLED, 
    WIFI_ONLY_MODE, TRANSCODE_ENABLED, DATA_DIR, LOG_FILE
)
from .utils import human_size, format_eta
from config import config

logger = logging.getLogger('extractor')

# Global state variables - these will be imported from main
pending_password = None
current_processing = None
processing_queue = None
semaphore = None
start_time = None


async def handle_password_command(event, password: str):
    """Handle password input for password-protected archives."""
    global pending_password, current_processing
    
    if not pending_password:
        await event.reply('ℹ️ No pending password-protected archive.')
        return
    
    archive_path = pending_password['archive_path']
    extract_path = pending_password['extract_path']
    filename = pending_password['filename']
    original_event = pending_password['original_event']
    file_hash = pending_password['hash']
    
    try:
        await event.reply(f'🔐 Attempting extraction with provided password for {filename}...')
        
        # Import here to avoid circular imports
        from .file_operations import extract_with_password
        
        # Try extraction with password
        extract_with_password(archive_path, extract_path, password)
        
        logger.info(f'Password extraction successful for {filename}')
        await event.reply(f'✅ Password extraction successful for {filename}! Starting media processing...')
        
        # Continue with media processing
        from .file_operations import compute_sha256
        
        # Update cache with the successful extraction
        file_info = {
            'filename': filename,
            'size': os.path.getsize(archive_path),
            'timestamp': time.time(),
            'extracted': True
        }
        
        # Add to processing queue for media upload
        processing_task = {
            'type': 'extract_and_upload',
            'archive_path': archive_path,
            'extract_path': extract_path,
            'filename': filename,
            'original_event': original_event,
            'file_hash': file_hash,
            'file_info': file_info
        }
        
        if processing_queue:
            await processing_queue.put(processing_task)
        
        # Clear pending password state
        pending_password = None
        
    except Exception as e:
        error_msg = str(e)
        
        from .file_operations import is_password_error
        
        if is_password_error(error_msg):
            await event.reply(f'❌ Incorrect password for {filename}. Please try again with /pass <password> or use /cancel-password to abort.')
            logger.warning(f'Incorrect password attempt for {filename}: {error_msg}')
        else:
            await event.reply(f'❌ Password extraction failed for {filename}: {error_msg}')
            logger.error(f'Password extraction error for {filename}: {error_msg}')
            
            # Clean up on other errors
            try:
                shutil.rmtree(extract_path, ignore_errors=True)
                if os.path.exists(archive_path):
                    os.remove(archive_path)
            except Exception as cleanup_e:
                logger.warning(f'Cleanup error after password extraction failure: {cleanup_e}')
            
            pending_password = None
            current_processing = None


async def handle_max_concurrent_command(event, value: int):
    """Handle the /max_concurrent command to change the maximum concurrent downloads"""
    global MAX_CONCURRENT, semaphore
    
    try:
        # Update the configuration
        if 'DEFAULT' not in config._config:
            config._config['DEFAULT'] = {}
        config._config['DEFAULT']['MAX_CONCURRENT'] = str(value)
        config.save()
        config.max_concurrent = value
        
        # Update global variables
        MAX_CONCURRENT = value
        
        # Create a new semaphore with the new value
        if semaphore:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
        await event.reply(f'✅ Maximum concurrent downloads set to {value}.')
        
    except Exception as e:
        logger.error(f"Error updating max_concurrent: {e}")
        await event.reply(f'❌ Failed to update maximum concurrent downloads: {e}')


async def handle_set_max_archive_gb_command(event, value: float):
    """Handle the /set_max_archive_gb command to change the maximum archive size"""
    global MAX_ARCHIVE_GB
    
    try:
        if 'DEFAULT' not in config._config:
            config._config['DEFAULT'] = {}
        config._config['DEFAULT']['MAX_ARCHIVE_GB'] = str(value)
        config.save()
        config.max_archive_gb = value
        MAX_ARCHIVE_GB = value
        
        await event.reply(f'✅ Maximum archive size set to {value} GB.')
        
    except Exception as e:
        logger.error(f"Error updating max_archive_gb: {e}")
        await event.reply(f'❌ Failed to update maximum archive size: {e}')


async def handle_toggle_fast_download_command(event):
    """Handle the /toggle_fast_download command to enable/disable fast download"""
    global FAST_DOWNLOAD_ENABLED
    
    try:
        new_value = not config.fast_download_enabled
        if 'DEFAULT' not in config._config:
            config._config['DEFAULT'] = {}
        config._config['DEFAULT']['FAST_DOWNLOAD_ENABLED'] = str(new_value)
        config.save()
        config.fast_download_enabled = new_value
        FAST_DOWNLOAD_ENABLED = new_value
        
        status = "Enabled" if new_value else "Disabled"
        await event.reply(f'✅ Fast download {status}.')
        
    except Exception as e:
        logger.error(f"Error updating fast_download_enabled: {e}")
        await event.reply(f'❌ Failed to update fast download setting: {e}')


async def handle_toggle_wifi_only_command(event):
    """Handle the /toggle_wifi_only command to enable/disable wifi only mode"""
    global WIFI_ONLY_MODE
    
    try:
        new_value = not config.wifi_only_mode
        if 'DEFAULT' not in config._config:
            config._config['DEFAULT'] = {}
        config._config['DEFAULT']['WIFI_ONLY_MODE'] = str(new_value)
        config.save()
        config.wifi_only_mode = new_value
        WIFI_ONLY_MODE = new_value
        
        status = "Enabled" if new_value else "Disabled"
        await event.reply(f'✅ WiFi-Only mode {status}.')
        
    except Exception as e:
        logger.error(f"Error updating wifi_only_mode: {e}")
        await event.reply(f'❌ Failed to update WiFi-Only mode setting: {e}')


async def handle_toggle_transcoding_command(event):
    """Handle the /toggle_transcoding command to enable/disable video transcoding"""
    global TRANSCODE_ENABLED
    
    try:
        new_value = not config.transcode_enabled
        if 'DEFAULT' not in config._config:
            config._config['DEFAULT'] = {}
        config._config['DEFAULT']['TRANSCODE_ENABLED'] = str(new_value)
        config.save()
        config.transcode_enabled = new_value
        TRANSCODE_ENABLED = new_value
        
        status = "Enabled" if new_value else "Disabled"
        await event.reply(f'✅ Video transcoding {status}.')
        
    except Exception as e:
        logger.error(f"Error updating transcode_enabled: {e}")
        await event.reply(f'❌ Failed to update video transcoding setting: {e}')


async def handle_help_command(event):
    """Show a list of all available commands"""
    help_message = (
        f"**Available Commands**\n\n"
        f"**/help** - Show this help message\n"
        f"**/status** - Show the current status of the bot\n"
        f"**/battery-status** - Show the battery status (Termux only)\n"
        f"**/q** or **/queue** - Show the current processing queue\n"
        f"**/pass <password>** - Provide the password for a protected archive\n"
        f"**/cancel-password** - Cancel password input for a protected archive\n"
        f"**/cancel-extraction** - Cancel the current extraction process\n"
        f"**/cancel-process** - Cancel the current process and delete any downloaded files\n"
        f"**/max_concurrent <number>** - Set the maximum concurrent downloads (e.g., /max_concurrent 3)\n"
        f"**/set_max_archive_gb <number>** - Set the maximum archive size in GB (e.g., /set_max_archive_gb 10.5)\n"
        f"**/toggle_fast_download** - Enable/disable fast download\n"
        f"**/toggle_wifi_only** - Enable/disable WiFi-Only mode\n"
        f"**/toggle_transcoding** - Enable/disable video transcoding\n"
    )
    await event.reply(help_message)


async def handle_battery_status_command(event):
    """Show battery status using termux-battery-status"""
    try:
        # Check if termux-battery-status is available
        if not shutil.which('termux-battery-status'):
            await event.reply('❌ `termux-battery-status` command not found. This command is only available on Termux.')
            return

        result = subprocess.run(['termux-battery-status'], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            try:
                status = json.loads(result.stdout)
                percentage = status.get('percentage', 'N/A')
                plugged = status.get('plugged', 'N/A')
                health = status.get('health', 'N/A')
                status_str = status.get('status', 'N/A')
                temp = status.get('temperature', 'N/A')
                current = status.get('current')

                current_str = "N/A"
                if current is not None:
                    # The value is in microamperes (µA). Convert to milliamperes (mA).
                    current_ma = current / 1000
                    current_str = f"{current_ma:.2f} mA"
                
                message = (
                    f"**🔋 Battery Status**\n\n"
                    f"**Percentage:** {percentage}%\n"
                    f"**Status:** {status_str}\n"
                    f"**Plugged in:** {plugged}\n"
                    f"**Health:** {health}\n"
                    f"**Temperature:** {temp}°C\n"
                    f"**Current:** {current_str}"
                )
                await event.reply(message)
            except json.JSONDecodeError:
                await event.reply(f"❌ Failed to parse battery status output:\n\n`{result.stdout}`")
        else:
            await event.reply(f"❌ Error getting battery status:\n\n`{result.stderr}`")
    except Exception as e:
        logger.error(f"Error in handle_battery_status_command: {e}")
        await event.reply(f"❌ An error occurred while fetching battery status: {e}")


async def handle_status_command(event):
    """Show a comprehensive status of the bot and system"""
    global start_time
    
    # System Usage
    try:
        cpu_usage = psutil.cpu_percent()
        cpu_status = f"{cpu_usage}%"
    except PermissionError:
        cpu_status = "N/A (permission denied)"
    except Exception as e:
        logger.warning(f"Could not get CPU usage: {e}")
        cpu_status = "N/A (error)"

    try:
        mem_info = psutil.virtual_memory()
        mem_status = f"{mem_info.percent}% ({human_size(mem_info.used)} / {human_size(mem_info.total)})"
    except Exception as e:
        logger.warning(f"Could not get memory usage: {e}")
        mem_status = "N/A"

    try:
        disk_info = psutil.disk_usage(DATA_DIR)
        disk_status = f"{disk_info.percent}% ({human_size(disk_info.used)} / {human_size(disk_info.total)})"
    except Exception as e:
        logger.warning(f"Could not get disk usage: {e}")
        disk_status = "N/A"

    # Bot Status
    uptime = datetime.now() - start_time if start_time else "Unknown"
    log_size = os.path.getsize(LOG_FILE) if os.path.exists(LOG_FILE) else 0

    # Configuration
    config_status = (
        f"**Max Archive Size:** {config.max_archive_gb} GB\n"
        f"**Max Concurrent Downloads:** {config.max_concurrent}\n"
        f"**Fast Download:** {'Enabled' if config.fast_download_enabled else 'Disabled'}\n"
        f"**WiFi-Only Mode:** {'Enabled' if config.wifi_only_mode else 'Disabled'}\n"
        f"**Video Transcoding:** {'Enabled' if config.transcode_enabled else 'Disabled'}"
    )

    status_message = (
        f"**🤖 Bot Status**\n"
        f"Uptime: {str(uptime).split('.')[0] if isinstance(uptime, object) else uptime}\n"
        f"Log Size: {human_size(log_size)}\n\n"
        f"**🖥️ System Usage**\n"
        f"CPU: {cpu_status}\n"
        f"Memory: {mem_status}\n"
        f"Disk: {disk_status}\n\n"
        f"**⚙️ Configuration**\n"
        f"{config_status}"
    )

    await event.reply(status_message)


async def handle_queue_command(event):
    """Show current processing status and queue information"""
    global current_processing, pending_password, processing_queue
    
    status_lines = []
    
    # Show current processing file
    if current_processing:
        cp = current_processing
        elapsed = time.time() - cp['start_time']
        status_line = f"📁 **{cp['filename']}**\n"
        status_line += f"Status: {cp['status'].title()}\n"
        status_line += f"Elapsed: {format_eta(elapsed)}\n"
        
        if cp['status'] == 'downloading' and 'progress' in cp:
            status_line += f"Progress: {cp['progress']}%\n"
        elif cp['status'] == 'uploading' and 'uploaded_files' in cp and 'total_files' in cp:
            status_line += f"Upload: {cp['uploaded_files']}/{cp['total_files']} files\n"
        
        status_line += f"Size: {human_size(cp['size'])}"
        status_lines.append(status_line)
    
    # Show pending password-protected archive
    if pending_password:
        pp = pending_password
        status_lines.append(f"🔐 **{pp['filename']}** - Waiting for password")
    
    # Show processing queue (files waiting for extraction/upload after download)
    if processing_queue:
        queue_size = processing_queue.qsize()
        if queue_size > 0:
            status_lines.append(f"🕒 **Processing queue:** {queue_size} files waiting for extraction/upload")
        elif current_processing or pending_password:
            # Show that there are no queued files
            status_lines.append("🕒 **Processing queue:** Empty")
    
    if not status_lines:
        await event.reply('📭 **Queue Status:** Empty\nNo active processing or queued tasks.')
    else:
        queue_msg = "📋 **Current Queue Status:**\n\n" + "\n\n".join(status_lines)
        await event.reply(queue_msg)


async def handle_cancel_password(event):
    """Cancel password input for a password-protected archive"""
    global pending_password, current_processing
    
    if not pending_password:
        await event.reply('ℹ️ No pending password-protected archive.')
        return
        
    archive_path = pending_password['archive_path']
    extract_path = pending_password['extract_path']
    
    try:
        shutil.rmtree(extract_path, ignore_errors=True)
        if os.path.exists(archive_path):
            os.remove(archive_path)
    except Exception as e:
        logger.warning(f'Error during cancel cleanup: {e}')
    
    pending_password = None
    current_processing = None
    await event.reply('✅ Password input cancelled and files removed.')


async def handle_cancel_extraction(event):
    """Cancel the current extraction process"""
    global current_processing, pending_password
    
    if not current_processing:
        await event.reply('ℹ️ No extraction currently in progress.')
        return
    
    # Store the file being processed for the response
    filename = current_processing.get('filename', 'unknown file')
    
    # Clean up any pending password state as well
    if pending_password:
        try:
            archive_path = pending_password['archive_path']
            extract_path = pending_password['extract_path']
            shutil.rmtree(extract_path, ignore_errors=True)
            if os.path.exists(archive_path):
                os.remove(archive_path)
        except Exception as e:
            logger.warning(f'Cleanup error during cancel: {e}')
        pending_password = None
    
    # Clean up current processing
    try:
        if 'temp_archive_path' in current_processing:
            archive_path = current_processing['temp_archive_path']
            if os.path.exists(archive_path):
                os.remove(archive_path)
        if 'extract_path' in current_processing:
            extract_path = current_processing['extract_path']
            shutil.rmtree(extract_path, ignore_errors=True)
    except Exception as e:
        logger.warning(f'Cleanup error during extraction cancel: {e}')
    
    current_processing = None
    await event.reply(f'✅ Extraction cancelled for {filename} and files cleaned up.')


async def handle_cancel_process(event):
    """Cancel the entire current process and clean up files"""
    global current_processing, pending_password
    
    if not current_processing and not pending_password:
        await event.reply('ℹ️ No process currently running.')
        return
    
    filename = "unknown file"
    if current_processing:
        filename = current_processing.get('filename', filename)
    elif pending_password:
        filename = pending_password.get('filename', filename)
    
    # Clean up everything
    cleanup_tasks = []
    
    if current_processing:
        if 'temp_archive_path' in current_processing:
            cleanup_tasks.append(('archive', current_processing['temp_archive_path']))
        if 'extract_path' in current_processing:
            cleanup_tasks.append(('directory', current_processing['extract_path']))
    
    if pending_password:
        cleanup_tasks.append(('archive', pending_password['archive_path']))
        cleanup_tasks.append(('directory', pending_password['extract_path']))
    
    # Perform cleanup
    for cleanup_type, path in cleanup_tasks:
        try:
            if cleanup_type == 'archive' and os.path.exists(path):
                os.remove(path)
                logger.info(f'Removed archive: {path}')
            elif cleanup_type == 'directory':
                shutil.rmtree(path, ignore_errors=True)
                logger.info(f'Removed directory: {path}')
        except Exception as e:
            logger.warning(f'Cleanup error for {path}: {e}')
    
    # Reset global state
    current_processing = None
    pending_password = None
    
    await event.reply(f'✅ Process cancelled for {filename}. All files cleaned up.')
