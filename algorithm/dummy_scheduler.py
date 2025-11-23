from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time as dtime, timedelta
from typing import List, Dict, Optional, Tuple

from db import SessionLocal, Task  # your db.py with parent_task_id


# ---------- Preferences ----------

@dataclass
class SchedulerPrefs:
    day_start: dtime = dtime(9, 0)            # start of study window
    day_end: dtime = dtime(23, 0)             # end of study window
    max_daily_hours: float = 6.0              # max total focused hours per day
    min_session_hours: float = 0.5            # minimum session length in hours
    max_session_hours: float = 2.0            # maximum continuous session length
    break_minutes_between_sessions: int = 10  # break between sessions in minutes


PRIORITY_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0}
FIXED_TYPES = {"class", "exam", "meeting"}  # these occupy fixed slots (from ASC / Moodle etc.)


# ---------- Internal views ----------

@dataclass
class ParentTaskView:
    task: Task
    remaining_hours: float
    effective_priority: str  # low / medium / high


@dataclass
class PlannedSessionView:
    parent_task_id: int
    start: datetime
    end: datetime
    hours: float


# ---------- Priority / urgency ----------

def infer_priority_if_missing(task: Task) -> str:
    """
    If the user didn't set a priority (or set 'auto'), infer from deadline.
    Earlier deadline → higher priority.

    This matches your spec:
      - if user skips priority, nearest deadline gets higher priority.
    """
    if task.priority in ("low", "medium", "high"):
        return task.priority
    if task.priority == "auto":
        # fall through to deadline-based inference
        pass

    if not task.end_time:
        return "medium"

    now = datetime.now()
    hours_to_deadline = (task.end_time - now).total_seconds() / 3600.0

    if hours_to_deadline <= 24:
        return "high"
    elif hours_to_deadline <= 72:
        return "medium"
    else:
        return "low"


def urgency_score(pt: ParentTaskView, now: datetime) -> float:
    """
    Higher score = more urgent.
    Combines remaining_hours, time_left, and priority.

    score ~ (priority * remaining_hours) / time_left

    Exam prep tasks get a boost so they appear regularly (your “exam should show up everyday” idea).
    """
    if pt.remaining_hours <= 0:
        return 0.0

    if not pt.task.end_time:
        base = PRIORITY_WEIGHT[pt.effective_priority]
        score = base / max(pt.remaining_hours, 0.1)
    else:
        time_left_hours = max(
            (pt.task.end_time - now).total_seconds() / 3600.0,
            1.0 / 60.0,
        )
        prio = PRIORITY_WEIGHT[pt.effective_priority]
        score = (prio * pt.remaining_hours) / time_left_hours

    # small bias for exam prep so it gets daily attention
    if pt.task.task_type == "exam_prep":
        score *= 1.5

    return score


# ---------- Load tasks & remaining hours ----------

def load_parent_tasks_with_remaining(session) -> List[ParentTaskView]:
    """
    Parent tasks:
      - parent_task_id IS NULL
      - status in (pending, in_progress)
      - task_type NOT in fixed types (we never auto-schedule exams/classes themselves)

    Remaining hours = estimated_hours - sum(hours of child sessions with status in ('planned','done')).
    """
    parents: List[Task] = (
        session.query(Task)
        .filter(
            Task.parent_task_id.is_(None),
            Task.status.in_(["pending", "in_progress"]),
            Task.task_type.notin_(list(FIXED_TYPES)),
        )
        .all()
    )

    children: List[Task] = (
        session.query(Task)
        .filter(Task.parent_task_id.isnot(None))
        .all()
    )

    by_parent: Dict[int, List[Task]] = {}
    for c in children:
        by_parent.setdefault(c.parent_task_id, []).append(c)

    result: List[ParentTaskView] = []
    for p in parents:
        allocated = 0.0
        for c in by_parent.get(p.task_id, []):
            # count only planned or done sessions as "used"
            if c.status in ("planned", "done") and c.estimated_hours:
                allocated += c.estimated_hours
        total = p.estimated_hours or 0.0
        remaining = max(total - allocated, 0.0)
        prio = infer_priority_if_missing(p)
        result.append(ParentTaskView(task=p, remaining_hours=remaining, effective_priority=prio))

    return result


