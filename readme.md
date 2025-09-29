# Telegram Compressed File Extractor

This script extracts photos and videos from compressed files (zip, rar, 7z, tar, etc.) sent to a Telegram user account and forwards them to a target user. It's designed to be run on a variety of platforms including low-power devices like Android phones with Termux.

## Features

- **User Account Based Access**: Uses a user account (not a bot token) for authentication, controlled by specifying a target username in the configuration.
- **Automatic Extraction**: Supports a wide range of compressed file formats, including zip, rar, 7z, tar, gz, bz2, and xz.
- **Direct Media Upload**: Send images/videos directly to the user account and they will be re-uploaded to the target user as media in the Media tab.
- **Media Filtering**: Automatically filters and forwards only photo and video files (.png, .jpg, .jpeg, .bmp, .mp4, .mkv, .avi, .mov, .webm, and many others).
- **Duplicate Detection**: Avoids reprocessing archives that have been previously processed by maintaining a cache of file hashes.
- **Efficient Storage Management**: Deletes the original compressed file and the extracted files after uploading to save storage space.
- **Password Protected Archive Support**: Handles password-protected archives with a simple command interface.
- **Unsupported Video Format Conversion**: All unsupported video formats (.ts, .mkv, .avi, .mov, .wmv, .flv, and many others) are automatically converted to MP4 format to ensure proper playback in Telegram, even when transcoding is disabled.
- **Proper Video Attributes**: Videos now have correct duration and thumbnail for proper display in Telegram (fixes black thumbnails and 00:00 duration).
- **Media Tab Support**: Files are uploaded as native media types (photos/videos) instead of documents to appear in the Media tab.
- **Grouped Media Uploads**: Uploads images and videos as separate grouped albums with archive name as caption.
- **Queue Management System**: Limits to 2 concurrent downloads and 2 concurrent uploads to prevent API rate limits, with all incoming files queued and processed according to the limits.
- **Crash Recovery System**: Current processing state is saved to `current_process.json` every minute to persist across restarts, ensuring graceful recovery after crashes.
- **Automatic Retry for Failed Operations**: Failed operations (due to FloodWaitError or other network issues) are automatically saved to `failed_operations.json` and retried every 30 minutes.
- **FastTelethon Parallel Downloads**: Automatic 10-20x speed acceleration for large files using parallel MTProto connections.
- **Optimized Download Speed**: Uses larger chunk sizes for Telegram Premium users to maximize download performance.
- **Progress Tracking**: Provides real-time status updates during download, extraction, and upload processes.
- **Configurable Limits**: Adjustable settings for maximum file size, disk space requirements, and concurrent processing.
- **Queue Monitoring**: Built-in status command to check current processing state.
- **Concurrent Downloads**: Supports multiple simultaneous downloads with sequential extraction/upload processing.

## Prerequisites

- Python 3.7+
- Required system tools: `7z` (p7zip) for password-protected archives, `unrar` for RAR files, `ffmpeg` and `ffprobe` for video processing
- A Telegram account with API credentials
- **Recommended**: `cryptg` package for optimal FastTelethon performance (`pip install cryptg`)

## Setup

1.  **Clone or download the repository:**

    ```bash
    git clone <repository-url>
    cd ExtractCompressedFiles
    ```

2.  **Install Python dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure the script:**

    -   Create a `secrets.properties` file in the root directory.
    -   Add your Telegram API credentials and target username:

        ```ini
        APP_API_ID=YOUR_TELEGRAM_API_ID
        APP_API_HASH=YOUR_TELEGRAM_API_HASH
        ACCOUNT_B_USERNAME=TARGET_USERNAME
        
        # Optional configuration parameters:
        # MAX_ARCHIVE_GB=6.0
        # DISK_SPACE_FACTOR=2.5
        # MAX_CONCURRENT=1
        # DOWNLOAD_CHUNK_SIZE_KB=512
        # PARALLEL_DOWNLOADS=4
        ```

