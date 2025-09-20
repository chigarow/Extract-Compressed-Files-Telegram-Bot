"""Telethon-based implementation to download large compressed archives via a user account,
extract media (images & videos) and forward them to a target user.

Workflow:
1. Run this script (Termux / PC). First run will ask for phone + code + (optional) 2FA password.
2. Send (or forward) a compressed archive (zip/rar/7z/tar/...) to the logged-in user account (A) via any chat (private, saved messages, etc.).
3. The script listens for new messages containing a document whose filename extension matches supported archive formats.
4. It downloads the file (Telethon has higher limits than Bot API), extracts media, and sends media files to target account B (configured in secrets).

Notes:
* Credentials loaded from secrets.properties: APP_API_ID, APP_API_HASH, ACCOUNT_B_USERNAME
* Session is persisted in data/session.session (Telethon default if session name is path) to avoid re-login.
"""

import os
import logging
import configparser
import asyncio
import shutil
import patoolib
import hashlib
import json
import time
import subprocess
import zipfile
import tarfile
import sys
from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events
from telethon.errors import RPCError
from math import ceil
import queue
import psutil
from datetime import datetime, timedelta

# Bot start time
start_time = datetime.now()

# Add the script's directory to the Python path to ensure modules can be found
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import our FastTelethon parallel download module
try:
    from fast_download import fast_download_to_file
    FAST_DOWNLOAD_AVAILABLE = True
except ImportError:
    FAST_DOWNLOAD_AVAILABLE = False

from config import config

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

API_ID = config.api_id
API_HASH = config.api_hash
TARGET_USERNAME = config.target_username

if not API_ID or not API_HASH:
    raise RuntimeError('APP_API_ID / APP_API_HASH missing in secrets.properties')
if not TARGET_USERNAME:
    raise RuntimeError('ACCOUNT_B_USERNAME missing in secrets.properties')

ARCHIVE_EXTENSIONS = ('.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz')
PHOTO_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp')  # exclude gif to avoid doc behavior
ANIMATED_EXTENSIONS = ('.gif',)  # treat as skip or later special handling (skipped for now)
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS  # only these will be sent

LOG_FILE = os.path.join(DATA_DIR, 'app.log')
logger = logging.getLogger('extractor')
logger.setLevel(logging.INFO)
_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_h = logging.StreamHandler()
stream_h.setFormatter(_fmt)
file_h = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
file_h.setFormatter(_fmt)
logger.handlers.clear()
logger.addHandler(stream_h)
logger.addHandler(file_h)

# Log FastTelethon availability
if not FAST_DOWNLOAD_AVAILABLE:
    logger.warning("FastTelethon module not available - download acceleration disabled. Run: pip install cryptg for better performance.")

SESSION_PATH = os.path.join(DATA_DIR, 'session')  # Telethon will append .session
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

# --- CONFIGURABLE LIMITS (read from config; defaults tuned for Termux device) ---
MAX_ARCHIVE_GB = config.max_archive_gb
DISK_SPACE_FACTOR = config.disk_space_factor
MAX_CONCURRENT = config.max_concurrent
DOWNLOAD_CHUNK_SIZE_KB = config.download_chunk_size_kb
PARALLEL_DOWNLOADS = config.parallel_downloads
VIDEO_TRANSCODE_THRESHOLD_MB = config.video_transcode_threshold_mb
TRANSCODE_ENABLED = config.transcode_enabled
FAST_DOWNLOAD_ENABLED = config.fast_download_enabled
FAST_DOWNLOAD_CONNECTIONS = config.fast_download_connections
WIFI_ONLY_MODE = config.wifi_only_mode

# Cache file path
PROCESSED_CACHE_PATH = os.path.join(DATA_DIR, 'processed_archives.json')
processed_cache = {}
if os.path.exists(PROCESSED_CACHE_PATH):
    try:
        with open(PROCESSED_CACHE_PATH, 'r') as f:
            processed_cache = json.load(f)
    except Exception:
        processed_cache = {}

cache_lock = asyncio.Lock()

semaphore = asyncio.Semaphore(MAX_CONCURRENT)

# Pending password state: only track one at a time for simplicity
pending_password = None  # dict keys: archive_path, extract_path, filename, original_event, hash

# Queue/status tracking
current_processing = None  # dict with filename, status, start_time, etc.
processing_queue = asyncio.Queue()  # Queue for extraction/upload processing
processing_task = None  # Task for processing the queue

# Track ongoing operations for cancellation
ongoing_operations = {
    'download': None,     # track download task
    'extraction': None,   # track extraction task
    'compression': None,  # track video compression tasks
    'upload': None,       # track upload task
    'status': None        # track current status message
}

# Track cancelled operations by filename to properly interrupt downloads
cancelled_operations = set()

def check_file_command_supports_mime():
    """Checks if the system's 'file' command supports the --mime-type flag."""
    # On some systems like Termux, the 'file' command is older and uses -i.
    # patoolib uses --mime-type, causing errors. This check prevents that.
    dummy_path = os.path.join(BASE_DIR, 'file_check.tmp')
    try:
        with open(dummy_path, 'w') as f:
            f.write('test')
        # We capture stderr to prevent it from printing to the console.
        result = subprocess.run(
            ['file', '--brief', '--mime-type', dummy_path],
            check=True, capture_output=True
        )
        # Check for the expected output format
        return 'text/plain' in result.stdout.decode().lower()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    finally:
        if os.path.exists(dummy_path):
            os.remove(dummy_path)

FILE_CMD_OK = check_file_command_supports_mime()

