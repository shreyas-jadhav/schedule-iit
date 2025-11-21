from flask import Flask, render_template, request, redirect, url_for, abort
from datetime import datetime
import uuid

app = Flask(__name__)

academic_events = [

]

def find_event_by_id(event_id):
    for event in academic_events:
        if event['ae_id'] == event_id:
            return event
    return None

@app.route('/')
def index():
    sorted_events = sorted(academic_events, key=lambda e: e['start'])
    return render_template('index.html', events=sorted_events)

@app.route('/add', methods=['GET', 'POST'])
def add_event():
    if request.method == 'POST':
        title = request.form.get('title')
        event_type = request.form.get('type')
        
        start_str = request.form.get('start')
        start_datetime = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
        
        session_hours = float(request.form.get('session_hours', 0))
        buffer_hours = float(request.form.get('buffer_hours', 0))
        
        repeat = request.form.get('repeat')
        if not repeat:
            repeat = None
            
        new_event = {
            'ae_id': str(uuid.uuid4()),
            'type': event_type,
            'start': start_datetime,
            'session_hours': session_hours,
            'buffer_hours': buffer_hours,
            'repeat': repeat,
            'title': title,
            'user_id': 'user_123'
        }
        
        academic_events.append(new_event)
        
        return redirect(url_for('index'))
    
    return render_template('add_event.html')

@app.route('/edit/<event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    event = find_event_by_id(event_id)
    if not event:
        return abort(404)

    if request.method == 'POST':
        event['title'] = request.form.get('title')
        event['type'] = request.form.get('type')
        
        start_str = request.form.get('start')
        event['start'] = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
        
        event['session_hours'] = float(request.form.get('session_hours', 0))
        event['buffer_hours'] = float(request.form.get('buffer_hours', 0))
        
        repeat = request.form.get('repeat')
        event['repeat'] = repeat if repeat else None
        
        return redirect(url_for('index'))

    return render_template('edit_event.html', event=event)

@app.route('/delete/<event_id>')
def delete_event(event_id):
    global academic_events
    event = find_event_by_id(event_id)
    if event:
        academic_events.remove(event)
    return redirect(url_for('index'))

@app.route('/fetch-moodle')
def fetch_moodle():
    moodle_data = [
        {
            'title': '[Moodle] Assignment 3 Spark (CS 631)',
            'start': datetime(2025, 10, 11, 23, 59)
        },
        {
            'title': '[Moodle] HW 8: Web Development (CS 699)',
            'start': datetime(2025, 10, 23, 23, 30)
        },
        {
            'title': '[Moodle] Assignment 3 - Animation (CS 675)',
            'start': datetime(2025, 11, 7, 23, 59)
        }
    ]
    
    for item in moodle_data:
        new_event = {
            'ae_id': str(uuid.uuid4()),
            'type': 'assignment',
            'start': item['start'],
            'session_hours': 0,
            'buffer_hours': 0,
            'repeat': None,
            'title': item['title'],
            'user_id': 'user_123'
        }
        academic_events.append(new_event)
        
    return redirect(url_for('index'))

@app.route('/fetch-asc')
def fetch_asc():
    asc_data = [
        {
            'title': '[ASC] CS 631 (S Sudarshan)',
            'start': datetime(2025, 10, 27, 14, 15),
            'session': 1.17,
            'repeat': '15 14 * * 1,4'
        },
        {
            'title': '[ASC] CS 675 (Parag Kumar Chaudhuri)',
            'start': datetime(2025, 10, 24, 14, 15),
            'session': 1.17,
            'repeat': '15 14 * * 2,5'
        },
        {
            'title': '[ASC] CS 699 (Om P. Damani)',
            'start': datetime(2025, 10, 29, 15, 30),
            'session': 1.42,
            'repeat': '30 15 * * 3'
        }
    ]
    
    for item in asc_data:
        new_event = {
            'ae_id': str(uuid.uuid4()),
            'type': 'class',
            'start': item['start'],
            'session_hours': item['session'],
            'buffer_hours': 0.25,
            'repeat': item['repeat'],
            'title': item['title'],
            'user_id': 'user_123'
        }
        academic_events.append(new_event)
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)

