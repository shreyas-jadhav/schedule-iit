from flask import Flask, render_template, request, jsonify
from models import db, Settings, Task
from scheduler import generate_schedule
from scraper import run_moodle_sync, run_asc_sync
from datetime import datetime

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
        dt = datetime.fromisoformat(data['deadline'])
        new_task = Task(
            title=data['title'],
            deadline=dt,
            estimated_hours=float(data['estimated_hours']),
            priority=int(data.get('priority', 1)),
            task_type=data.get('task_type', 'generic')
        )
        db.session.add(new_task)
        db.session.commit()
        return jsonify({'status': 'success'})
    tasks = Task.query.filter_by(is_completed=False).order_by(Task.deadline).all()
    return jsonify([t.to_dict() for t in tasks])

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.json
    
    if 'estimated_hours' in data:
        task.estimated_hours = float(data['estimated_hours'])
    
    # We can also allow editing other fields while we are here
    if 'title' in data:
        task.title = data['title']
    if 'priority' in data:
        task.priority = int(data['priority'])

    if 'task_type' in data:
        task.task_type = data['task_type']

    if 'deadline' in data and data['deadline']:
        # datetime.fromisoformat handles the 'YYYY-MM-DDTHH:MM' format sent by browser
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

@app.route('/api/sync_moodle', methods=['POST'])
def sync_moodle():
    result = run_moodle_sync(app, db, Task, Settings)
    return jsonify({'message': result})

@app.route('/api/sync_asc', methods=['POST'])
def sync_asc():
    result = run_asc_sync(app, db, Task, Settings)
    return jsonify({'message': result})

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    s = Settings.query.first()
    
    if request.method == 'POST':
        data = request.json
        s.daily_start_hour = int(data.get('start_hour', s.daily_start_hour))
        s.daily_end_hour = int(data.get('end_hour', s.daily_end_hour))
        s.weekend_mode = bool(data.get('weekend_mode', s.weekend_mode))
        
        # Save ASC Credentials
        if 'asc_username' in data: s.asc_username = data['asc_username']
        if 'asc_password' in data: s.asc_password = data['asc_password']
        
        # Config Fields
        s.max_daily_hours = float(data.get('max_daily_hours', s.max_daily_hours))
        s.min_session_minutes = int(data.get('min_session_minutes', s.min_session_minutes))
        s.max_session_minutes = int(data.get('max_session_minutes', s.max_session_minutes))
        s.break_minutes = int(data.get('break_minutes', s.break_minutes))
        
        # Handle Simulation Date
        sim_date_str = data.get('simulation_date')
        if sim_date_str:
            s.simulation_date = datetime.fromisoformat(sim_date_str)
        else:
            s.simulation_date = None 
            
        db.session.commit()
        return jsonify({'status': 'updated'})
    
    # GET
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
    app.run(debug=True, port=5000)