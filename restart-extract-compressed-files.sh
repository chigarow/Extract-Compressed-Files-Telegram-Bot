#!/bin/bash

# --- Configuration ---
# The name of the python script you want to manage
SCRIPT_NAME="extract-compressed-files.py"
# The directory where your project and git repository are located
PROJECT_DIR="/data/data/com.termux/files/home/Extract-Compressed-Files-Telegram-Bot"
# The path to your virtual environment's bin directory
# !!! IMPORTANT !!!
# You might need to change this path to match your Termux setup.
# A common location is /data/data/com.termux/files/home/venv/bin
VENV_BIN_DIR="/data/data/com.termux/files/home/venv/bin"
# Path to the data directory to be monitored for active processing
DATA_DIR="$PROJECT_DIR/data"

# --- Full Paths to Executables ---
PYTHON_EXEC="$VENV_BIN_DIR/python"
PIP_EXEC="$VENV_BIN_DIR/pip"
SCRIPT_PATH="$PROJECT_DIR/$SCRIPT_NAME"
REQUIREMENTS_PATH="$PROJECT_DIR/requirements.txt"

# --- Colors for output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Sanity Checks ---
# Check if the virtual environment path is correct before doing anything else.
if ! [ -x "$PIP_EXEC" ]; then
    echo -e "${RED}Error: The 'pip' executable was not found or is not executable at:${NC}"
    echo -e "${RED}$PIP_EXEC${NC}"
    echo -e "${YELLOW}Please make sure the 'VENV_BIN_DIR' variable in this script is set correctly.${NC}"
    exit 1
fi

# --- Main Script Logic ---

FORCE_RESTART=false
if [ "$1" == "--force" ]; then
    FORCE_RESTART=true
fi

if [ "$FORCE_RESTART" = true ]; then
    echo -e "${YELLOW}--- Starting Forceful Update & Restart for $SCRIPT_NAME ---${NC}"
else
    echo -e "${YELLOW}--- Starting Graceful Update & Restart for $SCRIPT_NAME ---${NC}"
fi

# Navigate to the project directory. Exit if it fails.
cd "$PROJECT_DIR" || { echo -e "${RED}Error: Could not navigate to project directory: $PROJECT_DIR${NC}"; exit 1; }

# 1. Wait until no operations are active (unless --force is used).
if [ "$FORCE_RESTART" = false ]; then
    echo -e "\n${YELLOW}[Step 1/6] Checking for active operations...${NC}"

    # First, check if the script is even running
    if pgrep -f "$SCRIPT_NAME" > /dev/null; then
        echo -e "${YELLOW} - Process is running. Waiting for all operations to complete...${NC}"

        # Wait for all ongoing operations to finish
        while true; do
            # Check for any active operations (download, upload, conversion, extraction)
            # This includes archive files, extracted directories, compressed videos, and temporary files
            ACTIVE_TASKS_FOUND=false

            # Check for archive files being processed
            if find "$DATA_DIR" -maxdepth 1 -mindepth 1 \( -type d -name 'extracted_*' -o -iname '*.zip' -o -iname '*.rar' -o -iname '*.7z' -o -iname '*.tar' -o -iname '*.gz' -o -iname '*.bz2' -o -iname '*.xz' -o -iname '*.ts' \) -print -quit | grep -q .; then
                ACTIVE_TASKS_FOUND=true
            fi

            # Check for video compression temp files
            if find "$DATA_DIR" -maxdepth 1 -mindepth 1 -iname '*_compressed.mp4' -print -quit | grep -q .; then
                ACTIVE_TASKS_FOUND=true
            fi

            # Check for video thumbnails
            if find "$DATA_DIR" -maxdepth 1 -mindepth 1 -iname '*.thumb.jpg' -print -quit | grep -q .; then
                ACTIVE_TASKS_FOUND=true
            fi

            # Check for any .part files (partial downloads)
            if find "$DATA_DIR" -maxdepth 1 -mindepth 1 -name '*.part' -print -quit | grep -q .; then
                ACTIVE_TASKS_FOUND=true
            fi

            if [ "$ACTIVE_TASKS_FOUND" = true ]; then
                echo -e "${YELLOW} - Active operations detected (downloads, uploads, conversions, extractions). Waiting for 30 seconds...${NC}"
                sleep 30
            else
                echo -e "${GREEN} - No active operations detected. The script appears to be idle.${NC}"
                break
            fi
        done
    else
        echo -e "${YELLOW} - Process is not running. Checking for leftover files from a previous run...${NC}"
        # Find temporary files/directories
        LEFTOVER_FILES=$(find "$DATA_DIR" -maxdepth 1 -mindepth 1 \( -type d -name 'extracted_*' -o -iname '*.zip' -o -iname '*.rar' -o -iname '*.7z' -o -iname '*.tar' -o -iname '*.gz' -o -iname '*.bz2' -o -iname '*.xz' -o -iname '*_compressed.mp4' -o -iname '*.thumb.jpg' -o -name '*.part' -o -iname '*.ts' \))
        if [ -n "$LEFTOVER_FILES" ]; then
            echo -e "${YELLOW} - Found leftover files. Cleaning them up...${NC}"
            # The -I{} and + are to handle many files without erroring
            find "$DATA_DIR" -maxdepth 1 -mindepth 1 \( -type d -name 'extracted_*' -o -iname '*.zip' -o -iname '*.rar' -o -iname '*.7z' -o -iname '*.tar' -o -iname '*.gz' -o -iname '*.bz2' -o -iname '*.xz' -o -iname '*_compressed.mp4' -o -iname '*.thumb.jpg' -o -name '*.part' -o -iname '*.ts' \) -exec rm -rf {} +
            echo -e "${GREEN} - Cleanup complete.${NC}"
        else
            echo -e "${GREEN} - No leftover files found.${NC}"
        fi
    fi
