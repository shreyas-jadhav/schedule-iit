#!/bin/bash


if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

echo "Launching Schedule-IIT..."
source venv/bin/activate


export FLASK_ENV=development
export FLASK_APP=app.py

python app.py