def compute_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def is_ffmpeg_available():
    """Check if ffmpeg is available in the system"""
    return shutil.which('ffmpeg') is not None

def is_ffprobe_available():
    """Check if ffprobe is available in the system"""
    return shutil.which('ffprobe') is not None

def validate_video_file(file_path: str) -> dict:
    """
    Validate video file and extract metadata using ffprobe.
    Returns a dictionary with video information or empty dict if validation fails.
    """
    if not is_ffprobe_available():
        logger.warning("ffprobe not found, skipping video validation")
        return {}
    
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            return info
        else:
            logger.error(f"Video validation failed for {file_path}: {result.stderr}")
            return {}
    except Exception as e:
        logger.error(f"Error during video validation for {file_path}: {e}")
        return {}

def needs_video_processing(file_path: str) -> bool:
    """
    Check if a video needs processing based on its format and metadata.
    Returns True if the video should be processed, False otherwise.
    """
    if not is_ffprobe_available():
        logger.warning("ffprobe not found, assuming video needs processing")
        return True
    
    try:
        # Check if file is already MP4
        if file_path.lower().endswith('.mp4'):
            # For MP4 files, check if they have proper keyframes and metadata
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'stream=codec_name,codec_type,avg_frame_rate,has_b_frames',
                '-select_streams', 'v:0',
                '-of', 'json',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                info = json.loads(result.stdout)
                if 'streams' in info and len(info['streams']) > 0:
                    stream = info['streams'][0]
                    # If it's already H.264 and has reasonable settings, we might not need to re-encode
                    # But for safety, we'll still process it to ensure proper Telegram compatibility
                    return True
            else:
                logger.warning(f"ffprobe failed for {file_path}, assuming video needs processing")
                return True
        else:
            # Non-MP4 files always need processing
            return True
            
        return False
    except Exception as e:
        logger.error(f"Error checking if video needs processing: {e}")
        # If in doubt, process the video
        return True

