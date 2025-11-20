#!/bin/bash

# --- Configuration ---
# The name of the python script you want to manage
SCRIPT_NAME="extract-compressed-files.py"
# The directory where your project and git repository are located
PROJECT_DIR="/data/data/com.termux/files/home/Extract-Compressed-Files-Telegram-Bot"
# The path to your virtual environment's bin directory
# !!! IMPORTANT !!!
# You might need to change this path to match your Termux setup.
VENV_BIN_DIR="/data/data/com.termux/files/home/venv/bin"
# Path to the data directory to be monitored for active processing
DATA_DIR="$PROJECT_DIR/data"
# Default git branch to pull when no branch argument is provided
DEFAULT_BRANCH="main"

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

# --- Help Function ---
show_help() {
    echo "Usage: $(basename "$0") [OPTION]"
    echo "A script to manage the lifecycle (update, restart, kill) of '$SCRIPT_NAME'."
    echo ""
    echo "Options:"
    echo "  --force       Forcefully restarts the script without waiting for active operations."
    echo "  --kill        Finds and kills the running script process without restarting it."
    echo "  -b, --branch BRANCH"
    echo "               Pull the specified git branch (defaults to 'main')."
    echo "  --help        Display this help message and exit."
    echo ""
    echo "If run with no options, the script performs a graceful restart: it waits for"
    echo "current operations to finish, pulls the latest code from git, updates Python"
    echo "dependencies, and then restarts the process."
}


# --- Sanity Checks ---
# Check if the virtual environment path is correct before doing anything else.
if ! [ -x "$PIP_EXEC" ]; then
    echo -e "${RED}Error: The 'pip' executable was not found or is not executable at:${NC}"
    echo -e "${RED}$PIP_EXEC${NC}"
    echo -e "${YELLOW}Please make sure the 'VENV_BIN_DIR' variable in this script is set correctly.${NC}"
    exit 1
fi

# --- Argument Parsing ---
FORCE_RESTART=false
GIT_BRANCH=""

# Handle command-line arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --help)
            show_help
            exit 0
            ;;
        --kill)
            echo -e "${RED}--- Killing Process: $SCRIPT_NAME ---${NC}"
            PID=$(pgrep -f "$SCRIPT_NAME")
            if [ -n "$PID" ]; then
                echo "Found process with PID: $PID. Terminating immediately..."
                kill -9 "$PID"
                sleep 1 # Brief pause to allow the OS to process the kill command
                if pgrep -f "$SCRIPT_NAME" > /dev/null; then
                    echo -e "${RED}Error: Failed to kill the process. It might be unresponsive.${NC}"
                    exit 1
                else
                    echo -e "${GREEN}Process successfully terminated.${NC}"
                    exit 0
                fi
            else
                echo -e "${GREEN}No running process found. Nothing to kill.${NC}"
                exit 0
            fi
            ;;
        --force)
            FORCE_RESTART=true
            shift
            ;;
        -b|--branch)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Missing branch name for '$1'.${NC}"
                exit 1
            fi
            GIT_BRANCH="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Error: Unknown option '$1'${NC}\n"
            show_help
            exit 1
            ;;
    esac
done


# --- Main Script Logic ---

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
            # The find command will exit with success (0) if it finds any matching file
            if find "$DATA_DIR" -maxdepth 1 -mindepth 1 \( \
                -type d -name 'extracted_*' -o \
                -iname '*.zip' -o -iname '*.rar' -o -iname '*.7z' -o \
                -iname '*.tar' -o -iname '*.gz' -o -iname '*.bz2' -o \
                -iname '*.xz' -o -iname '*.ts' -o \
                -iname '*_compressed.mp4' -o \
                -iname '*.thumb.jpg' -o \
                -name '*.part' \
            \) -print -quit | grep -q .; then
                echo -e "${YELLOW} - Active operations detected. Waiting for 30 seconds...${NC}"
                sleep 30
            else
                echo -e "${GREEN} - No active operations detected. The script appears to be idle.${NC}"
                break
            fi
        done
    else
        echo -e "${YELLOW} - Process is not running. Checking for leftover files from a previous run...${NC}"
        # Find temporary files/directories and clean them
        find "$DATA_DIR" -maxdepth 1 -mindepth 1 \( \
            -type d -name 'extracted_*' -o \
            -iname '*.zip' -o -iname '*.rar' -o -iname '*.7z' -o \
            -iname '*.tar' -o -iname '*.gz' -o -iname '*.bz2' -o \
            -iname '*.xz' -o -iname '*.ts' -o \
            -iname '*_compressed.mp4' -o \
            -iname '*.thumb.jpg' -o \
            -name '*.part' \
        \) -exec rm -rf {} +

        # Check if anything was actually deleted
        if find "$DATA_DIR" -maxdepth 1 -mindepth 1 \( -type d -name 'extracted_*' -o -iname '*.part' \) -print -quit | grep -q .; then
             echo -e "${YELLOW} - Some leftover files may remain.${NC}"
        else
             echo -e "${GREEN} - Cleanup complete. No leftover files found.${NC}"
        fi
    fi
else
    echo -e "\n${YELLOW}[Step 1/6] Skipping wait/cleanup due to --force flag.${NC}"
fi


# 2. Kill the existing process (if it's running)
echo -e "\n${YELLOW}[Step 2/6] Checking for existing process...${NC}"
PID=$(pgrep -f "$SCRIPT_NAME")

if [ -n "$PID" ]; then
    if [ "$FORCE_RESTART" = true ]; then
        echo "Force-killing process with PID: $PID."
        kill -9 "$PID"
    else
        echo "Gracefully terminating process with PID: $PID."
        kill -TERM "$PID"
        sleep 5
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
BRANCH_TO_PULL="${GIT_BRANCH:-$DEFAULT_BRANCH}"
echo -e "${YELLOW} - Pulling branch '${BRANCH_TO_PULL}' from origin...${NC}"
if git pull origin "$BRANCH_TO_PULL"; then
    echo -e "${GREEN}Git pull successful.${NC}"
else
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
nohup "$PYTHON_EXEC" "$SCRIPT_PATH" &

# 6. Verify that the process is running
echo -e "\n${YELLOW}[Step 6/6] Verifying that the process has restarted...${NC}"
sleep 2
NEW_PID=$(pgrep -f "$SCRIPT_NAME")

if [ -n "$NEW_PID" ]; then
    echo -e "${GREEN}Success! The script is now running with new PID: $NEW_PID${NC}"
else
    echo -e "${RED}Error: The script failed to start. Check 'nohup.out' for errors.${NC}"
    exit 1
fi

echo -e "\n${GREEN}--- Process Complete ---${NC}"