def load_fixed_events_for_day(session, day: date) -> List[Task]:
    """
    Fixed events: classes/exams/meetings that block time.
    These will come from ASC / Moodle once scraping is added.
    """
    start_dt = datetime.combine(day, dtime.min)
    end_dt = datetime.combine(day, dtime.max)

    fixed = (
        session.query(Task)
        .filter(
            Task.task_type.in_(list(FIXED_TYPES)),
            Task.start_time >= start_dt,
            Task.start_time <= end_dt,
        )
        .all()
    )
    return fixed


# ---------- Time window helpers ----------

def get_work_window(day: date, prefs: SchedulerPrefs) -> Tuple[datetime, datetime]:
    return (
        datetime.combine(day, prefs.day_start),
        datetime.combine(day, prefs.day_end),
    )


def subtract_fixed_from_window(
    work_start: datetime,
    work_end: datetime,
    fixed_events: List[Task],
) -> List[Tuple[datetime, datetime]]:
    """
    Starting from [work_start, work_end], subtract fixed events to get free intervals.
    """
    intervals: List[Tuple[datetime, datetime]] = [(work_start, work_end)]

    for ev in fixed_events:
        if not ev.start_time or not ev.end_time:
            continue

        new_intervals: List[Tuple[datetime, datetime]] = []
        for (s, e) in intervals:
            # no overlap
            if ev.end_time <= s or ev.start_time >= e:
                new_intervals.append((s, e))
                continue

            # left part before event
            if ev.start_time > s:
                new_intervals.append((s, ev.start_time))

            # right part after event
            if ev.end_time < e:
                new_intervals.append((ev.end_time, e))

        intervals = new_intervals

    return [(s, e) for (s, e) in intervals if e > s]


# ---------- Exam-prep daily target helper ----------

def compute_exam_daily_targets(
    parents: List[ParentTaskView],
    day: date,
    prefs: SchedulerPrefs,
) -> Dict[int, float]:
    """
    For each exam_prep task, compute how many hours we *aim* to study TODAY
    so that work is spread across days until the exam.

    Idea:
      remaining_hours / days_left  (clamped between min_session_hours and a sane upper bound)
    """
    targets: Dict[int, float] = {}

    for p in parents:
        if p.task.task_type != "exam_prep":
            continue
        if not p.task.end_time:
            # no deadline → treat like normal, but we can give a small daily cap
            days_left = 7  # arbitrary horizon
        else:
            exam_date = p.task.end_time.date()
            if day > exam_date:
                days_left = 1
            else:
                # include today in count
                days_left = (exam_date - day).days + 1
                if days_left <= 0:
                    days_left = 1

        if p.remaining_hours <= 0:
            targets[p.task.task_id] = 0.0
            continue

        raw_target = p.remaining_hours / days_left
        # Clamp the daily target:
        # - not less than min_session_hours
        # - not more than, say, 2 * max_session_hours
        lower = prefs.min_session_hours
        upper = max(prefs.max_session_hours * 2.0, prefs.min_session_hours)
        target_today = max(lower, min(upper, raw_target, p.remaining_hours))

        targets[p.task.task_id] = target_today

    return targets


# ---------- Core daily scheduling ----------