async def compress_video_for_telegram(input_path: str, output_path: str) -> bool:
    """
    Compress video to MP4 format optimized for Telegram streaming.
    Uses compatible compression settings to ensure proper metadata, thumbnails, and duration display.
    """
    if not is_ffmpeg_available():
        logger.warning("ffmpeg not found, skipping video compression")
        return False
    
    try:
        # Enhanced MP4 compression settings optimized for Telegram
        # Fixed thumbnail and duration display issues
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'medium',  # Better quality encoding
            '-crf', '23',  # Better quality setting for proper thumbnails
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '48000',  # Higher quality audio sample rate
            # Critical fixes for thumbnail and duration display:
            '-movflags', '+faststart+use_metadata_tags',  # Proper metadata handling
            '-pix_fmt', 'yuv420p',  # Ensures compatibility
            '-profile:v', 'main',  # Main profile is better than baseline for thumbnails
            '-level', '4.0',  # Higher level for better compatibility
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',  # Ensure even dimensions
            # Timestamp and duration fixes:
            '-copyts',  # Copy input timestamps
            '-start_at_zero',  # Start timestamps at zero
            '-avoid_negative_ts', 'disabled',  # Don't modify timestamps
            '-fflags', '+genpts+igndts',  # Generate PTS and ignore DTS issues
            # Metadata fixes:
            '-map_metadata', '0',  # Copy metadata from input
            '-write_tmcd', '0',  # Disable timecode track that can cause issues
            # GOP and keyframe settings for proper thumbnails:
            '-g', '48',  # GOP size matching frame rate
            '-keyint_min', '24',  # Minimum GOP size
            '-sc_threshold', '40',  # Allow some scene change detection
            # Force proper frame rate:
            '-r', '24',  # Set output frame rate to ensure consistency
            '-y',  # Overwrite output file
            output_path
        ]
        
        logger.info(f"Compressing video: {input_path} -> {output_path}")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=300))  # 5 min timeout
        
        if result.returncode == 0:
            logger.info(f"Video compression successful: {output_path}")
            return True
        else:
            logger.error(f"Video compression failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("Video compression timed out")
        return False
    except Exception as e:
        logger.error(f"Error during video compression: {e}")
        return False

async def save_cache():
    async with cache_lock:
        tmp = PROCESSED_CACHE_PATH + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(processed_cache, f, indent=2)
        os.replace(tmp, PROCESSED_CACHE_PATH)

def human_size(num_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"

def format_eta(seconds: float) -> str:
    if seconds <= 0 or seconds == float('inf'):
        return '--'
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"

async def ensure_target_entity():  # moved below originally
    try:
        entity = await client.get_entity(TARGET_USERNAME)
        logger.info(f'Target user resolved: {TARGET_USERNAME} -> id={entity.id}')
        return entity
    except RPCError as e:
        logger.error(f'Failed to resolve target username {TARGET_USERNAME}: {e}')
        raise



def extract_with_password(archive_path: str, extract_path: str, password: str) -> None:
    # Use 7z for universal extraction; requires p7zip (Termux: pkg install p7zip)
    sevenzip = shutil.which('7z') or shutil.which('7za')
    if not sevenzip:
        raise RuntimeError('7z binary not found; install p7zip to extract password-protected archives')
    cmd = [sevenzip, 'x', '-y', f'-p{password}', f'-o{extract_path}', archive_path]
    logger.info('Running password extraction via 7z')
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        raise RuntimeError(f'7z extraction failed (code {res.returncode}): {res.stdout[-400:]}')

def is_password_error(err_text: str) -> bool:
    t = err_text.lower()
    return 'password' in t or 'wrong password' in t or 'incorrect password' in t

async def process_archive_event(event):
    global pending_password
    # This function now only handles the download phase
    # After download, it puts the file info into a processing queue
    
    message = event.message
    filename = message.file.name or 'file'
    size_bytes = message.file.size or 0
    size_gb = size_bytes / (1024 ** 3)
    if size_gb > MAX_ARCHIVE_GB:
        await event.reply(f'❌ Archive too large ({human_size(size_bytes)}). Limit is {MAX_ARCHIVE_GB} GB.')
        return

    # Check if we've already processed a file with the same name and exact size
    # Since the size is exact, this is a reliable indicator that it's the same file
    already_processed = False
    for file_hash, info in processed_cache.items():
        if info.get('filename') == filename and info.get('size') == size_bytes:
            already_processed = True
            break
    
    if already_processed:
        await event.reply(f'⏩ Archive {filename} with size {human_size(size_bytes)} was already processed. Skipping download and extraction.')
        return

    logger.info(f'Received archive: {filename} size={human_size(size_bytes)}')
    temp_archive_path = os.path.join(DATA_DIR, filename)
    start_download_ts = time.time()
    chunk_size = DOWNLOAD_CHUNK_SIZE_KB * 1024  # Use the configured chunk size (default 1MB for Premium)
    
    # Update current processing status for download phase
    download_status = {
        'filename': filename,
        'status': 'downloading',
        'start_time': start_download_ts,
        'size': size_bytes,
        'progress': 0,
        'event': event,  # Store the event for later replies
        'temp_archive_path': temp_archive_path,
        'message': message
    }
    
    status_msg = await event.reply(f'⬇️ Download 0% | ETA -- | 0.00 / {human_size(size_bytes)}')

    # Progress state & throttling
    last_report = {'pct': -1, 'time': time.time(), 'last_edit_pct': -1, 'last_edit_time': time.time()}
    MIN_PCT_STEP = 5
    MIN_EDIT_INTERVAL = 7  # seconds
    speed_window = []  # (timestamp, bytes)

    def progress(downloaded: int, total: int):
        if not total or downloaded < 0:
            return
        pct = int(downloaded * 100 / total)
        now = time.time()
        # Update current processing progress
        download_status['progress'] = pct
        # Maintain small window for speed calc (last 5 samples / 20s).
        speed_window.append((now, downloaded))
        # prune
        while len(speed_window) > 5 or (speed_window and now - speed_window[0][0] > 20):
            speed_window.pop(0)
        elapsed = now - start_download_ts
        avg_speed = downloaded / elapsed if elapsed > 0 else 0
        # moving speed
        if len(speed_window) >= 2:
            dt = speed_window[-1][0] - speed_window[0][0]
            db = speed_window[-1][1] - speed_window[0][1]
            inst_speed = db / dt if dt > 0 else avg_speed
        else:
            inst_speed = avg_speed
        remaining = total - downloaded
        eta = remaining / inst_speed if inst_speed > 0 else float('inf')
        speed_h = human_size(inst_speed) + '/s'
        should_log = pct >= last_report['pct'] + 5 or (now - last_report['time']) >= 10
        if should_log:
            logger.info(f'Download progress {filename}: {pct}% ({human_size(downloaded)}/{human_size(total)}) ETA {format_eta(eta)} ({speed_h})')
            last_report['pct'] = pct
            last_report['time'] = now
        should_edit = (pct >= last_report['last_edit_pct'] + MIN_PCT_STEP) or ((now - last_report['last_edit_time']) >= MIN_EDIT_INTERVAL)
        if should_edit:
            txt = (f'⬇️ Download {pct}% | ETA {format_eta(eta)} | {speed_h} | '
                   f'{human_size(downloaded)} / {human_size(total)}')
            # Schedule async edit (can't await here)
            async def do_edit():
                try:
                    await status_msg.edit(txt)
                except Exception:
                    pass
            client.loop.create_task(do_edit())
            last_report['last_edit_pct'] = pct
            last_report['last_edit_time'] = now
    try:
        # Use semaphore to control concurrent downloads
        async with semaphore:
            # Check if the process has been cancelled before starting download
            if filename in cancelled_operations:
                cancelled_operations.discard(filename)
                await event.reply(f'❌ Download cancelled: {filename}')
                return
                
            # Choose download method based on configuration and availability
            if FAST_DOWNLOAD_ENABLED and FAST_DOWNLOAD_AVAILABLE and size_bytes > 10 * 1024 * 1024:  # Use FastTelethon for files > 10MB
                logger.info(f'Using FastTelethon parallel download with {FAST_DOWNLOAD_CONNECTIONS} connections')
                
                # Create a progress callback that handles cancellation
                downloaded_bytes = [0]  # Use list to allow modification in nested function
                def fast_progress_callback(current_bytes, total_bytes):
                    # Update downloaded bytes counter
                    downloaded_bytes[0] = current_bytes
                    
                    # Check if the process has been cancelled
                    if filename in cancelled_operations:
                        raise asyncio.CancelledError("Download cancelled by user")
                    
                    # Call the original progress function
                    progress(current_bytes, total_bytes)
                
                # Network status callbacks
                def pause_callback(reason):
                    logger.warning(f"⏸️ Download paused: {reason}")
                    ongoing_operations['status'] = f"⏸️ Paused: {reason}"
                
                def resume_callback(reason):
                    logger.info(f"▶️ Download resumed: {reason}")
                    ongoing_operations['status'] = "⬬ Downloading..."
                
                try:
                    # Use FastTelethon parallel download with WiFi-only mode
                    await fast_download_to_file(
                        client, 
                        message.document, 
                        temp_archive_path, 
                        progress_callback=fast_progress_callback,
                        max_connections=FAST_DOWNLOAD_CONNECTIONS,
                        wifi_only=WIFI_ONLY_MODE,  # Only download on WiFi if configured
                        pause_callback=pause_callback,
                        resume_callback=resume_callback
                    )
                    actual_size = downloaded_bytes[0] if downloaded_bytes[0] > 0 else size_bytes
                except asyncio.CancelledError:
                    cancelled_operations.discard(filename)
                    # Clean up partially downloaded file
                    if os.path.exists(temp_archive_path):
                        try:
                            os.remove(temp_archive_path)
                        except OSError:
                            pass
                    await event.reply(f'❌ Download cancelled: {filename}')
                    # Clear download task
                    ongoing_operations['download'] = None
                    return
                except Exception as e:
                    logger.warning(f'FastTelethon download failed: {e}. Falling back to standard download.')
                    # Fall back to standard download on error
                    downloaded_bytes_fallback = 0
                    chunk_size = DOWNLOAD_CHUNK_SIZE_KB * 1024
                    with open(temp_archive_path, 'wb') as f:
                        async for chunk in client.iter_download(message.document, chunk_size=chunk_size):
                            # Check if the process has been cancelled
                            if filename in cancelled_operations:
                                cancelled_operations.discard(filename)
                                # Clean up partially downloaded file
                                if os.path.exists(temp_archive_path):
                                    try:
                                        os.remove(temp_archive_path)
                                    except OSError:
                                        pass
                                await event.reply(f'❌ Download cancelled: {filename}')
                                # Clear download task
                                ongoing_operations['download'] = None
                                return
                            
                            f.write(chunk)
                            downloaded_bytes_fallback += len(chunk)
                            progress(downloaded_bytes_fallback, size_bytes)
                    actual_size = downloaded_bytes_fallback
            else:
                # Use standard iter_download for small files or when FastTelethon is disabled
                logger.info(f'Using standard Telethon download (FastTelethon: enabled={FAST_DOWNLOAD_ENABLED}, available={FAST_DOWNLOAD_AVAILABLE}, size={human_size(size_bytes)})')
                downloaded_bytes = 0
                chunk_size = DOWNLOAD_CHUNK_SIZE_KB * 1024  # Use the configured chunk size (default 1MB for Premium)
                with open(temp_archive_path, 'wb') as f:
                    async for chunk in client.iter_download(message.document, chunk_size=chunk_size):
                        # Check if the process has been cancelled
                        if filename in cancelled_operations:
                            cancelled_operations.discard(filename)
                            # Clean up partially downloaded file
                            if os.path.exists(temp_archive_path):
                                try:
                                    os.remove(temp_archive_path)
                                except OSError:
                                    pass
                            await event.reply(f'❌ Download cancelled: {filename}')
                            # Clear download task
                            ongoing_operations['download'] = None
                            return
                        
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        progress(downloaded_bytes, size_bytes)
                
                actual_size = downloaded_bytes
            total_elapsed = time.time() - start_download_ts
            avg_speed = actual_size / total_elapsed if total_elapsed > 0 else 0
            speed_h = human_size(avg_speed) + '/s'
            final_txt = (f'✅ Download complete: {human_size(actual_size)} in {format_eta(total_elapsed)} '
                         f'(~{speed_h}). Queued for processing...')
            try:
                await status_msg.edit(final_txt)
            except Exception:
                await event.reply(final_txt)
            logger.info(f'Download complete: {temp_archive_path} ({human_size(actual_size)}) elapsed {total_elapsed:.1f}s')
            
            # Clear download task
            ongoing_operations['download'] = None
            
            # Add to processing queue after download completes
            logger.info(f'Adding {filename} to processing queue')
            await processing_queue.put(download_status)
            
            # Start the processing task if it's not already running
            global processing_task
            if processing_task is None or processing_task.done():
                logger.info(f'Starting new processing task for {filename}')
                processing_task = asyncio.create_task(process_queue())
            else:
                logger.info(f'Processing task already running, {filename} added to queue')
                
    except FloodWaitError as e:
        logger.error(f'Flood wait error: {e}')
        try:
            await status_msg.edit(f'❌ Flood wait error: Please wait for {e.seconds} seconds.')
        except Exception:
            await event.reply(f'❌ Flood wait error: Please wait for {e.seconds} seconds.')
    except FileReferenceExpiredError:
        logger.error('File reference expired. The user needs to send the file again.')
        try:
            await status_msg.edit('❌ File reference expired. Please send the file again.')
        except Exception:
            await event.reply('❌ File reference expired. Please send the file again.')
    except Exception as e:
        logger.error(f'Error downloading {filename}: {e}')
        try:
            await status_msg.edit(f'❌ Download failed: {e}')
        except Exception:
            await event.reply(f'❌ Failed to download archive: {e}')
        # Clean up partially downloaded file
        if os.path.exists(temp_archive_path):
            try:
                os.remove(temp_archive_path)
            except OSError:
                pass
        # Clear download task
        ongoing_operations['download'] = None
        return

async def process_queue():
    """Process files from the queue in FIFO order (based on download completion)"""
    global current_processing
    while True:
        try:
            # Get the next file to process from the queue
            logger.info('Processing queue: waiting for next file')
            download_status = await processing_queue.get()
            filename = download_status.get('filename', 'unknown')
            logger.info(f'Processing queue: got file {filename}')
            
            # Set as current processing
            current_processing = download_status
            
            # Process the file (extraction, upload, etc.)
            logger.info(f'Starting extraction and upload for {filename}')
            await process_extract_and_upload(download_status)
            
            # Mark task as done
            processing_queue.task_done()
            logger.info(f'Processing complete for {filename}')
            
            # Clear current processing
            current_processing = None
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f'Error processing queue: {e}')
            current_processing = None
            # Continue processing other items in the queue

def extract_archive_async(temp_archive_path, extract_path, filename):
    logger.info(f'Start extracting {temp_archive_path} -> {extract_path}')

    # If the system 'file' command is not compatible, use our manual extension-based logic.
    if not FILE_CMD_OK:
        logger.warning("System 'file' command is not compatible, using manual extension-based extraction.")
        logger.info(f'Extracting {filename} using manual extension-based extraction')
        ext = os.path.splitext(filename.lower())[1]
        if ext == '.zip':
            with zipfile.ZipFile(temp_archive_path, 'r') as zf:
                zf.extractall(extract_path)
        elif ext == '.rar':
            unrar_cmd = shutil.which('unrar')
            if unrar_cmd:
                # We capture output to prevent it from filling up logs unless there's an error.
                subprocess.run([unrar_cmd, 'x', '-y', temp_archive_path, extract_path + '/'], check=True, capture_output=True)
            else:
                raise patoolib.util.PatoolError('RAR extraction failed: unrar command not found')
        elif ext in ['.7z']:
            sevenzip = shutil.which('7z') or shutil.which('7za')
            if sevenzip:
                subprocess.run([sevenzip, 'x', '-y', f'-o{extract_path}', temp_archive_path], check=True, capture_output=True)
            else:
                raise patoolib.util.PatoolError('7z extraction failed: 7z command not found')
        elif ext in ['.tar', '.gz', '.bz2', '.xz']:
            with tarfile.open(temp_archive_path, 'r:*') as tf:
                tf.extractall(extract_path)
        else:
            # If we don't have a manual handler, try patoolib and let it raise an error.
            logger.warning(f"No manual handler for '{ext}', trying patoolib as a last resort.")
            patoolib.extract_archive(temp_archive_path, outdir=extract_path)
    else:
        # This is the normal path where the 'file' command is compatible.
        logger.info("System 'file' command is compatible, using patoolib auto-detection.")
        patoolib.extract_archive(temp_archive_path, outdir=extract_path)

    logger.info(f'Extraction completed successfully for {filename}')

async def process_extract_and_upload(download_status):
    """Process the extraction and upload phases for a downloaded file"""
    event = download_status['event']
    filename = download_status['filename']
    temp_archive_path = download_status['temp_archive_path']
    size_bytes = download_status['size']
    message = download_status['message']
    
    logger.info(f'process_extract_and_upload: Starting processing for {filename}')
    
    # Update status message
    status_msg = await event.reply(f'⚙️ Processing {filename}...')
    logger.info(f'process_extract_and_upload: Status message sent for {filename}')
    
    # Disk space check
    try:
        du = shutil.disk_usage(DATA_DIR)
        free_bytes = du.free
    except Exception:
        free_bytes = 0
    required = int(size_bytes * DISK_SPACE_FACTOR)
    if free_bytes and free_bytes < required:
        await event.reply(f'❌ Not enough free space. Need ~{human_size(required)} free, only {human_size(free_bytes)} available.')
        try: os.remove(temp_archive_path)
        except Exception: pass
        return

    # Update status to hashing
    download_status['status'] = 'hashing'
    await status_msg.edit(f'🔍 Hashing {filename}...')
    
    # Hash caching - Check if we've already processed this exact file before
    # This is the definitive check that uses the file's SHA256 hash to determine
    # if we've processed this specific file previously, regardless of filename
    try:
        file_hash = compute_sha256(temp_archive_path)
        if file_hash in processed_cache:
            await event.reply('⏩ Archive already processed earlier. Skipping extraction.')
            os.remove(temp_archive_path)
            return
    except Exception as e:
        logger.warning(f'Hashing failed (continuing): {e}')
        file_hash = None

    extract_dir_name = f"extracted_{os.path.splitext(filename)[0]}_{int(time.time())}"
    extract_path = os.path.join(DATA_DIR, extract_dir_name)
    os.makedirs(extract_path, exist_ok=True)
    
    # Update status to extracting
    download_status['status'] = 'extracting'
    await status_msg.edit(f'📦 Extracting {filename}...')

    # Attempt extraction
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, extract_archive_async, temp_archive_path, extract_path, filename)
        await event.reply('✅ Extraction complete. Scanning media files…')
        logger.info(f'Starting media files scan for {filename}')
    except (patoolib.util.PatoolError, subprocess.CalledProcessError, zipfile.BadZipFile, tarfile.TarError) as e:
        err_text = str(e)
        # If the error is from a subprocess, add stderr to the message for more context.
        if hasattr(e, 'stderr') and e.stderr:
            err_text += f"\nDetails: {e.stderr.decode(errors='ignore')}"

        logger.error(f'Extraction error: {err_text}')
        if is_password_error(err_text):
            global pending_password
            pending_password = {
                'archive_path': temp_archive_path,
                'extract_path': extract_path,
                'filename': filename,
                'original_event': event,
                'hash': file_hash
            }
            await event.reply('🔐 Archive requires password. Reply with:\n/pass <password>        — to attempt extraction\n/cancel-password        — to abort and delete file\n/cancel-process         — to cancel entire process and delete all files')
            return
        else:
            # Provide a more detailed error to the user
            error_summary = str(e).splitlines()[0]
            await event.reply(f'❌ Extraction failed: {error_summary}')
            shutil.rmtree(extract_path, ignore_errors=True)
            if os.path.exists(temp_archive_path):
                os.remove(temp_archive_path)
            return

    # Process media
    logger.info(f'Scanning for media files in {extract_path}')
    media_files = []
    for root, _, files in os.walk(extract_path):
        for f in files:
            if f.lower().endswith(MEDIA_EXTENSIONS):
                media_files.append(os.path.join(root, f))
    
    logger.info(f'Found {len(media_files)} media files in {filename}')

    if not media_files:
        await event.reply('ℹ️ No media files found in archive.')
    else:
        # Update status to uploading
        download_status['status'] = 'uploading'
        download_status['total_files'] = len(media_files)
        download_status['uploaded_files'] = 0
        
        # Track upload task for cancellation
        ongoing_operations['upload'] = asyncio.current_task()
        
        # Separate images and videos
        image_files = []
        video_files = []
        for path in media_files:
            ext = os.path.splitext(path)[1].lower()
            if ext in PHOTO_EXTENSIONS:
                image_files.append(path)
            elif ext in VIDEO_EXTENSIONS:
                video_files.append(path)
        
        # Get archive name without extension for captions
        archive_name = os.path.splitext(filename)[0]
        
        await event.reply(f'📤 Found {len(media_files)} media files ({len(image_files)} images, {len(video_files)} videos). Uploading to {TARGET_USERNAME} ...')
        target = await ensure_target_entity()
        sent = 0
        
        # Upload images first as a group
        if image_files:
            try:
                await client.send_file(target, image_files, caption=f"Images from {archive_name}", force_document=False, album=True)
                sent += len(image_files)
                download_status['uploaded_files'] = sent
                logger.info(f'Sent {len(image_files)} images as group')
            except Exception as e:
                logger.error(f'Failed to send image group: {e}')
                # Fallback to individual uploads if group upload fails
                for path in image_files:
                    try:
                        await client.send_file(target, path, caption=os.path.basename(path), force_document=False)
                        sent += 1
                        download_status['uploaded_files'] = sent
                    except Exception as e:
                        logger.error(f'Failed to send {path}: {e}')
                        await event.reply(f'Error sending {os.path.basename(path)}: {e}')
        
        # Upload videos as a group
            video_files_to_send = []
            compressed_video_paths = []  # Keep track of compressed files for cleanup
            
            for path in video_files:
                ext = os.path.splitext(path)[1].lower()
                try:
                    # Validate video file before processing
                    video_info = validate_video_file(path)
                    
                    # Check if video needs processing
                    if TRANSCODE_ENABLED and needs_video_processing(path):
                        # Compress all video files to MP4 format for better Telegram streaming
                        compressed_path = os.path.splitext(path)[0] + '_compressed.mp4'
                        if await compress_video_for_telegram(path, compressed_path):
                            # Validate compressed video as well
                            compressed_info = validate_video_file(compressed_path)
                            # If compression is successful, add the compressed file to the list
                            video_files_to_send.append(compressed_path)
                            compressed_video_paths.append(compressed_path)
                        else:
                            # If compression fails, add the original file
                            video_files_to_send.append(path)
                    else:
                        # Add videos as-is when compression is disabled or not needed
                        video_files_to_send.append(path)
                except Exception as e:
                    logger.error(f'Error preparing video {path}: {e}')
                    # Add the original file if there's an error in preparation
                    video_files_to_send.append(path)
        
        # Send videos as a group
        if video_files_to_send:
            try:
                await client.send_file(target, video_files_to_send, caption=f"Videos from {archive_name}", supports_streaming=True, force_document=False, album=True)
                sent += len(video_files_to_send)
                download_status['uploaded_files'] = sent
                logger.info(f'Sent {len(video_files_to_send)} videos as group')
            except Exception as e:
                logger.error(f'Failed to send video group: {e}')
                # Fallback to individual uploads if group upload fails
                for i, path in enumerate(video_files_to_send):
                    original_path = video_files[i]  # Get the original path for error messages
                    try:
                        await client.send_file(target, path, caption=os.path.basename(original_path), supports_streaming=True, force_document=False)
                        sent += 1
                        download_status['uploaded_files'] = sent
                    except Exception as e:
                        logger.error(f'Failed to send {original_path}: {e}')
                        await event.reply(f'Error sending {os.path.basename(original_path)}: {e}')
        
        # Clean up compressed video files
        for compressed_path in compressed_video_paths:
            try:
                os.remove(compressed_path)
            except:
                pass
        
        await event.reply(f'✅ Upload complete: {sent}/{len(media_files)} files sent.')
        
        # Clear upload task
        ongoing_operations['upload'] = None

    # Update cache
    if file_hash:
        processed_cache[file_hash] = {
                'filename': filename,
                'time': int(time.time()),
                'size': size_bytes
        }
        await save_cache()

    # Cleanup
    try:
        shutil.rmtree(extract_path, ignore_errors=True)
        if os.path.exists(temp_archive_path):
            os.remove(temp_archive_path)
        logger.info('Cleanup complete')
    except Exception as e:
        logger.warning(f'Cleanup issue: {e}')
    finally:
        await status_msg.edit(f'✅ Processing complete for {filename}')

