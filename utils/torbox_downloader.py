"""
Torbox downloader module for the Telegram Compressed File Extractor.
Handles detection and downloading of files from Torbox CDN links.
Uses the official Torbox SDK to retrieve file metadata and download files.
"""

import os
import re
import logging
import asyncio
import aiohttp
from typing import Optional, Tuple, Dict, Any
from .utils import human_size, format_eta
import time

logger = logging.getLogger('extractor')

# Torbox CDN URL pattern
# Format: https://store-{number}.{region}.tb-cdn.st/{type}/{uuid}?token={token}
TORBOX_CDN_PATTERN = r'https://store-\d+\.[a-z]+\.tb-cdn\.st/[^/]+/[a-f0-9-]+(?:\?token=[a-f0-9-]+)?'


def is_torbox_link(url: str) -> bool:
    """
    Check if a URL is a Torbox CDN download link.
    
    Args:
        url: The URL to check
        
    Returns:
        True if the URL matches Torbox CDN pattern, False otherwise
    """
    if not url:
        return False
    
    match = re.search(TORBOX_CDN_PATTERN, url, re.IGNORECASE)
    return match is not None


def extract_torbox_links(text: str) -> list:
    """
    Extract all Torbox CDN links from a text message.
    
    Args:
        text: The text to search for links
        
    Returns:
        List of Torbox CDN URLs found in the text
    """
    if not text:
        return []
    
    matches = re.findall(TORBOX_CDN_PATTERN, text, re.IGNORECASE)
    return list(set(matches))  # Remove duplicates


def extract_file_id_from_url(url: str) -> Optional[str]:
    """
    Extract the file UUID from a Torbox CDN URL.
    
    Args:
        url: The Torbox CDN URL
        
    Returns:
        The file UUID if found, None otherwise
    """
    # Extract UUID from URL: https://store-XXX.region.tb-cdn.st/TYPE/UUID?token=...
    match = re.search(r'/([a-f0-9-]+)(?:\?|$)', url)
    if match:
        return match.group(1)
    return None


def get_filename_from_url(url: str) -> str:
    """
    Extract a filename from a Torbox CDN URL (fallback method).
    
    Args:
        url: The Torbox CDN URL
        
    Returns:
        A filename based on the URL structure
    """
    # Extract the file type and UUID from URL
    # Format: https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=...
    match = re.search(r'/([^/]+)/([a-f0-9-]+)', url)
    
    if match:
        file_type = match.group(1)  # e.g., 'zip', 'video', 'file'
        file_uuid = match.group(2)[:8]  # First 8 chars of UUID for brevity
        
        # Try to infer extension from type
        extension_map = {
            'zip': '.zip',
            'rar': '.rar',
            '7z': '.7z',
            'video': '.mp4',
            'audio': '.mp3',
            'image': '.jpg',
            'document': '.pdf'
        }
        
        extension = extension_map.get(file_type.lower(), '')
        return f"torbox_{file_uuid}{extension}"
    
    # Fallback to generic filename
    return f"torbox_download_{int(time.time())}"


async def get_torbox_metadata(api_key: str, web_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get metadata for a Torbox web download using the SDK.
    
    Args:
        api_key: Torbox API key
        web_id: Optional web download ID to fetch specific item
        
    Returns:
        Dictionary containing file metadata or None if failed
    """
    try:
        from torbox_api import TorboxApi
        
        sdk = TorboxApi(
            access_token=api_key,
            base_url="https://api.torbox.app",
            timeout=10000
        )
        
        # Get web downloads list
        # Note: Don't pass id_ parameter if None - SDK validator rejects None explicitly
        if web_id:
            result = sdk.web_downloads_debrid.get_web_download_list(
                api_version="v1",
                id_=str(web_id)
            )
        else:
            result = sdk.web_downloads_debrid.get_web_download_list(
                api_version="v1"
            )
        
        if result and hasattr(result, 'data'):
            return result.data
        
        logger.warning("No metadata returned from Torbox API")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get Torbox metadata: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def download_from_torbox(
    url: str,
    output_path: str,
    progress_callback=None,
    chunk_size: int = 1024 * 1024,  # 1 MB chunks
    api_key: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Download a file from Torbox CDN link.
    
    Args:
        url: The Torbox CDN download URL
        output_path: Path where the file should be saved
        progress_callback: Optional callback function for progress updates (current, total)
        chunk_size: Size of chunks to download (default 1MB)
        api_key: Optional Torbox API key for retrieving file metadata
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str], actual_filename: Optional[str])
    """
    actual_filename = None
    
    try:
        logger.info(f"Starting Torbox download: {url}")
        
        # Try to get file metadata from API if key is provided
        if api_key:
            file_id = extract_file_id_from_url(url)
            if file_id:
                logger.info(f"Attempting to retrieve metadata for file ID: {file_id}")
                metadata = await get_torbox_metadata(api_key)
                
                # Search for matching file in the downloads list
                if metadata and isinstance(metadata, dict):
                    downloads = metadata.get('data', [])
                    for download in downloads:
                        # Check if this download contains our file
                        if isinstance(download, dict):
                            files = download.get('files', [])
                            for file_info in files:
                                if isinstance(file_info, dict):
                                    # Match by ID or name pattern
                                    if file_id in str(file_info.get('id', '')):
                                        actual_filename = file_info.get('name', '')
                                        logger.info(f"Found filename from API: {actual_filename}")
                                        break
                            if actual_filename:
                                break
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Set up HTTP session with timeout
        timeout = aiohttp.ClientTimeout(total=None, connect=60, sock_read=60)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Make GET request
            async with session.get(url) as response:
                if response.status != 200:
                    error_msg = f"HTTP {response.status}: {response.reason}"
                    logger.error(f"Torbox download failed: {error_msg}")
                    return False, error_msg, None
                
                # Get total file size
                total_size = int(response.headers.get('content-length', 0))
                logger.info(f"Torbox file size: {human_size(total_size)}")
                
                # Get filename from Content-Disposition header if not from API
                if not actual_filename:
                    content_disposition = response.headers.get('content-disposition', '')
                    if content_disposition and 'filename=' in content_disposition:
                        # Extract filename from header
                        filename_match = re.search(r'filename[*]?=["\']?([^"\';\r\n]+)', content_disposition)
                        if filename_match:
                            actual_filename = filename_match.group(1)
                            logger.info(f"Using filename from Content-Disposition: {actual_filename}")
                
                # Update output path with actual filename if found
                if actual_filename:
                    output_dir = os.path.dirname(output_path)
                    output_path = os.path.join(output_dir, actual_filename)
                    logger.info(f"Saving to: {output_path}")
                
                # Download file in chunks
                downloaded = 0
                start_time = time.time()
                
                with open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Call progress callback if provided
                            if progress_callback and total_size > 0:
                                try:
                                    progress_callback(downloaded, total_size)
                                except Exception as e:
                                    logger.warning(f"Progress callback error: {e}")
                
                # Verify download
                actual_size = os.path.getsize(output_path)
                elapsed = time.time() - start_time
                avg_speed = actual_size / elapsed if elapsed > 0 else 0
                
                logger.info(f"Torbox download completed: {output_path}")
                logger.info(f"Downloaded {human_size(actual_size)} in {elapsed:.1f}s ({human_size(avg_speed)}/s)")
                
                if total_size > 0 and actual_size != total_size:
                    logger.warning(f"Size mismatch: expected {total_size}, got {actual_size}")
                    return False, f"Download incomplete: {actual_size}/{total_size} bytes", actual_filename
                
                return True, None, actual_filename or os.path.basename(output_path)
                
    except asyncio.TimeoutError:
        error_msg = "Download timeout"
        logger.error(f"Torbox download timeout: {url}")
        return False, error_msg, actual_filename
        
    except aiohttp.ClientError as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"Torbox download network error: {error_msg}")
        return False, error_msg, actual_filename
        
    except OSError as e:
        error_msg = f"File system error: {str(e)}"
        logger.error(f"Torbox download file system error: {error_msg}")
        return False, error_msg, actual_filename
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Torbox download unexpected error: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return False, error_msg, actual_filename


