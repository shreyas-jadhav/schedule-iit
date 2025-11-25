#!/bin/bash

RED='\033[0;31m'
NC='\033[0m'

echo -e "${RED}WARNING: This will delete your Database and Saved Login Sessions.${NC}"
read -p "Are you sure? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    # delete Database
    if [ -f "instance/schedule.db" ]; then
        rm instance/schedule.db
        echo "Database deleted."
    fi

    # clear chrome data
    if [ -d "chrome_data" ]; then
        rm -rf chrome_data
        mkdir chrome_data
        echo "Chrome session data cleared."
    fi

    # remove python cache
    find . -type d -name "__pycache__" -exec rm -r {} +
    
    echo "System reset successfully."
fi