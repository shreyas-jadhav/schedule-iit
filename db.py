import sqlite3

def get_db():
    return sqlite3.connect("tasks.db")

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT,
    course_name TEXT,
    task_name TEXT NOT NULL,
    start_time DATETIME,
    end_time DATETIME,
    estimated_hours REAL,
    task_type TEXT NOT NULL CHECK (task_type IN ('assignment','quiz','exam','class','study_session','misc')),
    priority TEXT NOT NULL CHECK (priority IN ('low','medium','high')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','planned','done','skipped')),
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('moodle','asc','manual','planner')),
    parent_task_id INTEGER,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()
    
def insert_task(course_code, course_name, task_name, task_type, start_time, end_time):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO tasks (course_code, course_name, task_name, task_type, start_time, end_time, source)
    VALUES (?, ?, ?, ?, ?, ?, 'moodle');
    """, (course_code, course_name, task_name, task_type, start_time, end_time))

    conn.commit()
    conn.close()


def insert_task(
    course_code=None,
    course_name=None,
    task_name=None,
    task_type=None,
    start_time=None,
    end_time=None,
    estimated_hours=None,
    priority="medium",
    status="pending",
    source="moodle",
    parent_task_id=None
):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO tasks (
            course_code,
            course_name,
            task_name,
            task_type,
            start_time,
            end_time,
            estimated_hours,
            priority,
            status,
            source,
            parent_task_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        course_code,
        course_name,
        task_name,
        task_type,
        start_time,
        end_time,
        estimated_hours,
        priority,
        status,
        source,
        parent_task_id
    ))

    conn.commit()
    conn.close()

def clear_all_tasks():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks")
    cur.execute("DELETE FROM sqlite_sequence WHERE name='tasks'")
    conn.commit()
    conn.close()