4.  **Install system dependencies (if needed):**

    On Termux:
    ```bash
    pkg install p7zip unrar ffmpeg
    ```

    On Ubuntu/Debian:
    ```bash
    sudo apt install p7zip-full unrar ffmpeg
    ```

5.  **Run the script:**

    ```bash
    python extract-compressed-files.py
    ```

    On first run, you'll be prompted to enter your phone number and the code sent by Telegram.

    **Note**: The script now uses a modular architecture with components in the `utils/` directory. All dependencies and imports are handled automatically.

## Usage

1.  **Send a compressed file** to your user account (the one running this script) from any chat.
2.  The script will automatically:
    -   Download the file (if not previously processed).
    -   Check if the file has been processed before using hash-based deduplication.
    -   Extract the contents.
    -   Filter for photos and videos.
    -   Forward the media files to the target user specified in the configuration.
    -   Delete the local files.

### Direct Media Upload

In addition to processing compressed archives, you can now send images and videos directly to the user account and they will be re-uploaded to the target user as media files in the Media tab:

1.  **Send an image or video** directly to your user account.
2.  The script will automatically:
    -   Check if the media file has been processed before using hash-based deduplication.
    -   Download the media file (if not previously processed).
    -   Upload it to the target user as a native media file (photo or video).
    -   The file will appear in the target user's Media tab.
    -   Delete the local file after upload.

This feature is particularly useful when you want to optimize media files for Telegram or re-upload them to another account while ensuring they appear properly in the Media tab.

### Video Quality and Thumbnail Fixes

The script now ensures videos have proper thumbnails and durations displayed in Telegram by:

- Extracting video attributes using `ffprobe`
- Generating proper thumbnails with `ffmpeg`
- Setting correct duration and dimensions when uploading
- Using proper video attributes (`DocumentAttributeVideo`) during upload
- This resolves the common issue of black thumbnails and 00:00 duration display

### Special Handling for .ts Files

The script now includes special handling for MPEG Transport Stream (.ts) files:

- .ts files are automatically converted to MP4 format regardless of the `TRANSCODE_ENABLED` setting
- This ensures proper playback and streaming in Telegram, since Telegram's video player is optimized for MP4 files
- Conversion uses the same optimized settings as regular video transcoding
- This applies to both direct media uploads and videos extracted from archives

### Enhanced Video Format Support

The script now includes comprehensive support for various video formats:

- All unsupported video formats (.ts, .mkv, .avi, .mov, .wmv, .flv, and many others) are automatically converted to MP4 format
- This ensures proper playback and streaming in Telegram, since Telegram's video player is optimized for MP4 files
- Conversion uses the same optimized settings as regular video transcoding
- This applies to both direct media uploads and videos extracted from archives
- The script checks if videos are compatible with Telegram before uploading, and only converts when necessary to save processing time

### Grouped Media Uploads

The script now uploads media files as grouped albums for better organization:

- Images are uploaded first as a single grouped album
- Videos are uploaded separately as another grouped album
- Both groups use the archive filename (without extension) as the caption
- Fallback to individual uploads if grouped upload fails

This feature makes it easier to identify which files came from which archive.

### Queue Management System

The script now includes a comprehensive queue management system to control resource usage:

- Download queue: Limits to 2 concurrent downloads to prevent API rate limits
- Upload queue: Limits to 2 concurrent uploads to prevent API rate limits
- All incoming files are queued and processed according to the limits
- Queue status is reported to the user with position information
- Queued operations are persisted to files (`download_queue.json` and `upload_queue.json`) and restored on restart
- This ensures stable performance even with high volume file traffic

### Crash Recovery System

The script now includes crash recovery to handle unexpected shutdowns gracefully:

- Current processing state is saved to `current_process.json` every minute
- If the script crashes during a download or upload, the current process state is preserved
- Upon restart, the script can resume from where it left off or handle incomplete operations appropriately
- This ensures that temporary network issues or rate limits don't cause permanent failures

### Fast Video Compression

The script includes an optional fast video compression feature that converts all video files to MP4 format optimized for Telegram streaming. This feature:

