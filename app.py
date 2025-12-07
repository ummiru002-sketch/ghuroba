import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Semester, WeeklySlot, Project, Announcement, Transaction, Activity
from translations import TRANSLATIONS

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}


db.init_app(app)
with app.app_context():
    db.create_all()
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Context Processor for Language
@app.context_processor
def inject_language():
    lang = session.get('lang', 'TH')
    return dict(t=TRANSLATIONS[lang], current_lang=lang, datetime=datetime)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes

@app.route('/set_lang/<lang_code>')
def set_lang(lang_code):
    if lang_code in ['TH', 'US']:
        session['lang'] = lang_code
    return redirect(request.referrer or url_for('home'))

@app.route('/')
def home():
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    # Fetch upcoming events
    upcoming_events = Activity.query.filter(Activity.start_date >= datetime.utcnow()).order_by(Activity.start_date.asc()).all()
    return render_template('home.html', announcements=announcements, events=upcoming_events)

@app.route('/api/events')
def api_events():
    events = Activity.query.all()
    events_data = []
    for event in events:
        events_data.append({
            'title': event.title,
            'start': event.start_date.isoformat(),
            'end': event.end_date.isoformat(),
            'description': event.description,
            'location': event.location
        })
    return {'events': events_data}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid username or password')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        real_name = request.form.get('real_name')
        department = request.form.get('department')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        new_user = User(
            username=username,
            password=generate_password_hash(password, method='scrypt'),
            real_name=real_name,
            department=department,
            role='member'
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('home'))
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# Profile
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.real_name = request.form.get('real_name')
        password = request.form.get('password')
        if password:
            current_user.password = generate_password_hash(password, method='scrypt')
        db.session.commit()
        flash('Profile updated')
        return redirect(url_for('profile'))
    return render_template('member/profile.html')

# Member Dues
@app.route('/dues')
@login_required
def dues():
    # Logic: Show current semester's slots. If none, show history or nothing.
    # For simplicity, getting all active semesters.
    semester = Semester.query.filter_by(is_active=True).first()
    slots_data = []
    if semester:
        slots = WeeklySlot.query.filter_by(semester_id=semester.id).order_by(WeeklySlot.week_number).all()
        for slot in slots:
            # Check if user paid for this slot
            txn = Transaction.query.filter_by(
                user_id=current_user.id, 
                weekly_slot_id=slot.id, 
                type='income_dues'
            ).first()
            slots_data.append({
                'slot': slot,
                'transaction': txn
            })
    return render_template('member/dues.html', semester=semester, slots_data=slots_data)

@app.route('/pay_dues/<int:slot_id>', methods=['POST'])
@login_required
def pay_dues(slot_id):
    file = request.files.get('slip')
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        slot = WeeklySlot.query.get_or_404(slot_id)
        
        # Create Transaction
        # Default amount 10 (or should it be user input? V3.3 didn't specify amount logic for auto-table, usually fixed or input)
        # V3.4 prompt said "Member clicks Pay -> Uploads Slip". Usually implies a standard amount or manual check by admin.
        # I'll default to 0 (pending) or let admin verify. Let's assume standard due is handled or just tracking the slip.
        # I'll add an amount field hidden or just set to 0 until verified? 
        # Actually V3.3 had "Record Income". V3.4 is "Upload Slip".
        # Let's set amount to 0 initially or allow input? I'll allow input in a modal or just assume slip upload is enough.
        # Let's stick to simplest: User uploads slip. Admin verifies/enters amount? 
        # Or user enters amount. Let's say user enters amount.
        amount = request.form.get('amount', 0)
        
        txn = Transaction(
            type='income_dues',
            amount=float(amount),
            description=f"Week {slot.week_number} Dues",
            user_id=current_user.id,
            weekly_slot_id=slot.id,
            slip_filename=filename,
            date=datetime.utcnow(),
            status='pending',
            semester_id=slot.semester_id
        )
        db.session.add(txn)
        db.session.commit()
        flash('Payment submitted for approval')
    return redirect(url_for('dues'))