else
    echo -e "\n${YELLOW}[Step 1/6] Skipping wait/cleanup due to --force flag.${NC}"
fi


# 2. Kill the existing process (if it's running)
echo -e "\n${YELLOW}[Step 2/6] Checking for existing process...${NC}"
# Use pgrep to find the Process ID (PID). The -f flag matches the full command line.
PID=$(pgrep -f "$SCRIPT_NAME")

if [ -n "$PID" ]; then
    if [ "$FORCE_RESTART" = true ]; then
        echo "Force-killing process with PID: $PID."
        kill -9 "$PID"
    else
        echo "Gracefully terminating process with PID: $PID."
        # Send SIGTERM first to allow graceful shutdown
        kill -TERM "$PID"
        # Wait a bit for graceful shutdown
        sleep 5
        # Check if process still exists, force kill if needed
        if pgrep -f "$SCRIPT_NAME" > /dev/null; then
            echo "Process still running after SIGTERM. Force-killing..."
            kill -9 "$PID"
            sleep 2
        fi
    fi
    echo -e "${GREEN}Process terminated.${NC}"
else
    echo -e "${GREEN}No running process found. Skipping.${NC}"
fi


# 3. Update the code using git pull
echo -e "\n${YELLOW}[Step 3/6] Pulling latest changes from git...${NC}"
# Execute git pull and check if it was successful.
if git pull; then
    echo -e "${GREEN}Git pull successful.${NC}"
else
    # If git pull fails, exit the script to prevent running old/broken code.
    echo -e "${RED}Error: Git pull failed. Aborting script.${NC}"
    exit 1
fi

# 4. Install/update dependencies
echo -e "\n${YELLOW}[Step 4/6] Installing/updating Python dependencies...${NC}"
if [ -f "$REQUIREMENTS_PATH" ]; then
    if "$PIP_EXEC" install -r "$REQUIREMENTS_PATH"; then
        echo -e "${GREEN}Dependencies are up to date.${NC}"
    else
        echo -e "${RED}Error: Failed to install dependencies from requirements.txt. Aborting.${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Warning: requirements.txt not found. Skipping dependency installation.${NC}"
fi

# 5. Start the script again using nohup
echo -e "\n${YELLOW}[Step 5/6] Starting the script in the background...${NC}"
# Use nohup to run the process so it doesn't stop when you close the terminal.
# The '&' at the end runs the command in the background.
# Output will be redirected to a file named 'nohup.out' in the PROJECT_DIR.
nohup "$PYTHON_EXEC" "$SCRIPT_PATH" &

# 6. Verify that the process is running
echo -e "\n${YELLOW}[Step 6/6] Verifying that the process has restarted...${NC}"
# Give the script a couple of seconds to initialize
sleep 2
NEW_PID=$(pgrep -f "$SCRIPT_NAME")

if [ -n "$NEW_PID" ]; then
    echo -e "${GREEN}Success! The script is now running with new PID: $NEW_PID${NC}"
else
    echo -e "${RED}Error: The script failed to start. Check 'nohup.out' for errors.${NC}"
    exit 1
fi

echo -e "\n${GREEN}--- Process Complete ---${NC}"