def generate_daily_plan(
    day: date,
    prefs: Optional[SchedulerPrefs] = None,
) -> List[PlannedSessionView]:
    """
    - Load parent tasks & fixed events from DB
    - Find free intervals in the day
    - Fill them with study sessions based on urgency score
    - Spread exam_prep across days via per-day cap
    - RETURN list of PlannedSessionView (not yet saved)
    """
    if prefs is None:
        prefs = SchedulerPrefs()

    session = SessionLocal()
    try:
        # Use the day's start as reference time for urgency,
        # so planning for future days differs from "right now".
        ref_now = datetime.combine(day, prefs.day_start)

        parents = load_parent_tasks_with_remaining(session)
        parents = [p for p in parents if p.remaining_hours > 0]

        # Compute per-day targets for exam prep tasks
        exam_daily_remaining = compute_exam_daily_targets(parents, day, prefs)

        fixed_events = load_fixed_events_for_day(session, day)

        work_start, work_end = get_work_window(day, prefs)
        free_intervals = subtract_fixed_from_window(work_start, work_end, fixed_events)

        planned: List[PlannedSessionView] = []
        total_planned_hours = 0.0

        for (iv_start, iv_end) in free_intervals:
            if total_planned_hours >= prefs.max_daily_hours:
                break

            cursor = iv_start
            while cursor < iv_end and total_planned_hours < prefs.max_daily_hours:
                # remaining capacity for day
                remaining_daily = prefs.max_daily_hours - total_planned_hours
                if remaining_daily <= 0:
                    break

                # how much time left in this interval
                interval_left = (iv_end - cursor).total_seconds() / 3600.0
                if interval_left <= 0:
                    break

                # Filter parents with remaining hours,
                # and for exam_prep, ensure we still have today's daily target left.
                available_parents: List[ParentTaskView] = []
                for p in parents:
                    if p.remaining_hours <= 0:
                        continue
                    if p.task.task_type == "exam_prep":
                        if exam_daily_remaining.get(p.task.task_id, 0.0) < prefs.min_session_hours:
                            # already hit today's target for this exam
                            continue
                    available_parents.append(p)

                if not available_parents:
                    # nothing left to schedule meaningfully
                    return planned

                # pick most urgent task
                available_parents.sort(
                    key=lambda p: urgency_score(p, ref_now),
                    reverse=True,
                )
                current = available_parents[0]

                # basic session length
                ses_len = min(
                    prefs.max_session_hours,
                    current.remaining_hours,
                    remaining_daily,
                    interval_left,
                )

                # for exam prep, also respect today's per-exam cap
                if current.task.task_type == "exam_prep":
                    per_exam_left = exam_daily_remaining.get(current.task.task_id, 0.0)
                    ses_len = min(ses_len, per_exam_left)

                if ses_len < prefs.min_session_hours:
                    # can't fit a meaningful session here
                    break

                ses_end = cursor + timedelta(hours=ses_len)
                planned.append(
                    PlannedSessionView(
                        parent_task_id=current.task.task_id,
                        start=cursor,
                        end=ses_end,
                        hours=ses_len,
                    )
                )

                # Update remaining hours
                current.remaining_hours -= ses_len
                total_planned_hours += ses_len

                if current.task.task_type == "exam_prep":
                    exam_daily_remaining[current.task.task_id] = max(
                        0.0,
                        exam_daily_remaining.get(current.task.task_id, 0.0) - ses_len,
                    )

                # move cursor after break
                cursor = ses_end + timedelta(minutes=prefs.break_minutes_between_sessions)

        return planned

    finally:
        session.close()


# ---------- Persist plan into DB ----------

def clear_today_planned_sessions(day: date):
    """
    Delete today's planner-generated, not-done sessions so we can replan cleanly.

    This is your "replanning when things slip":
      - what was 'planned' but not done is removed and rescheduled based
        on new remaining_hours next time.
    """
    session = SessionLocal()
    try:
        start = datetime.combine(day, dtime.min)
        end = datetime.combine(day, dtime.max)

        session.query(Task).filter(
            Task.task_type == "study_session",
            Task.source == "planner",
            Task.status == "planned",
            Task.start_time >= start,
            Task.start_time <= end,
        ).delete(synchronize_session=False)

        session.commit()
    finally:
        session.close()


def save_plan_to_db(sessions: List[PlannedSessionView]) -> None:
    """
    Save generated sessions as rows in tasks table.
    """
    if not sessions:
        return

    session = SessionLocal()
    try:
        for ps in sessions:
            parent = session.get(Task, ps.parent_task_id)
            if not parent:
                continue

            t = Task(
                parent_task_id=parent.task_id,
                course_code=parent.course_code,
                course_name=parent.course_name,
                task_name=f"{parent.task_name} – study",
                start_time=ps.start,
                end_time=ps.end,
                estimated_hours=ps.hours,
                task_type="study_session",
                priority=parent.priority,
                status="planned",
                source="planner",
            )
            session.add(t)

        session.commit()
    finally:
        session.close()


def build_and_save_daily_plan(
    day: Optional[date] = None,
    prefs: Optional[SchedulerPrefs] = None,
) -> List[PlannedSessionView]:
    """
    Public entrypoint:
    - clear existing planned sessions for that day
    - generate new plan
    - save to DB
    - return list of sessions (for UI)
    """
    if day is None:
        day = date.today()

    clear_today_planned_sessions(day)
    sessions = generate_daily_plan(day, prefs)
    save_plan_to_db(sessions)
    return sessions


if __name__ == "__main__":
    # Manual quick test (calls into your DB!)
    today = date.today()
    prefs = SchedulerPrefs()
    plan = build_and_save_daily_plan(today, prefs)
    print(f"Planned {len(plan)} sessions for {today}")
    for s in plan:
        print(s)
