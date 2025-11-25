from flask import Flask, render_template, request, jsonify
from models import db, Settings, Task
from utils import generate_schedule
from moodle import run_moodle_sync
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///schedule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()
    if not Settings.query.first():
        db.session.add(Settings())
        db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    if request.method == 'POST':
        data = request.json
        dt = datetime.fromisoformat(data['deadline']) if data.get('deadline') else None
        
        
        start_time = datetime.fromisoformat(data['start_time']) if data.get('start_time') else None
        end_time = datetime.fromisoformat(data['end_time']) if data.get('end_time') else None
        
        new_task = Task(
            title=data['title'],
            deadline=dt,
            estimated_hours=float(data.get('estimated_hours', 0)),
            priority=int(data.get('priority', 1)),
            task_type=data.get('task_type', 'generic'),
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(new_task)
        db.session.commit()
        return jsonify({'status': 'success'})
    
    
    tasks = Task.query.filter_by(is_completed=False).all()
    
    def sort_key(t):
        if t.start_time: return t.start_time
        if t.deadline: return t.deadline
        return datetime.max
        
    tasks.sort(key=sort_key)
    return jsonify([t.to_dict() for t in tasks])

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.json
    
    if 'estimated_hours' in data:
        task.estimated_hours = float(data['estimated_hours'])
    if 'title' in data:
        task.title = data['title']
    if 'priority' in data:
        task.priority = int(data['priority'])
    if 'task_type' in data:
        task.task_type = data['task_type']
    if 'deadline' in data and data['deadline']:
        task.deadline = datetime.fromisoformat(data['deadline'])
        
    db.session.commit()
    return jsonify({'status': 'updated'})

@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.is_completed = True
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/schedule')
def get_schedule_route():
    settings = Settings.query.first()
    tasks = Task.query.filter(Task.is_completed == False).all()
    data = generate_schedule(tasks, settings)
    return jsonify(data)



def get_semester_end():
    """Returns the closer of Dec 1st or May 1st."""
    now = datetime.now()
    year = now.year
    
    
    dates = [
        datetime(year, 5, 1),
        datetime(year, 12, 1),
        datetime(year + 1, 5, 1) 
    ]
    
    
    future_dates = [d for d in dates if d > now]
    
    
    if not future_dates:
        return datetime(year + 1, 5, 1) 
    
    return min(future_dates, key=lambda d: d - now)

@app.route('/api/populate_classes', methods=['POST'])
def populate_classes():
    """
    Expects payload: 
    [
        {"name": "Math", "day": 0, "start": "10:00", "end": "11:00"},
        ...
    ]
    day: 0=Monday, 6=Sunday
    """
    schedule_data = request.json
    semester_end = get_semester_end()
    current_date = datetime.now()
    
    cursor = current_date
    
    added_count = 0
    
    js_to_py_day = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}

    while cursor <= semester_end:
        py_weekday = cursor.weekday()
        
        for item in schedule_data:

            target_day = int(item['day'])
            
            if py_weekday == target_day:
                
                
                s_h, s_m = map(int, item['start'].split(':'))
                e_h, e_m = map(int, item['end'].split(':'))
                
                start_dt = cursor.replace(hour=s_h, minute=s_m, second=0, microsecond=0)
                end_dt = cursor.replace(hour=e_h, minute=e_m, second=0, microsecond=0)
                
                
                exists = Task.query.filter_by(
                    title=item['name'],
                    start_time=start_dt,
                    task_type='class'
                ).first()
                
                if not exists:
                    new_task = Task(
                        title=item['name'],
                        estimated_hours=0,
                        priority=3, 
                        task_type='class',
                        start_time=start_dt,
                        end_time=end_dt,
                        deadline=start_dt 
                    )
                    db.session.add(new_task)
                    added_count += 1
        
        cursor += timedelta(days=1)
        
    db.session.commit()
    return jsonify({
        'status': 'success', 
        'message': f'Added {added_count} class sessions until {semester_end.strftime("%b %d, %Y")}'
    })



@app.route('/api/sync_moodle', methods=['POST'])
def sync_moodle():
    result = run_moodle_sync(app, db, Task, Settings)
    return jsonify({'message': result})






@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    s = Settings.query.first()
    
    if request.method == 'POST':
        data = request.json
        
        
        if data.get('start_hour') is not None and str(data['start_hour']).strip():
            s.daily_start_hour = int(data['start_hour'])
            
        if data.get('end_hour') is not None and str(data['end_hour']).strip():
            s.daily_end_hour = int(data['end_hour'])
            
        if 'weekend_mode' in data:
            s.weekend_mode = bool(data.get('weekend_mode'))
        
        
        if 'asc_username' in data: s.asc_username = data['asc_username']
        if 'asc_password' in data: s.asc_password = data['asc_password']
        
        
        if data.get('max_daily_hours'): 
            s.max_daily_hours = float(data['max_daily_hours'])
        if data.get('min_session_minutes'): 
            s.min_session_minutes = int(data['min_session_minutes'])
        if data.get('max_session_minutes'): 
            s.max_session_minutes = int(data['max_session_minutes'])
        if data.get('break_minutes'): 
            s.break_minutes = int(data['break_minutes'])
        
        
        sim_date_str = data.get('simulation_date')
        if sim_date_str:
            try:
                
                if len(sim_date_str) == 16: 
                    sim_date_str += ":00"
                s.simulation_date = datetime.fromisoformat(sim_date_str)
            except ValueError:
                pass 
        else:
            s.simulation_date = None 
            
        db.session.commit()
        return jsonify({'status': 'updated'})
    
    return jsonify({
        'start_hour': s.daily_start_hour,
        'end_hour': s.daily_end_hour,
        'weekend_mode': s.weekend_mode,
        'asc_username': s.asc_username or "",
        'asc_password': s.asc_password or "",
        'max_daily_hours': s.max_daily_hours,
        'min_session_minutes': s.min_session_minutes,
        'max_session_minutes': s.max_session_minutes,
        'break_minutes': s.break_minutes,
        'simulation_date': s.simulation_date.isoformat() if s.simulation_date else ''
    })
if __name__ == '__main__':
    app.run(debug=True, port=5001)