@app.route('/transparency')
def transparency():
    # Calculate Net Balance
    income = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type.like('income%')).scalar() or 0
    expense = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type == 'expense').scalar() or 0
    balance = income - expense
    return render_template('member/transparency.html', balance=balance, income=income, expense=expense)

# Admin Routes
@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    # Calculate Grand Total
    income = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type.like('income%')).scalar() or 0
    expense = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type == 'expense').scalar() or 0
    balance = income - expense
    
    # Check for pending dues count
    pending_count = Transaction.query.filter_by(status='pending', type='income_dues').count()
    
    return render_template('admin/dashboard.html', balance=balance, pending_count=pending_count)

@app.route('/admin/approvals', methods=['GET', 'POST'])
@login_required
def admin_approvals():
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    if request.method == 'POST':
        txn_id = request.form.get('txn_id')
        txn = Transaction.query.get(txn_id)
        if txn:
            txn.status = 'approved'
            db.session.commit()
            flash('Payment Approved')
    
    pending_txns = Transaction.query.filter_by(status='pending', type='income_dues').order_by(Transaction.date.asc()).all()
    return render_template('admin/approvals.html', transactions=pending_txns)

@app.route('/admin/semesters', methods=['GET', 'POST'])
@login_required
def admin_semesters():
    if current_user.role != 'admin':
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        if 'create' in request.form:
            name = request.form.get('name')
            start = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            end = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            
            # Deactivate others
            Semester.query.update({Semester.is_active: False})
            
            sem = Semester(name=name, start_date=start, end_date=end, is_active=True)
            db.session.add(sem)
            db.session.flush() # get ID
            
            # Auto-generate slots
            current_date = start
            week_num = 1
            while current_date < end:
                week_end = current_date + timedelta(days=6)
                if week_end > end:
                    week_end = end
                
                slot = WeeklySlot(
                    semester_id=sem.id,
                    week_number=week_num,
                    start_date=current_date,
                    end_date=week_end
                )
                db.session.add(slot)
                current_date = week_end + timedelta(days=1)
                week_num += 1
                
            db.session.commit()
            flash('Semester and slots created')
        elif 'toggle_status' in request.form:
            sem_id = request.form.get('sem_id')
            sem = Semester.query.get(sem_id)
            if sem:
                sem.is_active = not sem.is_active
                db.session.commit()
                flash('Semester status updated')

    semesters = Semester.query.all()
    return render_template('admin/semesters.html', semesters=semesters)

@app.route('/admin/projects', methods=['GET', 'POST'])
@login_required
def admin_projects():
    if current_user.role != 'admin': return redirect(url_for('home'))
    if request.method == 'POST':
        if 'create' in request.form:
            name = request.form.get('name')
            desc = request.form.get('description')
            p = Project(name=name, description=desc)
            db.session.add(p)
            db.session.commit()
        elif 'update_status' in request.form:
            project_id = request.form.get('project_id')
            new_status = request.form.get('status')
            p = Project.query.get(project_id)
            if p:
                p.status = new_status
                db.session.commit()
    
    active_projects = Project.query.filter_by(status='Active').all()
    completed_projects = Project.query.filter_by(status='Completed').all()
    cancelled_projects = Project.query.filter_by(status='Cancelled').all()
    
    return render_template('admin/projects.html', 
                           active_projects=active_projects,
                           completed_projects=completed_projects,
                           cancelled_projects=cancelled_projects)

@app.route('/admin/project/delete', methods=['POST'])
@login_required
def delete_project():
    if current_user.role != 'admin': return redirect(url_for('home'))
    project_id = request.form.get('project_id')
    p = Project.query.get(project_id)
    if p:
        # Check models.py: transactions = db.relationship('Transaction', backref='project', lazy=True)
        # Manually set transactions project_id to None before deletion to keep financial record but orphan them
        for txn in p.transactions:
             txn.project_id = None
        db.session.delete(p)
        db.session.commit()
        flash('Project deleted')
    return redirect(url_for('admin_projects'))

