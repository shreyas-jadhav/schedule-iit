from datetime import datetime, timedelta

def generate_schedule(tasks, settings):
    """
    Strict Scheduler: Never schedules work past a deadline.
    """
    
    # 1. Snapshot of Demand
    # Only take tasks that are NOT completed
    pending_tasks = [t for t in tasks if not t.is_completed and t.estimated_hours > 0]
    
    # Sort: Earliest Deadline First (EDF)
    pending_tasks.sort(key=lambda x: (x.deadline, -x.priority))

    # Track remaining hours for each task
    task_ledger = {
        t.id: {'remaining': t.estimated_hours} 
        for t in pending_tasks
    }

    metrics = {
        'total_tasks': len(pending_tasks),
        'total_hours_needed': sum(t.estimated_hours for t in pending_tasks),
        'total_hours_scheduled': 0,
        'days_projected': 30
    }
    
    schedule = []
    expired_tasks = [] # Tasks that couldn't be finished on time
    
    # 2. Setup Simulation Time
    if settings.simulation_date:
        current_time = settings.simulation_date
    else:
        current_time = datetime.now()
        
    # Align to next 30 min block
    if current_time.minute >= 30:
        current_time = current_time.replace(minute=0) + timedelta(hours=1)
    else:
        current_time = current_time.replace(minute=30)
    current_time = current_time.replace(second=0, microsecond=0)

    max_horizon = current_time + timedelta(days=metrics['days_projected'])
    
    work_start = settings.daily_start_hour
    work_end = settings.daily_end_hour
    allow_weekends = settings.weekend_mode
    step_delta = timedelta(minutes=30)
    chunk_hours = 0.5
    
    # 3. Simulation Loop
    while pending_tasks and current_time < max_horizon:
        
        end_time = current_time + step_delta

        # --- A. Prune Expired Tasks ---
        # Before we try to work, check if any tasks have ALREADY expired
        # or if working now would push them past deadline.
        active_tasks = []
        for t in pending_tasks:
            # If the slot end time is AFTER the deadline, we can't use this slot for this task.
            if end_time > t.deadline:
                # Task has expired (or at least this specific chunk is impossible)
                # We mark it as expired and remove from pending
                if t.id not in [x['id'] for x in expired_tasks]:
                    expired_tasks.append({
                        'id': t.id,
                        'title': t.title,
                        'missed_hours': task_ledger[t.id]['remaining'],
                        'deadline': t.deadline.isoformat()
                    })
            else:
                active_tasks.append(t)
        
        pending_tasks = active_tasks # Update the main list
        
        # If everything expired, break early or continue to find next valid slots
        if not pending_tasks:
            break

        # --- B. Check Working Hours Constraints ---
        is_weekend = current_time.weekday() >= 5
        hour = current_time.hour

        if (not allow_weekends and is_weekend) or not (work_start <= hour < work_end):
            current_time += step_delta
            continue

        # --- C. Select Best Task ---
        selected_task = None
        for task in pending_tasks:
            if task_ledger[task.id]['remaining'] > 0:
                selected_task = task
                break
        
        if selected_task:
            ledger_entry = task_ledger[selected_task.id]
            
            schedule.append({
                'title': selected_task.title,
                'start': current_time.isoformat(),
                'end': end_time.isoformat(),
                'color': '#3B82F6', # Always blue, because we don't allow red (overdue) anymore
                'task_id': selected_task.id,
                'type': selected_task.task_type,
                'chunk_duration': chunk_hours,
                'progress_msg': f"Remaining: {ledger_entry['remaining'] - chunk_hours:.1f}h"
            })
            
            ledger_entry['remaining'] -= chunk_hours
            metrics['total_hours_scheduled'] += chunk_hours
            
            if ledger_entry['remaining'] <= 1e-5:
                pending_tasks.remove(selected_task)
        
        current_time += step_delta

    return {
        'metrics': metrics,
        'schedule': merge_slots(schedule),
        'unscheduled': [t.to_dict() for t in pending_tasks], # Tasks that didn't fit in 30 days
        'expired': expired_tasks # Tasks where deadline passed before we could finish
    }

def merge_slots(raw_schedule):
    if not raw_schedule: return []
    merged = []
    current = raw_schedule[0]
    current['total_block_duration'] = current['chunk_duration']
    
    for next_block in raw_schedule[1:]:
        if (current['task_id'] == next_block['task_id'] and 
            current['end'] == next_block['start']):
            
            current['end'] = next_block['end']
            current['total_block_duration'] += next_block['chunk_duration']
            current['progress_msg'] = next_block['progress_msg'] 
        else:
            merged.append(current)
            current = next_block
            current['total_block_duration'] = current['chunk_duration']
            
    merged.append(current)
    return merged