async def handle_password_command(event, password: str):
    global pending_password
    if not pending_password:
        await event.reply('ℹ️ No pending password-protected archive.')
        return
    archive_path = pending_password['archive_path']
    extract_path = pending_password['extract_path']
    filename = pending_password['filename']
    original_event = pending_password['original_event']
    file_hash = pending_password['hash']
    await event.reply('🔄 Attempting password extraction...')
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, extract_with_password, archive_path, extract_path, password)
        await event.reply('✅ Password extraction successful. Scanning media files…')
    except Exception as e:
        await event.reply(f'❌ Password extraction failed: {e}')
        # Option to retry remains; keep pending
        return
    # After successful extraction process like normal
    media_files = []
    for root, _, files in os.walk(extract_path):
        for f in files:
            if f.lower().endswith(MEDIA_EXTENSIONS):
                media_files.append(os.path.join(root, f))
    if not media_files:
        await event.reply('ℹ️ No media files found in archive.')
    else:
        # Get archive name without extension for captions
        archive_name = os.path.splitext(filename)[0]
        
        # Separate images and videos
        image_files = []
        video_files = []
        for path in media_files:
            ext = os.path.splitext(path)[1].lower()
            if ext in PHOTO_EXTENSIONS:
                image_files.append(path)
            elif ext in VIDEO_EXTENSIONS:
                video_files.append(path)
        
        target = await ensure_target_entity()
        sent = 0
        await event.reply(f'📤 Found {len(media_files)} media files ({len(image_files)} images, {len(video_files)} videos). Uploading...')
        
        # Upload images first as a group
        if image_files:
            try:
                await client.send_file(target, image_files, caption=f"Images from {archive_name}", force_document=False, album=True)
                sent += len(image_files)
                logger.info(f'Sent {len(image_files)} images as group')
            except Exception as e:
                logger.error(f'Failed to send image group: {e}')
                # Fallback to individual uploads if group upload fails
                for path in image_files:
                    try:
                        await client.send_file(target, path, caption=os.path.basename(path), force_document=False)
                        sent += 1
                    except Exception as e:
                        await event.reply(f'Error sending {os.path.basename(path)}: {e}')
        
        # Upload videos as a group
        video_files_to_send = []
        compressed_video_paths = []  # Keep track of compressed files for cleanup
        
        for path in video_files:
            ext = os.path.splitext(path)[1].lower()
            try:
                # Validate video file before processing
                video_info = validate_video_file(path)
                
                # Check if video needs processing
                if TRANSCODE_ENABLED and needs_video_processing(path):
                    # Compress all video files to MP4 format for better Telegram streaming
                    compressed_path = os.path.splitext(path)[0] + '_compressed.mp4'
                    if await compress_video_for_telegram(path, compressed_path):
                        # Validate compressed video as well
                        compressed_info = validate_video_file(compressed_path)
                        # If compression is successful, add the compressed file to the list
                        video_files_to_send.append(compressed_path)
                        compressed_video_paths.append(compressed_path)
                    else:
                        # If compression fails, add the original file
                        video_files_to_send.append(path)
                else:
                    # Add videos as-is when compression is disabled or not needed
                    video_files_to_send.append(path)
            except Exception as e:
                logger.error(f'Error preparing video {path}: {e}')
                # Add the original file if there's an error in preparation
                video_files_to_send.append(path)
        
        # Send videos as a group
        if video_files_to_send:
            try:
                await client.send_file(target, video_files_to_send, caption=f"Videos from {archive_name}", supports_streaming=True, force_document=False, album=True)
                sent += len(video_files_to_send)
                logger.info(f'Sent {len(video_files_to_send)} videos as group')
            except Exception as e:
                logger.error(f'Failed to send video group: {e}')
                # Fallback to individual uploads if group upload fails
                for i, path in enumerate(video_files_to_send):
                    original_path = video_files[i]  # Get the original path for error messages
                    try:
                        await client.send_file(target, path, caption=os.path.basename(original_path), supports_streaming=True, force_document=False)
                        sent += 1
                    except Exception as e:
                        await event.reply(f'Error sending {os.path.basename(original_path)}: {e}')
        
        # Clean up compressed video files
        for compressed_path in compressed_video_paths:
            try:
                os.remove(compressed_path)
            except:
                pass
        
        await event.reply(f'✅ Upload complete: {sent}/{len(media_files)} files sent.')
        
        # Clear upload task
        ongoing_operations['upload'] = None
    if file_hash:
        processed_cache[file_hash] = {
            'filename': filename,
            'time': int(time.time()),
            'size': os.path.getsize(archive_path)
        }
        await save_cache()
    # Cleanup and clear pending
    try:
        shutil.rmtree(extract_path, ignore_errors=True)
        if os.path.exists(archive_path):
            os.remove(archive_path)
    except Exception as e:
        logger.warning(f'Cleanup issue after password extraction: {e}')
    pending_password = None
    await event.reply('🧹 Cleanup done.')

