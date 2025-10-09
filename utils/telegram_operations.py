"""
Telegram operations module for the Telegram Compressed File Extractor.
Contains functions for Telegram client operations, uploads, downloads, and message handling.
"""

import os
import time
import asyncio
import logging
from telethon import TelegramClient
from telethon.errors import RPCError, FloodWaitError, FileReferenceExpiredError
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
from .constants import (
    API_ID, API_HASH, TARGET_USERNAME, SESSION_PATH,
    FAST_DOWNLOAD_ENABLED, FAST_DOWNLOAD_CONNECTIONS, WIFI_ONLY_MODE,
    PHOTO_EXTENSIONS, VIDEO_EXTENSIONS, MEDIA_EXTENSIONS
)
from .utils import human_size, format_eta
from . import media_processing

logger = logging.getLogger('extractor')

# Global client instance
client = None


def get_client() -> TelegramClient:
    """Get or create the global Telethon client."""
    global client
    if client is None:
        client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    return client


async def ensure_target_entity(client_instance=None):
    """Resolve the target username to a Telegram entity."""
    global client
    if client_instance:
        use_client = client_instance
    elif client:
        use_client = client  
    else:
        use_client = get_client()
        
    try:
        entity = await use_client.get_entity(TARGET_USERNAME)
        logger.info(f'Target user resolved: {TARGET_USERNAME} -> id={entity.id}')
        return entity
    except RPCError as e:
        logger.error(f'Failed to resolve target username {TARGET_USERNAME}: {e}')
        raise


class TelegramOperations:
    """Main class for Telegram operations."""
    
    def __init__(self, client_instance: TelegramClient = None):
        global client
        if client_instance:
            self.client = client_instance
        elif client:
            self.client = client
        else:
            self.client = get_client()
    
    async def download_file_with_progress(self, message, file_path: str, progress_callback=None):
        """Download a file from Telegram with progress reporting."""
        try:
            # Try FastTelethon if enabled and available
            if FAST_DOWNLOAD_ENABLED:
                try:
                    from .fast_download import fast_download_to_file
                    await fast_download_to_file(
                        self.client, 
                        message.document, 
                        file_path,
                        progress_callback=progress_callback,
                        max_connections=FAST_DOWNLOAD_CONNECTIONS,
                        wifi_only=WIFI_ONLY_MODE
                    )
                    logger.info(f"FastTelethon download completed: {file_path}")
                    return True
                except Exception as e:
                    logger.warning(f"FastTelethon download failed, falling back to standard: {e}")
            
            # Fallback to standard Telethon download
            await self.client.download_media(
                message,
                file=file_path,
                progress_callback=progress_callback
            )
            logger.info(f"Standard Telethon download completed: {file_path}")
            return True
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited during download, need to wait {e.seconds} seconds")
            raise
        except FileReferenceExpiredError:
            logger.error("File reference expired during download")
            raise
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise
    
    async def upload_photo(self, target, file_path: str, caption: str = "", progress_callback=None):
        """Upload a photo to Telegram."""
        try:
            await self.client.send_file(
                target,
                file_path,
                caption=caption,
                progress_callback=progress_callback
            )
            logger.info(f"Photo uploaded successfully: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Photo upload failed for {file_path}: {e}")
            raise
    
    async def upload_video(self, target, file_path: str, caption: str = "", progress_callback=None):
        """Upload a video to Telegram with proper attributes."""
        try:
            # Get video attributes and thumbnail
            duration, width, height, thumbnail_path = await media_processing.get_video_attributes_and_thumbnail(file_path)
            
            # Prepare video attributes
            attributes = []
            if duration > 0 and width > 0 and height > 0:
                attributes.append(DocumentAttributeVideo(
                    duration=duration,
                    w=width,
                    h=height,
                    supports_streaming=True
                ))
            
            # Add filename attribute
            attributes.append(DocumentAttributeFilename(os.path.basename(file_path)))
            
            # Upload with attributes
            await self.client.send_file(
                target,
                file_path,
                caption=caption,
                attributes=attributes,
                thumb=thumbnail_path,
                progress_callback=progress_callback
            )
            
            # Clean up thumbnail
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except Exception as e:
                    logger.warning(f"Failed to remove thumbnail {thumbnail_path}: {e}")
            
            logger.info(f"Video uploaded successfully: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Video upload failed for {file_path}: {e}")
            raise
    
    async def upload_media_grouped(self, target, media_files: list, caption: str = ""):
        """Upload media files as a grouped album."""
        if not media_files:
            return True
        
        try:
            # Prepare media list with attributes
            media_list = []
            
            for file_path in media_files:
                file_ext = os.path.splitext(file_path)[1].lower()
                
                if file_ext in VIDEO_EXTENSIONS:
                    # Get video attributes
                    duration, width, height, thumbnail_path = await media_processing.get_video_attributes_and_thumbnail(file_path)
                    
                    attributes = []
                    if duration > 0 and width > 0 and height > 0:
                        attributes.append(DocumentAttributeVideo(
                            duration=duration,
                            w=width,
                            h=height,
                            supports_streaming=True
                        ))
                    attributes.append(DocumentAttributeFilename(os.path.basename(file_path)))
                    
                    from telethon.tl.types import InputMediaUploadedDocument
                    media_list.append(InputMediaUploadedDocument(
                        file=await self.client.upload_file(file_path),
                        mime_type='video/mp4',
                        attributes=attributes,
                        thumb=await self.client.upload_file(thumbnail_path) if thumbnail_path else None
                    ))
                    
                    # Clean up thumbnail
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        try:
                            os.remove(thumbnail_path)
                        except Exception:
                            pass
                else:
                    # Photo
                    from telethon.tl.types import InputMediaUploadedPhoto
                    media_list.append(InputMediaUploadedPhoto(
                        file=await self.client.upload_file(file_path)
                    ))
            
            # Send as album
            await self.client.send_file(
                target,
                media_list,
                caption=caption
            )
            
            logger.info(f"Grouped media uploaded successfully: {len(media_files)} files")
            return True
            
        except Exception as e:
            logger.error(f"Grouped media upload failed: {e}")
            raise
    
    async def upload_media_file(self, target, file_path: str, caption: str = "", progress_callback=None):
        """Upload a single media file with appropriate handling."""
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in PHOTO_EXTENSIONS:
            return await self.upload_photo(target, file_path, caption, progress_callback)
        elif file_ext in VIDEO_EXTENSIONS:
            return await self.upload_video(target, file_path, caption, progress_callback)
        else:
            # Upload as document
            try:
                await self.client.send_file(
                    target,
                    file_path,
                    caption=caption,
                    progress_callback=progress_callback
                )
                logger.info(f"Document uploaded successfully: {file_path}")
                return True
            except Exception as e:
                logger.error(f"Document upload failed for {file_path}: {e}")
                raise
    
    def create_progress_callback(self, status_msg, file_type: str = "file"):
        """Create a progress callback for upload/download operations."""
        start_time = time.time()
        last_edit_pct = -15
        last_edit_time = 0
        
        async def progress_callback(current, total):
            nonlocal last_edit_pct, last_edit_time
            
            pct = int(current * 100 / total) if total > 0 else 0
            now = time.time()
            
            elapsed = now - start_time
            speed = current / elapsed if elapsed > 0 else 0
            eta = (total - current) / speed if speed > 0 else float('inf')
            
            # Very conservative throttling to prevent rate limits
            # Update only every 15% and minimum 15 seconds apart
            # This reduces API calls significantly during large uploads
            if (pct >= last_edit_pct + 15) or ((now - last_edit_time) > 15):
                txt = f'📤 Uploading {file_type}: {pct}% | {human_size(speed)}/s | ETA: {format_eta(eta)}'
                try:
                    await status_msg.edit(txt)
                    last_edit_pct = pct
                    last_edit_time = now
                    logger.debug(f"Progress update sent: {pct}% for {file_type}")
                except FloodWaitError as e:
                    # If even progress updates hit rate limits, log and continue silently
                    logger.warning(f"Progress update hit rate limit (wait {e.seconds}s), skipping updates")
                    # Set last_edit_time far in future to prevent further updates
                    last_edit_time = now + e.seconds
                except Exception as e:
                    logger.debug(f"Progress update failed: {e}")
                    pass  # Ignore other edit errors
        
        return progress_callback


