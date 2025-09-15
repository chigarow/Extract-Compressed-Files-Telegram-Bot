# Telegram Compressed File Extractor Bot

This Telegram bot extracts photos and videos from compressed files (zip, rar, 7z, tar, etc.) and forwards them to a target user. It's designed to be run on a low-power device like an Android phone with Termux, ensuring it can operate 24/7 without needing a dedicated server.

## Features

- **User Account Based Access**: The bot uses a user account (not a bot token) for authentication, controlled by specifying a target username in the configuration.
- **Automatic Extraction**: Supports a wide range of compressed file formats, including zip, rar, 7z, tar, gz, bz2, and xz.
- **Media Filtering**: Automatically filters and forwards only photo and video files.
- **Duplicate Detection**: Avoids reprocessing archives that have been previously processed by maintaining a cache of file hashes.
- **Efficient Storage Management**: Deletes the original compressed file and the extracted files after uploading to save storage space.
- **Password Protected Archive Support**: Handles password-protected archives with a simple command interface.
- **24/7 Operation**: Can be run continuously on an Android device using Termux.
- **Progress Tracking**: Provides real-time status updates during download, extraction, and upload processes.

## Prerequisites

- Python 3.7+
- Required system tools: `7z` (p7zip) for password-protected archives, `unrar` for RAR files
- A Telegram account with API credentials

## Setup

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure the bot:**

    -   Rename `secrets.properties.example` to `secrets.properties`.
    -   Open `secrets.properties` and add your Telegram API credentials and target username:

        ```ini
        APP_API_ID=YOUR_TELEGRAM_API_ID
        APP_API_HASH=YOUR_TELEGRAM_API_HASH
        ACCOUNT_B_USERNAME=YOUR_TARGET_USERNAME
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

5.  **Run the bot:**

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

### Handling Password-Protected Archives

If the script encounters a password-protected archive, it will prompt you with instructions:

- Reply with `/pass <password>` to attempt extraction with a password
- Reply with `/cancel` to abort processing and delete the file

### Checking Processing Status

You can check the current processing status by sending `/queue` or `/q` to the script.

## Configuration Options

The following options can be added to `secrets.properties` to customize behavior:

- `MAX_ARCHIVE_GB` - Maximum archive size to process (default: 6.0)
- `DISK_SPACE_FACTOR` - Required free space factor (default: 2.5)
- `MAX_CONCURRENT` - Maximum concurrent extractions (default: 1)
- `DOWNLOAD_CHUNK_SIZE_KB` - Download chunk size in KB (default: 512)

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you have any suggestions or find any bugs.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