async def handle_max_concurrent_command(event, value: int):
    """Handle the /max_concurrent command to change the maximum concurrent downloads"""
    global MAX_CONCURRENT, semaphore
    
    # Update the configuration file
    try:
        # Update the MAX_CONCURRENT value
        if 'DEFAULT' not in config._config:
            config._config['DEFAULT'] = {}
        config._config['DEFAULT']['MAX_CONCURRENT'] = str(value)
        
        # Save the configuration
        config.save()
        
        # Update the global variable
        config.max_concurrent = value
        MAX_CONCURRENT = value
        
        # Create a new semaphore with the new value
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




async def handle_status_command(event):
    """Show a comprehensive status of the bot and system"""

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
    uptime = datetime.now() - start_time
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
        f"Uptime: {str(uptime).split('.')[0]}\n"
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
    
    # Show download queue (files currently being downloaded)
    # Since we're using a semaphore, we can show how many downloads are in progress
    # by checking how many permits are currently acquired
    # This is a bit tricky with asyncio.Semaphore, so we'll just show queue size
    
    # Show processing queue (files waiting for extraction/upload after download)
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
    global pending_password
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
            logger.warning(f'Error during cancel extraction cleanup: {e}')
        pending_password = None
    
    # Clear current processing
    current_processing = None
    
    await event.reply(f'✅ Extraction of "{filename}" has been cancelled.')

