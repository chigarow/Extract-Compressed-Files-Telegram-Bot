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
VIDEO_TRANSCODE_THRESHOLD_MB = config.getfloat('DEFAULT', 'VIDEO_TRANSCODE_THRESHOLD_MB', fallback=300.0)
TRANSCODE_ENABLED = config.getboolean('DEFAULT', 'TRANSCODE_ENABLED', fallback=True)
MAX_CONCURRENT = config.getint('DEFAULT', 'MAX_CONCURRENT', fallback=1)  # semaphore size

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

FFMPEG_AVAILABLE = shutil.which('ffmpeg') is not None

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

async def transcode_video_if_needed(path: str) -> str:
    if not TRANSCODE_ENABLED or not FFMPEG_AVAILABLE:
        return path
    try:
        size_mb = os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return path
    ext = os.path.splitext(path)[1].lower()
    # Force transcode if not mp4 to enable streaming; otherwise threshold-based
    force_due_to_container = ext != '.mp4'
    if size_mb < VIDEO_TRANSCODE_THRESHOLD_MB and not force_due_to_container:
        return path
    # Target output path (avoid overriding original until validated)
    out_path = path + '.mp4' if ext != '.mp4' else path + '.t.mp4'
    cmd = [
        'ffmpeg', '-y', '-i', path,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28',
        '-c:a', 'aac', '-b:a', '128k', out_path
    ]
    logger.info(f'Transcoding large video ({size_mb:.1f} MB) -> {out_path}')
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # If output smaller, replace; else keep original
        if os.path.exists(out_path):
            orig_size = os.path.getsize(path)
            new_size = os.path.getsize(out_path)
            if new_size < orig_size * 0.98:  # savings threshold
                logger.info(f'Transcode saved space: {human_size(orig_size)} -> {human_size(new_size)}')
                return out_path
            else:
                os.remove(out_path)
                return path
        return path
    except Exception as e:
        logger.warning(f'Transcode failed: {e}')
        if os.path.exists(out_path):
            try: os.remove(out_path)
            except Exception: pass
        return path

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
            await message.download_media(file=temp_archive_path, progress_callback=progress)
            actual_size = os.path.getsize(temp_archive_path) if os.path.exists(temp_archive_path) else 0
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

        # Hash caching
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

        # Attempt extraction
        try:
            logger.info(f'Start extracting {temp_archive_path} -> {extract_path}')
            patoolib.extract_archive(temp_archive_path, outdir=extract_path)
            await event.reply('✅ Extraction complete. Scanning media files…')
        except patoolib.util.PatoolError as e:
            err_text = str(e)
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
                await event.reply(f'❌ Extraction failed: {e}')
                shutil.rmtree(extract_path, ignore_errors=True)
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
            await event.reply(f'📤 Found {len(media_files)} media files. Uploading to {TARGET_USERNAME} ...')
            target = await ensure_target_entity()
            sent = 0
            for path in media_files:
                ext = os.path.splitext(path)[1].lower()
                send_path = path
                if ext in VIDEO_EXTENSIONS:
                    send_path = await transcode_video_if_needed(path)
                try:
                    if ext in PHOTO_EXTENSIONS:
                        await client.send_file(target, send_path, caption=os.path.basename(send_path), force_document=False)
                    elif ext in VIDEO_EXTENSIONS:
                        await client.send_file(target, send_path, caption=os.path.basename(send_path), supports_streaming=True, force_document=False)
                    else:
                        continue  # skip anything not explicitly allowed
                    sent += 1
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
            send_path = path
            if ext in VIDEO_EXTENSIONS:
                send_path = await transcode_video_if_needed(path)
            try:
                if ext in PHOTO_EXTENSIONS:
                    await client.send_file(target, send_path, caption=os.path.basename(send_path), force_document=False)
                elif ext in VIDEO_EXTENSIONS:
                    await client.send_file(target, send_path, caption=os.path.basename(send_path), supports_streaming=True, force_document=False)
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
    if FFMPEG_AVAILABLE:
        logger.info('ffmpeg detected: video transcoding enabled')
    else:
        logger.info('ffmpeg not found: skipping video transcoding')
    logger.info('Waiting for incoming archives from target user...')
    await client.run_until_disconnected()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info('Shutting down (KeyboardInterrupt)')

if __name__ == '__main__':
    main()
