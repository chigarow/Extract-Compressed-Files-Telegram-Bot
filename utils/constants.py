"""
Constants and configuration definitions for the Telegram Compressed File Extractor.
"""

import os
from config import config

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# File extensions
ARCHIVE_EXTENSIONS = ('.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz')
PHOTO_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp')  # exclude gif to avoid doc behavior
ANIMATED_EXTENSIONS = ('.gif',)  # treat as skip or later special handling (skipped for now)
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts', '.m4v', '.flv', '.wmv', 
                   '.3gp', '.webm', '.vob', '.m2ts', '.mts', '.m2v', '.mpg', '.mpeg', 
                   '.ogv', '.ogg', '.drc', '.gifv', '.mng', '.qt', '.yuv', '.rm', '.rmvb', 
                   '.asf', '.amv', '.m3u8')
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS  # only these will be sent

# Configuration values from config
API_ID = config.api_id
API_HASH = config.api_hash
TARGET_USERNAME = config.target_username

# Validation
if not API_ID or not API_HASH:
    raise RuntimeError('APP_API_ID / APP_API_HASH missing in secrets.properties')
if not TARGET_USERNAME:
    raise RuntimeError('ACCOUNT_B_USERNAME missing in secrets.properties')

# Configurable limits
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

# File paths
LOG_FILE = os.path.join(DATA_DIR, 'app.log')
SESSION_PATH = os.path.join(DATA_DIR, 'session')  # Telethon will append .session
PROCESSED_CACHE_PATH = os.path.join(DATA_DIR, 'processed_archives.json')
DOWNLOAD_QUEUE_FILE = os.path.join(DATA_DIR, 'download_queue.json')
UPLOAD_QUEUE_FILE = os.path.join(DATA_DIR, 'upload_queue.json')
CURRENT_PROCESS_FILE = os.path.join(DATA_DIR, 'current_process.json')
FAILED_OPERATIONS_FILE = os.path.join(DATA_DIR, 'failed_operations.json')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Progress reporting settings
MIN_PCT_STEP = 5
MIN_EDIT_INTERVAL = 7  # seconds

# Queue concurrency limits
DOWNLOAD_SEMAPHORE_LIMIT = 2  # Allow max 2 concurrent downloads
UPLOAD_SEMAPHORE_LIMIT = 2    # Allow max 2 concurrent uploads

# Retry mechanism settings
MAX_RETRY_ATTEMPTS = 5        # Maximum retry attempts per operation
RETRY_BASE_INTERVAL = 5       # Base interval for exponential backoff (seconds)
RETRY_QUEUE_FILE = os.path.join(DATA_DIR, 'retry_queue.json')