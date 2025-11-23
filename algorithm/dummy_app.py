# app.py
from datetime import datetime, date, timedelta, time as dtime

from flask import Flask, render_template, request, redirect, url_for, flash
from db import init_db, SessionLocal, Task
from dummy_scheduler import build_and_save_daily_plan, SchedulerPrefs

app = Flask(__name__)
app.secret_key = "change_this_secret"
init_db()

# In-memory user prefs for now (single user)
USER_PREFS = SchedulerPrefs()


# ---------- Helpers ----------

def compute_progress_for_parent(session, parent: Task):
    """
    For a parent task:
      total = parent.estimated_hours
      done = sum(child.hours where status='done')
      planned = sum(child.hours where status='planned')
      remaining = max(total - done, 0)
    """
    children = (
        session.query(Task)
        .filter(Task.parent_task_id == parent.task_id,
                Task.task_type == "study_session")
        .all()
    )

    total = parent.estimated_hours or 0.0
    done = 0.0
    planned = 0.0
    for c in children:
        h = c.estimated_hours or 0.0
        if c.status == "done":
            done += h
        elif c.status == "planned":
            planned += h

    remaining = max(total - done, 0.0)
    completion_pct = 0.0
    if total > 0:
        completion_pct = round(100.0 * done / total, 1)

    return {
        "total": round(total, 2),
        "done": round(done, 2),
        "planned": round(planned, 2),
        "remaining": round(remaining, 2),
        "completion_pct": completion_pct,
    }


def urgency_color(score: float) -> str:
    """
    Map urgency score to color label for UI.
      green / yellow / red
    """
    if score < 0.5:
        return "green"
    elif score < 2.0:
        return "yellow"
    else:
        return "red"


# ---------- Routes ----------

@app.route("/")
def index():
    """
    Home:
      - List parent tasks with basic info + progress
      - Show 'Generate today's plan' button
      - Show a 'What should I do next?' suggested task
    """
    session = SessionLocal()
    parents = (
        session.query(Task)
        .filter(Task.parent_task_id.is_(None))
        .order_by(Task.end_time)
        .all()
    )

    # attach progress info
    parent_data = []
    from dummy_scheduler import load_parent_tasks_with_remaining, urgency_score  # avoid circular imports

    pt_views = load_parent_tasks_with_remaining(session)
    urgency_map = {pt.task.task_id: urgency_score(pt, datetime.now()) for pt in pt_views}

    for p in parents:
        prog = compute_progress_for_parent(session, p)
        score = urgency_map.get(p.task_id, 0.0)
        parent_data.append(
            {
                "task": p,
                "progress": prog,
                "urgency_score": round(score, 2),
                "urgency_color": urgency_color(score),
            }
        )

    # pick top "what should I do next?" (highest urgency)
    next_task = None
    if parent_data:
        sorted_by_urg = sorted(parent_data, key=lambda x: x["urgency_score"], reverse=True)
        if sorted_by_urg[0]["urgency_score"] > 0:
            next_task = sorted_by_urg[0]

    session.close()
    return render_template("index.html", parents=parent_data, next_task=next_task, prefs=USER_PREFS)


