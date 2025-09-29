# Telegram Compressed File Extractor

This script extracts photos and videos from compressed files (zip, rar, 7z, tar, etc.) sent to a Telegram user account and forwards them to a target user. It's designed to be run on a variety of platforms including low-power devices like Android phones with Termux.

## Features

- **User Account Based Access**: Uses a user account (not a bot token) for authentication, controlled by specifying a target username in the configuration.
- **Automatic Extraction**: Supports a wide range of compressed file formats, including zip, rar, 7z, tar, gz, bz2, and xz.
- **Direct Media Upload**: Send images/videos directly to the user account and they will be re-uploaded to the target user as media in the Media tab.
- **Media Filtering**: Automatically filters and forwards only photo and video files (.png, .jpg, .jpeg, .bmp, .mp4, .mkv, .avi, .mov, .webm).
- **Duplicate Detection**: Avoids reprocessing archives that have been previously processed by maintaining a cache of file hashes.
- **Duplicate Detection for Direct Media**: Avoids reprocessing direct media uploads that have been previously processed by maintaining a cache of file hashes.
- **Efficient Storage Management**: Deletes the original compressed file and the extracted files after uploading to save storage space.
- **Password Protected Archive Support**: Handles password-protected archives with a simple command interface.
- **Fast Video Compression**: Automatically compresses all video files to MP4 format optimized for Telegram streaming.
- **Proper Video Attributes**: Videos now have correct duration and thumbnail for proper display in Telegram (fixes black thumbnails and 00:00 duration).
- **Unsupported Video Format Conversion**: All unsupported video formats (not just .ts) are automatically converted to MP4 format to ensure proper playback in Telegram, even when transcoding is disabled.
- **Media Tab Support**: Files are uploaded as native media types (photos/videos) instead of documents to appear in the Media tab.
- **Grouped Media Uploads**: Uploads images and videos as separate grouped albums with archive name as caption.
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
    sudo apt install p7zip-full unrar
    ```

5.  **Run the script:**

    ```bash
    python extract-compressed-files.py
    ```

    On first run, you'll be prompted to enter your phone number and the code sent by Telegram.

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

### Duplicate Detection for Direct Media

Similar to compressed archives, the script now implements duplicate detection for direct media uploads:

- The script checks if a media file with the same name and exact size has been previously processed
- If a match is found, the script skips downloading and uploading the file entirely
- This saves bandwidth and processing time for identical media files
- The duplicate detection uses SHA256 hashing for definitive verification after download

### Video Quality and Thumbnail Fixes

The script now ensures videos have proper thumbnails and durations displayed in Telegram by:

- Extracting video attributes using `ffprobe`
- Generating proper thumbnails with `ffmpeg`
- Setting correct duration and dimensions when uploading
- Using proper video attributes (`DocumentAttributeVideo`) during upload
- This resolves the common issue of black thumbnails and 00:00 duration display

### Enhanced Video Format Support

The script now includes comprehensive support for various video formats:

- All unsupported video formats (.ts, .mkv, .avi, .mov, .wmv, .flv, and many others) are automatically converted to MP4 format
- This ensures proper playback and streaming in Telegram, since Telegram's video player is optimized for MP4 files
- Conversion uses the same optimized settings as regular video transcoding
- This applies to both direct media uploads and videos extracted from archives
- The script checks if videos are compatible with Telegram before uploading, and only converts when necessary to save processing time

### Automatic Retry for Failed Operations

The script now includes robust error handling and automatic retry mechanisms:

- Failed operations (due to FloodWaitError or other network issues) are automatically saved to `failed_operations.json`
- A background task runs every 30 minutes to retry failed operations
- Each retry attempt is logged and tracked to prevent infinite retry loops
- Operations involving FloodWaitError respect the required waiting periods
- This ensures that temporary network issues or rate limits don't cause permanent failures

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
- This prevents data loss and ensures reliable processing even in unstable environments

### Grouped Media Uploads

The script now uploads media files as grouped albums for better organization:

- Images are uploaded first as a single grouped album
- Videos are uploaded separately as another grouped album
- Both groups use the archive filename (without extension) as the caption
- Fallback to individual uploads if grouped upload fails

This feature makes it easier to identify which files came from which archive.

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

### Additional Commands

The script supports additional commands for managing the bot:

- Reply with `/help` to show all available commands
- Reply with `/status` to show the current status of the bot
- Reply with `/battery-status` to show battery information (Termux only)
- Reply with `/q` or `/queue` to show the current processing queue
- Reply with `/pass <password>` to provide a password for a protected archive
- Reply with `/toggle_fast_download` to enable/disable fast download
- Reply with `/toggle_wifi_only` to enable/disable WiFi-Only mode
- Reply with `/toggle_transcoding` to enable/disable video transcoding
- Reply with `/set_max_archive_gb <number>` to set the maximum archive size in GB

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

## How It Works

1. The script uses Telethon to connect to Telegram as a user account
2. It listens for incoming messages containing document attachments with recognized archive extensions
3. When an archive is detected:
   - It checks if the file has been processed before using SHA256 hash verification
   - Downloads the file with progress tracking
   - Verifies sufficient disk space is available
   - Extracts the contents using patoolib or format-specific tools
   - Scans for media files (images and videos)
   - Sends each media file to the configured target user
   - Updates the processed files cache
   - Cleans up temporary files

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.