async def handle_cancel_process(event):
    """Cancel the current process and delete any downloaded files"""
    global current_processing, pending_password, ongoing_operations, cancelled_operations
    if not current_processing and not pending_password:
        await event.reply('ℹ️ No process currently running.')
        return
    
    cancelled_files = []
    
    # Add filename to cancelled operations so download loop can check
    if current_processing and 'filename' in current_processing:
        filename = current_processing['filename']
        cancelled_operations.add(filename)
        cancelled_files.append(filename)
    
    # Cancel any ongoing operations
    # Cancel download task
    if ongoing_operations['download']:
        try:
            ongoing_operations['download'].cancel()
        except Exception as e:
            logger.warning(f'Error cancelling download task: {e}')
        ongoing_operations['download'] = None
    
    # Cancel upload task
    if ongoing_operations['upload']:
        try:
            ongoing_operations['upload'].cancel()
        except Exception as e:
            logger.warning(f'Error cancelling upload task: {e}')
        ongoing_operations['upload'] = None
    
    # Terminate video compression process if running
    if ongoing_operations['compression'] and ongoing_operations['compression'].get('process'):
        try:
            process = ongoing_operations['compression']['process']
            process.terminate()
            # Wait a bit for graceful termination
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate gracefully
                process.kill()
        except Exception as e:
            logger.warning(f'Error terminating compression process: {e}')
        ongoing_operations['compression'] = None
    
    # Cancel any ongoing extraction
    if current_processing:
        filename = current_processing.get('filename', 'unknown file')
        cancelled_files.append(filename)
        current_processing = None
    
    # Cancel any pending password process and clean up files
    if pending_password:
        try:
            archive_path = pending_password['archive_path']
            extract_path = pending_password['extract_path']
            filename = pending_password['filename']
            
            # Add to cancelled files list
            cancelled_files.append(filename)
            
            # Clean up files
            shutil.rmtree(extract_path, ignore_errors=True)
            if os.path.exists(archive_path):
                os.remove(archive_path)
        except Exception as e:
            logger.warning(f'Error during cancel process cleanup: {e}')
        pending_password = None
    
    # Reset all ongoing operations
    ongoing_operations = {
        'download': None,
        'extraction': None,
        'compression': None,
        'upload': None
    }
    
    # Create response message
    if len(cancelled_files) == 1:
        await event.reply(f'✅ Process for "{cancelled_files[0]}" has been cancelled and files deleted.')
    else:
        file_list = ', '.join([f'"{f}"' for f in cancelled_files])
        await event.reply(f'✅ Processes for {file_list} have been cancelled and files deleted.')

