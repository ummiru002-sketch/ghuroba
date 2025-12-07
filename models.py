from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    real_name = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), default='member')  # 'admin' or 'member'

class Semester(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    slots = db.relationship('WeeklySlot', backref='semester', lazy=True, cascade="all, delete-orphan")

class WeeklySlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Active') # Active, Completed, Cancelled
    transactions = db.relationship('Transaction', backref='project', lazy=True)

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)  # 'income_dues', 'income_donation', 'expense'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Who paid (for dues)
    
    # Evidence
    slip_filename = db.Column(db.String(200), nullable=True)
    
    # Context (e.g. for dues, which week?)
    weekly_slot_id = db.Column(db.Integer, db.ForeignKey('weekly_slot.id'), nullable=True)
    weekly_slot = db.relationship('WeeklySlot', backref='transactions')
    user = db.relationship('User', backref='transactions')
    
    # New columns for V3.5 critical update
    status = db.Column(db.String(20), default='approved') # 'pending', 'approved'
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=True)
    semester = db.relationship('Semester', backref='transactions')

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