@app.route("/add-task", methods=["GET", "POST"])
def add_task():
    """
    Add a new parent task (assignment / exam prep / project / one-time / extracurricular / meeting).
    Scraping (Moodle/ASC) will also create similar tasks but from another module.
    """
    if request.method == "POST":
        task_name = request.form.get("task_name", "").strip()
        course_code = request.form.get("course_code") or None
        course_name = request.form.get("course_name") or None
        task_type = request.form.get("task_type") or "assignment"
        priority = request.form.get("priority") or "auto"  # allow 'auto'
        est_hours_str = request.form.get("estimated_hours", "0")
        deadline_str = request.form.get("deadline")  # datetime-local

        if not task_name:
            flash("Task name is required.", "error")
            return redirect(url_for("add_task"))

        try:
            estimated_hours = float(est_hours_str)
        except ValueError:
            estimated_hours = 0.0

        deadline = None
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
            except ValueError:
                deadline = None

        session = SessionLocal()
        t = Task(
            course_code=course_code,
            course_name=course_name,
            task_name=task_name,
            start_time=None,
            end_time=deadline,
            estimated_hours=estimated_hours,
            task_type=task_type,
            priority=priority,
            status="pending",
            source="manual",
            parent_task_id=None,
        )
        session.add(t)
        session.commit()
        session.close()
        flash("Task added.", "success")
        return redirect(url_for("index"))

    return render_template("add_task.html")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """
    Simple UI for:
      - workday start/end
      - max daily hours
      - break minutes
      - min/max session length
    """
    global USER_PREFS

    if request.method == "POST":
        try:
            start_hour = int(request.form.get("day_start_hour", "9"))
            end_hour = int(request.form.get("day_end_hour", "23"))
            max_daily = float(request.form.get("max_daily_hours", "6"))
            break_min = int(request.form.get("break_minutes", "10"))
            min_sess = float(request.form.get("min_session_hours", "0.5"))
            max_sess = float(request.form.get("max_session_hours", "2"))
        except ValueError:
            flash("Invalid numeric input in settings.", "error")
            return redirect(url_for("settings"))

        USER_PREFS = SchedulerPrefs(
            day_start=dtime(start_hour, 0),
            day_end=dtime(end_hour, 0),
            max_daily_hours=max_daily,
            min_session_hours=min_sess,
            max_session_hours=max_sess,
            break_minutes_between_sessions=break_min,
        )
        flash("Settings updated.", "success")
        return redirect(url_for("index"))

    return render_template("settings.html", prefs=USER_PREFS)


@app.route("/sync-moodle", methods=["POST"])
def sync_moodle():
    """
    Placeholder: in future, your friend will implement scraping + insertion here.
    Right now, just flash a message.
    """
    flash("Moodle sync is not implemented yet (placeholder).", "info")
    return redirect(url_for("index"))


@app.route("/plan/today", methods=["POST"])
def plan_today():
    """
    Generate today's study sessions using current USER_PREFS.
    """
    sessions = build_and_save_daily_plan(date.today(), USER_PREFS)
    flash(f"Generated {len(sessions)} sessions for today.", "info")
    return redirect(url_for("today_view"))


@app.route("/today")
def today_view():
    """
    Daily check-in view:
      - shows today's study sessions
      - user can mark them done/skipped
    """
    session = SessionLocal()
    start = datetime.combine(date.today(), datetime.min.time())
    end = datetime.combine(date.today(), datetime.max.time())

    sessions_q = (
        session.query(Task)
        .filter(
            Task.task_type == "study_session",
            Task.start_time >= start,
            Task.start_time <= end,
        )
        .order_by(Task.start_time)
    )

    sessions = list(sessions_q)
    session.close()
    return render_template("today.html", sessions=sessions)


@app.route("/session/<int:task_id>/done", methods=["POST"])
def mark_session_done(task_id):
    """
    Mark a study session as done.
    This contributes to the parent task's 'done' hours.
    """
    session = SessionLocal()
    t = session.get(Task, task_id)
    if not t:
        session.close()
        flash("Session not found.", "error")
        return redirect(url_for("today_view"))

    t.status = "done"
    session.commit()
    session.close()
    flash("Session marked as done.", "success")
    return redirect(url_for("today_view"))


@app.route("/session/<int:task_id>/skip", methods=["POST"])
def mark_session_skipped(task_id):
    """
    Mark a study session as skipped.
    Skipped hours are *not* counted as used, so future planning re-allocates them.
    """
    session = SessionLocal()
    t = session.get(Task, task_id)
    if not t:
        session.close()
        flash("Session not found.", "error")
        return redirect(url_for("today_view"))

    t.status = "skipped"
    session.commit()
    session.close()
    flash("Session marked as skipped.", "info")
    return redirect(url_for("today_view"))


@app.route("/courses")
def courses_view():
    """
    Task list by course: group parent tasks by course_code.
    """
    session = SessionLocal()
    parents = (
        session.query(Task)
        .filter(Task.parent_task_id.is_(None))
        .order_by(Task.course_code, Task.end_time)
        .all()
    )

    grouped = {}
    for p in parents:
        key = p.course_code or "No course"
        grouped.setdefault(key, []).append(p)

    # attach progress
    data = {}
    for course, tasks in grouped.items():
        items = []
        for t in tasks:
            prog = compute_progress_for_parent(session, t)
            items.append({"task": t, "progress": prog})
        data[course] = items

    session.close()
    return render_template("courses.html", courses=data)


