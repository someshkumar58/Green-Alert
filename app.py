from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
import os
import re
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load environment variables from .env file if present
def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"\''))

_load_env_file()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'static/uploads')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    image = db.Column(db.String(300))
    status = db.Column(db.String(100), default='Pending')
    department = db.Column(db.String(100), default='')

# ---------------- Admin and Departments ----------------
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'adminpass')

departments = {
    'sanitation': {
        'email': os.environ.get('DEPT_SANITATION_EMAIL', 'sanitation@green.com'),
        'password': os.environ.get('DEPT_SANITATION_PASSWORD', 'san123')
    },
    'water': {
        'email': os.environ.get('DEPT_WATER_EMAIL', 'water@green.com'),
        'password': os.environ.get('DEPT_WATER_PASSWORD', 'wat123')
    },
    'pollution': {
        'email': os.environ.get('DEPT_POLLUTION_EMAIL', 'pollution@green.com'),
        'password': os.environ.get('DEPT_POLLUTION_PASSWORD', 'pol123')
    },
    'forest': {
        'email': os.environ.get('DEPT_FOREST_EMAIL', 'forest@green.com'),
        'password': os.environ.get('DEPT_FOREST_PASSWORD', 'for123')
    }
}

# 🔐 Email credentials for notifications
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', 'greenalert6@gmail.com')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')

# ---------------- Routes ----------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'], strict_slashes=False)
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # 1. Validate required empty fields
        if not name or not email or not password:
            error = 'All fields are required. Please fill in your name, email, and password.'
            return render_template('register.html', error=error, name=name, email=email)

        # 2. Validate email format
        email_regex = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
        if not re.match(email_regex, email):
            error = 'Please enter a valid email address (e.g., user@example.com).'
            return render_template('register.html', error=error, name=name, email=email)

        # 3. Prevent duplicate email registration (case-insensitive)
        try:
            existing_user = User.query.filter(db.func.lower(User.email) == email).first()
            if existing_user:
                error = 'Email is already registered. Please login or use a different email.'
                return render_template('register.html', error=error, name=name, email=email)

            # 4. Securely hash password and save user
            hashed_password = generate_password_hash(password)
            user = User(name=name, email=email, password=hashed_password)
            db.session.add(user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            error = f'Database error occurred: {str(e)}'
            return render_template('register.html', error=error, name=name, email=email)

        flash('Registration successful! Please login with your credentials.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'], strict_slashes=False)
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            error = 'Please enter both email and password.'
            return render_template('login.html', error=error, email=email)

        try:
            user = User.query.filter(db.func.lower(User.email) == email).first()
        except Exception as e:
            db.session.rollback()
            return render_template('login.html', error=f'Database error: {str(e)}', email=email)

        # Check for unregistered email
        if not user:
            error = 'Unregistered email address. Please check your email or register.'
            return render_template('login.html', error=error, email=email)

        # Check for incorrect password
        if not check_password_hash(user.password, password):
            error = 'Incorrect password. Please try again.'
            return render_template('login.html', error=error, email=email)

        # Successful login: clear prior session, set permanent session
        session.clear()
        session.permanent = True
        session['user_id'] = user.id
        session['user_name'] = user.name
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/dashboard', strict_slashes=False)
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    complaints = Complaint.query.filter_by(user_id=session['user_id']).all()
    return render_template('dashboard.html', complaints=complaints, user_name=session.get('user_name', 'Citizen'))

@app.route('/add_complaint', methods=['POST'])
def add_complaint():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    title = request.form['title']
    description = request.form['description']
    location = request.form['location']
    image = request.files['image']
    image_filename = None

    if image and image.filename != '':
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_filename = filename

    complaint = Complaint(
        user_id=session['user_id'],
        title=title,
        description=description,
        location=location,
        image=image_filename
    )
    db.session.add(complaint)
    db.session.commit()
    flash('Complaint submitted.')
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:complaint_id>', methods=['POST'])
def delete_complaint(complaint_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    complaint = Complaint.query.get_or_404(complaint_id)
    if complaint.user_id != session['user_id']:
        flash('Unauthorized.')
        return redirect(url_for('dashboard'))

    db.session.delete(complaint)
    db.session.commit()
    flash('Complaint deleted.')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.after_request
def add_cache_control_headers(response):
    if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# ---------------- Admin ----------------
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = 'Invalid email or password'
            return render_template('admin_login.html', error=error)
    
    return render_template('admin_login.html', error=None)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    complaints = Complaint.query.all()
    return render_template('admin_dashboard.html', complaints=complaints, departments=departments)

@app.route('/forward_complaint/<int:complaint_id>', methods=['POST'])
def forward_complaint(complaint_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    department = request.form.get('department')
    complaint = Complaint.query.get(complaint_id)
    if complaint:
        complaint.department = department
        complaint.status = f'Forwarded to {department}'
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:complaint_id>', methods=['POST'])
def admin_delete_complaint(complaint_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    complaint = Complaint.query.get_or_404(complaint_id)
    db.session.delete(complaint)
    db.session.commit()
    flash('Complaint deleted.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin', None)
    flash('Logged out successfully.')
    return redirect(url_for('home'))

# ---------------- Department ----------------
@app.route('/department_login', methods=['GET', 'POST'])
def department_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        for dept, creds in departments.items():
            if creds['email'] == email and creds['password'] == password:
                session['department'] = dept
                return redirect(url_for('department_dashboard', dept_name=dept))
        flash('Invalid department credentials')
    return render_template('department_login.html')

@app.route('/department/<dept_name>')
def department_dashboard(dept_name):
    if session.get('department') != dept_name:
        return redirect(url_for('department_login'))

    dept_complaints = Complaint.query.filter_by(department=dept_name).all()
    return render_template(f"{dept_name}.html", complaints=dept_complaints, department=dept_name)

@app.route('/department/update_status/<int:complaint_id>', methods=['POST'])
def department_update_status(complaint_id):
    if 'department' not in session:
        return redirect(url_for('department_login'))

    new_status = request.form['status']
    complaint = Complaint.query.get(complaint_id)

    if complaint and complaint.department == session['department']:
        complaint.status = new_status
        db.session.commit()

        user = User.query.get(complaint.user_id)
        if user:
            try:
                subject = f"Complaint Status Updated: {new_status}"
                body = f"""
Hello {user.name},

The status of your complaint titled "{complaint.title}" has been updated to "{new_status}" by the {complaint.department} department.

Thank you for using our portal to improve your surroundings!

Regards,  
Green Portal Team
                """

                msg = MIMEMultipart()
                msg['From'] = EMAIL_SENDER
                msg['To'] = user.email
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))

                print(f"📧 Sending email to {user.email}...")

                if EMAIL_SENDER and EMAIL_PASSWORD:
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.ehlo()
                    server.starttls()
                    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                    server.send_message(msg)
                    server.quit()
                    print("✅ Email sent successfully.")
                else:
                    print("ℹ️ Email notifications skipped: EMAIL_SENDER or EMAIL_PASSWORD not configured.")

            except Exception as e:
                print("❌ Error sending email:", e)

    return redirect(url_for('department_dashboard', dept_name=session['department']))

@app.route('/department/logout')
def department_logout():
    session.pop('department', None)
    flash('Logged out successfully.')
    return redirect(url_for('department_login'))

# ---------------- Run ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
