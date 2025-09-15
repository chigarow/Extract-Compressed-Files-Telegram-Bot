# Telegram Compressed File Extractor Bot

This Telegram bot extracts photos and videos from compressed files (zip, rar, 7z, etc.) and uploads them to your "Saved Messages". It's designed to be run on a low-power device like an Android phone with Termux, ensuring it can operate 24/7 without needing a dedicated server.

## Features

- **Secure Access**: The bot is protected by a password to prevent unauthorized use.
- **Automatic Extraction**: Supports a wide range of compressed file formats, including zip, rar, and 7z.
- **Media Filtering**: Automatically filters and uploads only photo and video files.
- **Efficient Cleanup**: Deletes the original compressed file and the extracted files after uploading to save storage space.
- **24/7 Operation**: Can be run continuously on an Android device using Termux.

## Prerequisites

- An Android device with [Termux](https://termux.com/) installed.
- A Telegram account and a bot token.

## Setup

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```

2.  **Install dependencies:**

    ```bash
    pkg install python
    pip install -r requirements.txt
    ```

3.  **Configure the bot:**

    -   Rename `secrets.properties.example` to `secrets.properties`.
    -   Open `secrets.properties` and add your Telegram bot token and a password of your choice:

        ```ini
        TELEGRAM_API_KEY=YOUR_TELEGRAM_API_KEY
        PASSWORD=YOUR_SECRET_PASSWORD
        ```

4.  **Run the bot:**

    ```bash
    python extract-compressed-files.py
    ```

## Usage

1.  **Start a chat with your bot on Telegram.**
2.  **Send the password** you set in `secrets.properties` to authenticate.
3.  **Send a compressed file** (zip, rar, 7z, etc.) to the bot.
4.  The bot will then:
    -   Download the file.
    -   Extract the contents.
    -   Filter for photos and videos.
    -   Upload the media to your "Saved Messages".
    -   Delete the local files.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you have any suggestions or find any bugs.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
