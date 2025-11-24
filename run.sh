#!/bin/bash

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

echo "🚀 Launching Schedule-IIT..."
source venv/bin/activate

# Set Flask env to development for auto-reload
export FLASK_ENV=development
export FLASK_APP=app.py

python app.py