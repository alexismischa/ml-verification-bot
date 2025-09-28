#!/bin/bash

# Set script title (for terminal window title)
echo -e "\033]0;Launching Discord Bot...\007"

# Change to the directory where this script lives
cd "$(dirname "$0")"

# Step 0: Check if Python 3.11 is available
echo "Checking Python installation..."
if ! command -v python3.11 &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found. Please install Python 3.11 from python.org or using Homebrew:"
    echo "  brew install python@3.11"
    read -p "Press any key to exit..."
    exit 1
fi

# Determine which Python command to use
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
fi

echo "Using Python command: $PYTHON_CMD"

# Step 1: Create virtual environment if missing
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Step 2: Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Step 3: Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing required packages..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Step 4: Run the bot
echo "Starting bot..."
python main.py

# Step 5: Pause to show output if script exits
echo ""
echo "Bot has stopped. Press any key to exit..."
read -n 1 -s