from datetime import datetime, timedelta, date, time as dtime
import copy

def generate_schedule(tasks, settings):
    
    fixed_events = [t for t in tasks if t.start_time and t.end_time and not t.is_completed]
    
    flexible_tasks = [t for t in tasks if not t.is_completed and t.estimated_hours > 0 and t.task_type not in ['class', 'meeting']]
    
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
    
    # for simulation
    
    if settings.simulation_date:
        current_date = settings.simulation_date.date()
    else:
        current_date = datetime.now().date()

    # from settings in db
    DAY_START = dtime(settings.daily_start_hour, 0)
    DAY_END = dtime(settings.daily_end_hour, 0)
    MAX_DAILY_HOURS = settings.max_daily_hours
    MIN_SESSION_HRS = settings.min_session_minutes / 60.0
    MAX_SESSION_HRS = settings.max_session_minutes / 60.0
    BREAK_HRS = settings.break_minutes / 60.0

    days_simulated = 0
    max_days = metrics['days_projected']
    
    daily_stats = []

    # day by day 
    while days_simulated < max_days and any(i['remaining'] > 0 for i in task_ledger.values()):
        
        # user window
        day_start_dt = datetime.combine(current_date, DAY_START)
        day_end_dt = datetime.combine(current_date, DAY_END)
        
        # check weekend
        is_weekend = current_date.weekday() >= 5
        if (not settings.weekend_mode and is_weekend):

            daily_stats.append({
                'date': current_date.isoformat(),
                'day_name': current_date.strftime("%a"),
                'hours': 0,
                'utilization': 0
            })
            current_date += timedelta(days=1)
            days_simulated += 1
            continue


        free_slots = [(day_start_dt, day_end_dt)]
        

        todays_fixed = [
            e for e in fixed_events 
            if e.start_time.date() == current_date
        ]
        todays_fixed.sort(key=lambda x: x.start_time)


        for ev in todays_fixed:
            new_slots = []
            for start, end in free_slots:
                # no overlap
                if ev.end_time <= start or ev.start_time >= end:
                    new_slots.append((start, end))
                    continue
                
                # cut the slot
                if ev.start_time > start:
                    new_slots.append((start, ev.start_time))
                if ev.end_time < end:
                    new_slots.append((ev.end_time, end))
            free_slots = new_slots

        # filter 
        free_slots = [
            (s, e) for s, e in free_slots 
            if (e - s).total_seconds() / 3600.0 >= MIN_SESSION_HRS
        ]

        # fill Free Slots with Tasks
        daily_work_hours = 0
        
        for slot_start, slot_end in free_slots:
            if daily_work_hours >= MAX_DAILY_HOURS:
                break
            
            cursor = slot_start
            
            # while there is room
            while cursor < slot_end:

                slot_remaining = (slot_end - cursor).total_seconds() / 3600.0
                daily_remaining = MAX_DAILY_HOURS - daily_work_hours
                
                capacity = min(slot_remaining, daily_remaining)
                
                if capacity < MIN_SESSION_HRS:
                    break

                best_task_id = None
                best_score = -1
                
                for tid, data in task_ledger.items():
                    if data['remaining'] <= 0:
                        continue
                    
                    task = data['task']
                    
                   
                    if task.deadline and task.deadline < cursor:
                       
                        if tid not in [x['id'] for x in expired_tasks]:
                            expired_tasks.append({
                                'id': task.id,
                                'title': task.title,
                                'deadline': task.deadline.isoformat(),
                                'missed_hours': data['remaining']
                            })
                        continue

                   
                    score = calculate_urgency(task, data['remaining'], cursor)
                    
                    if score > best_score:
                        best_score = score
                        best_task_id = tid
                
                if not best_task_id:
                    break
                
               
                task_data = task_ledger[best_task_id]
                
               
               
               
               
                duration = min(
                    task_data['remaining'], 
                    MAX_SESSION_HRS, 
                    capacity
                )
                
               
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
                
               
                task_data['remaining'] -= duration
                metrics['total_hours_scheduled'] += duration
                daily_work_hours += duration
                
               
                cursor = session_end + timedelta(minutes=settings.break_minutes)
                
                if daily_work_hours >= MAX_DAILY_HOURS:
                    break

       
        daily_stats.append({
            'date': current_date.isoformat(),
            'day_name': current_date.strftime("%a"),
            'hours': daily_work_hours,
            'utilization': (daily_work_hours / MAX_DAILY_HOURS * 100) if MAX_DAILY_HOURS > 0 else 0
        })

       
        current_date += timedelta(days=1)
        days_simulated += 1

   
    
   
    active_days = [d for d in daily_stats if d['hours'] > 0]
    
    # metrics
    if active_days:
        metrics['avg_daily_hours'] = sum(d['hours'] for d in active_days) / len(active_days)
    else:
        metrics['avg_daily_hours'] = 0

    if daily_stats:
        metrics['peak_hours'] = max((d['hours'] for d in daily_stats), default=0)
    else:
        metrics['peak_hours'] = 0
        
    metrics['active_days_count'] = len(active_days)

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

#    score = (priority weight * remaining Work) / time until deadline

    p_weight = {1: 1.0, 2: 2.5, 3: 5.0}.get(task.priority, 1.0)
    
    if not task.deadline:
        hours_until_deadline = 720 
    else:
        hours_until_deadline = (task.deadline - current_time).total_seconds() / 3600.0
    
    hours_until_deadline = max(hours_until_deadline, 0.1)
    
    score = (p_weight * remaining_hours * 10) / hours_until_deadline
    
    return score