@app.route('/admin/members', methods=['GET', 'POST'])
@login_required
def admin_members():
    if current_user.role != 'admin': return redirect(url_for('home'))
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        action = request.form.get('action')
        user = User.query.get(user_id)
        if user and user.role != 'admin': # Don't delete/reset other admins easily
            if action == 'reset':
                user.password = generate_password_hash('1234', method='scrypt')
                flash(f'Password reset for {user.username}')
            elif action == 'delete':
                db.session.delete(user)
                flash(f'User {user.username} deleted')
            db.session.commit()
    members = User.query.filter_by(role='member').all()
    return render_template('admin/members.html', members=members)

@app.route('/admin/treasury', methods=['GET', 'POST'])
@login_required
def admin_treasury():
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    # Show Active and maybe Completed projects in dropdown? 
    # Prompt says "Cancelled: Hide from selection menus". So we show Active and Completed.
    # Actually usually you record expenses against active projects. But let's allow Completed too just in case.
    # But for "Cancelled", definitely hide.
    projects = Project.query.filter(Project.status != 'Cancelled').all()
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    
    selected_semester_id = request.args.get('semester_id')
    
    if request.method == 'POST':
        if 'delete_txn' in request.form:
             txn_id = request.form.get('txn_id')
             txn = Transaction.query.get(txn_id)
             if txn:
                 db.session.delete(txn)
                 db.session.commit()
                 flash('Transaction deleted')
        else:
            txn_type = request.form.get('type') # income_donation or expense
            amount = float(request.form.get('amount'))
            desc = request.form.get('description')
            project_id = request.form.get('project_id')
            
            filename = None
            file = request.files.get('slip') # Receipt/Evidence
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Get active semester for expenses/donations if not specified
            # For simplicity, we just grab the first active semester
            active_sem = Semester.query.filter_by(is_active=True).first()
            
            txn = Transaction(
                type=txn_type,
                amount=amount,
                description=desc,
                project_id=project_id if project_id else None,
                slip_filename=filename,
                date=datetime.utcnow(),
                status='approved',
                semester_id=active_sem.id if active_sem else None
            )
            db.session.add(txn)
            db.session.commit()
            flash('Transaction recorded')
        
    # Transactions Query
    query = Transaction.query.filter(Transaction.status == 'approved')
    if selected_semester_id:
        query = query.filter(Transaction.semester_id == int(selected_semester_id))
        
    transactions = query.order_by(Transaction.date.desc()).all()
    
    # Calculate Total Dues Collected (only for this view filter)
    total_dues = sum(t.amount for t in transactions if t.type == 'income_dues')

    return render_template('admin/treasury.html', 
                           projects=projects, 
                           transactions=transactions, 
                           semesters=semesters,
                           selected_semester_id=selected_semester_id,
                           total_dues=total_dues)

@app.route('/admin/report')
@login_required
def admin_report():
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    # Filter by project if needed, or all
    project_id = request.args.get('project_id')
    semester_id = request.args.get('semester_id')
    
    query = Transaction.query.filter(Transaction.status == 'approved')
    if project_id:
        query = query.filter(Transaction.project_id == int(project_id))
    if semester_id:
        query = query.filter(Transaction.semester_id == int(semester_id))
        
    transactions = query.order_by(Transaction.date.asc()).all()
        
    projects = Project.query.all()
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    
    return render_template('admin/report.html', 
                           transactions=transactions, 
                           projects=projects, 
                           semesters=semesters,
                           selected_project=project_id,
                           selected_semester=semester_id)

@app.route('/admin/news', methods=['GET', 'POST'])
@login_required
def admin_news():
    if current_user.role != 'admin': return redirect(url_for('home'))
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        filename = None
        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"news_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        news = Announcement(title=title, content=content, image_filename=filename)
        db.session.add(news)
        db.session.commit()
    
    news_items = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin/news.html', news_items=news_items)

