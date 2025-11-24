# 📅 Schedule-IIT | Intelligent Academic Planner

**Schedule-IIT** is a smart personal assistant designed specifically for students to automate the chaos of academic life. Unlike standard calendars, it doesn't just store dates, it **mathematically generates** an optimized study plan based on deadlines, priorities, and your personal burnout limits.

It combines a **Flask** backend with a dynamic **Tailwind CSS** frontend and uses **Selenium** to automatically sync assignments from Moodle and class timetables from ASC.

---

## ⚡ Quick Start (Bash Scripts)

We have provided convenient Bash scripts to automate setup, execution, and maintenance.

1.  **First-Time Setup**
    Installs the virtual environment, dependencies, and creates necessary data folders (`instance/`, `chrome_data/`).
    ```bash
    ./setup.sh
    ```

2.  **Run the Application**
    Activates the environment and launches the Flask server.
    ```bash
    ./run.sh
    ```

3.  **Hard Reset (Maintenance)**
    ⚠️ *Warning: Deletes your database and login sessions.* Use this if the scraper gets stuck or you want a fresh start.
    ```bash
    ./reset.sh
    ```

---

## 📦 Manual Installation

If you prefer not to use the scripts, follow these steps:



  **Install Dependencies**

    It is recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

  **Run the Application**

    ```bash
    python app.py
    ```

  **Access the Dashboard**

    Open your browser and navigate to:
    `http://127.0.0.1:5000`



## 📂 Codebase 


### 1. The Controller & API
* **`app.py`**
    * The Flask Server Entry Point.
    * Initializes the application and SQLite database. It defines REST API endpoints (e.g., `/api/tasks`, `/api/sync_moodle`) that the frontend calls to fetch data or trigger actions. It acts as the bridge between the UI, the Database, and the Scheduler.

### 2. The Data Layer
* **`models.py`**
    * Database Schema (SQLAlchemy).
    * Defines the structure of the `schedule.db` database.
        * `class Task`: Stores title, deadline, estimated hours, priority, and completion status.
        * `class Settings`: Stores user preferences (Daily Start/End hours, ASC credentials, simulation dates).

### 3. The Logic Engine
* **`scheduler.py`**
    * *The  Algorithm.
    * Contains the `generate_schedule()` function. This script runs a greedy heuristic algorithm that:
        1.  Simulates time day-by-day.
        2.  Calculates an **Urgency Score** for every task.
        3.  Fits tasks into free time slots (Bin Packing) while respecting class times and max-work-hour constraints.

### 4. Automation & Integration
* **`scraper.py`**
    * Selenium Automation.
    * Handles all external interactions.
        * `run_moodle_sync()`: Logs into Moodle, parses the Dashboard HTML, and extracts assignment due dates.
        * `run_asc_sync()`: Navigates the ASC portal to scrape course timetables.
        * **Persistent Profile:** Uses a local `chrome_data/` folder to save cookies, so you don't have to log in manually every time.

### 5. The User Interface
* **`templates/index.html`**
    * Single Page Frontend.
    * A dashboard built with **Tailwind CSS**. It uses vanilla JavaScript to fetch JSON from `app.py` and render the interactive Timeline, Task Backlog, and Configuration forms without page reloads.

### 6. Utilities
* **`setup.sh`, `run.sh`, `reset.sh`**
    * Bash Automation Scripts.
    * **Details:** Helper scripts to simplify the developer workflow (installing dependencies, running the server, and cleaning the database).
---

## 📖 Usage Guide

### 1. Configuration
Go to the **Configuration** tab in the dashboard:
* **Daily Limits:** Set your start/end time (e.g., 9:00 to 17:00) and max focus hours (e.g., 6 hours/day).
* **Moodle/ASC:** Enter the Moodle URL and your ASC credentials. The first time you sync, a browser window will open. The system saves your session cookies in `chrome_data/` for future auto-syncs.

### 2. Setting Up Classes
1.  Go to the **Configuration** tab.
2.  Under **Class Schedule**, add your weekly classes (e.g., "Math 101, Mon, 10:00-11:00").
3.  Click **Populate Semester** to generate these fixed events until the end of the term.

### 3. Managing Tasks
* **Sync Buttons:** Click the "Moodle" button on the sidebar to fetch assignments.
* **Manual Entry:** Add personal tasks, exams, or projects via the sidebar form.
* **Timeline:** Switch to the "Timeline View" to see your generated schedule.
* **Completion:** Click the Checkmark icon on a task block to mark that specific session as done.

--

## 🛠️ Tech Stack

* **Backend:** Python, Flask, SQLAlchemy (SQLite)
* **Frontend:** HTML5, Tailwind CSS (via CDN), Lucide Icons
* **Automation:** Selenium WebDriver (Chrome)
* **Algorithm:** Custom greedy heuristic scheduling

---

## 👥 Team

* **25M2138** - Shreyash Jadhav
* **25M2127** - Ananya Kamalapur
* **25M2109** - Shalini Madderla