- Uses enhanced ffmpeg settings to ensure proper metadata, thumbnails, and duration display
- Converts all video files regardless of their format or size
- Optimizes videos for Telegram's streaming capabilities
- Ensures compatibility with Telegram's video requirements (H.264 baseline profile, proper pixel format, even dimensions)
- Fixes common issues with black thumbnails and 00:00 duration display
- Validates video files before processing using ffprobe
- Only processes videos that need processing (skips already compliant MP4 files when possible)

To enable this feature, set `TRANSCODE_ENABLED=true` in your `secrets.properties` file.

### Download Speed Optimization

The script includes **FastTelethon parallel download acceleration** that can provide **10-20x speed improvements** for large files:

#### FastTelethon Parallel Downloads
- **Automatic acceleration**: Enabled by default for files larger than 10MB
- **Multiple connections**: Uses up to 8 parallel MTProto connections
- **Proven performance**: Based on mautrix-telegram's battle-tested implementation
- **Smart fallback**: Falls back to standard download on any errors

#### Performance Improvements
- **Typical speeds**: 200 KB/s → 5-20 MB/s (reported by FastTelethon users)
- **Small files** (<10MB): Uses standard download (no overhead)
- **Large files** (>10MB): Automatic parallel download acceleration
- **Premium accounts**: Combined with larger chunk sizes for maximum speed

#### Configuration Options
Add these settings to your `secrets.properties`:

```ini
# FastTelethon parallel download acceleration
FAST_DOWNLOAD_ENABLED=true              # Enable/disable FastTelethon (default: true)
FAST_DOWNLOAD_CONNECTIONS=8             # Number of parallel connections (default: 8)

# Standard Telethon optimization
DOWNLOAD_CHUNK_SIZE_KB=1024             # Chunk size for Premium users (default: 1024 KB)
```

#### Requirements
- **cryptg**: Install with `pip install cryptg` for optimal AES performance
- **Telethon**: Automatic with existing installation

The script will automatically detect and use FastTelethon when available, with seamless fallback to standard downloads if needed.

### Handling Password-Protected Archives

If the script encounters a password-protected archive, it will prompt you with instructions:

- Reply with `/pass <password>` to attempt extraction with a password
- Reply with `/cancel-password` to abort password input and delete the file

### Canceling Processes

The script provides several commands to cancel ongoing processes:

- Reply with `/cancel-password` to cancel password input for a password-protected archive
- Reply with `/cancel-extraction` to cancel the current extraction process
- Reply with `/cancel-process` to cancel the entire process and delete any downloaded files
- Reply with `/max_concurrent <number>` to dynamically change the maximum number of concurrent downloads

### Checking Processing Status

You can check the current processing status by sending `/queue` or `/q` to the script. The queue status now shows:

- Currently processing files (download, extraction, or upload)
- Password-protected archives waiting for input
- Processing queue (files that have completed download and are waiting for extraction/upload)

## Configuration Options

The following options can be added to `secrets.properties` to customize behavior:

- `MAX_ARCHIVE_GB` - Maximum archive size to process (default: 6.0)
- `DISK_SPACE_FACTOR` - Required free space factor (default: 2.5)
- `MAX_CONCURRENT` - Maximum concurrent extractions (default: 1)
- `DOWNLOAD_CHUNK_SIZE_KB` - Download chunk size in KB (default: 1024)
- `FAST_DOWNLOAD_ENABLED` - Enable FastTelethon parallel downloads (default: true)
- `FAST_DOWNLOAD_CONNECTIONS` - Parallel connections for FastTelethon (default: 8)
- `TRANSCODE_ENABLED` - Enable/disable video compression feature (default: false)
- `PARALLEL_DOWNLOADS` - Number of parallel downloads for faster speed (default: 4)

## Code Architecture

The project has been refactored into a modular architecture for better maintainability:

### Main Components

