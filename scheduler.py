from datetime import datetime, timedelta, date, time as dtime
import copy

def generate_schedule(tasks, settings):
    """
    Advanced Scheduler:
    1. Simulates day-by-day.
    2. Subtracts fixed events (classes) from available hours.
    3. Fills remaining time with tasks based on dynamic Urgency Scores.
    4. Tracks daily analytics for bar charts and burnout metrics.
    """

    # --- 1. PREPARE DATA ---
    
    # A. Separate Fixed Events (Classes) vs Flexible Tasks (Assignments)
    fixed_events = [t for t in tasks if t.start_time and t.end_time and not t.is_completed]
    
    flexible_tasks = [t for t in tasks if not t.is_completed and t.estimated_hours > 0 and t.task_type not in ['class', 'meeting']]
    
    # B. Ledger to track remaining work (Don't modify DB objects directly)
    task_ledger = {
        t.id: {
            'remaining': t.estimated_hours, 
            'task': t,
            'original_hours': t.estimated_hours
        } 
        for t in flexible_tasks
    }

    metrics = {
        'total_tasks': len(flexible_tasks),
        'total_hours_needed': sum(t.estimated_hours for t in flexible_tasks),
        'total_hours_scheduled': 0,
        'days_projected': 30,
        'avg_daily_hours': 0,
        'completion_rate': 100,
        'daily_trends': []
    }

    schedule = []
    expired_tasks = [] 
    
    # --- 2. SETUP SIMULATION ---
    
    if settings.simulation_date:
        current_date = settings.simulation_date.date()
    else:
        current_date = datetime.now().date()

    # Constants from Settings
    DAY_START = dtime(settings.daily_start_hour, 0)
    DAY_END = dtime(settings.daily_end_hour, 0)
    MAX_DAILY_HOURS = settings.max_daily_hours
    MIN_SESSION_HRS = settings.min_session_minutes / 60.0
    MAX_SESSION_HRS = settings.max_session_minutes / 60.0
    BREAK_HRS = settings.break_minutes / 60.0

    # Safety Horizon
    days_simulated = 0
    max_days = metrics['days_projected']
    
    # Track daily stats for graphs
    daily_stats = []

    # --- 3. DAY-BY-DAY SIMULATION LOOP ---
    
    while days_simulated < max_days and any(i['remaining'] > 0 for i in task_ledger.values()):
        
        # A. Setup Day Windows
        day_start_dt = datetime.combine(current_date, DAY_START)
        day_end_dt = datetime.combine(current_date, DAY_END)
        
        # Check Weekend Mode
        is_weekend = current_date.weekday() >= 5
        if (not settings.weekend_mode and is_weekend):
            # Record empty stats for weekend to keep chart continuity
            daily_stats.append({
                'date': current_date.isoformat(),
                'day_name': current_date.strftime("%a"),
                'hours': 0,
                'utilization': 0
            })
            current_date += timedelta(days=1)
            days_simulated += 1
            continue

        # B. Identify Free Time Slots (Subtract Fixed Events)
        # Start with one big slot: [Start, End]
        free_slots = [(day_start_dt, day_end_dt)]
        
        # Filter fixed events for TODAY
        todays_fixed = [
            e for e in fixed_events 
            if e.start_time.date() == current_date
        ]
        todays_fixed.sort(key=lambda x: x.start_time)

        # Subtract fixed events from free slots
        for ev in todays_fixed:
            new_slots = []
            for start, end in free_slots:
                # No overlap
                if ev.end_time <= start or ev.start_time >= end:
                    new_slots.append((start, end))
                    continue
                
                # Overlap: Cut the slot
                if ev.start_time > start:
                    new_slots.append((start, ev.start_time))
                if ev.end_time < end:
                    new_slots.append((ev.end_time, end))
            free_slots = new_slots

        # Filter out tiny slots (smaller than min session)
        free_slots = [
            (s, e) for s, e in free_slots 
            if (e - s).total_seconds() / 3600.0 >= MIN_SESSION_HRS
        ]

        # C. Fill Free Slots with Tasks
        daily_work_hours = 0
        
        for slot_start, slot_end in free_slots:
            if daily_work_hours >= MAX_DAILY_HOURS:
                break
            
            cursor = slot_start
            
            # While there is room in this slot
            while cursor < slot_end:
                
                # 1. Calculate Capacity
                slot_remaining = (slot_end - cursor).total_seconds() / 3600.0
                daily_remaining = MAX_DAILY_HOURS - daily_work_hours
                
                capacity = min(slot_remaining, daily_remaining)
                
                if capacity < MIN_SESSION_HRS:
                    break # Slot too small or day cap reached

                # 2. Pick Best Task (Urgency Score)
                best_task_id = None
                best_score = -1
                
                for tid, data in task_ledger.items():
                    if data['remaining'] <= 0:
                        continue
                    
                    task = data['task']
                    
                    # Skip if deadline passed
                    if task.deadline and task.deadline < cursor:
                        # Log as expired if not already
                        if tid not in [x['id'] for x in expired_tasks]:
                            expired_tasks.append({
                                'id': task.id,
                                'title': task.title,
                                'deadline': task.deadline.isoformat(),
                                'missed_hours': data['remaining']
                            })
                        continue

                    # Calculate Urgency
                    score = calculate_urgency(task, data['remaining'], cursor)
                    
                    if score > best_score:
                        best_score = score
                        best_task_id = tid
                
                if not best_task_id:
                    break # No doable tasks left
                
                # 3. Create Session
                task_data = task_ledger[best_task_id]
                
                # Duration is min of:
                # - Task remaining
                # - Max session length setting
                # - Available capacity in slot/day
                duration = min(
                    task_data['remaining'], 
                    MAX_SESSION_HRS, 
                    capacity
                )
                
                # Ensure we don't schedule tiny fragments unless it finishes the task
                if duration < MIN_SESSION_HRS and duration < task_data['remaining']:
                    break

                session_end = cursor + timedelta(hours=duration)
                
                schedule.append({
                    'title': task_data['task'].title,
                    'start': cursor.isoformat(),
                    'end': session_end.isoformat(),
                    'color': '#3B82F6', 
                    'task_id': best_task_id,
                    'type': task_data['task'].task_type,
                    'chunk_duration': duration,
                    'progress_msg': f"Remaining: {task_data['remaining'] - duration:.1f}h"
                })
                
                # 4. Update State
                task_data['remaining'] -= duration
                metrics['total_hours_scheduled'] += duration
                daily_work_hours += duration
                
                # 5. Add Break
                cursor = session_end + timedelta(minutes=settings.break_minutes)
                
                if daily_work_hours >= MAX_DAILY_HOURS:
                    break

        # Capture Daily Stats for Charts
        daily_stats.append({
            'date': current_date.isoformat(),
            'day_name': current_date.strftime("%a"), # Mon, Tue
            'hours': daily_work_hours,
            'utilization': (daily_work_hours / MAX_DAILY_HOURS * 100) if MAX_DAILY_HOURS > 0 else 0
        })

        # Move to next day
        current_date += timedelta(days=1)
        days_simulated += 1

    # --- 4. CALCULATE FINAL METRICS ---
    
    # Calculate Average Daily Load (excluding empty days if desired, but usually better to average over active work days)
    active_days = [d for d in daily_stats if d['hours'] > 0]
    
    # Metric 1: Average Load (only on days you actually work)
    if active_days:
        metrics['avg_daily_hours'] = sum(d['hours'] for d in active_days) / len(active_days)
    else:
        metrics['avg_daily_hours'] = 0

    # Metric 2: Peak Load (The busiest day)
    if daily_stats:
        metrics['peak_hours'] = max((d['hours'] for d in daily_stats), default=0)
    else:
        metrics['peak_hours'] = 0
        
    # Metric 3: Active Work Days
    metrics['active_days_count'] = len(active_days)

    # Pass raw trends
    metrics['daily_trends'] = daily_stats[:14]

    return {
        'metrics': metrics,
        'schedule': schedule,
        'unscheduled': [
            {'id': t['task'].id, 'title': t['task'].title, 'remaining': t['remaining']}
            for t in task_ledger.values() if t['remaining'] > 0.1
        ],
        'expired': expired_tasks
    }

def calculate_urgency(task, remaining_hours, current_time):
    """
    Score = (Priority Weight * Remaining Work) / Time Until Deadline
    """
    p_weight = {1: 1.0, 2: 2.5, 3: 5.0}.get(task.priority, 1.0)
    
    if not task.deadline:
        hours_until_deadline = 720 
    else:
        hours_until_deadline = (task.deadline - current_time).total_seconds() / 3600.0
    
    hours_until_deadline = max(hours_until_deadline, 0.1)
    
    score = (p_weight * remaining_hours * 10) / hours_until_deadline
    
    return score