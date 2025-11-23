from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    
    # Moodle & Automation
    moodle_url = db.Column(db.String(255), default="https://moodle.iitb.ac.in")
    
    # Algorithm Constraints
    daily_start_hour = db.Column(db.Integer, default=9) # 9 AM
    daily_end_hour = db.Column(db.Integer, default=17)  # 5 PM
    weekend_mode = db.Column(db.Boolean, default=False)
    
    # Simulation / Time Travel
    # If Null, defaults to "Now". If set, scheduler starts from here.
    simulation_date = db.Column(db.DateTime, nullable=True) 

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    
    title = db.Column(db.String(200), nullable=False)
    task_type = db.Column(db.String(50), nullable=True)
    
    deadline = db.Column(db.DateTime, nullable=False)
    estimated_hours = db.Column(db.Float, nullable=False) 
    priority = db.Column(db.Integer, default=1)
    
    source = db.Column(db.String(20), default='manual') 
    external_id = db.Column(db.String(100), nullable=True)
    
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'deadline': self.deadline.isoformat(),
            'estimated_hours': self.estimated_hours,
            'priority': self.priority,
            'task_type': self.task_type,
            'source': self.source,
            'is_completed': self.is_completed
        }