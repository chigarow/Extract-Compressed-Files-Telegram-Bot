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
from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events
from telethon.errors import RPCError
from math import ceil

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, 'secrets.properties')
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

API_ID = config.getint('DEFAULT', 'APP_API_ID', fallback=None)
API_HASH = config.get('DEFAULT', 'APP_API_HASH', fallback=None)
TARGET_USERNAME = config.get('DEFAULT', 'ACCOUNT_B_USERNAME', fallback=None)

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

SESSION_PATH = os.path.join(DATA_DIR, 'session')  # Telethon will append .session
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

# --- CONFIGURABLE LIMITS (read from config; defaults tuned for Termux device) ---
MAX_ARCHIVE_GB = config.getfloat('DEFAULT', 'MAX_ARCHIVE_GB', fallback=6.0)  # Skip if bigger than this
DISK_SPACE_FACTOR = config.getfloat('DEFAULT', 'DISK_SPACE_FACTOR', fallback=2.5)  # Need free >= factor * archive size
MAX_CONCURRENT = config.getint('DEFAULT', 'MAX_CONCURRENT', fallback=1)  # semaphore size
DOWNLOAD_CHUNK_SIZE_KB = config.getint('DEFAULT', 'DOWNLOAD_CHUNK_SIZE_KB', fallback=512) # Affects download speed

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
    global pending_password, current_processing
    async with semaphore:
        message = event.message
        filename = message.file.name or 'file'
        size_bytes = message.file.size or 0
        size_gb = size_bytes / (1024 ** 3)
        if size_gb > MAX_ARCHIVE_GB:
            await event.reply(f'❌ Archive too large ({human_size(size_bytes)}). Limit is {MAX_ARCHIVE_GB} GB.')
            return

        logger.info(f'Received archive: {filename} size={human_size(size_bytes)}')
        temp_archive_path = os.path.join(DATA_DIR, filename)
        start_download_ts = time.time()
        
        # Update current processing status
        current_processing = {
            'filename': filename,
            'status': 'downloading',
            'start_time': start_download_ts,
            'size': size_bytes,
            'progress': 0
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
            if current_processing:
                current_processing['progress'] = pct
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
            should_log = pct >= last_report['pct'] + 5 or (now - last_report['time']) >= 10
            if should_log:
                logger.info(f'Download progress {filename}: {pct}% ({human_size(downloaded)}/{human_size(total)}) ETA {format_eta(eta)}')
                last_report['pct'] = pct
                last_report['time'] = now
            should_edit = (pct >= last_report['last_edit_pct'] + MIN_PCT_STEP) or ((now - last_report['last_edit_time']) >= MIN_EDIT_INTERVAL)
            if should_edit:
                txt = (f'⬇️ Download {pct}% | ETA {format_eta(eta)} | '
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
            # Use iter_download for more control over chunk size for performance tuning
            downloaded_bytes = 0
            chunk_size = DOWNLOAD_CHUNK_SIZE_KB * 1024
            with open(temp_archive_path, 'wb') as f:
                async for chunk in client.iter_download(message.document, chunk_size=chunk_size):
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    progress(downloaded_bytes, size_bytes)

            actual_size = downloaded_bytes
            total_elapsed = time.time() - start_download_ts
            avg_speed = actual_size / total_elapsed if total_elapsed > 0 else 0
            speed_h = human_size(avg_speed) + '/s'
            final_txt = (f'✅ Download complete: {human_size(actual_size)} in {format_eta(total_elapsed)} '
                         f'(~{speed_h}). Extracting...')
            try:
                await status_msg.edit(final_txt)
            except Exception:
                await event.reply(final_txt)
            logger.info(f'Download complete: {temp_archive_path} ({human_size(actual_size)}) elapsed {total_elapsed:.1f}s')
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
            return

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

        # Update status to extracting
        if current_processing:
            current_processing['status'] = 'hashing'
        
        # Hash caching
        try:
            file_hash = compute_sha256(temp_archive_path)
            if file_hash in processed_cache:
                await event.reply('⏩ Archive already processed earlier. Skipping extraction.')
                os.remove(temp_archive_path)
                current_processing = None
                return
        except Exception as e:
            logger.warning(f'Hashing failed (continuing): {e}')
            file_hash = None

        extract_dir_name = f"extracted_{os.path.splitext(filename)[0]}_{int(time.time())}"
        extract_path = os.path.join(DATA_DIR, extract_dir_name)
        os.makedirs(extract_path, exist_ok=True)
        
        # Update status to extracting
        if current_processing:
            current_processing['status'] = 'extracting'

        # Attempt extraction
        try:
            logger.info(f'Start extracting {temp_archive_path} -> {extract_path}')

            # If the system 'file' command is not compatible, use our manual extension-based logic.
            if not FILE_CMD_OK:
                logger.warning("System 'file' command is not compatible, using manual extension-based extraction.")
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

            await event.reply('✅ Extraction complete. Scanning media files…')
        except (patoolib.util.PatoolError, subprocess.CalledProcessError, zipfile.BadZipFile, tarfile.TarError) as e:
            err_text = str(e)
            # If the error is from a subprocess, add stderr to the message for more context.
            if hasattr(e, 'stderr') and e.stderr:
                err_text += f"\nDetails: {e.stderr.decode(errors='ignore')}"

            logger.error(f'Extraction error: {err_text}')
            if is_password_error(err_text):
                pending_password = {
                    'archive_path': temp_archive_path,
                    'extract_path': extract_path,
                    'filename': filename,
                    'original_event': event,
                    'hash': file_hash
                }
                await event.reply('🔐 Archive requires password. Reply with:\n/pass <password>  — to attempt extraction\n/cancel            — to abort and delete file')
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
        media_files = []
        for root, _, files in os.walk(extract_path):
            for f in files:
                if f.lower().endswith(MEDIA_EXTENSIONS):
                    media_files.append(os.path.join(root, f))

        if not media_files:
            await event.reply('ℹ️ No media files found in archive.')
        else:
            # Update status to uploading
            if current_processing:
                current_processing['status'] = 'uploading'
                current_processing['total_files'] = len(media_files)
                current_processing['uploaded_files'] = 0
            
            await event.reply(f'📤 Found {len(media_files)} media files. Uploading to {TARGET_USERNAME} ...')
            target = await ensure_target_entity()
            sent = 0
            for path in media_files:
                ext = os.path.splitext(path)[1].lower()
                try:
                    if ext in PHOTO_EXTENSIONS:
                        await client.send_file(target, path, caption=os.path.basename(path), force_document=False)
                    elif ext in VIDEO_EXTENSIONS:
                        await client.send_file(target, path, caption=os.path.basename(path), supports_streaming=True, force_document=False)
                    else:
                        continue  # skip anything not explicitly allowed
                    sent += 1
                    if current_processing:
                        current_processing['uploaded_files'] = sent
                    if sent % 10 == 0:
                        logger.info(f'Sent {sent}/{len(media_files)} files')
                except Exception as e:
                    logger.error(f'Failed to send {path}: {e}')
                    await event.reply(f'Error sending {os.path.basename(path)}: {e}')
            await event.reply(f'✅ Upload complete: {sent}/{len(media_files)} files sent.')

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
            # Clear current processing status
            current_processing = None

async def handle_password_command(event, password: str):
    global pending_password
    if not pending_password:
        await event.reply('ℹ️ No pending password-protected archive.')
        return
    archive_path = pending_password['archive_path']
    extract_path = pending_password['extract_path']
    filename = pending_password['filename']
    file_hash = pending_password['hash']
    await event.reply('🔄 Attempting password extraction...')
    try:
        extract_with_password(archive_path, extract_path, password)
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
        target = await ensure_target_entity()
        sent = 0
        await event.reply(f'📤 Found {len(media_files)} media files. Uploading...')
        for path in media_files:
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext in PHOTO_EXTENSIONS:
                    await client.send_file(target, path, caption=os.path.basename(path), force_document=False)
                elif ext in VIDEO_EXTENSIONS:
                    await client.send_file(target, path, caption=os.path.basename(path), supports_streaming=True, force_document=False)
                else:
                    continue
                sent += 1
            except Exception as e:
                await event.reply(f'Error sending {os.path.basename(path)}: {e}')
        await event.reply(f'✅ Upload complete: {sent}/{len(media_files)} files sent.')
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

async def handle_queue_command(event):
    """Show current processing status and queue information"""
    global current_processing, pending_password
    
    status_lines = []
    
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
    
    if pending_password:
        pp = pending_password
        status_lines.append(f"🔐 **{pp['filename']}** - Waiting for password")
    
    # Check for any leftover files in data directory
    leftover_files = []
    try:
        for item in os.listdir(DATA_DIR):
            item_path = os.path.join(DATA_DIR, item)
            if os.path.isfile(item_path) and item.lower().endswith(ARCHIVE_EXTENSIONS):
                leftover_files.append(item)
            elif os.path.isdir(item_path) and item.startswith('extracted_'):
                leftover_files.append(f"{item}/ (extraction folder)")
    except Exception:
        pass
    
    if leftover_files:
        status_lines.append(f"📂 **Leftover files:** {len(leftover_files)} items")
    
    if not status_lines:
        await event.reply('📭 **Queue Status:** Empty\nNo active processing or pending tasks.')
    else:
        queue_msg = "📋 **Current Queue Status:**\n\n" + "\n\n".join(status_lines)
        await event.reply(queue_msg)

async def handle_cancel(event):
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
    await event.reply('✅ Operation cancelled and files removed.')

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
        if txt == '/cancel':
            await handle_cancel(event)
            return
        if txt == '/q' or txt == '/queue':
            await handle_queue_command(event)
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