@app.route("/deadlines")
def deadlines_view():
    """
    Deadline 'heatmap': show number of tasks due per date.
    """
    session = SessionLocal()
    parents = (
        session.query(Task)
        .filter(Task.parent_task_id.is_(None), Task.end_time.isnot(None))
        .all()
    )

    counts = {}
    for p in parents:
        day = p.end_time.date()
        counts[day] = counts.get(day, 0) + 1

    items = sorted(counts.items(), key=lambda x: x[0])  # list of (date, count)
    session.close()
    return render_template("deadlines.html", items=items)


@app.route("/progress")
def progress_view():
    """
    Progress per parent task.
    """
    session = SessionLocal()
    parents = (
        session.query(Task)
        .filter(Task.parent_task_id.is_(None))
        .order_by(Task.end_time)
        .all()
    )

    rows = []
    for p in parents:
        prog = compute_progress_for_parent(session, p)
        rows.append({"task": p, "progress": prog})
    session.close()
    return render_template("progress.html", rows=rows)


@app.route("/stats")
def stats_view():
    """
    Simple stats + slack detector for last 7 days:
      - total planned hours
      - total done hours
      - by-course hours
      - warn if consistently under 60% completion
    """
    session = SessionLocal()
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)

    sessions_q = session.query(Task).filter(
        Task.task_type == "study_session",
        Task.start_time >= seven_days_ago,
        Task.start_time <= now,
    )

    total_planned = 0.0
    total_done = 0.0
    by_course = {}

    for s in sessions_q:
        h = s.estimated_hours or 0.0
        total_planned += h
        if s.status == "done":
            total_done += h

        course = s.course_code or "No course"
        if course not in by_course:
            by_course[course] = {"planned": 0.0, "done": 0.0}
        by_course[course]["planned"] += h
        if s.status == "done":
            by_course[course]["done"] += h

    completion_rate = 0.0
    if total_planned > 0:
        completion_rate = round(100.0 * total_done / total_planned, 1)

    # Slack detector
    slack_warning = completion_rate < 60.0 and total_planned >= 3.0

    # convert to nicer list for template
    by_course_list = []
    for course, v in by_course.items():
        rate = 0.0
        if v["planned"] > 0:
            rate = round(100.0 * v["done"] / v["planned"], 1)
        by_course_list.append(
            {
                "course": course,
                "planned": round(v["planned"], 2),
                "done": round(v["done"], 2),
                "completion_rate": rate,
            }
        )

    session.close()
    return render_template(
        "stats.html",
        total_planned=round(total_planned, 2),
        total_done=round(total_done, 2),
        completion_rate=completion_rate,
        slack_warning=slack_warning,
        by_course=by_course_list,
    )

@app.route("/task/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):
    """Edit an existing parent task (name, course, type, hours, deadline, priority)."""
    session = SessionLocal()
    t = session.get(Task, task_id)

    if not t:
        session.close()
        flash("Task not found.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        task_name = request.form.get("task_name", "").strip()
        course_code = request.form.get("course_code") or None
        course_name = request.form.get("course_name") or None
        task_type = request.form.get("task_type") or "assignment"
        priority = request.form.get("priority") or t.priority
        est_hours_str = request.form.get("estimated_hours", "0")
        deadline_str = request.form.get("deadline")  # datetime-local

        if not task_name:
            session.close()
            flash("Task name is required.", "error")
            return redirect(url_for("edit_task", task_id=task_id))

        try:
            estimated_hours = float(est_hours_str)
        except ValueError:
            estimated_hours = t.estimated_hours or 0.0

        deadline = None
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
            except ValueError:
                deadline = t.end_time  # keep old deadline if parsing fails
        else:
            deadline = None

        # update fields
        t.task_name = task_name
        t.course_code = course_code
        t.course_name = course_name
        t.task_type = task_type
        t.priority = priority
        t.estimated_hours = estimated_hours
        t.end_time = deadline

        session.commit()
        session.close()
        flash("Task updated.", "success")
        return redirect(url_for("index"))

    # GET: render form with existing values
    # keep object alive after closing session (detached object)
    # so copy needed fields now if you want, or just close after render
    deadline_value = ""
    if t.end_time:
        deadline_value = t.end_time.strftime("%Y-%m-%dT%H:%M")

    session.close()
    return render_template("edit_task.html", task=t, deadline_value=deadline_value)



if __name__ == "__main__":
    app.run(debug=True)