@client.on(events.NewMessage(incoming=True))
async def watcher(event):
    global pending_password
    # Only allow messages from target user
    try:
        target_entity = await ensure_target_entity()
        if not event.sender_id == target_entity.id:
            return
    except Exception:
        return

    # Commands for password handling
    if event.raw_text:
        txt = event.raw_text.strip()
        if txt.startswith('/pass '):
            password = txt[6:].strip()
            if password:
                await handle_password_command(event, password)
            else:
                await event.reply('Usage: /pass <password>')
            return
        if txt == '/cancel-password':
            await handle_cancel_password(event)
            return
        if txt == '/cancel-extraction':
            await handle_cancel_extraction(event)
            return
        if txt == '/cancel-process':
            await handle_cancel_process(event)
            return
        if txt == '/q' or txt == '/queue':
            await handle_queue_command(event)
            return
        if txt == '/status':
            await handle_status_command(event)
            return
        if txt.startswith('/max_concurrent '):
            try:
                value = int(txt.split()[1])
                if value > 0:
                    await handle_max_concurrent_command(event, value)
                else:
                    await event.reply('❌ Please provide a positive integer value for max concurrent downloads.')
            except (ValueError, IndexError):
                await event.reply('❌ Usage: /max_concurrent <number> (e.g., /max_concurrent 3)')
            return
        if txt.startswith('/set_max_archive_gb '):
            try:
                value = float(txt.split()[1])
                if value > 0:
                    await handle_set_max_archive_gb_command(event, value)
                else:
                    await event.reply('❌ Please provide a positive float value for max archive size.')
            except (ValueError, IndexError):
                await event.reply('❌ Usage: /set_max_archive_gb <number> (e.g., /set_max_archive_gb 10.5)')
            return
        if txt == '/toggle_fast_download':
            await handle_toggle_fast_download_command(event)
            return
        if txt == '/toggle_wifi_only':
            await handle_toggle_wifi_only_command(event)
            return
        if txt == '/toggle_transcoding':
            await handle_toggle_transcoding_command(event)
            return
        if txt == '/help':
            await handle_help_command(event)
            return

    # If a document & archive extension & not waiting for password (or waiting but new one arrives -> process anyway after) 
    if event.message and event.message.document:
        filename = event.message.file.name or 'file'
        if filename.lower().endswith(ARCHIVE_EXTENSIONS):
            if pending_password:
                await event.reply('⚠️ Another archive is awaiting password; process this one after finishing/cancelling.')
                return
            await process_archive_event(event)

async def main_async():
    logger.info('Starting Telethon client...')
    await client.start()
    me = await client.get_me()
    logger.info(f'Logged in as: {me.id} / {me.username or me.first_name}')
    logger.info('Waiting for incoming archives from target user...')
    await client.run_until_disconnected()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info('Shutting down (KeyboardInterrupt)')

if __name__ == '__main__':
    main()
