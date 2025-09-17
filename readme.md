# Telegram Compressed File Extractor

This script extracts photos and videos from compressed files (zip, rar, 7z, tar, etc.) sent to a Telegram user account and forwards them to a target user. It's designed to be run on a variety of platforms including low-power devices like Android phones with Termux.

## Features

- **User Account Based Access**: Uses a user account (not a bot token) for authentication, controlled by specifying a target username in the configuration.
- **Automatic Extraction**: Supports a wide range of compressed file formats, including zip, rar, 7z, tar, gz, bz2, and xz.
- **Media Filtering**: Automatically filters and forwards only photo and video files (.png, .jpg, .jpeg, .bmp, .mp4, .mkv, .avi, .mov, .webm).
- **Duplicate Detection**: Avoids reprocessing archives that have been previously processed by maintaining a cache of file hashes.
- **Efficient Storage Management**: Deletes the original compressed file and the extracted files after uploading to save storage space.
- **Password Protected Archive Support**: Handles password-protected archives with a simple command interface.
- **Fast Video Compression**: Automatically compresses all video files to MP4 format optimized for Telegram streaming.
- **Grouped Media Uploads**: Uploads images and videos as separate grouped albums with archive name as caption.
- **Optimized Download Speed**: Uses larger chunk sizes for Telegram Premium users to maximize download performance.
- **Progress Tracking**: Provides real-time status updates during download, extraction, and upload processes.
- **Configurable Limits**: Adjustable settings for maximum file size, disk space requirements, and concurrent processing.
- **Queue Monitoring**: Built-in status command to check current processing state.

## Prerequisites

- Python 3.7+
- Required system tools: `7z` (p7zip) for password-protected archives, `unrar` for RAR files
- A Telegram account with API credentials

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
        ```

4.  **Install system dependencies (if needed):**

    On Termux:
    ```bash
    pkg install p7zip unrar
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

### Grouped Media Uploads

The script now uploads media files as grouped albums for better organization:

- Images are uploaded first as a single grouped album
- Videos are uploaded separately as another grouped album
- Both groups use the archive filename (without extension) as the caption
- Fallback to individual uploads if grouped upload fails

This feature makes it easier to identify which files came from which archive.

### Fast Video Compression

The script includes an optional fast video compression feature that converts all video files to MP4 format optimized for Telegram streaming. This feature:

- Uses compatible ffmpeg settings for proper metadata and duration display
- Converts all video files regardless of their format or size
- Optimizes videos for Telegram's streaming capabilities

To enable this feature, set `TRANSCODE_ENABLED=true` in your `secrets.properties` file.

### Download Speed Optimization

For Telegram Premium users, the script is optimized to take advantage of higher download speeds:

- Uses larger chunk sizes (up to 1MB) for faster downloads
- Configurable through the `DOWNLOAD_CHUNK_SIZE_KB` setting in `secrets.properties`
- Automatically optimized for Telegram Premium accounts

To maximize download speed with Telegram Premium, ensure `DOWNLOAD_CHUNK_SIZE_KB` is set to 1024 (1MB) in your configuration.

### Handling Password-Protected Archives

If the script encounters a password-protected archive, it will prompt you with instructions:

- Reply with `/pass <password>` to attempt extraction with a password
- Reply with `/cancel-password` to abort password input and delete the file

### Canceling Processes

The script provides several commands to cancel ongoing processes:

- Reply with `/cancel-password` to cancel password input for a password-protected archive
- Reply with `/cancel-extraction` to cancel the current extraction process
- Reply with `/cancel-process` to cancel the entire process and delete any downloaded files

### Checking Processing Status

You can check the current processing status by sending `/queue` or `/q` to the script.

## Configuration Options

The following options can be added to `secrets.properties` to customize behavior:

- `MAX_ARCHIVE_GB` - Maximum archive size to process (default: 6.0)
- `DISK_SPACE_FACTOR` - Required free space factor (default: 2.5)
- `MAX_CONCURRENT` - Maximum concurrent extractions (default: 1)
- `DOWNLOAD_CHUNK_SIZE_KB` - Download chunk size in KB (default: 512)
- `TRANSCODE_ENABLED` - Enable/disable video compression feature (default: false)

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