async def download_torbox_with_progress(
    url: str,
    output_path: str,
    status_msg=None,
    filename: str = None,
    api_key: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Download a file from Torbox with progress reporting to Telegram.
    
    Args:
        url: The Torbox CDN download URL
        output_path: Path where the file should be saved
        status_msg: Optional Telegram message object for progress updates
        filename: Optional filename for progress messages
        api_key: Optional Torbox API key for retrieving file metadata
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str], actual_filename: Optional[str])
    """
    start_time = time.time()
    last_edit_time = 0
    last_edit_pct = -10
    
    if not filename:
        filename = os.path.basename(output_path)
    
    def progress_callback(current: int, total: int):
        nonlocal last_edit_time, last_edit_pct
        
        if total <= 0:
            return
        
        pct = int(current * 100 / total)
        now = time.time()
        
        elapsed = now - start_time
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else float('inf')
        
        # Throttle updates to prevent rate limits
        # Update every 10% or minimum 10 seconds apart
        should_update = (pct >= last_edit_pct + 10) or ((now - last_edit_time) > 10)
        
        if should_update and status_msg:
            txt = (
                f'⬇️ Torbox: {filename}\n'
                f'Progress: {pct}% | {human_size(speed)}/s | ETA: {format_eta(eta)}\n'
                f'{human_size(current)} / {human_size(total)}'
            )
            try:
                # Schedule the coroutine to run in the event loop without blocking
                asyncio.create_task(status_msg.edit(txt))
                last_edit_pct = pct
                last_edit_time = now
            except Exception as e:
                logger.warning(f"Could not update progress message: {e}")
    
    # Download with progress callback
    success, error, actual_filename = await download_from_torbox(
        url,
        output_path,
        progress_callback=progress_callback if status_msg else None,
        api_key=api_key
    )
    
    # Use the actual filename returned from download
    display_name = actual_filename or filename
    
    if success and status_msg:
        try:
            await status_msg.edit(f'✅ Torbox download completed: {display_name}')
        except Exception:
            pass
    elif not success and status_msg:
        try:
            await status_msg.edit(f'❌ Torbox download failed: {display_name}\n{error}')
        except Exception:
            pass
    
    return success, error, actual_filename


def detect_file_type_from_url(url: str) -> Optional[str]:
    """
    Detect the file type from Torbox URL path.
    
    Args:
        url: The Torbox CDN URL
        
    Returns:
        File type string ('archive', 'video', 'photo', 'unknown') or None
    """
    # Extract the type segment from URL - must match after domain
    # Pattern: https://store-XXX.region.tb-cdn.st/TYPE/UUID
    match = re.search(r'tb-cdn\.st/([^/]+)/[a-f0-9-]+', url)
    
    if not match:
        return None
    
    url_type = match.group(1).lower()
    
    # Map URL types to our file categories
    archive_types = ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz']
    video_types = ['video', 'mp4', 'mkv', 'avi', 'mov', 'webm']
    photo_types = ['image', 'photo', 'jpg', 'jpeg', 'png']
    
    if url_type in archive_types:
        return 'archive'
    elif url_type in video_types:
        return 'video'
    elif url_type in photo_types:
        return 'photo'
    else:
        return 'unknown'
