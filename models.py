from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    moodle_url = db.Column(db.String(255), default="https://moodle.iitb.ac.in")
    
    # ASC Credentials
    asc_username = db.Column(db.String(100), nullable=True)
    asc_password = db.Column(db.String(100), nullable=True)
    
    # time Window
    daily_start_hour = db.Column(db.Integer, default=9)
    daily_end_hour = db.Column(db.Integer, default=17) 
    weekend_mode = db.Column(db.Boolean, default=False)
    
    max_daily_hours = db.Column(db.Float, default=6.0)
    min_session_minutes = db.Column(db.Integer, default=30)
    max_session_minutes = db.Column(db.Integer, default=120)
    break_minutes = db.Column(db.Integer, default=15)
    
    simulation_date = db.Column(db.DateTime, nullable=True) 

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    
    title = db.Column(db.String(200), nullable=False)
    task_type = db.Column(db.String(50), nullable=True) 
    
    deadline = db.Column(db.DateTime, nullable=True)
    estimated_hours = db.Column(db.Float, default=1.0)
    
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    
    priority = db.Column(db.Integer, default=1)
    source = db.Column(db.String(20), default='manual') 
    external_id = db.Column(db.String(100), nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'estimated_hours': self.estimated_hours,
            'priority': self.priority,
            'task_type': self.task_type,
            'source': self.source,
            'is_completed': self.is_completed
        }