def create_download_progress_callback(status_msg, download_status, start_time, filename: str = None):
    """Create a progress callback for download operations.

    Adds filename and instantaneous speed to the edited message.
    """
    last_report = {'pct': -1, 'time': time.time(), 'last_edit_pct': -1, 'last_edit_time': time.time()}
    speed_window = []  # (timestamp, bytes)
    
    def progress(downloaded: int, total: int):
        if not total or downloaded < 0:
            return
        
        pct = int(downloaded * 100 / total)
        now = time.time()
        
        # Update current processing progress
        download_status['progress'] = pct
        
        # Maintain small window for speed calc (last 5 samples / 20s)
        speed_window.append((now, downloaded))
        while len(speed_window) > 5 or (speed_window and now - speed_window[0][0] > 20):
            speed_window.pop(0)
        
        elapsed = now - start_time
        avg_speed = downloaded / elapsed if elapsed > 0 else 0
        
        # Moving speed calculation
        if len(speed_window) >= 2:
            dt = speed_window[-1][0] - speed_window[0][0]
            db = speed_window[-1][1] - speed_window[0][1]
            inst_speed = db / dt if dt > 0 else avg_speed
        else:
            inst_speed = avg_speed
        
        remaining = total - downloaded
        eta = remaining / inst_speed if inst_speed > 0 else float('inf')
        speed_h = human_size(inst_speed) + '/s'
        
        # Throttle status updates
        should_log = pct >= last_report['pct'] + 5 or (now - last_report['time']) >= 10
        should_edit = pct >= last_report['last_edit_pct'] + 5 or (now - last_report['last_edit_time']) >= 7
        
        if should_log:
            logger.info(f'Download {pct}% | {speed_h} | ETA {format_eta(eta)}')
            last_report['pct'] = pct
            last_report['time'] = now
        
        if should_edit:
            name_part = f'{filename} | ' if filename else ''
            txt = (
                f'⬇️ {name_part}Download {pct}% | {speed_h} | ETA {format_eta(eta)} | '
                f'{human_size(downloaded)} / {human_size(total)}'
            )
            asyncio.create_task(_safe_edit_message(status_msg, txt))
            last_report['last_edit_pct'] = pct
            last_report['last_edit_time'] = now
    
    return progress


async def _safe_edit_message(msg, text):
    """Safely edit a message, ignoring errors."""
    try:
        await msg.edit(text)
    except Exception:
        pass  # Ignore edit errors


# Initialize the global client
client = get_client()