- **`extract-compressed-files.py`** - Main entry point and event handling
- **`utils/`** - Modular utility components:
  - **`constants.py`** - Configuration constants and file paths
  - **`utils.py`** - General utility functions (human_size, format_eta, logging setup)
  - **`file_operations.py`** - File handling, extraction, and hashing operations
  - **`media_processing.py`** - Video processing and media format validation
  - **`telegram_operations.py`** - Telegram client operations and file transfers
  - **`cache_manager.py`** - File processing cache and persistent data management
  - **`queue_manager.py`** - Download/upload queue management with concurrency control
  - **`command_handlers.py`** - User command processing and interaction handling
  - **`fast_download.py`** - FastTelethon parallel download implementation
  - **`network_monitor.py`** - Network connectivity monitoring utilities

### Module Organization

Each module handles a specific aspect of functionality:

- **File Operations**: SHA256 hashing, archive extraction, password handling
- **Media Processing**: Video format validation, ffmpeg operations, thumbnail generation
- **Telegram Operations**: File uploads/downloads, progress tracking, message handling
- **Cache Management**: Processed file tracking, persistent queues, crash recovery
- **Queue Management**: Concurrent download/upload control, task scheduling
- **Command Handling**: User interaction, configuration updates, status reporting

This modular design makes the codebase easier to maintain, test, and extend with new features.

## How It Works

1. The script uses Telethon to connect to Telegram as a user account
2. It listens for incoming messages containing document attachments with recognized archive extensions
3. When an archive is detected:
   - It checks if the file has been processed before using SHA256 hash verification
   - Downloads the file with progress tracking using the queue management system
   - Verifies sufficient disk space is available
   - Extracts the contents using specialized extraction tools
   - Scans for media files (images and videos) using media processing utilities
   - Sends each media file to the configured target user via Telegram operations
   - Updates the processed files cache using the cache manager
   - Cleans up temporary files and manages queue state

## Development Notes

### Modular Architecture Benefits

The refactored modular structure provides several advantages:

1. **Separation of Concerns**: Each module handles a specific functionality area
2. **Easier Testing**: Individual components can be tested independently
3. **Better Maintainability**: Bug fixes and features can be isolated to specific modules
4. **Code Reusability**: Modules can be imported and used by other components
5. **Cleaner Dependencies**: Import relationships are clearly defined

### Adding New Features

When adding new functionality:

1. **File Operations**: Add to `utils/file_operations.py`
2. **Media Processing**: Add to `utils/media_processing.py` 
3. **Telegram Features**: Add to `utils/telegram_operations.py`
4. **User Commands**: Add to `utils/command_handlers.py`
5. **Configuration**: Add to `utils/constants.py`

### Import Structure

The main script imports from `utils` which provides a clean API:

```python
from utils import (
    # Constants
    ARCHIVE_EXTENSIONS, MAX_ARCHIVE_GB, 
    # Functions
    human_size, compute_sha256, ensure_target_entity,
    # Classes  
    CacheManager, TelegramOperations
)
```

### File Organization

```
ExtractCompressedFiles/
├── extract-compressed-files.py      # Main application entry point
├── extract-compressed-files-original.py  # Original monolithic version (backup)
├── config.py                        # Configuration management
├── requirements.txt                  # Python dependencies
├── utils/                           # Modular utility components
│   ├── __init__.py                  # Module exports and API
│   ├── constants.py                 # Configuration and constants
│   ├── utils.py                     # General utility functions
│   ├── file_operations.py           # File handling operations
│   ├── media_processing.py          # Video/media processing
│   ├── telegram_operations.py       # Telegram client operations
│   ├── cache_manager.py             # Cache and persistence
│   ├── queue_manager.py             # Queue management
│   ├── command_handlers.py          # User command processing
│   ├── fast_download.py             # FastTelethon downloads
│   └── network_monitor.py           # Network monitoring
└── data/                            # Runtime data directory
    ├── processed_archives.json      # Cache of processed files
    ├── download_queue.json           # Persistent download queue
    ├── upload_queue.json             # Persistent upload queue
    ├── current_process.json          # Current processing state
    ├── failed_operations.json        # Failed operations for retry
    └── session.session               # Telegram session data
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.