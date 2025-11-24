#!/bin/bash

# Colors for pretty output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Schedule-IIT Setup...${NC}"

# 1. Create Virtual Environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "Creating Python virtual environment..."
    python3 -m venv venv
else
    echo -e "Virtual environment already exists."
fi

# 2. Activate and Install
echo -e "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

# 3. Create necessary directories for the App and Selenium
echo -e "Creating data directories..."
# 'instance' is where Flask-SQLAlchemy stores the sqlite db by default
mkdir -p instance
# 'chrome_data' is required by your scraper.py for the persistent profile
mkdir -p chrome_data

echo -e "${GREEN}Setup Complete! You can now run ./run.sh${NC}"