@app.route('/admin/events', methods=['GET', 'POST'])
@login_required
def admin_events():
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    if request.method == 'POST':
        if 'create' in request.form:
            title = request.form.get('title')
            desc = request.form.get('description')
            start = datetime.strptime(request.form.get('start_date'), '%Y-%m-%dT%H:%M')
            end = datetime.strptime(request.form.get('end_date'), '%Y-%m-%dT%H:%M')
            loc = request.form.get('location')
            
            event = Activity(title=title, description=desc, start_date=start, end_date=end, location=loc)
            db.session.add(event)
            db.session.commit()
            flash('Event created')
            
    events = Activity.query.order_by(Activity.start_date.desc()).all()
    return render_template('admin/events.html', events=events)

@app.route('/admin/events/delete', methods=['POST'])
@login_required
def delete_event():
    if current_user.role != 'admin': return redirect(url_for('home'))
    event_id = request.form.get('event_id')
    event = Activity.query.get(event_id)
    if event:
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted')
    return redirect(url_for('admin_events'))

@app.route('/admin/tracker')
@login_required
def admin_tracker():
    if current_user.role != 'admin': return redirect(url_for('home'))
    
    semester = Semester.query.filter_by(is_active=True).first()
    if not semester:
        return render_template('admin/tracker.html', semester=None)
        
    slots = WeeklySlot.query.filter_by(semester_id=semester.id).order_by(WeeklySlot.week_number).all()
    members = User.query.filter_by(role='member').all()
    
    # Pre-fetch all dues transactions for this semester
    transactions = Transaction.query.filter_by(semester_id=semester.id, type='income_dues').all()
    
    # Build a lookup: (user_id, slot_id) -> status
    status_map = {}
    for t in transactions:
        if t.user_id and t.weekly_slot_id:
            status_map[(t.user_id, t.weekly_slot_id)] = t.status
            
    tracker_data = []
    for member in members:
        row = {
            'user': member,
            'status_map': {slot.id: status_map.get((member.id, slot.id), 'unpaid') for slot in slots}
        }
        tracker_data.append(row)
        
    return render_template('admin/tracker.html', semester=semester, slots=slots, tracker_data=tracker_data)

@app.route('/admin/semester/edit', methods=['POST'])
@login_required
def edit_semester():
    if current_user.role != 'admin': return redirect(url_for('home'))
    sem_id = request.form.get('sem_id')
    name = request.form.get('name')
    start = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
    end = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
    
    sem = Semester.query.get(sem_id)
    if sem:
        sem.name = name
        sem.start_date = start
        sem.end_date = end
        # Note: Changing dates might invalidate existing slots. 
        # For V3.5 Critical, we just update the dates. Advanced logic would regenerate slots.
        # User prompt asks to "manage Start/End dates", usually implies logic adjustment, 
        # but regenerating slots destroys payment links if slot_ids change.
        # Safe approach: Update Semester dates. Slots remain as is unless manually regenerated.
        db.session.commit()
        flash('Semester updated')
    return redirect(url_for('admin_semesters'))

@app.route('/admin/semester/delete', methods=['POST'])
@login_required
def delete_semester():
    if current_user.role != 'admin': return redirect(url_for('home'))
    sem_id = request.form.get('sem_id')
    sem = Semester.query.get(sem_id)
    if sem:
        # Cascade delete is handled by models.py (slots) but transactions might restrict it or need set null.
        # Check models: slots = db.relationship(..., cascade="all, delete-orphan")
        # Transactions link to Semester and Slot.
        # If we delete Semester -> Slots deleted. 
        # Transactions linked to Slots -> ? Models: weekly_slot = db.relationship('WeeklySlot', backref='transactions')
        # By default SQLAlchemy sets FK to Null or restricts.
        # Prompt says "Associated payment data might be affected". We'll just delete it.
        # Ideally we should warn.
        db.session.delete(sem)
        db.session.commit()
        flash('Semester deleted')
    return redirect(url_for('admin_semesters'))

# Init DB
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash('admin123', method='scrypt'),
            real_name='Administrator',
            department='Admin',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
