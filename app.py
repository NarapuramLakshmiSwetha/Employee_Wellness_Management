import os
import io
import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime, date
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF
import database
import google.generativeai as genai
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
# Initialize Flask app
app = Flask(__name__)
# Use a stable secret key from env var (needed for Vercel so sessions work across invocations)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
# Register blueprints
from routes.recommendations import recommendations_bp
app.register_blueprint(recommendations_bp)

# Try to configure Gemini API using the environment variable if present
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    try:
        genai.configure(api_key=gemini_api_key)
    except Exception as e:
        app.logger.error(f"Failed to configure Gemini API: {e}")

# Configure Uploads — use /tmp/ on Vercel (only writable directory)
if os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp/uploads'
else:
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database schema and seed default admin user
database.init_db()

@app.route('/')
def index():
    if 'username' in session:
        user = database.get_user_by_username(session['username'])
        if user and (user['job_role'] == 'admin' or user['username'] == 'admin'):
            return redirect(url_for('admin_portal'))
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))
    # Admin gets redirected to the admin portal
    user = database.get_user_by_username(session['username'])
    if user and (user['job_role'] == 'admin' or user['username'] == 'admin'):
        return redirect(url_for('admin_portal'))
    designation = user['designation'] if (user and user['designation']) else 'Staff'
    return render_template('dashboard.html', username=session['username'], profile_photo=user['profile_photo'] if user else None, designation=designation)

@app.route('/admin')
def admin_portal():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Verify user has admin permissions
    user = database.get_user_by_username(session['username'])
    if not user or (user['job_role'] != 'admin' and user['username'] != 'admin'):
        return "403 Forbidden: Access denied. Only administrators can access this page.", 403
        
    # Fetch registered users and recent logins for admin auditing
    db_users = database.get_all_users()
    users = []
    for u in db_users:
        u_dict = dict(u)
        health_data_row = database.get_health_data(u_dict['id'])
        u_dict['health_risk'] = health_data_row['health_status'] if health_data_row else 'Unknown'
        # Get latest sentiment record to show latest mental health status
        sentiment_history = database.get_sentiment_history(u_dict['id'])
        u_dict['mental_health_status'] = sentiment_history[0]['mental_health_status'] if sentiment_history else 'No Record'
        users.append(u_dict)
    
    logs = database.get_login_history(limit=50)
    
    # Calculate statistics for the dashboard widgets
    total_users = len(users)
    locked_users = sum(1 for u in users if u['locked_until'] is not None)
    active_users = total_users - locked_users
    total_logins = len(logs)
    
    stats = {
        'total_users': total_users,
        'active_users': active_users,
        'locked_users': locked_users,
        'total_logins': total_logins
    }

    # Wellness summary stats for the health overview cards
    wellness_stats = database.get_dashboard_stats()
    
    return render_template('admin.html', username=session['username'], users=users, logs=logs, stats=stats, wellness_stats=wellness_stats)

@app.route('/api/session', methods=['GET'])
def get_session():
    if 'username' in session:
        return jsonify({
            'authenticated': True,
            'username': session['username'],
            'email': session['email']
        })
    return jsonify({'authenticated': False})

@app.route('/api/check-uniqueness', methods=['POST'])
def api_check_uniqueness():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    employee_id = data.get('employee_id', '').strip()

    result = database.check_uniqueness(
        username=username or None,
        email=email or None,
        employee_id=employee_id or None
    )
    return jsonify({'success': True, 'taken': result})

@app.route('/api/register', methods=['POST'])
def api_register():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    job_role = request.form.get('job_role', 'Employee').strip()
    fullname = request.form.get('fullname', '').strip()
    employee_id = request.form.get('employee_id', '').strip()
    mobile_number = request.form.get('mobile_number', '').strip()
    gender = request.form.get('gender', '').strip()
    dob = request.form.get('dob', '').strip()

    if not username or not email or not password or not fullname or not employee_id or not mobile_number or not gender or not dob:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters.'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

    # Prevent public registration of admin accounts
    if job_role.lower() == 'admin':
        return jsonify({'success': False, 'message': 'Admin registration is not allowed publicly.'}), 400

    # Ensure valid job roles
    valid_roles = ['HR Manager', 'Software Engineer', 'Team Leader', 'Project Manager', 'Data Analyst', 'Intern']
    if job_role not in valid_roles:
        job_role = 'Employee'

    # Save profile photo if provided
    profile_photo_path = None
    if 'profile_photo' in request.files:
        file = request.files['profile_photo']
        if file and file.filename != '':
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'message': 'Invalid photo format. Allowed formats: PDF, PNG, JPG, JPEG.'}), 400
            
            filename = f"profile_{username}_{secure_filename(file.filename)}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            profile_photo_path = f"/static/uploads/{filename}"

    success, message = database.register_user(
        username, email, password, job_role, profile_photo=profile_photo_path,
        full_name=fullname, employee_id=employee_id, mobile_number=mobile_number,
        gender=gender, dob=dob
    )
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    is_admin_login = data.get('is_admin_login', False)

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    # 1. Check if user is locked out
    is_locked, cooldown, locked_until = database.check_user_lock(username)
    if is_locked:
        database.log_login(username, status="FAILED (LOCKED)")
        return jsonify({
            'success': False,
            'message': 'Account is temporarily locked.',
            'locked': True,
            'cooldown_seconds': cooldown
        }), 403

    user = database.get_user_by_username(username)
    if not user:
        database.log_login(username, status="FAILED (UNKNOWN USER)")
        return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401

    # 2. Check password
    if check_password_hash(user['password_hash'], password):
        is_user_admin = (user['job_role'] == 'admin' or user['username'] == 'admin')
        
        # Enforce admin role check for admin portal login
        if is_admin_login and not is_user_admin:
            database.log_login(username, status="FAILED (NOT AN ADMIN)")
            return jsonify({'success': False, 'message': 'Access denied. Only administrators can log in here.'}), 403

        # Enforce employee role check for employee portal login
        if not is_admin_login and is_user_admin:
            database.log_login(username, status="FAILED (ADMIN ON EMP PORTAL)")
            return jsonify({'success': False, 'message': 'Administrators must log in using the Admin Login page.'}), 403

        database.reset_failed_attempts(username)
        database.log_login(username, status="SUCCESS")
        
        # Store user details in session and finalize login
        session['username'] = user['username']
        session['email'] = user['email']
        database.update_login_time(user['id'])
        # Determine redirect path based on user role
        redirect_url = '/admin' if is_user_admin else '/dashboard'
        return jsonify({'success': True, 'message': 'Login successful.', 'redirect_url': redirect_url})
    else:
        locked_until, remaining = database.increment_failed_attempts(username)
        database.log_login(username, status="FAILED (WRONG PASSWORD)")
        if locked_until:
            # Fetch new lock details
            is_locked, cooldown, locked_until = database.check_user_lock(username)
            return jsonify({
                'success': False,
                'message': 'Invalid password. Account is now locked.',
                'locked': True,
                'cooldown_seconds': cooldown
            }), 403
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid password.',
                'remaining_attempts': remaining
            }), 401

@app.route('/api/admin/create-admin', methods=['POST'])
def api_create_admin():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    
    # Verify current user is admin
    current_user = database.get_user_by_username(session['username'])
    if not current_user or (current_user['job_role'] != 'admin' and current_user['username'] != 'admin'):
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403
        
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters.'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

    # Explicitly register as admin
    success, message = database.register_user(username, email, password, job_role='admin')
    if success:
        return jsonify({'success': True, 'message': 'Admin account created successfully.'})
    else:
        return jsonify({'success': False, 'message': message}), 400

@app.route('/api/logout', methods=['POST'])
def api_logout():
    if 'username' in session:
        user = database.get_user_by_username(session['username'])
        if user:
            database.update_logout_time(user['id'])
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'})

@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and new password are required.'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

    success, message = database.reset_password(username, password)
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400

@app.route('/api/clear-logs', methods=['POST'])
def api_clear_logs():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    
    # Verify user is admin
    user = database.get_user_by_username(session['username'])
    if not user or (user['job_role'] != 'admin' and user['username'] != 'admin'):
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403
    
    success, message = database.clear_login_logs()
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 500

@app.route('/api/dashboard-stats')
def api_dashboard_stats():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return jsonify({'success': False, 'message': 'Access denied.'}), 403
    stats = database.get_dashboard_stats()
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/health-score')
def api_health_score():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    score = database.calculate_health_score(user['id'])
    if score is None:
        return jsonify({'success': False, 'message': 'No health data available.'}), 404
    if score >= 80:
        status = 'Excellent'
    elif score >= 60:
        status = 'Good'
    elif score >= 40:
        status = 'Average'
    else:
        status = 'Needs Improvement'

    # Build per-factor breakdown for the Health Score card
    breakdown, updated_at = database.get_health_score_breakdown(user['id'])

    return jsonify({
        'success': True,
        'health_score': score,
        'health_status': status,
        'breakdown': breakdown,
        'updated_at': updated_at
    })

@app.route('/health-data')
def health_data_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    # Make sure admin cannot access
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    return render_template('health_data.html', username=session['username'], profile_photo=user['profile_photo'] if user else None, user=user)

@app.route('/wellness-performance')
def wellness_performance_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    designation = user['designation'] if user['designation'] else 'Staff'
    return render_template(
        'wellness_performance.html',
        username=session['username'],
        profile_photo=user['profile_photo'] if user else None,
        designation=designation
    )


@app.route('/api/health-data', methods=['GET', 'POST'])
def api_health_data():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    if request.method == 'GET':
        data = database.get_health_data(user['id'])
        if data:
            return jsonify({'success': True, 'exists': True, 'data': data})
        else:
            return jsonify({'success': True, 'exists': False})

    # POST method: save data
    bg = request.form.get('blood_group', '').strip()
    height = request.form.get('height', '').strip()
    weight = request.form.get('weight', '').strip()
    bmi = request.form.get('bmi', '').strip()
    bmi_category = request.form.get('bmi_category', '').strip()
    bp = request.form.get('blood_pressure', '').strip()
    water = request.form.get('water_intake', '').strip()
    em_name = request.form.get('emergency_name', '').strip()
    em_relation = request.form.get('emergency_relation', '').strip()
    em_phone = request.form.get('emergency_phone', '').strip()
    last_checkup = request.form.get('last_checkup', '').strip()
    next_checkup = request.form.get('next_checkup', '').strip()
    health_status = request.form.get('health_status', '').strip()
    has_allergies = request.form.get('has_allergies', '').strip()
    allergies_detail = request.form.get('allergies_detail', '').strip()
    medical_condition = request.form.get('medical_condition', '').strip()
    medical_condition_other = request.form.get('medical_condition_other', '').strip()
    current_medication = request.form.get('current_medication', '').strip()
    has_disability = request.form.get('has_disability', '').strip()
    disability_detail = request.form.get('disability_detail', '').strip()

    # New lifestyle & work fields
    smoking_habit = request.form.get('smoking_habit', '').strip()
    alcohol_consumption = request.form.get('alcohol_consumption', '').strip()
    exercise_frequency = request.form.get('exercise_frequency', '').strip()
    exercise_type = request.form.get('exercise_type', '').strip()
    daily_step_count = request.form.get('daily_step_count', '0').strip()
    stress_level = request.form.get('stress_level', '').strip()
    attendance_percentage = request.form.get('attendance_percentage', '0').strip()
    work_hours_per_day = request.form.get('work_hours_per_day', '0').strip()
    doctor_remarks = request.form.get('doctor_remarks', '').strip()
    sugar_level = request.form.get('sugar_level', '').strip()

    # Validations
    if not bg or not height or not weight or not bp or not water or not em_name or not em_relation or not em_phone or not last_checkup or not next_checkup or not health_status:
        return jsonify({'success': False, 'message': 'All required fields must be filled.'}), 400

    try:
        height_val = float(height)
        weight_val = float(weight)
        if height_val <= 0 or weight_val <= 0:
            return jsonify({'success': False, 'message': 'Height and Weight must be positive numbers.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Height and Weight must be valid numbers.'}), 400

    import re
    if not re.match(r'^[6-9]\d{9}$', em_phone):
        return jsonify({'success': False, 'message': 'Emergency contact number must be exactly 10 digits.'}), 400

    if not re.match(r'^\d{2,3}\/\d{2,3}$', bp):
        return jsonify({'success': False, 'message': 'Blood Pressure must be in systolic/diastolic format (e.g., 120/80).'}), 400

    if next_checkup <= last_checkup:
        return jsonify({'success': False, 'message': 'Next checkup date must be after the last checkup date.'}), 400

    # Retrieve existing data to check/preserve certificate path if no new file is uploaded
    existing_data = database.get_health_data(user['id'])
    cert_path = existing_data['medical_cert_path'] if existing_data else ''

    # Handle file upload
    if 'medical_certificate' in request.files:
        file = request.files['medical_certificate']
        if file and file.filename != '':
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'message': 'Invalid file format. Allowed formats: PDF, PNG, JPG, JPEG.'}), 400
            
            # Secure file name
            filename = f"user_{user['id']}_{secure_filename(file.filename)}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            # Store relative path for URL retrieval
            cert_path = f"/static/uploads/{filename}"

    health_record = {
        'blood_group': bg,
        'height': height_val,
        'weight': weight_val,
        'bmi': float(bmi) if bmi else (weight_val / ((height_val/100.0)**2)),
        'bmi_category': bmi_category,
        'blood_pressure': bp,
        'water_intake': water,
        'emergency_name': em_name,
        'emergency_relation': em_relation,
        'emergency_phone': em_phone,
        'last_checkup': last_checkup,
        'next_checkup': next_checkup,
        'health_status': health_status,
        'medical_cert_path': cert_path,
        'has_allergies': has_allergies,
        'allergies_detail': allergies_detail if has_allergies == 'Yes' else '',
        'medical_condition': medical_condition,
        'medical_condition_other': medical_condition_other if medical_condition == 'Other' else '',
        'current_medication': current_medication,
        'has_disability': has_disability,
        'disability_detail': disability_detail if has_disability == 'Yes' else '',
        'smoking_habit': smoking_habit,
        'alcohol_consumption': alcohol_consumption,
        'exercise_frequency': exercise_frequency,
        'exercise_type': exercise_type,
        'daily_step_count': int(daily_step_count) if daily_step_count else 0,
        'stress_level': stress_level,
        'attendance_percentage': float(attendance_percentage) if attendance_percentage else 0,
        'work_hours_per_day': float(work_hours_per_day) if work_hours_per_day else 0,
        'doctor_remarks': doctor_remarks,
        'sugar_level': sugar_level
    }

    success, msg = database.save_health_data(user['id'], health_record)
    if success:
        return jsonify({'success': True, 'message': 'Health profile updated successfully.'})
    else:
        return jsonify({'success': False, 'message': msg}), 500

@app.route('/risk-prediction')
def risk_prediction_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    user = dict(user)

    health_data = database.get_health_data(user['id'])
    if not health_data:
        return redirect(url_for('health_data_page'))

    # ========== ENHANCED WELLNESS RISK PREDICTION ==========
    # Uses all available health data for comprehensive scoring
    # Total: 100 points across 8 weighted categories

    # --- User demographic data ---
    user_dob = user.get('dob', '')
    user_gender = user.get('gender', '')
    try:
        dob_date = datetime.strptime(user_dob, '%Y-%m-%d').date()
        age = (date.today() - dob_date).days // 365
    except Exception:
        age = 30  # default

    # === CATEGORY 1: BMI Score (max 15 points, rating 0-100) ===
    bmi = health_data['bmi']
    bmi_cat = health_data['bmi_category']
    if bmi_cat == 'Normal':
        bmi_score_rating = 100
        bmi_score = 15
    elif bmi_cat in ['Overweight', 'Underweight']:
        bmi_score_rating = 65
        bmi_score = 10
    else:  # Obese
        bmi_score_rating = 30
        bmi_score = 4

    # === CATEGORY 2: Blood Pressure Score (max 15 points, rating 0-100) ===
    bp_str = health_data['blood_pressure']
    try:
        systolic, diastolic = map(int, bp_str.split('/'))
    except Exception:
        systolic, diastolic = 120, 80

    if systolic <= 120 and diastolic <= 80:
        bp_score_rating = 100
        bp_score = 15
    elif systolic <= 130 and diastolic <= 85:
        bp_score_rating = 75
        bp_score = 11
    elif systolic <= 140 or diastolic <= 90:
        bp_score_rating = 50
        bp_score = 7
    else:
        bp_score_rating = 25
        bp_score = 3

    # === CATEGORY 3: Hydration Score (max 10 points, rating 0-100) ===
    water = health_data['water_intake']
    if water in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres']:
        water_score_rating = 100
        water_score = 10
    elif water in ['2 Litres', 'More than 4 Litres']:
        water_score_rating = 70
        water_score = 7
    else:  # Less than 2 Litres
        water_score_rating = 30
        water_score = 3

    # === CATEGORY 4: Medical History (max 15 points, rating 0-100) ===
    condition = health_data['medical_condition']
    allergies = health_data['has_allergies']
    disability = health_data['has_disability']
    sugar_level = health_data.get('sugar_level', '')

    medical_points = 15
    medical_risk_rating = 0  # starts low risk

    if condition != 'None':
        medical_points -= 5
        medical_risk_rating += 35
    if allergies == 'Yes':
        medical_points -= 2
        medical_risk_rating += 10
    if disability == 'Yes':
        medical_points -= 2
        medical_risk_rating += 10
    if sugar_level in ['Pre-diabetic', 'Diabetic', 'Low']:
        medical_points -= 3
        medical_risk_rating += 15
    if sugar_level == 'Diabetic':
        medical_points -= 1
        medical_risk_rating += 10

    medical_points = max(0, medical_points)
    medical_risk_rating = min(90, medical_risk_rating)

    # === CATEGORY 5: Lifestyle Score — Smoking & Alcohol (max 12 points, rating 0-100) ===
    smoking = health_data.get('smoking_habit', '')
    alcohol = health_data.get('alcohol_consumption', '')

    lifestyle_points = 12
    if smoking == 'Regular':
        lifestyle_points -= 5
    elif smoking == 'Occasional':
        lifestyle_points -= 3
    elif smoking == 'Former':
        lifestyle_points -= 1

    if alcohol == 'Heavy':
        lifestyle_points -= 5
    elif alcohol == 'Regular':
        lifestyle_points -= 3
    elif alcohol == 'Moderate':
        lifestyle_points -= 1

    lifestyle_points = max(0, lifestyle_points)
    lifestyle_rating = int((lifestyle_points / 12) * 100)

    # === CATEGORY 6: Exercise & Activity Score (max 13 points, rating 0-100) ===
    exercise_freq = health_data.get('exercise_frequency', '')
    exercise_type = health_data.get('exercise_type', '')
    daily_steps = health_data.get('daily_step_count', 0) or 0

    exercise_points = 0
    # Exercise frequency (max 5)
    if exercise_freq == 'Daily':
        exercise_points += 5
    elif exercise_freq == 'Regular':
        exercise_points += 4
    elif exercise_freq == 'Sometimes':
        exercise_points += 3
    elif exercise_freq == 'Rarely':
        exercise_points += 1
    # else Never = 0

    # Exercise type (max 3)
    if exercise_type in ['Gym', 'Swimming', 'Mixed', 'Running']:
        exercise_points += 3
    elif exercise_type in ['Cycling', 'Sports', 'Yoga']:
        exercise_points += 2
    elif exercise_type == 'Walking':
        exercise_points += 1
    # else None = 0

    # Daily steps (max 5)
    if daily_steps >= 10000:
        exercise_points += 5
    elif daily_steps >= 7500:
        exercise_points += 4
    elif daily_steps >= 5000:
        exercise_points += 3
    elif daily_steps >= 3000:
        exercise_points += 2
    elif daily_steps >= 1000:
        exercise_points += 1

    exercise_points = min(13, exercise_points)
    exercise_rating = int((exercise_points / 13) * 100)

    # === CATEGORY 7: Stress & Work-Life Score (max 10 points, rating 0-100) ===
    stress_level = health_data.get('stress_level', '')
    work_hours = health_data.get('work_hours_per_day', 0) or 0
    attendance = health_data.get('attendance_percentage', 0) or 0

    stress_work_points = 10

    if stress_level == 'Very High':
        stress_work_points -= 4
    elif stress_level == 'High':
        stress_work_points -= 3
    elif stress_level == 'Moderate':
        stress_work_points -= 1

    if work_hours > 12:
        stress_work_points -= 3
    elif work_hours > 10:
        stress_work_points -= 2
    elif work_hours > 8:
        stress_work_points -= 1

    # Low attendance can indicate health issues
    if attendance < 60:
        stress_work_points -= 2
    elif attendance < 75:
        stress_work_points -= 1

    stress_work_points = max(0, stress_work_points)
    stress_work_rating = int((stress_work_points / 10) * 100)

    # === CATEGORY 8: Preventive Care Score (max 10 points, rating 0-100) ===
    last_checkup = health_data.get('last_checkup', '')
    next_checkup = health_data.get('next_checkup', '')
    doctor_remarks = health_data.get('doctor_remarks', '')
    health_status = health_data.get('health_status', 'Average')

    preventive_points = 0
    # Last checkup recency (max 4)
    try:
        last_checkup_date = datetime.strptime(last_checkup, '%Y-%m-%d').date()
        days_since_checkup = (date.today() - last_checkup_date).days
        if days_since_checkup <= 90:
            preventive_points += 4
        elif days_since_checkup <= 180:
            preventive_points += 3
        elif days_since_checkup <= 365:
            preventive_points += 2
        else:
            preventive_points += 0
    except Exception:
        preventive_points += 0

    # Next checkup scheduled (max 2)
    try:
        next_checkup_date = datetime.strptime(next_checkup, '%Y-%m-%d').date()
        if next_checkup_date >= date.today():
            preventive_points += 2
        else:
            preventive_points += 0  # overdue
    except Exception:
        preventive_points += 0

    # Health status (max 4)
    if health_status == 'Excellent':
        preventive_points += 4
    elif health_status == 'Good':
        preventive_points += 3
    elif health_status == 'Average':
        preventive_points += 2
    else:
        preventive_points += 0

    preventive_points = min(10, preventive_points)
    preventive_rating = int((preventive_points / 10) * 100)

    # === OVERALL WELLNESS SCORE (max 100) ===
    wellness_score = (bmi_score + bp_score + water_score + medical_points +
                      lifestyle_points + exercise_points + stress_work_points + preventive_points)
    wellness_score = min(100, max(0, int(wellness_score)))

    # Risk Percentage & Category
    risk_percentage = 100 - wellness_score
    if wellness_score >= 80:
        risk_category = 'Low Risk'
    elif wellness_score >= 50:
        risk_category = 'Moderate Risk'
    else:
        risk_category = 'High Risk'

    # === DYNAMIC AI NARRATIVE ===
    narrative = []

    # Age context
    if age >= 50:
        narrative.append(f"At age {age}, proactive health monitoring becomes critical. Age-related cardiovascular and metabolic risks require consistent preventive care.")
    elif age >= 40:
        narrative.append(f"At age {age}, pay close attention to metabolic markers like blood pressure, BMI, and blood sugar as risk factors increase after 40.")

    # BMI narrative
    if bmi_cat == 'Obese':
        narrative.append(f"Your BMI is classified as Obese ({bmi:.1f}). This elevates your risk of strain on joints, respiratory difficulty, and cardiovascular disease.")
    elif bmi_cat == 'Overweight':
        narrative.append(f"Your BMI indicates you are Overweight ({bmi:.1f}). Adopting portion controls and introducing regular aerobic workouts will help reduce metabolic load.")
    elif bmi_cat == 'Underweight':
        narrative.append(f"Your BMI indicates you are Underweight ({bmi:.1f}). Focus on building lean muscle mass and optimizing calorie intake.")
    else:
        narrative.append(f"Your BMI is in the healthy, Normal range ({bmi:.1f}). Keep up the balanced diet.")

    # BP narrative
    if systolic > 140 or diastolic > 90:
        narrative.append(f"Your Blood Pressure is elevated at Stage 2 Hypertension ({bp_str} mmHg). Consistent monitoring, reduced salt intake, and speaking with a physician is highly recommended.")
    elif systolic > 130 or diastolic > 85:
        narrative.append(f"Your Blood Pressure indicates mild pre-hypertension ({bp_str} mmHg). Focus on stress management and dietary regulation.")
    else:
        narrative.append(f"Your Blood Pressure is optimal ({bp_str} mmHg), pointing to a strong cardiovascular foundation.")

    # Sugar level narrative
    if sugar_level == 'Diabetic':
        narrative.append("Your blood sugar level is in the Diabetic range (126+ mg/dL). Strict glycemic control through diet, medication, and regular monitoring is essential.")
    elif sugar_level == 'Pre-diabetic':
        narrative.append("Your blood sugar is in the Pre-diabetic range (100-125 mg/dL). Lifestyle modifications including reduced sugar intake and increased physical activity can prevent progression to diabetes.")
    elif sugar_level == 'Low':
        narrative.append("Your blood sugar is below normal (<70 mg/dL). Frequent small meals and monitoring for hypoglycemic episodes is recommended.")

    # Water intake narrative
    if water == 'Less than 2 Litres':
        narrative.append("Your daily water intake is low. Dehydration affects kidney health, skin, and triggers early muscle fatigue during activities.")
    elif water in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres']:
        narrative.append("You maintain excellent daily hydration levels, supporting normal detoxification and digestion.")
    else:
        narrative.append("Your water intake is moderate, but could be adjusted upwards to optimize daily energy.")

    # Smoking narrative
    if smoking == 'Regular':
        narrative.append("Regular smoking significantly increases your risk of lung disease, cardiovascular events, and cancer. Smoking cessation programs can dramatically improve long-term health outcomes.")
    elif smoking == 'Occasional':
        narrative.append("Even occasional smoking contributes to arterial damage and reduced lung capacity. Consider gradually eliminating this habit.")

    # Alcohol narrative
    if alcohol == 'Heavy':
        narrative.append("Heavy alcohol consumption places severe strain on your liver, nervous system, and cardiovascular health. Reducing intake is strongly recommended.")
    elif alcohol == 'Regular':
        narrative.append("Regular alcohol intake can impact liver function and blood pressure over time. Moderating consumption will help preserve metabolic health.")

    # Stress & work narrative
    if stress_level in ['Very High', 'High']:
        narrative.append(f"Your reported stress level is {stress_level}. Chronic stress elevates cortisol, disrupts sleep, and increases cardiovascular risk. Active stress management is essential.")
    if work_hours > 10:
        narrative.append(f"Working {work_hours:.0f} hours per day may contribute to burnout and chronic fatigue. Aim for better work-life balance to sustain long-term productivity and health.")

    # Exercise narrative
    if exercise_freq in ['Never', 'Rarely', '']:
        narrative.append("Your physical activity level is insufficient. The WHO recommends at least 150 minutes of moderate exercise per week for adults.")
    elif exercise_freq == 'Daily' and daily_steps >= 10000:
        narrative.append(f"Excellent physical activity with {daily_steps:,} daily steps and daily exercise. This supports strong cardiovascular and metabolic health.")

    # Medical conditions
    if condition != 'None':
        cond_name = condition if condition != 'Other' else health_data['medical_condition_other']
        narrative.append(f"Your diagnosed condition ({cond_name}) is a primary risk contributor. Regular medical review is necessary.")

    if allergies == 'Yes':
        narrative.append(f"Take care to minimize exposure to allergens ({health_data['allergies_detail']}) to control systemic immune stress.")

    # Doctor remarks
    if doctor_remarks and len(doctor_remarks.strip()) > 0:
        narrative.append(f"Doctor's remarks noted: \"{doctor_remarks}\". Please follow any prescribed advice and schedule follow-ups accordingly.")

    # Checkup compliance
    try:
        if days_since_checkup > 365:
            narrative.append(f"Your last health check-up was over {days_since_checkup // 30} months ago. Scheduling an annual preventive screening is strongly recommended.")
    except Exception:
        pass

    ai_summary = " ".join(narrative)

    return render_template(
        'risk_prediction.html',
        username=session['username'],
        profile_photo=user['profile_photo'] if user else None,
        health_data=health_data,
        wellness_score=wellness_score,
        risk_percentage=risk_percentage,
        risk_category=risk_category,
        bmi_score_rating=bmi_score_rating,
        bp_score_rating=bp_score_rating,
        water_score_rating=water_score_rating,
        medical_risk_rating=medical_risk_rating,
        lifestyle_rating=lifestyle_rating,
        exercise_rating=exercise_rating,
        stress_work_rating=stress_work_rating,
        preventive_rating=preventive_rating,
        ai_summary=ai_summary
    )

@app.route('/recommendations')
def recommendations_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    health_data = database.get_health_data(user['id'])
    if not health_data:
        return redirect(url_for('health_data_page'))

    # ── Pull all health fields ──────────────────────────────────────────
    bmi_cat       = health_data.get('bmi_category', '') or ''
    bmi_val       = float(health_data.get('bmi', 0) or 0)
    bp_str        = health_data.get('blood_pressure', '120/80') or '120/80'
    water         = health_data.get('water_intake', '') or ''
    condition     = health_data.get('medical_condition', 'None') or 'None'
    cond_other    = health_data.get('medical_condition_other', '') or ''
    allergies     = health_data.get('has_allergies', '') or ''
    disability    = health_data.get('has_disability', '') or ''
    sugar_level   = health_data.get('sugar_level', '') or ''
    smoking       = health_data.get('smoking_habit', '') or ''
    alcohol       = health_data.get('alcohol_consumption', '') or ''
    exercise_freq = health_data.get('exercise_frequency', '') or ''
    exercise_type = health_data.get('exercise_type', '') or ''
    daily_steps   = int(health_data.get('daily_step_count', 0) or 0)
    stress_level  = health_data.get('stress_level', '') or ''
    work_hours    = float(health_data.get('work_hours_per_day', 0) or 0)
    attendance    = float(health_data.get('attendance_percentage', 0) or 0)
    dr_remarks    = (health_data.get('doctor_remarks', '') or '').strip()
    last_checkup  = health_data.get('last_checkup', '') or ''
    next_checkup  = health_data.get('next_checkup', '') or ''
    health_status = health_data.get('health_status', 'Average') or 'Average'
    current_med   = (health_data.get('current_medication', '') or '').strip()
    cond_label    = cond_other if condition == 'Other' else condition

    try:
        systolic, diastolic = map(int, bp_str.split('/'))
    except Exception:
        systolic, diastolic = 120, 80

    # ── Re-compute wellness score for risk level ─────────────────────────
    _bmi_sc = 15 if bmi_cat == 'Normal' else (10 if bmi_cat in ['Overweight','Underweight'] else 4)
    _bp_sc  = (15 if systolic <= 120 and diastolic <= 80 else
               11 if systolic <= 130 and diastolic <= 85 else
               7  if systolic <= 140 or  diastolic <= 90 else 3)
    _w_sc   = (10 if water in ['3 Litres','3.5 Litres','4 Litres','2.5 Litres'] else
               7  if water in ['2 Litres','More than 4 Litres'] else 3)
    _m = 15
    if condition != 'None': _m -= 5
    if allergies == 'Yes':  _m -= 2
    if disability == 'Yes': _m -= 2
    if sugar_level in ['Pre-diabetic','Diabetic','Low']: _m -= 3
    if sugar_level == 'Diabetic': _m -= 1
    _m = max(0, _m)
    _l = 12
    if smoking == 'Regular': _l -= 5
    elif smoking == 'Occasional': _l -= 3
    elif smoking == 'Former': _l -= 1
    if alcohol == 'Heavy': _l -= 5
    elif alcohol == 'Regular': _l -= 3
    elif alcohol in ['Moderate','Occasional']: _l -= 1
    _l = max(0, _l)
    _e = 0
    if exercise_freq == 'Daily': _e += 5
    elif exercise_freq == 'Regular': _e += 4
    elif exercise_freq == 'Sometimes': _e += 3
    elif exercise_freq == 'Rarely': _e += 1
    if exercise_type in ['Gym','Swimming','Mixed','Running']: _e += 3
    elif exercise_type in ['Cycling','Sports','Yoga']: _e += 2
    elif exercise_type == 'Walking': _e += 1
    if daily_steps >= 10000: _e += 5
    elif daily_steps >= 7500: _e += 4
    elif daily_steps >= 5000: _e += 3
    elif daily_steps >= 3000: _e += 2
    elif daily_steps >= 1000: _e += 1
    _e = min(13, _e)
    _sw = 10
    if stress_level == 'Very High': _sw -= 4
    elif stress_level == 'High': _sw -= 3
    elif stress_level == 'Moderate': _sw -= 1
    if work_hours > 12: _sw -= 3
    elif work_hours > 10: _sw -= 2
    elif work_hours > 8: _sw -= 1
    if attendance < 60: _sw -= 2
    elif attendance < 75: _sw -= 1
    _sw = max(0, _sw)
    _pv = 0
    days_since_checkup = 9999
    days_to_checkup = -1
    try:
        _lc = datetime.strptime(last_checkup, '%Y-%m-%d').date()
        days_since_checkup = (date.today() - _lc).days
        if days_since_checkup <= 90: _pv += 4
        elif days_since_checkup <= 180: _pv += 3
        elif days_since_checkup <= 365: _pv += 2
    except Exception:
        pass
    try:
        _nc = datetime.strptime(next_checkup, '%Y-%m-%d').date()
        days_to_checkup = (_nc - date.today()).days
        if days_to_checkup >= 0: _pv += 2
    except Exception:
        pass
    if health_status == 'Excellent': _pv += 4
    elif health_status == 'Good': _pv += 3
    elif health_status == 'Average': _pv += 2
    _pv = min(10, _pv)
    wellness_score = min(100, max(0, _bmi_sc + _bp_sc + _w_sc + _m + _l + _e + _sw + _pv))
    risk_level = 'Low Risk' if wellness_score >= 80 else ('Moderate Risk' if wellness_score >= 50 else 'High Risk')

    recommendations = []

    # ── 1. HEALTHY DIET ──────────────────────────────────────────────────
    if sugar_level == 'Diabetic' and bmi_cat in ['Obese','Overweight']:
        recommendations.append({
            'icon': 'fa-wheat-awn-circle-exclamation',
            'icon_bg': 'linear-gradient(135deg, #ef4444 0%, #7f1d1d 100%)',
            'priority': 'High',
            'title': 'Diabetic-Friendly Weight Reduction Diet',
            'description': (
                f'Your profile shows Diabetic blood sugar with a {bmi_cat} BMI ({bmi_val:.1f}). '
                'Eliminate white rice, refined flour, and sugary drinks. Focus on moong dal, bitter gourd, oats, '
                'and grilled protein. Eat every 3 hours in small portions to prevent glucose spikes.'
            ),
            'benefit': 'Dual control of glucose and body weight reduces risk of diabetic complications and cardiovascular events.'
        })
    elif sugar_level == 'Diabetic':
        recommendations.append({
            'icon': 'fa-wheat-awn-circle-exclamation',
            'icon_bg': 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
            'priority': 'High',
            'title': 'Strict Glycemic Control Diet Plan',
            'description': (
                'Your blood sugar is in the Diabetic range. Limit simple carbohydrates to under 45g per meal. '
                'Replace white rice with brown rice or millets. Swap sugary snacks with roasted chickpeas or cucumber. '
                'Include chromium-rich foods like broccoli and barley to improve insulin sensitivity.'
            ),
            'benefit': 'Stabilises HbA1c and reduces risk of neuropathy, retinopathy, and kidney disease progression.'
        })
    elif sugar_level == 'Pre-diabetic':
        recommendations.append({
            'icon': 'fa-wheat-awn',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
            'priority': 'Medium',
            'title': 'Pre-Diabetic Reversal Diet',
            'description': (
                'Your blood sugar is Pre-diabetic (100-125 mg/dL). Adopt a low-GI, high-fibre diet: replace maida '
                'with whole wheat or ragi alternatives. Add 1 tablespoon of chia seeds daily. '
                'Avoid fruit juices; consume whole fruits with the skin to slow glucose absorption.'
            ),
            'benefit': 'Diet alone can reverse pre-diabetes in 58% of cases within 12 months.'
        })
    elif sugar_level == 'Low':
        recommendations.append({
            'icon': 'fa-apple-whole',
            'icon_bg': 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            'priority': 'High',
            'title': 'Hypoglycemia Prevention Diet',
            'description': (
                'Your blood sugar is below normal (hypoglycemic). Never skip meals — eat every 2-3 hours. '
                'Include complex carbs with protein at every meal: banana + peanut butter, whole grain toast + eggs. '
                'Keep glucose tablets or raisins with you at all times.'
            ),
            'benefit': 'Prevents dangerous hypoglycemic episodes and dizziness during work hours.'
        })
    elif bmi_cat == 'Obese':
        recommendations.append({
            'icon': 'fa-weight-scale',
            'icon_bg': 'linear-gradient(135deg, #ef4444 0%, #c2410c 100%)',
            'priority': 'High',
            'title': f'Caloric Deficit Plan — BMI {bmi_val:.1f} (Obese)',
            'description': (
                f'Target a 500-700 kcal daily deficit. Remove all fried foods, packaged snacks, and full-fat dairy. '
                'Build every meal around a palm-sized protein (eggs, paneer, fish), half a plate of vegetables, '
                'and a quarter plate of complex carbs. Track meals for 30 days.'
            ),
            'benefit': 'Sustainable deficit eliminates visceral fat, reducing metabolic disease burden significantly.'
        })
    elif bmi_cat == 'Overweight':
        recommendations.append({
            'icon': 'fa-salad',
            'icon_bg': 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
            'priority': 'Medium',
            'title': f'Portion Control Plan — BMI {bmi_val:.1f} (Overweight)',
            'description': (
                'Use the plate method: 50% non-starchy vegetables, 25% lean protein (chicken, dal, tofu), '
                '25% complex carbs (quinoa, oats). Eat dinner at least 2.5 hours before bedtime '
                'and eliminate post-dinner snacking entirely.'
            ),
            'benefit': 'Promotes 0.5-1 kg/week steady weight loss without muscle loss.'
        })
    elif bmi_cat == 'Underweight':
        recommendations.append({
            'icon': 'fa-egg',
            'icon_bg': 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            'priority': 'High',
            'title': f'Weight Gain Protocol — BMI {bmi_val:.1f} (Underweight)',
            'description': (
                'Add 300-500 kcal above maintenance daily. Eat 5-6 meals. '
                'Include: 2 tablespoons peanut butter, 2 whole eggs, full-fat milk, mixed nuts, and half an avocado daily. '
                'Add protein shakes between meals if appetite is low.'
            ),
            'benefit': 'Builds lean mass, restores hormone balance, and strengthens bone density.'
        })
    elif systolic > 140 or diastolic > 90:
        recommendations.append({
            'icon': 'fa-heart',
            'icon_bg': 'linear-gradient(135deg, #e11d48 0%, #9f1239 100%)',
            'priority': 'High',
            'title': f'Stage 2 Hypertension DASH Diet ({bp_str} mmHg)',
            'description': (
                f'Blood pressure {bp_str} indicates Stage 2 Hypertension. Follow DASH strictly: '
                'limit sodium to 1,500 mg/day. Eliminate pickles, papads, and processed foods. '
                'Increase potassium with sweet potatoes, spinach, and bananas.'
            ),
            'benefit': 'DASH diet alone can lower systolic BP by 8-14 mmHg — comparable to an antihypertensive drug.'
        })
    elif systolic > 130 or diastolic > 85:
        recommendations.append({
            'icon': 'fa-heart-pulse',
            'icon_bg': 'linear-gradient(135deg, #e11d48 0%, #be123c 100%)',
            'priority': 'Medium',
            'title': f'Anti-Hypertensive Diet ({bp_str} mmHg)',
            'description': (
                f'BP {bp_str} indicates pre-hypertension. Reduce sodium to 2,000 mg/day. '
                'Remove table salt from meals, replace with lemon juice and herbs. '
                'Include 2 cloves of raw garlic daily and drink hibiscus tea to support arterial flexibility.'
            ),
            'benefit': 'Prevents progression to Stage 1 hypertension, reduces cardiovascular risk by 20%.'
        })
    elif condition != 'None':
        recommendations.append({
            'icon': 'fa-notes-medical',
            'icon_bg': 'linear-gradient(135deg, #0ea5e9 0%, #0369a1 100%)',
            'priority': 'Medium',
            'title': f'Medical Condition-Adapted Diet ({cond_label})',
            'description': (
                f'You have a diagnosed condition: {cond_label}. '
                'Avoid inflammatory foods — refined sugars, trans fats, and processed meats. '
                'Eat anti-inflammatory foods daily: turmeric milk, fatty fish (omega-3), green leafy vegetables, and berries. '
                'Follow any dietary prescriptions from your physician precisely.'
            ),
            'benefit': 'Reduces systemic inflammation and supports pharmaceutical treatment effectiveness.'
        })
    else:
        recommendations.append({
            'icon': 'fa-leaf',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            'priority': 'Low',
            'title': 'Antioxidant & Longevity Wellness Diet',
            'description': (
                'Your metabolic markers are healthy. Maintain a Mediterranean-inspired diet: '
                'extra virgin olive oil as your primary fat, 2-3 servings of fatty fish per week, '
                'a handful of walnuts and almonds daily, 5 servings of colourful vegetables. '
                'Limit red meat to once a week and add fermented foods (curd, kimchi) for gut health.'
            ),
            'benefit': 'Reduces all-cause mortality risk and supports long-term cognitive function.'
        })

    # ── 2. EXERCISE PLAN ────────────────────────────────────────────────
    if exercise_freq in ['Never', '', 'Rarely'] and daily_steps < 3000:
        priority = 'High' if bmi_cat in ['Obese','Overweight'] or systolic > 130 else 'Medium'
        recommendations.append({
            'icon': 'fa-person-walking',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
            'priority': priority,
            'title': 'Beginner Movement Plan — Start from Zero',
            'description': (
                f'You are currently sedentary (frequency: "{exercise_freq or "None"}", steps: {daily_steps:,}/day). '
                'Week 1-2: Walk 15 min morning and 15 min after dinner. '
                'Week 3-4: Increase to 30-min brisk walks. '
                'Week 5+: Add bodyweight exercises — 10 squats, 10 push-ups, 10 lunges, 3 sets every alternate day.'
            ),
            'benefit': '30 minutes of daily walking reduces cardiovascular mortality risk by 35% in sedentary individuals.'
        })
    elif daily_steps < 5000 or exercise_freq == 'Rarely':
        recommendations.append({
            'icon': 'fa-person-biking',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #b45309 100%)',
            'priority': 'Medium',
            'title': f'Gradual Activity Escalation — {daily_steps:,} steps/day',
            'description': (
                f'Your activity is below optimal ({daily_steps:,} steps/day, "{exercise_freq}"). '
                'Target 7,500 steps daily within a month. Add a 20-min cycling or swimming session twice a week. '
                'Take stairs instead of lifts and park farther from your workplace.'
            ),
            'benefit': 'Achieving 7,500 steps/day improves insulin sensitivity by 25% and reduces visceral fat accumulation.'
        })
    elif exercise_freq in ['Daily','Regular'] and daily_steps >= 10000:
        ex_upgrade = 'HIIT intervals' if exercise_type in ['Running','Gym','Mixed'] else 'resistance band training'
        recommendations.append({
            'icon': 'fa-dumbbell',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #047857 100%)',
            'priority': 'Low',
            'title': f'Performance Optimisation — {daily_steps:,} steps/day',
            'description': (
                f'Excellent activity: {daily_steps:,} steps/day, {exercise_freq} {exercise_type or "exercise"}. '
                f'Level up with {ex_upgrade} twice a week. '
                'Consider quarterly VO2 max or resting heart rate measurement to track cardiovascular fitness gains.'
            ),
            'benefit': 'Progressive overload builds cardiovascular reserve and metabolic efficiency beyond baseline fitness.'
        })
    else:
        rec_type = 'yoga and stretching' if stress_level in ['High','Very High'] else 'interval training'
        recommendations.append({
            'icon': 'fa-person-running',
            'icon_bg': 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            'priority': 'Medium',
            'title': f'Structured Weekly Routine with {rec_type.title()}',
            'description': (
                f'You exercise {exercise_freq.lower() or "sometimes"} ({exercise_type or "mixed"}), {daily_steps:,} steps/day. '
                f'Build a fixed 4-day/week schedule: 2 cardio days + 2 {rec_type} days. '
                'Target at least 150 minutes of moderate exercise weekly.'
            ),
            'benefit': 'Structured routines improve adherence by 60% versus unplanned activity and drive compound fitness gains.'
        })

    # ── 3. WATER INTAKE ──────────────────────────────────────────────────
    if water == 'Less than 2 Litres':
        target = '3.5 Litres' if bmi_cat in ['Obese','Overweight'] or exercise_freq in ['Daily','Regular'] else '2.5-3 Litres'
        recommendations.append({
            'icon': 'fa-bottle-water',
            'icon_bg': 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',
            'priority': 'High',
            'title': f'Critical Hydration Upgrade — Target {target}/Day',
            'description': (
                'You drink less than 2 litres daily — well below the healthy threshold. '
                'Set a phone alarm every 60 minutes to drink 250 ml. '
                'Keep a 1-litre bottle at your desk and refill it twice during work. '
                'Add cucumber, lemon, or mint slices to improve palatability.'
            ),
            'benefit': 'Proper hydration improves kidney filtration, boosts energy by 25%, and supports fat metabolism.'
        })
    elif water == 'More than 4 Litres':
        recommendations.append({
            'icon': 'fa-droplet-slash',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
            'priority': 'Medium',
            'title': 'Electrolyte Balance — Avoid Over-Hydration',
            'description': (
                'Drinking more than 4 litres daily can dilute blood sodium (hyponatremia). '
                'Reduce to 3-3.5 litres unless exercising intensely. '
                'Replenish electrolytes post-exercise with coconut water or a pinch of Himalayan salt in water.'
            ),
            'benefit': 'Maintains optimal blood osmolarity and prevents fatigue and cramps from electrolyte imbalances.'
        })
    elif water == '2 Litres':
        recommendations.append({
            'icon': 'fa-glass-water-droplet',
            'icon_bg': 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
            'priority': 'Medium',
            'title': 'Increase Hydration to Optimal Range',
            'description': (
                'You drink 2 litres daily — close but below optimal. Increase to 2.5-3 litres. '
                'Add one extra 500 ml bottle during lunch and another in the evening. '
                'Eat high-water-content foods: cucumber, watermelon, oranges, and tomatoes daily.'
            ),
            'benefit': 'Optimal hydration improves skin health, digestion, and reduces urinary tract infection risk.'
        })
    else:
        recommendations.append({
            'icon': 'fa-circle-check',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            'priority': 'Low',
            'title': f'Maintain Excellent Hydration ({water})',
            'description': (
                f'Your water intake ({water}) is in the ideal range. '
                'Pre-hydrate with 500 ml 30 minutes before exercise. '
                'Drink 200 ml of warm water first thing each morning to kickstart digestion and metabolism.'
            ),
            'benefit': 'Sustained optimal hydration supports peak cellular metabolism, detoxification, and joint lubrication.'
        })

    # ── 4. SLEEP IMPROVEMENT ─────────────────────────────────────────────
    if work_hours > 12 and stress_level in ['High','Very High']:
        recommendations.append({
            'icon': 'fa-bed',
            'icon_bg': 'linear-gradient(135deg, #4f46e5 0%, #1e1b4b 100%)',
            'priority': 'High',
            'title': f'Critical Sleep Restoration — {work_hours:.0f} hrs/day + {stress_level} Stress',
            'description': (
                f'Working {work_hours:.0f} hrs/day with {stress_level.lower()} stress severely disrupts sleep. '
                'Implement a non-negotiable digital sunset 60 minutes before bed. '
                'Use blackout curtains, keep bedroom at 18-20°C. '
                'Practice 4-7-8 breathing for 3 cycles before sleeping. Target 7.5-8 hrs.'
            ),
            'benefit': 'Restorative sleep reduces cortisol by 30%, improves decision-making, and repairs cardiac tissue.'
        })
    elif work_hours > 10 or stress_level == 'High':
        recommendations.append({
            'icon': 'fa-bed',
            'icon_bg': 'linear-gradient(135deg, #4f46e5 0%, #312e81 100%)',
            'priority': 'High',
            'title': 'Sleep Hygiene & Recovery Protocol',
            'description': (
                f'Elevated work hours ({work_hours:.0f} hrs/day) or {stress_level.lower()} stress are disrupting recovery. '
                'Stop all work tasks by 9 PM. Avoid caffeine after 2 PM. '
                'Create a 20-minute wind-down: light stretching, warm shower, 5 minutes of journaling. '
                'Use a white noise app to block disturbances.'
            ),
            'benefit': 'Consistent sleep hygiene increases REM cycles, boosting memory consolidation and immune function.'
        })
    elif stress_level == 'Moderate' or work_hours > 8:
        recommendations.append({
            'icon': 'fa-moon',
            'icon_bg': 'linear-gradient(135deg, #6366f1 0%, #4338ca 100%)',
            'priority': 'Medium',
            'title': 'Circadian Rhythm Alignment',
            'description': (
                'Maintain consistent wake and sleep times — even on weekends. '
                'Avoid naps longer than 20 minutes after 3 PM. '
                'Expose yourself to natural morning sunlight for 10 minutes within 30 minutes of waking to anchor your body clock.'
            ),
            'benefit': 'Aligned circadian rhythms optimise daytime cortisol, energy, and hormonal balance.'
        })
    else:
        recommendations.append({
            'icon': 'fa-moon',
            'icon_bg': 'linear-gradient(135deg, #6366f1 0%, #4338ca 100%)',
            'priority': 'Low',
            'title': 'Sleep Quality Enhancement',
            'description': (
                'Your workload and stress are manageable. To enhance sleep quality further: '
                'keep a fixed 7.5-8 hour sleep window, avoid heavy meals within 2 hours of sleeping, '
                'and do a 10-minute gratitude journal session before bed to calm the mind.'
            ),
            'benefit': 'Deep sleep stages support hormonal recovery, fat metabolism overnight, and cardiovascular health.'
        })

    # ── 5. STRESS MANAGEMENT ─────────────────────────────────────────────
    if stress_level == 'Very High':
        recommendations.append({
            'icon': 'fa-brain',
            'icon_bg': 'linear-gradient(135deg, #8b5cf6 0%, #5b21b6 100%)',
            'priority': 'High',
            'title': 'Urgent Stress Intervention Plan',
            'description': (
                'Your stress level is Very High — immediate action required. '
                'Begin daily 15-minute mindfulness meditation (Headspace, Calm, or Insight Timer). '
                'Schedule a mental health check-in with HR or a professional counsellor. '
                'Practice box breathing (4 counts in, 4 hold, 4 out, 4 hold) during stressful moments. '
                'Disconnect from all devices for 2 continuous hours each evening.'
            ),
            'benefit': 'Reduces elevated cortisol by up to 40%, lowering cardiovascular event risk and improving emotional regulation.'
        })
    elif stress_level == 'High':
        recommendations.append({
            'icon': 'fa-brain',
            'icon_bg': 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
            'priority': 'High',
            'title': 'Cortisol Control & Nervous System Reset',
            'description': (
                'High stress elevates cortisol chronically, impairing immunity and sleep. '
                'Add a 10-minute midday walk outside — natural light is a proven cortisol reducer. '
                'Practice diaphragmatic breathing (4-7-8 method) twice daily. '
                'Journal 3 gratitude points each evening to shift cognitive focus.'
            ),
            'benefit': 'Reduces physiological stress markers and prevents stress-related hypertension and gut disorders.'
        })
    elif stress_level == 'Moderate':
        recommendations.append({
            'icon': 'fa-spa',
            'icon_bg': 'linear-gradient(135deg, #a855f7 0%, #9333ea 100%)',
            'priority': 'Medium',
            'title': 'Proactive Stress Buffer Habits',
            'description': (
                'Build stress resilience with 3 micro-breaks per day (5 minutes each): '
                'step away from your screen, stretch, and breathe. '
                'Add one weekly hobby activity (music, cooking, gardening) that disengages your analytical mind completely.'
            ),
            'benefit': 'Proactive stress management prevents burnout escalation and reduces absenteeism risk by 28%.'
        })
    else:
        recommendations.append({
            'icon': 'fa-face-smile',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            'priority': 'Low',
            'title': 'Maintain Positive Stress Resilience',
            'description': (
                'Your stress level is well-managed. Sustain this with regular social connections — '
                'eat lunch with colleagues, join a team activity, or call a friend weekly. '
                'Continue any current mindfulness or relaxation practices you already follow.'
            ),
            'benefit': 'Social connectedness reduces mortality risk by 50% and is the strongest predictor of mental health longevity.'
        })

    # ── 6. SMOKING CESSATION (only if applicable) ───────────────────────
    if smoking == 'Regular':
        recommendations.append({
            'icon': 'fa-ban-smoking',
            'icon_bg': 'linear-gradient(135deg, #ef4444 0%, #7f1d1d 100%)',
            'priority': 'High',
            'title': 'Structured Smoking Cessation Plan',
            'description': (
                'You are a regular smoker — the single highest-impact change you can make. '
                'Set a quit date within 14 days. Speak to your physician about Nicotine Replacement Therapy (patches, gums, lozenges). '
                'Download the "Smoke Free" app to track smoke-free hours. '
                'Replace every smoking break with a 3-minute breathing walk outside.'
            ),
            'benefit': 'Quitting reduces lung cancer risk by 50% in 10 years; cardiovascular risk returns to near-normal within 5 years.'
        })
    elif smoking == 'Occasional':
        recommendations.append({
            'icon': 'fa-ban-smoking',
            'icon_bg': 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
            'priority': 'High',
            'title': 'Eliminate Occasional Smoking Habit',
            'description': (
                'Even occasional smoking causes arterial inflammation and DNA damage. '
                'Identify your top 3 triggers (stress, after meals, social settings) and create a substitute habit for each. '
                'Join an online cessation community for peer accountability. '
                'Avoid alcohol temporarily as it often triggers smoking urges.'
            ),
            'benefit': 'Complete cessation improves lung capacity and reverses arterial stiffness within 3 months.'
        })
    elif smoking == 'Former':
        recommendations.append({
            'icon': 'fa-circle-check',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #047857 100%)',
            'priority': 'Low',
            'title': 'Sustain Your Smoke-Free Status',
            'description': (
                'Well done on quitting! Protect your progress: avoid situations that previously triggered smoking urges. '
                'Monitor lung health annually with spirometry. '
                'Eat antioxidant-rich foods (berries, citrus, leafy greens) to support ongoing lung tissue repair.'
            ),
            'benefit': 'Continued smoke-free living allows lung function to recover and reduces residual carcinogen exposure.'
        })

    # ── 7. ALCOHOL REDUCTION (only if applicable) ───────────────────────
    if alcohol == 'Heavy':
        recommendations.append({
            'icon': 'fa-glass-empty',
            'icon_bg': 'linear-gradient(135deg, #f97316 0%, #7c2d12 100%)',
            'priority': 'High',
            'title': 'Medically-Supervised Alcohol Reduction',
            'description': (
                'Heavy alcohol consumption is causing significant liver, cardiovascular, and neurological strain. '
                'Do not attempt abrupt cessation without physician guidance (withdrawal can be dangerous). '
                'Reduce by 1-2 drinks per week progressively. '
                'Replace alcohol with sparkling water with lime, kombucha, or herbal teas. '
                'Seek an addiction specialist — this is a medical matter, not a willpower issue.'
            ),
            'benefit': 'Reducing from heavy to moderate intake reverses early liver fibrosis and lowers cardiac arrhythmia risk.'
        })
    elif alcohol == 'Regular':
        recommendations.append({
            'icon': 'fa-glass-empty',
            'icon_bg': 'linear-gradient(135deg, #f97316 0%, #c2410c 100%)',
            'priority': 'High',
            'title': 'Structured Alcohol Moderation Plan',
            'description': (
                'Regular alcohol raises blood pressure, disrupts sleep, and contributes to weight gain. '
                'Commit to at least 4 alcohol-free days per week. On drinking days, limit to 1 standard drink. '
                'Track your weekly units using the "Drinkaware" app.'
            ),
            'benefit': 'Cutting regular alcohol reduces liver enzyme levels within 4 weeks and measurably improves sleep depth.'
        })
    elif alcohol in ['Occasional','Moderate']:
        recommendations.append({
            'icon': 'fa-wine-glass',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #b45309 100%)',
            'priority': 'Medium',
            'title': f'Mindful Alcohol Awareness ({alcohol})',
            'description': (
                f'Your alcohol intake is {alcohol.lower()}. Keep consumption below the safe threshold: '
                'max 14 units/week with at least 2 consecutive dry days. '
                'Drink a full glass of water between each alcoholic drink and avoid mixing alcohol with high-fat foods.'
            ),
            'benefit': 'Staying within safe limits prevents cumulative liver load and maintains healthy blood triglyceride levels.'
        })

    # ── 8. LIFESTYLE IMPROVEMENTS ────────────────────────────────────────
    lifestyle_added = 0
    if work_hours > 12:
        recommendations.append({
            'icon': 'fa-clock-rotate-left',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #92400e 100%)',
            'priority': 'High',
            'title': f'Critical Work Hours Restructuring ({work_hours:.0f} hrs/day)',
            'description': (
                f'Working {work_hours:.0f} hours daily exceeds safe occupational limits. '
                'Have a direct conversation with your manager about workload redistribution. '
                'Delegate lower-priority tasks and enforce a hard stop at 7 PM. '
                'Use the Pomodoro technique (25-min work + 5-min break) to improve per-hour output.'
            ),
            'benefit': 'Reducing below 10 hrs/day lowers burnout risk by 55% and prevents cardiovascular wear.'
        })
        lifestyle_added += 1
    elif work_hours > 10:
        recommendations.append({
            'icon': 'fa-briefcase',
            'icon_bg': 'linear-gradient(135deg, #f59e0b 0%, #b45309 100%)',
            'priority': 'High',
            'title': f'Work-Life Boundary Management ({work_hours:.0f} hrs/day)',
            'description': (
                f'At {work_hours:.0f} hrs/day, you are exceeding recommended limits. '
                'Block 30-minute lunch breaks as non-negotiable calendar events. '
                'Log off devices by 8:30 PM — communicate this clearly to your team. '
                'Use Friday evenings to plan the following week to avoid overrunning into personal time.'
            ),
            'benefit': 'Protected personal time reduces cortisol accumulation and improves weekly productivity paradoxically.'
        })
        lifestyle_added += 1
    if attendance < 70:
        recommendations.append({
            'icon': 'fa-calendar-day',
            'icon_bg': 'linear-gradient(135deg, #6b7280 0%, #1f2937 100%)',
            'priority': 'High',
            'title': f'Attendance Recovery Plan ({attendance:.0f}%)',
            'description': (
                f'Your attendance is {attendance:.0f}% — significantly below healthy levels. '
                'Work with HR to explore a graduated return plan or health accommodation. '
                'Address the root health cause first (medical condition or stress/burnout). '
                'Prioritise consistency — even 60% attendance while recovering is progress.'
            ),
            'benefit': 'A supported return plan reduces chronic absence while protecting long-term employability and health.'
        })
        lifestyle_added += 1
    elif attendance < 85:
        recommendations.append({
            'icon': 'fa-calendar-check',
            'icon_bg': 'linear-gradient(135deg, #6b7280 0%, #374151 100%)',
            'priority': 'Medium',
            'title': f'Attendance Stabilisation Strategy ({attendance:.0f}%)',
            'description': (
                f'Your attendance is {attendance:.0f}%. Identify your most common absence trigger '
                '(illness, fatigue, or personal stress) and address it directly. '
                'Build a consistent morning routine: fixed wake time, light breakfast, and 5-min planning.'
            ),
            'benefit': 'Higher attendance correlates with stronger social support, lower stress, and career growth.'
        })
        lifestyle_added += 1
    if lifestyle_added == 0:
        recommendations.append({
            'icon': 'fa-trophy',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #047857 100%)',
            'priority': 'Low',
            'title': 'Sustain Healthy Work-Life Integration',
            'description': (
                f'Your work hours ({work_hours:.0f} hrs/day) and attendance ({attendance:.0f}%) are in a healthy range. '
                'Schedule one full unplugged rest day per week, protect at least one social evening per week, '
                'and do a monthly digital detox weekend to fully recharge.'
            ),
            'benefit': 'Proactive lifestyle maintenance prevents gradual drift into overwork and sustains high performance.'
        })

    # ── 9. DOCTOR FOLLOW-UP ──────────────────────────────────────────────
    if dr_remarks:
        med_note = f' You are on medication: "{current_med}" — do not miss doses.' if current_med else ''
        recommendations.append({
            'icon': 'fa-user-doctor',
            'icon_bg': 'linear-gradient(135deg, #0ea5e9 0%, #0369a1 100%)',
            'priority': 'High',
            'title': "Act on Your Doctor's Remarks",
            'description': (
                f'Your physician noted: "{dr_remarks}".{med_note} '
                'Book any prescribed diagnostic tests within 7 days. '
                "Carry a written copy of your doctor's advice to every follow-up and record new symptoms in a health diary."
            ),
            'benefit': 'Clinical compliance reduces disease progression risk and improves treatment outcomes significantly.'
        })
    if days_since_checkup > 365:
        months_ago = days_since_checkup // 30
        cond_suffix = f' Also ask your doctor to review your {cond_label} condition.' if condition != 'None' else ''
        recommendations.append({
            'icon': 'fa-calendar-check',
            'icon_bg': 'linear-gradient(135deg, #ec4899 0%, #9d174d 100%)',
            'priority': 'High',
            'title': f'Overdue Annual Health Checkup ({months_ago} months ago)',
            'description': (
                f'Your last checkup was {months_ago} months ago — significantly overdue. '
                'Schedule a comprehensive physical exam this week: CBC, lipid panel, fasting glucose, '
                f'liver function, and thyroid screening.{cond_suffix}'
            ),
            'benefit': 'Annual screenings detect chronic conditions in pre-symptomatic stages when intervention is most effective.'
        })
    elif 0 <= days_to_checkup <= 30:
        recommendations.append({
            'icon': 'fa-calendar-plus',
            'icon_bg': 'linear-gradient(135deg, #10b981 0%, #047857 100%)',
            'priority': 'Medium',
            'title': f'Upcoming Checkup in {days_to_checkup} Days — Prepare Now',
            'description': (
                f'Your next wellness exam is in {days_to_checkup} days (scheduled: {next_checkup}). '
                'Log any symptoms, energy changes, or concerns since your last visit. '
                'Avoid heavy exercise and alcohol 24 hours before blood tests for accurate readings.'
            ),
            'benefit': 'Well-prepared consultations yield more accurate diagnostics and personalised treatment guidance.'
        })
    elif not dr_remarks and days_since_checkup <= 365:
        recommendations.append({
            'icon': 'fa-stethoscope',
            'icon_bg': 'linear-gradient(135deg, #0ea5e9 0%, #075985 100%)',
            'priority': 'Low',
            'title': 'Preventive Monitoring on Schedule',
            'description': (
                f'Your last checkup was {days_since_checkup} days ago — still within the annual window. '
                'Track lifestyle metrics yourself: resting heart rate, home blood pressure, and weekly body weight. '
                'Note any persistent symptoms for your next scheduled consultation.'
            ),
            'benefit': 'Self-monitoring between clinical visits enables early detection of deviations before they become clinical events.'
        })

    return render_template(
        'recommendations.html',
        username=session['username'],
        profile_photo=user['profile_photo'] if user else None,
        risk_level=risk_level,
        recommendations=recommendations
    )

@app.route('/profile')
def profile_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    return render_template('profile.html', username=session['username'], profile_photo=user['profile_photo'], user=user)

@app.route('/security')
def security_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    
    logins = database.get_recent_user_logins(session['username'], limit=5)
    return render_template(
        'security.html',
        username=session['username'],
        profile_photo=user['profile_photo'],
        user=user,
        logins=logins
    )

@app.route('/api/profile/update', methods=['POST'])
def api_profile_update():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
        
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    fullname = request.form.get('full_name', '').strip()
    employee_id = request.form.get('employee_id', '').strip()
    email = request.form.get('email', '').strip()
    mobile_number = request.form.get('mobile_number', '').strip()
    department = request.form.get('department', '').strip()
    designation = request.form.get('designation', '').strip()

    if not fullname or not employee_id or not email or not mobile_number or not department or not designation:
        return jsonify({'success': False, 'message': 'All details fields are required.'}), 400

    import re
    if not re.match(r'^[6-9]\d{9}$', mobile_number):
        return jsonify({'success': False, 'message': 'Mobile number must be exactly 10 digits.'}), 400

    if '@' not in email:
        return jsonify({'success': False, 'message': 'Email address must contain @.'}), 400

    profile_photo_path = None
    if 'profile_photo' in request.files:
        file = request.files['profile_photo']
        if file and file.filename != '':
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'message': 'Invalid file format. Allowed formats: PNG, JPG, JPEG.'}), 400
            
            # Check size limit 2MB
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            if file_length > 2 * 1024 * 1024:
                return jsonify({'success': False, 'message': 'File size exceeds maximum limit of 2 MB.'}), 400
            file.seek(0)

            filename = f"profile_{session['username']}_{secure_filename(file.filename)}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            profile_photo_path = f"/static/uploads/{filename}"

    profile_data = {
        'full_name': fullname,
        'employee_id': employee_id,
        'email': email,
        'mobile_number': mobile_number,
        'department': department,
        'designation': designation,
        'profile_photo': profile_photo_path
    }

    success, msg = database.update_user_profile(user['id'], profile_data)
    if success:
        session['email'] = email
        return jsonify({'success': True, 'message': 'Profile updated successfully.'})
    else:
        return jsonify({'success': False, 'message': msg}), 500

@app.route('/api/security/update-password', methods=['POST'])
def api_security_update_password():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401

    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    data = request.get_json() or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': 'All password fields are required.'}), 400

    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'New passwords do not match.'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'New password must be at least 6 characters.'}), 400

    if not check_password_hash(user['password_hash'], current_password):
        return jsonify({'success': False, 'message': 'Current password verification failed.'}), 400

    from werkzeug.security import generate_password_hash
    hashed = generate_password_hash(new_password)
    success, msg = database.update_user_password(user['id'], hashed)
    if success:
        return jsonify({'success': True, 'message': 'Password updated successfully.'})
    else:
        return jsonify({'success': False, 'message': msg}), 500

@app.route('/api/security/update-profile', methods=['POST'])
def api_security_update_profile():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401

    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    new_username = request.form.get('username', '').strip()
    photo_file = request.files.get('profile_photo')

    if not new_username:
        return jsonify({'success': False, 'message': 'Username is required.'}), 400

    username_to_update = None
    photo_path_to_update = None

    # Check username uniqueness if changed
    if new_username.lower() != user['username'].lower():
        dup = database.check_uniqueness(username=new_username, exclude_user_id=user['id'])
        if dup.get('username'):
            return jsonify({'success': False, 'message': 'Username already exists.'}), 400
        username_to_update = new_username

    # Process photo upload if provided
    if photo_file and photo_file.filename:
        filename = secure_filename(photo_file.filename)
        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                unique_filename = f"profile_{user['id']}_{int(datetime.now().timestamp())}{ext}"
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                full_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                photo_file.save(full_path)
                photo_path_to_update = f"/static/uploads/{unique_filename}"

    if username_to_update or photo_path_to_update:
        success, msg = database.update_username_and_photo(user['id'], new_username=username_to_update, new_photo=photo_path_to_update)
        if success:
            if username_to_update:
                session['username'] = username_to_update
            return jsonify({'success': True, 'message': 'Profile updated successfully.'})
        else:
            return jsonify({'success': False, 'message': msg}), 500

    return jsonify({'success': True, 'message': 'No changes detected.'})

@app.route('/api/admin/add-employee', methods=['POST'])
def api_admin_add_employee():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401

    current_user = database.get_user_by_username(session['username'])
    if not current_user or (current_user['job_role'] != 'admin' and current_user['username'] != 'admin'):
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403

    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    employee_id = data.get('employee_id', '').strip()
    mobile_number = data.get('mobile_number', '').strip()
    gender = data.get('gender', 'Male')
    dob = data.get('dob', '')
    department = data.get('department', 'Engineering')
    designation = data.get('designation', 'Staff')

    if not username or not email or not password or not full_name or not employee_id:
        return jsonify({'success': False, 'message': 'Required fields are missing.'}), 400

    success, msg = database.register_user(
        username=username,
        email=email,
        password=password,
        job_role='Employee',
        full_name=full_name,
        employee_id=employee_id,
        mobile_number=mobile_number,
        gender=gender,
        dob=dob
    )

    if success:
        new_user = database.get_user_by_username(username)
        if new_user:
            database.update_user_profile(new_user['id'], {
                'full_name': full_name,
                'employee_id': employee_id,
                'email': email,
                'mobile_number': mobile_number,
                'department': department,
                'designation': designation
            })
        return jsonify({'success': True, 'message': 'Employee added successfully.'})
    else:
        return jsonify({'success': False, 'message': msg}), 400

@app.before_request
def update_last_active_time():
    # Ignore static file requests
    if request.path.startswith('/static'):
        return
    if 'username' in session:
        user = database.get_user_by_username(session['username'])
        if user:
            database.update_last_active(user['id'])

@app.route('/api/admin/delete-employee', methods=['POST'])
def api_delete_employee():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    
    current_user = database.get_user_by_username(session['username'])
    if not current_user or (current_user['job_role'] != 'admin' and current_user['username'] != 'admin'):
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403
        
    data = request.get_json() or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'}), 400
        
    if int(user_id) == current_user['id']:
        return jsonify({'success': False, 'message': 'You cannot delete your own admin account.'}), 400
        
    success, msg = database.delete_user(user_id)
    if success:
        return jsonify({'success': True, 'message': msg})
    else:
        return jsonify({'success': False, 'message': msg}), 500

# ====================================================================
# PDF Health Report Generation
# ====================================================================
class HealthReportPDF(FPDF):
    """Custom FPDF subclass with branded header/footer for healthcare reports."""

    def __init__(self, employee_name='Employee', employee_id='N/A'):
        super().__init__()
        self.employee_name = employee_name
        self.employee_id_str = employee_id
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        # Top bar
        self.set_fill_color(15, 118, 110)  # Teal
        self.rect(0, 0, 210, 14, 'F')
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 3)
        self.cell(0, 8, 'Employee Wellness Management Analytics', align='L')
        self.set_font('Helvetica', '', 8)
        self.set_xy(-70, 3)
        self.cell(60, 8, 'Confidential Health Report', align='R')
        self.ln(16)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(140, 140, 140)
        self.cell(0, 6, f'Employee: {self.employee_name}  |  ID: {self.employee_id_str}  |  Page {self.page_no()}/{{nb}}', align='C')

    def section_heading(self, title, r=15, g=118, b=110):
        """Draws a coloured section heading bar."""
        self.ln(4)
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 11)
        self.cell(0, 9, f'  {title}', ln=True, fill=True)
        self.set_text_color(40, 40, 40)
        self.ln(3)

    def add_kv_row(self, key, value, shade=False):
        """Adds a key-value row (two-column table row)."""
        if shade:
            self.set_fill_color(245, 247, 250)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(70, 70, 70)
        self.cell(65, 7, f'  {key}', border=0, fill=True)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(40, 40, 40)
        val_str = str(value) if value not in (None, '', 'None') else 'N/A'
        self.cell(0, 7, f'  {val_str}', border=0, ln=True, fill=True)


@app.route('/api/download-health-report')
def download_health_report():
    try:
        if 'username' not in session:
            return redirect(url_for('index'))

        user = database.get_user_by_username(session['username'])
        if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
            return redirect(url_for('index'))

        health_data = database.get_health_data(user['id'])
        if not health_data:
            return redirect(url_for('health_data_page'))

        # Convert SQLite Row objects to standard dictionaries so .get() works cleanly
        user = dict(user)
        health_data = dict(health_data)

        emp_name = user.get('full_name') or user['username']
        emp_id = user.get('employee_id') or str(user['id'])

        pdf = HealthReportPDF(employee_name=emp_name, employee_id=emp_id)
        pdf.alias_nb_pages()
        pdf.add_page()

        # --- Title Block ---
        pdf.set_font('Helvetica', 'B', 20)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(0, 12, 'Employee Health Report', ln=True, align='C')
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(120, 120, 120)
        now_str = datetime.now().strftime('%B %d, %Y  |  %I:%M %p')
        pdf.cell(0, 7, f'Generated on: {now_str}', ln=True, align='C')
        pdf.ln(6)
        pdf.set_draw_color(15, 118, 110)
        pdf.set_line_width(0.6)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)

        # ==== Section 1: Employee Details ====
        pdf.section_heading('1.  Employee Details')
        details = [
            ('Employee ID', emp_id),
            ('Full Name', emp_name),
            ('Username', user['username']),
            ('Email', user['email']),
            ('Phone Number', user.get('mobile_number')),
            ('Gender', user.get('gender')),
            ('Date of Birth', user.get('dob')),
            ('Department', user.get('department')),
            ('Designation', user.get('designation')),
            ('Job Role', user.get('job_role')),
        ]
        for i, (k, v) in enumerate(details):
            pdf.add_kv_row(k, v, shade=(i % 2 == 0))

        # ==== Section 2: Employee Health Data ====
        pdf.section_heading('2.  Employee Health Data', 6, 95, 140)

        # Calculate Age from DOB
        age_str = 'N/A'
        try:
            dob = user.get('dob', '')
            if dob:
                dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                today = date.today()
                age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                age_str = f'{age} years'
        except Exception:
            pass

        # Heart rate from health data
        heart_rate = health_data.get('heart_rate', 'N/A')
        if heart_rate in (None, '', 0, 'None'):
            heart_rate = 'N/A'

        health_fields = [
            ('Age', age_str),
            ('Gender', user.get('gender')),
            ('Height', f"{health_data['height']} cm" if health_data.get('height') else 'N/A'),
            ('Weight', f"{health_data['weight']} kg" if health_data.get('weight') else 'N/A'),
            ('BMI', f"{health_data.get('bmi', 'N/A')} ({health_data.get('bmi_category', '')})"),
            ('Blood Group', health_data.get('blood_group')),
            ('Blood Pressure', f"{health_data.get('blood_pressure', 'N/A')} mmHg"),
            ('Blood Sugar Level', health_data.get('sugar_level')),
            ('Heart Rate', heart_rate),
            ('Medical Conditions', health_data.get('medical_condition')),
            ('Allergies', f"{health_data.get('has_allergies', 'No')} - {health_data.get('allergies_detail', 'N/A')}"),
            ('Smoking Habit', health_data.get('smoking_habit')),
            ('Alcohol Consumption', health_data.get('alcohol_consumption')),
            ('Water Intake', health_data.get('water_intake')),
            ('Exercise Frequency', health_data.get('exercise_frequency')),
            ('Exercise Type', health_data.get('exercise_type')),
            ('Daily Step Count', f"{health_data.get('daily_step_count', 0):,}"),
            ('Stress Level', health_data.get('stress_level')),
            ('Attendance Percentage', f"{health_data.get('attendance_percentage', 0):.1f}%"),
            ('Work Hours Per Day', f"{health_data.get('work_hours_per_day', 0):.1f} hrs"),
            ('Health Status', health_data.get('health_status')),
            ('Current Medication', health_data.get('current_medication')),
            ('Doctor Remarks', health_data.get('doctor_remarks')),
            ('Last Health Check-up', health_data.get('last_checkup')),
            ('Next Health Check-up', health_data.get('next_checkup')),
        ]
        for i, (k, v) in enumerate(health_fields):
            pdf.add_kv_row(k, v, shade=(i % 2 == 0))

        # ==== Section 3: Wellness Risk Prediction ====
        pdf.section_heading('3.  Wellness Risk Prediction', 180, 60, 60)

        # Recalculate wellness score (same logic as recommendations_page)
        bmi_cat = health_data.get('bmi_category', '')
        bp_str = health_data.get('blood_pressure', '120/80')
        try:
            systolic, diastolic = map(int, bp_str.split('/'))
        except Exception:
            systolic, diastolic = 120, 80

        bmi_score = 15 if bmi_cat == 'Normal' else (10 if bmi_cat in ['Overweight', 'Underweight'] else 4)
        bp_score = 15 if (systolic <= 120 and diastolic <= 80) else (11 if (systolic <= 130 and diastolic <= 85) else (7 if (systolic <= 140 or diastolic <= 90) else 3))
        water_score = 10 if health_data.get('water_intake') in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres'] else (7 if health_data.get('water_intake') in ['2 Litres', 'More than 4 Litres'] else 3)

        condition = health_data.get('medical_condition', 'None')
        allergies_yn = health_data.get('has_allergies', 'No')
        disability = health_data.get('has_disability', 'No')
        sugar_level = health_data.get('sugar_level', '')

        medical_points = 15
        if condition != 'None':
            medical_points -= 5
        if allergies_yn == 'Yes':
            medical_points -= 2
        if disability == 'Yes':
            medical_points -= 2
        if sugar_level in ['Pre-diabetic', 'Diabetic', 'Low']:
            medical_points -= 3
        if sugar_level == 'Diabetic':
            medical_points -= 1
        medical_points = max(0, medical_points)

        smoking = health_data.get('smoking_habit', '')
        alcohol = health_data.get('alcohol_consumption', '')
        lifestyle_points = 12
        if smoking == 'Regular': lifestyle_points -= 5
        elif smoking == 'Occasional': lifestyle_points -= 3
        elif smoking == 'Former': lifestyle_points -= 1
        if alcohol == 'Heavy': lifestyle_points -= 5
        elif alcohol == 'Regular': lifestyle_points -= 3
        elif alcohol == 'Moderate': lifestyle_points -= 1
        lifestyle_points = max(0, lifestyle_points)

        exercise_freq = health_data.get('exercise_frequency', '')
        exercise_type = health_data.get('exercise_type', '')
        daily_steps = health_data.get('daily_step_count', 0) or 0
        exercise_points = 0
        if exercise_freq == 'Daily': exercise_points += 5
        elif exercise_freq == 'Regular': exercise_points += 4
        elif exercise_freq == 'Sometimes': exercise_points += 3
        elif exercise_freq == 'Rarely': exercise_points += 1
        if exercise_type in ['Gym', 'Swimming', 'Mixed', 'Running']: exercise_points += 3
        elif exercise_type in ['Cycling', 'Sports', 'Yoga']: exercise_points += 2
        elif exercise_type == 'Walking': exercise_points += 1
        if daily_steps >= 10000: exercise_points += 5
        elif daily_steps >= 7500: exercise_points += 4
        elif daily_steps >= 5000: exercise_points += 3
        elif daily_steps >= 3000: exercise_points += 2
        elif daily_steps >= 1000: exercise_points += 1
        exercise_points = min(13, exercise_points)

        stress_level = health_data.get('stress_level', '')
        work_hours = health_data.get('work_hours_per_day', 0) or 0
        attendance = health_data.get('attendance_percentage', 0) or 0
        stress_work_points = 10
        if stress_level == 'Very High': stress_work_points -= 4
        elif stress_level == 'High': stress_work_points -= 3
        elif stress_level == 'Moderate': stress_work_points -= 1
        if work_hours > 12: stress_work_points -= 3
        elif work_hours > 10: stress_work_points -= 2
        elif work_hours > 8: stress_work_points -= 1
        if attendance < 60: stress_work_points -= 2
        elif attendance < 75: stress_work_points -= 1
        stress_work_points = max(0, stress_work_points)

        last_checkup = health_data.get('last_checkup', '')
        next_checkup = health_data.get('next_checkup', '')
        health_status = health_data.get('health_status', 'Average')
        preventive_points = 0
        try:
            last_checkup_date = datetime.strptime(last_checkup, '%Y-%m-%d').date()
            days_since = (date.today() - last_checkup_date).days
            if days_since <= 90: preventive_points += 4
            elif days_since <= 180: preventive_points += 3
            elif days_since <= 365: preventive_points += 2
        except Exception:
            pass
        try:
            next_checkup_date = datetime.strptime(next_checkup, '%Y-%m-%d').date()
            if next_checkup_date >= date.today(): preventive_points += 2
        except Exception:
            pass
        if health_status == 'Excellent': preventive_points += 4
        elif health_status == 'Good': preventive_points += 3
        elif health_status == 'Average': preventive_points += 2
        preventive_points = min(10, preventive_points)

        wellness_score = min(100, max(0, int(bmi_score + bp_score + water_score + medical_points +
                                             lifestyle_points + exercise_points + stress_work_points + preventive_points)))
        risk_level = 'Low Risk' if wellness_score >= 80 else ('Moderate Risk' if wellness_score >= 50 else 'High Risk')

        # Risk prediction rows
        risk_fields = [
            ('Predicted Risk Level', risk_level),
            ('Wellness Score', f'{wellness_score} / 100'),
        ]
        for i, (k, v) in enumerate(risk_fields):
            pdf.add_kv_row(k, v, shade=(i % 2 == 0))

        # Prediction summary paragraph
        pdf.ln(3)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(65, 7, '  Prediction Summary', ln=True)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(50, 50, 50)
        if risk_level == 'Low Risk':
            summary = f'{emp_name} demonstrates a strong wellness profile with a score of {wellness_score}/100. Key metrics including BMI, blood pressure, and hydration are within optimal ranges. Current lifestyle habits support long-term health sustainability.'
        elif risk_level == 'Moderate Risk':
            summary = f'{emp_name} shows a moderate wellness profile scoring {wellness_score}/100. Some health parameters require attention. Targeted improvements in diet, exercise, or stress management can significantly improve overall wellness outcomes.'
        else:
            summary = f'{emp_name} has an elevated risk profile with a score of {wellness_score}/100. Multiple health parameters indicate areas of concern including medical conditions, lifestyle factors, or physical metrics that require immediate clinical intervention.'
        pdf.multi_cell(0, 5, f'  {summary}')

        # Contributing factors table
        pdf.ln(3)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(65, 7, '  Contributing Factors', ln=True)
        factors = [
            ('BMI Assessment', f'{bmi_score}/15', bmi_cat or 'N/A'),
            ('Blood Pressure', f'{bp_score}/15', f'{systolic}/{diastolic} mmHg'),
            ('Hydration', f'{water_score}/10', health_data.get('water_intake', 'N/A')),
            ('Medical History', f'{medical_points}/15', condition),
            ('Lifestyle (Smoking/Alcohol)', f'{lifestyle_points}/12', f'{smoking or "None"} / {alcohol or "None"}'),
            ('Exercise & Mobility', f'{exercise_points}/13', f'{exercise_freq or "N/A"} - {daily_steps:,} steps'),
            ('Stress & Work Balance', f'{stress_work_points}/10', f'Stress: {stress_level or "N/A"}, {work_hours:.0f} hrs/day'),
            ('Preventive Care', f'{preventive_points}/10', f'Status: {health_status}'),
        ]
        # Table header
        pdf.set_fill_color(15, 118, 110)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(70, 7, '  Factor', border=0, fill=True)
        pdf.cell(25, 7, '  Score', border=0, fill=True)
        pdf.cell(0, 7, '  Details', border=0, ln=True, fill=True)
        pdf.set_text_color(40, 40, 40)
        for i, (factor, score, detail) in enumerate(factors):
            if i % 2 == 0:
                pdf.set_fill_color(245, 247, 250)
            else:
                pdf.set_fill_color(255, 255, 255)
            pdf.set_font('Helvetica', '', 8)
            pdf.cell(70, 6.5, f'  {factor}', border=0, fill=True)
            pdf.set_font('Helvetica', 'B', 8)
            pdf.cell(25, 6.5, f'  {score}', border=0, fill=True)
            pdf.set_font('Helvetica', '', 8)
            pdf.cell(0, 6.5, f'  {detail}', border=0, ln=True, fill=True)

        # ==== Section 4: Personalized Recommendations ====
        pdf.section_heading('4.  Personalized Recommendations', 99, 102, 241)

        # Build the same recommendations list as the route does
        recs = []

        # Diet
        if sugar_level == 'Diabetic':
            recs.append(('Diet', 'High', 'Strict Glycemic Control & Carb Monitoring',
                          'Limit simple carbs, processed snacks, and sweetened beverages. Incorporate fiber-rich vegetables, lean proteins, and complex whole grains.'))
        elif sugar_level == 'Pre-diabetic':
            recs.append(('Diet', 'Medium', 'Pre-Diabetic Dietary Adjustments',
                          'Focus on low-glycemic foods. Practice portion control with carbohydrates and pair them with healthy fats and proteins.'))
        elif bmi_cat == 'Obese':
            recs.append(('Diet', 'High', 'Caloric Restructuring & Whole Foods Plan',
                          'Target a sustainable daily caloric deficit. Focus on nutrient-dense foods and eliminate empty liquid calories.'))
        elif bmi_cat == 'Overweight':
            recs.append(('Diet', 'Medium', 'Balanced Macronutrient & Portion Control',
                          'Ensure half your plate is non-starchy vegetables, one quarter lean protein, one quarter complex carbs.'))
        elif bmi_cat == 'Underweight':
            recs.append(('Diet', 'High', 'Nutrient-Dense Caloric Surplus Guide',
                          'Consume calorie-dense whole foods like nuts, avocados, eggs, cheese, olive oil, and protein shakes.'))
        elif systolic > 130 or diastolic > 85:
            recs.append(('Diet', 'High' if (systolic > 140 or diastolic > 90) else 'Medium', 'Sodium-Restricted DASH Diet Plan',
                          'Keep sodium under 1,500-2,000 mg daily. Maximize potassium with spinach, sweet potatoes, and bananas.'))
        else:
            recs.append(('Diet', 'Low', 'Antioxidant-Rich Wellness Diet',
                          'Continue eating fresh berries, nuts, olive oil, green tea, and colorful vegetables.'))

        # Exercise
        if exercise_freq in ['Never', 'Rarely', ''] or daily_steps < 5000:
            recs.append(('Exercise', 'High' if bmi_cat in ['Obese', 'Overweight'] else 'Medium',
                          'Incremental Daily Step & Cardio Goals',
                          f'Current activity is low ({exercise_freq or "Never"}, {daily_steps:,} steps). Start with 15-min walks twice daily, aim for 7,500 steps.'))
        else:
            recs.append(('Exercise', 'Low', 'Strength & Cardiovascular Conditioning',
                          f'Great foundation ({exercise_freq}, {exercise_type or "Mixed"}). Add 2-3 resistance training sessions weekly.'))

        # Water
        water_intake = health_data.get('water_intake', '')
        if water_intake == 'Less than 2 Litres':
            recs.append(('Water Intake', 'High', 'Hydration Protocol & Tracking',
                          'Set repeating alarms to drink 250ml every hour. Keep a reusable bottle at your workstation.'))
        elif water_intake in ['2 Litres', 'More than 4 Litres']:
            recs.append(('Water Intake', 'Medium', 'Targeted Hydration Adjustment',
                          'Adjust to 2.5-3.5 liters. Balance electrolyte intake if over 4 liters.'))
        else:
            recs.append(('Water Intake', 'Low', 'Ideal Hydration Maintenance',
                          'Continue consuming clean water evenly throughout the day.'))

        # Sleep
        if work_hours > 10 or stress_level in ['Very High', 'High']:
            recs.append(('Sleep', 'High', 'Restorative Sleep Hygiene Protocol',
                          f'High work demand ({work_hours:.0f} hrs/day) impacts sleep. Keep bedroom dark and cool. Stop screens 45 min before bed.'))
        else:
            recs.append(('Sleep', 'Low', 'Consistent Circadian Sleep Cycles',
                          'Maintain strict sleep schedule. Aim for 7-8 hours of uninterrupted rest nightly.'))

        # Stress
        if stress_level in ['Very High', 'High']:
            recs.append(('Stress Management', 'High', 'Cortisol Regulation & Autonomic Calm',
                          f'Stress is {stress_level}. Dedicate 10 min mid-day to deep breathing (4-7-8 method). Use meditation apps.'))
        elif stress_level == 'Moderate':
            recs.append(('Stress Management', 'Medium', 'Active Workday Relaxation Breaks',
                          'Implement micro-breaks. Stand and stretch 3 min every 90 min. Practice progressive muscle relaxation.'))

        # Lifestyle
        if work_hours > 10:
            recs.append(('Lifestyle', 'High', 'Work Hours & Boundaries Optimization',
                          f'Working {work_hours:.0f} hrs/day risks chronic fatigue. Discuss workload distribution with team leads.'))
        if attendance < 80:
            recs.append(('Lifestyle', 'Medium', 'Health Recovery & Attendance Support',
                          f'Attendance is {attendance:.0f}%. Explore flexible hours or partial WFH with HR.'))

        # Smoking
        if smoking in ['Regular', 'Occasional']:
            recs.append(('Smoking Cessation', 'High', 'Smoking Cessation Plan',
                          f'You are a {smoking} smoker. Discuss cessation aids (NRT, patches) with your physician. Set a target quit date.'))

        # Alcohol
        if alcohol in ['Heavy', 'Regular', 'Moderate']:
            recs.append(('Alcohol Reduction', 'High' if alcohol in ['Heavy', 'Regular'] else 'Medium',
                          'Alcohol Intake Moderation Plan',
                          f'Consumption is {alcohol}. Establish alcohol-free days. Substitute with mineral water with lime.'))

        # Doctor follow-up
        dr_remarks = health_data.get('doctor_remarks', '').strip()
        if dr_remarks:
            recs.append(('Doctor Follow-up', 'High', 'Physician Follow-up Action',
                          f'Doctor\'s notes: "{dr_remarks}". Book prescribed blood panels, specialist visits, and follow medication.'))

        # Render recommendations table
        pdf.set_fill_color(99, 102, 241)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(30, 7, '  Category', border=0, fill=True)
        pdf.cell(18, 7, '  Priority', border=0, fill=True)
        pdf.cell(55, 7, '  Recommendation', border=0, fill=True)
        pdf.cell(0, 7, '  Details', border=0, ln=True, fill=True)
        pdf.set_text_color(40, 40, 40)

        for i, (cat, priority, title, desc) in enumerate(recs):
            if i % 2 == 0:
                pdf.set_fill_color(245, 247, 250)
            else:
                pdf.set_fill_color(255, 255, 255)

            # Calculate row height based on desc length
            max_desc_width = 87  # approx width for the Details column in mm
            pdf.set_font('Helvetica', '', 7.5)
            # Estimate lines needed
            desc_lines = max(1, len(desc) // 50 + 1)
            row_h = max(6, desc_lines * 4.5)

            x_start = pdf.get_x()
            y_start = pdf.get_y()

            # Check if we need a new page
            if y_start + row_h > 270:
                pdf.add_page()
                # Re-draw table header
                pdf.set_fill_color(99, 102, 241)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font('Helvetica', 'B', 8)
                pdf.cell(30, 7, '  Category', border=0, fill=True)
                pdf.cell(18, 7, '  Priority', border=0, fill=True)
                pdf.cell(55, 7, '  Recommendation', border=0, fill=True)
                pdf.cell(0, 7, '  Details', border=0, ln=True, fill=True)
                pdf.set_text_color(40, 40, 40)
                y_start = pdf.get_y()
                if i % 2 == 0:
                    pdf.set_fill_color(245, 247, 250)
                else:
                    pdf.set_fill_color(255, 255, 255)

            pdf.set_font('Helvetica', 'B', 7.5)
            pdf.cell(30, row_h, f'  {cat}', border=0, fill=True)
            pdf.set_font('Helvetica', '', 7.5)
            pdf.cell(18, row_h, f'  {priority}', border=0, fill=True)
            pdf.set_font('Helvetica', 'B', 7.5)
            pdf.cell(55, row_h, f'  {title}', border=0, fill=True)
            pdf.set_font('Helvetica', '', 7)
            # For long descriptions, use multi_cell inside the remaining space
            x_desc = pdf.get_x()
            pdf.multi_cell(87, row_h / desc_lines, f'  {desc}', border=0, fill=True)
            pdf.set_xy(10, y_start + row_h)

        # --- Disclaimer ---
        pdf.ln(10)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
        pdf.set_font('Helvetica', 'I', 7)
        pdf.set_text_color(150, 150, 150)
        pdf.multi_cell(0, 4, 'Disclaimer: This report is generated by the Employee Wellness Management Analytics system for informational purposes only. '
                             'It does not constitute professional medical advice. Please consult a qualified healthcare provider for clinical decisions.')

        # Generate and send
        pdf_string = pdf.output(dest='S')
        pdf_bytes = pdf_string.encode('latin-1') if isinstance(pdf_string, str) else pdf_string
        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)
        filename = f'Employee_{emp_id}_Health_Report.pdf'
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


    except Exception as e:
        return f"<h3>Error Generating PDF</h3><p>An error occurred: {str(e)}</p><p>Please ensure all your health profile fields are complete.</p>", 500

@app.route('/api/notifications')
def get_notifications():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Admin Notifications: count high wellness risk employees
    if user['job_role'] == 'admin' or user['username'] == 'admin':
        notifications = []
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, height, weight, bmi_category, blood_pressure, water_intake, medical_condition, has_allergies, has_disability, sugar_level, smoking_habit, alcohol_consumption, exercise_frequency, exercise_type, daily_step_count, stress_level, work_hours_per_day, attendance_percentage, last_checkup, next_checkup, health_status FROM health_data")
        all_hd = cursor.fetchall()
        high_risk_emp_count = 0
        for hd in all_hd:
            # Replicate score calculation logic
            bmi_cat = hd['bmi_category']
            bp_str = hd['blood_pressure'] or '120/80'
            try:
                systolic, diastolic = map(int, bp_str.split('/'))
            except Exception:
                systolic, diastolic = 120, 80
            bmi_score = 15 if bmi_cat == 'Normal' else (10 if bmi_cat in ['Overweight', 'Underweight'] else 4)
            bp_score = 15 if (systolic <= 120 and diastolic <= 80) else (11 if (systolic <= 130 and diastolic <= 85) else (7 if (systolic <= 140 or diastolic <= 90) else 3))
            water_score = 10 if hd['water_intake'] in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres'] else (7 if hd['water_intake'] in ['2 Litres', 'More than 4 Litres'] else 3)

            condition = hd['medical_condition'] or 'None'
            allergies_yn = hd['has_allergies'] or 'No'
            disability = hd['has_disability'] or 'No'
            sugar_level = hd['sugar_level'] or ''

            medical_points = 15
            if condition != 'None': medical_points -= 5
            if allergies_yn == 'Yes': medical_points -= 2
            if disability == 'Yes': medical_points -= 2
            if sugar_level in ['Pre-diabetic', 'Diabetic', 'Low']: medical_points -= 3
            if sugar_level == 'Diabetic': medical_points -= 1
            medical_points = max(0, medical_points)

            smoking = hd['smoking_habit'] or ''
            alcohol = hd['alcohol_consumption'] or ''
            lifestyle_points = 12
            if smoking == 'Regular': lifestyle_points -= 5
            elif smoking == 'Occasional': lifestyle_points -= 3
            elif smoking == 'Former': lifestyle_points -= 1
            if alcohol == 'Heavy': lifestyle_points -= 5
            elif alcohol == 'Regular': lifestyle_points -= 3
            elif alcohol == 'Moderate': lifestyle_points -= 1
            lifestyle_points = max(0, lifestyle_points)

            exercise_freq = hd['exercise_frequency'] or ''
            exercise_type = hd['exercise_type'] or ''
            daily_steps = hd['daily_step_count'] or 0
            exercise_points = 0
            if exercise_freq == 'Daily': exercise_points += 5
            elif exercise_freq == 'Regular': exercise_points += 4
            elif exercise_freq == 'Sometimes': exercise_points += 3
            elif exercise_freq == 'Rarely': exercise_points += 1
            if exercise_type in ['Gym', 'Swimming', 'Mixed', 'Running']: exercise_points += 3
            elif exercise_type in ['Cycling', 'Sports', 'Yoga']: exercise_points += 2
            elif exercise_type == 'Walking': exercise_points += 1
            if daily_steps >= 10000: exercise_points += 5
            elif daily_steps >= 7500: exercise_points += 4
            elif daily_steps >= 5000: exercise_points += 3
            elif daily_steps >= 3000: exercise_points += 2
            elif daily_steps >= 1000: exercise_points += 1
            exercise_points = min(13, exercise_points)

            stress_level = hd['stress_level'] or ''
            work_hours = hd['work_hours_per_day'] or 0
            attendance = hd['attendance_percentage'] or 0
            stress_work_points = 10
            if stress_level == 'Very High': stress_work_points -= 4
            elif stress_level == 'High': stress_work_points -= 3
            elif stress_level == 'Moderate': stress_work_points -= 1
            if work_hours > 12: stress_work_points -= 3
            elif work_hours > 10: stress_work_points -= 2
            elif work_hours > 8: stress_work_points -= 1
            if attendance < 60: stress_work_points -= 2
            elif attendance < 75: stress_work_points -= 1
            stress_work_points = max(0, stress_work_points)

            last_checkup = hd['last_checkup'] or ''
            next_checkup = hd['next_checkup'] or ''
            health_status = hd['health_status'] or 'Average'
            preventive_points = 0
            try:
                last_checkup_date = datetime.strptime(last_checkup, '%Y-%m-%d').date()
                days_since = (date.today() - last_checkup_date).days
                if days_since <= 90: preventive_points += 4
                elif days_since <= 180: preventive_points += 3
                elif days_since <= 365: preventive_points += 2
            except Exception:
                pass
            try:
                next_checkup_date = datetime.strptime(next_checkup, '%Y-%m-%d').date()
                if next_checkup_date >= date.today(): preventive_points += 2
            except Exception:
                pass
            if health_status == 'Excellent': preventive_points += 4
            elif health_status == 'Good': preventive_points += 3
            elif health_status == 'Average': preventive_points += 2
            preventive_points = min(10, preventive_points)

            wellness_score = int(bmi_score + bp_score + water_score + medical_points + lifestyle_points + exercise_points + stress_work_points + preventive_points)
            if wellness_score < 50:
                high_risk_emp_count += 1
        conn.close()

        if high_risk_emp_count > 0:
            notifications.append({
                'id': f'admin_high_risk_{high_risk_emp_count}',
                'type': 'danger',
                'title': 'High Risk Alert',
                'message': f'There are {high_risk_emp_count} employees classified as High Wellness Risk.',
                'icon': 'fa-triangle-exclamation',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        return jsonify({'success': True, 'notifications': notifications})

    # Employee Notifications
    user = dict(user)
    health_data = database.get_health_data(user['id'])

    notifications = []
    if not health_data:
        notifications.append({
            'id': 'no_biometrics',
            'type': 'warning',
            'title': 'Complete Biometrics',
            'message': 'Please complete your biometrics data to receive wellness predictions and recommendations.',
            'icon': 'fa-user-doctor',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        return jsonify({'success': True, 'notifications': notifications})

    health_data = dict(health_data)

    # 1. Missed/Upcoming Health Check-up
    next_checkup = health_data.get('next_checkup')
    if next_checkup:
        try:
            next_checkup_date = datetime.strptime(next_checkup, '%Y-%m-%d').date()
            today = date.today()
            diff_days = (next_checkup_date - today).days

            if diff_days < 0:
                notifications.append({
                    'id': f'missed_checkup_{next_checkup}',
                    'type': 'danger',
                    'title': 'Missed Health Check-up',
                    'message': f'Your health check-up scheduled for {next_checkup} was missed. Please reschedule.',
                    'icon': 'fa-calendar-times',
                    'timestamp': f'{next_checkup} 09:00:00'
                })
            elif 0 <= diff_days <= 7:
                remaining_str = 'today' if diff_days == 0 else ('tomorrow' if diff_days == 1 else f'in {diff_days} days')
                notifications.append({
                    'id': f'upcoming_checkup_{next_checkup}',
                    'type': 'info',
                    'title': 'Upcoming Health Check-up',
                    'message': f'You have a health check-up scheduled {remaining_str} ({next_checkup}).',
                    'icon': 'fa-calendar-check',
                    'timestamp': f'{next_checkup} 09:00:00'
                })
        except Exception:
            pass

    # 2. High Wellness Risk
    bmi_cat = health_data.get('bmi_category')
    bp_str = health_data.get('blood_pressure') or '120/80'
    try:
        systolic, diastolic = map(int, bp_str.split('/'))
    except Exception:
        systolic, diastolic = 120, 80

    bmi_score = 15 if bmi_cat == 'Normal' else (10 if bmi_cat in ['Overweight', 'Underweight'] else 4)
    bp_score = 15 if (systolic <= 120 and diastolic <= 80) else (11 if (systolic <= 130 and diastolic <= 85) else (7 if (systolic <= 140 or diastolic <= 90) else 3))
    water_score = 10 if health_data.get('water_intake') in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres'] else (7 if health_data.get('water_intake') in ['2 Litres', 'More than 4 Litres'] else 3)

    condition = health_data.get('medical_condition') or 'None'
    allergies_yn = health_data.get('has_allergies') or 'No'
    disability = health_data.get('has_disability') or 'No'
    sugar_level = health_data.get('sugar_level') or ''

    medical_points = 15
    if condition != 'None': medical_points -= 5
    if allergies_yn == 'Yes': medical_points -= 2
    if disability == 'Yes': medical_points -= 2
    if sugar_level in ['Pre-diabetic', 'Diabetic', 'Low']: medical_points -= 3
    if sugar_level == 'Diabetic': medical_points -= 1
    medical_points = max(0, medical_points)

    smoking = health_data.get('smoking_habit') or ''
    alcohol = health_data.get('alcohol_consumption') or ''
    lifestyle_points = 12
    if smoking == 'Regular': lifestyle_points -= 5
    elif smoking == 'Occasional': lifestyle_points -= 3
    elif smoking == 'Former': lifestyle_points -= 1
    if alcohol == 'Heavy': lifestyle_points -= 5
    elif alcohol == 'Regular': lifestyle_points -= 3
    elif alcohol == 'Moderate': lifestyle_points -= 1
    lifestyle_points = max(0, lifestyle_points)

    exercise_freq = health_data.get('exercise_frequency') or ''
    exercise_type = health_data.get('exercise_type') or ''
    daily_steps = health_data.get('daily_step_count') or 0
    exercise_points = 0
    if exercise_freq == 'Daily': exercise_points += 5
    elif exercise_freq == 'Regular': exercise_points += 4
    elif exercise_freq == 'Sometimes': exercise_points += 3
    elif exercise_freq == 'Rarely': exercise_points += 1
    if exercise_type in ['Gym', 'Swimming', 'Mixed', 'Running']: exercise_points += 3
    elif exercise_type in ['Cycling', 'Sports', 'Yoga']: exercise_points += 2
    elif exercise_type == 'Walking': exercise_points += 1
    if daily_steps >= 10000: exercise_points += 5
    elif daily_steps >= 7500: exercise_points += 4
    elif daily_steps >= 5000: exercise_points += 3
    elif daily_steps >= 3000: exercise_points += 2
    elif daily_steps >= 1000: exercise_points += 1
    exercise_points = min(13, exercise_points)

    stress_level = health_data.get('stress_level') or ''
    work_hours = health_data.get('work_hours_per_day') or 0
    attendance = health_data.get('attendance_percentage') or 0
    stress_work_points = 10
    if stress_level == 'Very High': stress_work_points -= 4
    elif stress_level == 'High': stress_work_points -= 3
    elif stress_level == 'Moderate': stress_work_points -= 1
    if work_hours > 12: stress_work_points -= 3
    elif work_hours > 10: stress_work_points -= 2
    elif work_hours > 8: stress_work_points -= 1
    if attendance < 60: stress_work_points -= 2
    elif attendance < 75: stress_work_points -= 1
    stress_work_points = max(0, stress_work_points)

    last_checkup = health_data.get('last_checkup') or ''
    health_status = health_data.get('health_status') or 'Average'
    preventive_points = 0
    try:
        last_checkup_date = datetime.strptime(last_checkup, '%Y-%m-%d').date()
        days_since = (date.today() - last_checkup_date).days
        if days_since <= 90: preventive_points += 4
        elif days_since <= 180: preventive_points += 3
        elif days_since <= 365: preventive_points += 2
    except Exception:
        pass
    try:
        next_checkup_date = datetime.strptime(next_checkup, '%Y-%m-%d').date()
        if next_checkup_date >= date.today(): preventive_points += 2
    except Exception:
        pass
    if health_status == 'Excellent': preventive_points += 4
    elif health_status == 'Good': preventive_points += 3
    elif health_status == 'Average': preventive_points += 2
    preventive_points = min(10, preventive_points)

    wellness_score = int(bmi_score + bp_score + water_score + medical_points + lifestyle_points + exercise_points + stress_work_points + preventive_points)

    if wellness_score < 50:
        notifications.append({
            'id': f'high_risk_{wellness_score}',
            'type': 'danger',
            'title': 'High Wellness Risk Alert',
            'message': f'Your current wellness score is {wellness_score}/100, which puts you at High Risk. Please check recommendations.',
            'icon': 'fa-triangle-exclamation',
            'timestamp': health_data.get('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        })

    # 3. New Personalized Recommendations
    updated_at_str = health_data.get('updated_at')
    if updated_at_str:
        try:
            updated_at_date = datetime.strptime(updated_at_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - updated_at_date).days <= 7:
                notifications.append({
                    'id': f'new_recommendations_{updated_at_str}',
                    'type': 'success',
                    'title': 'New Recommendations',
                    'message': f'New personalized recommendations are available based on your health assessment from {updated_at_date.strftime("%b %d, %Y")}.',
                    'icon': 'fa-lightbulb',
                    'timestamp': updated_at_str
                })
        except Exception:
            pass

    # Sort notifications by timestamp desc
    notifications.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify({'success': True, 'notifications': notifications})


@app.route('/health-history')
def health_history_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    return render_template('health_history.html', username=session['username'], profile_photo=user['profile_photo'] if user else None, user=user)

@app.route('/api/health-history', methods=['GET'])
def api_health_history():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    history = database.get_health_history(user['id'])
    return jsonify({'success': True, 'history': history})

# ─────────────────────────────────────────────────────────────
# MODULE 6: AI Wellness Chatbot & Engagement
# ─────────────────────────────────────────────────────────────

@app.route('/ai-chatbot')
def ai_chatbot_page():
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))
    designation = user['designation'] if user['designation'] else 'Staff'
    return render_template(
        'ai_chatbot.html',
        username=session['username'],
        profile_photo=user['profile_photo'] if user else None,
        designation=designation
    )



# ── DUCKDUCKGO SEARCH PARSING LOGIC ──────────────────────────────────────
class DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.current_result = None
        self.in_title = False
        self.in_snippet = False
        self.in_url = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get('class', '')
        if tag == 'div' and 'web-result' in cls:
            if self.current_result:
                self.results.append(self.current_result)
            self.current_result = {'title': '', 'url': '', 'snippet': ''}
            
        if self.current_result is not None:
            if tag == 'a' and 'result__a' in cls:
                self.in_title = True
                raw_href = attrs_dict.get('href', '')
                if "uddg=" in raw_href:
                    actual_url = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
                else:
                    actual_url = raw_href
                self.current_result['url'] = actual_url
            elif tag == 'a' and 'result__snippet' in cls:
                self.in_snippet = True
            elif tag == 'a' and 'result__url' in cls:
                self.in_url = True

    def handle_endtag(self, tag):
        if self.in_title and tag == 'a':
            self.in_title = False
        elif self.in_snippet and tag == 'a':
            self.in_snippet = False
            if self.current_result:
                self.results.append(self.current_result)
                self.current_result = None
        elif self.in_url and tag == 'a':
            self.in_url = False

    def handle_data(self, data):
        if self.current_result is not None:
            if self.in_title:
                self.current_result['title'] += data
            elif self.in_snippet:
                self.current_result['snippet'] += data

    def close(self):
        super().close()
        if self.current_result:
            self.results.append(self.current_result)
            self.current_result = None

def is_internet_available():
    try:
        # Check by opening Google with a 2 second timeout
        with urllib.request.urlopen('https://www.google.com', timeout=2) as response:
            return response.status == 200
    except Exception:
        return False

def get_online_health_info(query):
    trusted_domains = {
        'who.int': 'World Health Organization (WHO)',
        'cdc.gov': 'Centers for Disease Control (CDC)',
        'nhs.uk': 'National Health Service (NHS)',
        'mayoclinic.org': 'Mayo Clinic',
        'medlineplus.gov': 'MedlinePlus',
        'nih.gov': 'National Institutes of Health (NIH)',
        'clevelandclinic.org': 'Cleveland Clinic',
        'webmd.com': 'WebMD',
        'healthline.com': 'Healthline',
        'medicalnewstoday.com': 'Medical News Today'
    }
    
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
    
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode('utf-8')
            parser = DDGParser()
            parser.feed(html)
            parser.close()
            
            matched_findings = []
            seen_snippets = set()
            
            for res in parser.results:
                res_url = res['url'].lower().strip()
                res_snippet = res['snippet'].strip()
                res_title = res['title'].strip()
                
                if not res_snippet:
                    continue
                    
                # Identify if from a trusted domain
                source_name = None
                for domain, name in trusted_domains.items():
                    if domain in res_url:
                        source_name = name
                        break
                
                # If matched and snippet is unique, collect
                if source_name and res_snippet not in seen_snippets:
                    seen_snippets.add(res_snippet)
                    matched_findings.append({
                        'source': source_name,
                        'title': res_title,
                        'snippet': res_snippet,
                        'url': res['url']
                    })
            
            if matched_findings:
                reply = "According to trusted health sources:<br><br>"
                for item in matched_findings[:3]:
                    snip = item['snippet']
                    # Clean snippet text from any raw trailing ellipsis
                    snip = re.sub(r'\s*\.\.\.\s*$', '', snip).strip()
                    if not snip.endswith('.'):
                        snip += '.'
                    reply += f"• {snip} (Source: <i>{item['source']}</i>)<br>"
                return reply
    except Exception:
        pass
    return None

def get_general_health_answer(query):
    # Built-in health knowledge fallback
    builtin_knowledge = {
        'cold': (
            "To help prevent a cold:<br><br>"
            "• Wash your hands regularly with soap and water.<br>"
            "• Avoid close contact with people who are sick.<br>"
            "• Eat a balanced diet rich in fruits and vegetables.<br>"
            "• Stay hydrated by drinking plenty of fluids.<br>"
            "• Get enough sleep (7-8 hours per night).<br>"
            "• Exercise regularly to boost your immune system.<br>"
            "• Consider speaking with a healthcare professional if you frequently get sick."
        ),
        'immunity': (
            "To help improve your immunity, consider adding these foods to your diet:<br><br>"
            "• Citrus fruits (oranges, lemons, grapefruits) - rich in Vitamin C.<br>"
            "• Red bell peppers - high in Vitamin C and beta-carotene.<br>"
            "• Broccoli - packed with Vitamins A, C, and E.<br>"
            "• Garlic - contains sulfur compounds like allicin.<br>"
            "• Ginger - helps reduce inflammation and sore throat.<br>"
            "• Spinach - rich in Vitamin C, antioxidants, and beta-carotene.<br>"
            "• Yogurt - look for 'live and active cultures' to stimulate the immune system.<br>"
            "• Almonds - source of Vitamin E, a powerful antioxidant.<br>"
            "• Turmeric - known for its anti-inflammatory properties."
        ),
        'water': (
            "For adults, the recommended daily water intake is:<br><br>"
            "• Approximately 2.5 to 3.5 litres (10-12 cups) for daily intake.<br>"
            "• Approximately 2.0 to 2.7 litres (8-10 cups) for hydration.<br>"
            "• Individual needs vary based on exercise levels, climate, and overall health.<br><br>"
            "💡 Tip: You can check your current water intake in your health data, or ask me: 'What is my water intake?'"
        ),
        'diabetes': (
            "Diabetes is a chronic health condition that affects how your body turns food into energy:<br><br>"
            "• In diabetes, your body either doesn't make enough insulin or can't use it effectively.<br>"
            "• When there isn't enough insulin or cells stop responding to insulin, too much blood sugar stays in your bloodstream.<br>"
            "• Over time, this can cause serious health problems, such as heart disease, vision loss, and kidney disease.<br>"
            "• There are two main types: Type 1 (an autoimmune reaction) and Type 2 (developed over time, often linked to lifestyle factors)."
        ),
        'blood pressure': (
            "High blood pressure (hypertension) usually develops over time and can be caused by various factors, including:<br><br>"
            "• Unhealthy lifestyle choices, such as lack of regular physical activity.<br>"
            "• A diet high in sodium (salt) and low in potassium.<br>"
            "• Being overweight or obese.<br>"
            "• Regular alcohol consumption and tobacco use.<br>"
            "• High stress levels.<br>"
            "• Older age and family history of hypertension.<br>"
            "• Chronic conditions like kidney disease or diabetes."
        ),
        'vitamin d': (
            "Common symptoms of Vitamin D deficiency include:<br><br>"
            "• Frequent fatigue or tiredness.<br>"
            "• Bone pain, lower back pain, or muscle aches.<br>"
            "• Hair loss or slow-healing wounds.<br>"
            "• Muscle weakness or joint stiffness.<br>"
            "• Frequent sickness or infections (Vitamin D is key for immune support).<br>"
            "• Mood changes or feelings of depression.<br><br>"
            "💡 Tip: Spending 10-15 minutes in daily sunlight or eating foods like fatty fish, egg yolks, and fortified dairy can help."
        ),
        'sleep': (
            "For optimal health and well-being:<br><br>"
            "• Most adults need between 7 and 9 hours of quality sleep per night.<br>"
            "• Getting less than 7 hours on a regular basis is linked to health issues like weakened immunity, high blood pressure, weight gain, and increased stress.<br>"
            "• Consistency in sleep and wake times is just as important as the duration."
        ),
        'eating habits': (
            "Healthy eating habits to adopt for long-term wellness include:<br><br>"
            "• Eat a variety of nutrient-rich foods, focusing on fruits, vegetables, whole grains, and lean proteins.<br>"
            "• Control portion sizes to avoid overeating.<br>"
            "• Eat slowly and mindfully, listening to your body's hunger cues.<br>"
            "• Drink water instead of sugary beverages.<br>"
            "• Limit processed foods, trans fats, and added sugars.<br>"
            "• Cook meals at home to better control ingredients.<br>"
            "• Do not skip breakfast, as it jumpstarts your metabolism."
        ),
        'stress': (
            "To manage and reduce stress levels:<br><br>"
            "• Practice mindfulness, meditation, or deep breathing exercises daily.<br>"
            "• Engage in regular physical activity, which releases endorphins.<br>"
            "• Maintain a consistent sleep schedule to rest your mind.<br>"
            "• Set healthy boundaries at work and prioritize tasks to avoid burnout.<br>"
            "• Connect with friends, family, or support networks.<br>"
            "• Dedicate time to hobbies, relaxation, or nature walks.<br>"
            "• Limit caffeine and alcohol, which can exacerbate anxiety."
        ),
        'exercises': (
            "Excellent beginner-friendly exercises include:<br><br>"
            "• **Brisk Walking:** Safe, requires no equipment, and boosts cardiovascular health.<br>"
            "• **Bodyweight Squats:** Builds lower body and core strength.<br>"
            "• **Wall Push-ups:** A gentle way to build upper body strength before transitioning to floor push-ups.<br>"
            "• **Planks:** Great for building core stability and strength.<br>"
            "• **Yoga or Stretching:** Improves flexibility, balance, and reduces stress.<br>"
            "• **Stationary Cycling:** Low-impact cardio that is easy on the joints.<br><br>"
            "💡 Tip: Start with 10-15 minutes a day, 3 times a week, and gradually increase intensity and duration."
        )
    }

    # Match topics
    matched_topic = None
    q = query.lower()
    if 'cold' in q or 'prevent cold' in q or 'prevent a cold' in q or 'flu' in q:
        matched_topic = 'cold'
    elif 'immunity' in q or 'immune' in q or 'foods improve immunity' in q or 'boost immunity' in q:
        matched_topic = 'immunity'
    elif 'water' in q and ('drink' in q or 'how much' in q or 'daily' in q):
        matched_topic = 'water'
    elif 'diabetes' in q or 'what is diabetes' in q or 'sugar' in q:
        matched_topic = 'diabetes'
    elif 'blood pressure' in q or 'bp' in q or 'hypertension' in q:
        matched_topic = 'blood pressure'
    elif 'vitamin d' in q or 'deficiency' in q:
        matched_topic = 'vitamin d'
    elif 'sleep' in q or 'insomnia' in q or 'tired' in q:
        matched_topic = 'sleep'
    elif 'eating' in q or 'diet' in q or 'habit' in q or 'nutrition' in q:
        matched_topic = 'eating habits'
    elif 'stress' in q or 'anxiety' in q or 'mental' in q:
        matched_topic = 'stress'
    elif 'exercise' in q or 'workout' in q or 'beginner' in q:
        matched_topic = 'exercises'

    # If internet is available, search and try to fetch trusted information
    if is_internet_available():
        online_info = get_online_health_info(query)
        if online_info:
            return online_info

    # Otherwise, fall back to built-in knowledge
    if matched_topic and matched_topic in builtin_knowledge:
        return builtin_knowledge[matched_topic]

    # General default health message
    return (
        "To maintain optimal health and wellness, follow these general tips:<br><br>"
        "• Eat a balanced diet rich in fruits, vegetables, and lean proteins.<br>"
        "• Stay hydrated by drinking 2-3 litres of water daily.<br>"
        "• Aim for 30 minutes of physical activity most days of the week.<br>"
        "• Ensure you get 7-9 hours of restful sleep every night.<br>"
        "• Manage stress with mindfulness, deep breathing, or yoga.<br>"
        "• Schedule regular medical check-ups and follow your physician's guidance.<br><br>"
        "💡 Please check your personalized health dashboard or ask specific questions about your health parameters!"
    )


@app.route('/api/chatbot', methods=['POST'])
def api_chatbot():
    """Rule-based AI Wellness Chatbot – reads employee's live health data and answers wellness questions."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401

    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    data = request.get_json(silent=True) or {}
    question = (data.get('message', '') or '').strip().lower()
    original_question = (data.get('message', '') or '').strip()
    q = question

    if not question:
        return jsonify({'success': False, 'message': 'No message provided.'}), 400

    # ── Fetch employee data ──────────────────────────────────────────────
    user = dict(user)
    hd = database.get_health_data(user['id'])

    # Compute health score
    score = database.calculate_health_score(user['id'])
    if score is None:
        score = 0

    if score >= 80:
        score_status = 'Excellent'
    elif score >= 60:
        score_status = 'Good'
    elif score >= 40:
        score_status = 'Average'
    else:
        score_status = 'Needs Improvement'

    full_name = user.get('full_name') or user.get('username', 'Employee')

    # ── Smart Greeting Helper ────────────────────────────────────────────
    now_hour = datetime.now().hour
    if now_hour < 12:
        greeting_emoji = '🌅'
        greeting_text = 'Good Morning'
    elif now_hour < 17:
        greeting_emoji = '☀️'
        greeting_text = 'Good Afternoon'
    elif now_hour < 21:
        greeting_emoji = '🌇'
        greeting_text = 'Good Evening'
    else:
        greeting_emoji = '🌙'
        greeting_text = 'Good Night'

    # ── REMINDER PARSING ─────────────────────────────────────────────────
    # Check if the user is requesting a reminder
    reminder_keywords = ['remind me', 'set a reminder', 'set reminder', 'create reminder', 'add reminder', 'reminder to', 'remind about']
    is_reminder_request = any(kw in question for kw in reminder_keywords)

    if is_reminder_request:
        # Parse time from the message
        time_match = re.search(r'(\d{1,2})[:.]?(\d{2})?\s*(am|pm|AM|PM)', question)
        at_time_match = re.search(r'at\s+(\d{1,2})[:.]?(\d{2})?\s*(am|pm|AM|PM)?', question)
        
        reminder_hour = None
        reminder_minute = '00'
        
        if time_match:
            reminder_hour = int(time_match.group(1))
            reminder_minute = time_match.group(2) or '00'
            ampm = (time_match.group(3) or 'AM').upper()
            if ampm == 'PM' and reminder_hour != 12:
                reminder_hour += 12
            elif ampm == 'AM' and reminder_hour == 12:
                reminder_hour = 0
        elif at_time_match:
            reminder_hour = int(at_time_match.group(1))
            reminder_minute = at_time_match.group(2) or '00'
            ampm = (at_time_match.group(3) or '').upper()
            if ampm == 'PM' and reminder_hour != 12:
                reminder_hour += 12
            elif ampm == 'AM' and reminder_hour == 12:
                reminder_hour = 0
            elif not ampm and reminder_hour <= 12:
                # Assume PM if hour is between 1-7 and no AM/PM specified
                if 1 <= reminder_hour <= 7:
                    reminder_hour += 12

        # Parse repeat type
        repeat_type = 'Once'
        if 'every day' in question or 'daily' in question:
            repeat_type = 'Daily'
        elif 'every week' in question or 'weekly' in question:
            repeat_type = 'Weekly'
        elif 'every month' in question or 'monthly' in question:
            repeat_type = 'Monthly'
        elif re.search(r'every\s+\d+\s*hours?', question):
            repeat_type = 'Daily'

        # Extract the reminder title from the message
        title = original_question
        # Clean up common prefixes
        for prefix in ['remind me to ', 'remind me about ', 'set a reminder to ', 'set reminder to ', 'create reminder to ', 'add reminder to ', 'reminder to ']:
            if question.startswith(prefix):
                title = original_question[len(prefix):]
                break
        # Remove time references from title
        title = re.sub(r'\s*at\s+\d{1,2}[:.]?\d{0,2}\s*(am|pm|AM|PM)?', '', title)
        title = re.sub(r'\s*(every day|daily|every week|weekly|every month|monthly)', '', title, flags=re.IGNORECASE)
        title = title.strip().strip('.')
        if not title:
            title = 'Health Reminder'
        # Capitalize first letter
        title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()

        # Set reminder date and time
        today = date.today().strftime('%Y-%m-%d')
        if reminder_hour is not None:
            time_str = f"{reminder_hour:02d}:{int(reminder_minute):02d}"
            # If the time has already passed today, set for tomorrow
            now_time = datetime.now().strftime('%H:%M')
            if time_str <= now_time:
                from datetime import timedelta
                tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
                reminder_date = tomorrow
            else:
                reminder_date = today
        else:
            # Default to 1 hour from now
            from datetime import timedelta
            future = datetime.now() + timedelta(hours=1)
            time_str = future.strftime('%H:%M')
            reminder_date = future.strftime('%Y-%m-%d')

        # Format display time
        disp_hour = int(time_str.split(':')[0])
        disp_min = time_str.split(':')[1]
        disp_ampm = 'AM' if disp_hour < 12 else 'PM'
        disp_hour_12 = disp_hour % 12
        disp_hour_12 = disp_hour_12 if disp_hour_12 != 0 else 12
        display_time = f"{disp_hour_12}:{disp_min} {disp_ampm}"

        # Create the reminder in the database
        success, msg, reminder_id = database.create_reminder(
            user_id=user['id'],
            title=title,
            description=f"Created via AI Chatbot: {original_question}",
            reminder_date=reminder_date,
            reminder_time=time_str,
            repeat_type=repeat_type
        )

        if success:
            reply = (
                f"✅ Sure! I've set a reminder for <b>{display_time}</b> on <b>{reminder_date}</b>.<br><br>"
                f"💊 <b>{title}</b><br>"
                f"🔁 Repeat: <b>{repeat_type}</b><br><br>"
                f"I'll remind you at the scheduled time. 😊<br>"
                f"💙 Take care of your health, {full_name}!"
            )
        else:
            reply = f"😔 Sorry, I couldn't create the reminder. {msg}. Please try again!"

        return jsonify({'success': True, 'reply': reply, 'reminder_created': success})



    # If no health data yet – return a helpful nudge
    if not hd:
        return jsonify({
            'success': True,
            'reply': (
                f"{greeting_emoji} {greeting_text}, {full_name}! 😊<br><br>"
                "I don't have your health data on file yet. "
                "Please complete your Health Data form first so I can give you personalized insights. "
                "Go to <b>Employee Health Data Management</b> from the Dashboard. 💙"
            )
        })

    hd = dict(hd)

    # ── Recompute wellness risk (mirrors risk_prediction_page logic) ─────
    bmi_val       = float(hd.get('bmi', 0) or 0)
    bmi_cat       = hd.get('bmi_category', '') or ''
    bp_str        = hd.get('blood_pressure', '120/80') or '120/80'
    water         = hd.get('water_intake', '') or ''
    condition     = hd.get('medical_condition', 'None') or 'None'
    cond_other    = hd.get('medical_condition_other', '') or ''
    allergies     = hd.get('has_allergies', '') or ''
    disability    = hd.get('has_disability', '') or ''
    sugar_level   = hd.get('sugar_level', '') or ''
    smoking       = hd.get('smoking_habit', '') or ''
    alcohol       = hd.get('alcohol_consumption', '') or ''
    exercise_freq = hd.get('exercise_frequency', '') or ''
    exercise_type = hd.get('exercise_type', '') or ''
    daily_steps   = int(hd.get('daily_step_count', 0) or 0)
    stress_level  = hd.get('stress_level', '') or ''
    work_hours    = float(hd.get('work_hours_per_day', 0) or 0)
    attendance    = float(hd.get('attendance_percentage', 0) or 0)
    dr_remarks    = (hd.get('doctor_remarks', '') or '').strip()
    last_checkup  = hd.get('last_checkup', '') or ''
    next_checkup  = hd.get('next_checkup', '') or ''
    health_status = hd.get('health_status', '') or ''
    current_med   = (hd.get('current_medication', '') or '').strip()
    blood_group   = hd.get('blood_group', '') or ''
    height_val    = float(hd.get('height', 0) or 0)
    weight_val    = float(hd.get('weight', 0) or 0)
    allergies_det = hd.get('allergies_detail', '') or ''
    cond_label    = cond_other if condition == 'Other' else condition

    try:
        systolic, diastolic = map(int, bp_str.split('/'))
    except Exception:
        systolic, diastolic = 120, 80

    # Quick wellness score re-calc for risk category
    _bmi_sc = 15 if bmi_cat == 'Normal' else (10 if bmi_cat in ['Overweight','Underweight'] else 4)
    _bp_sc  = (15 if systolic <= 120 and diastolic <= 80 else
               11 if systolic <= 130 and diastolic <= 85 else
               7  if systolic <= 140 or  diastolic <= 90 else 3)
    _w_sc   = (10 if water in ['3 Litres','3.5 Litres','4 Litres','2.5 Litres'] else
               7  if water in ['2 Litres','More than 4 Litres'] else 3)
    _m = 15
    if condition != 'None': _m -= 5
    if allergies == 'Yes':  _m -= 2
    if disability == 'Yes': _m -= 2
    if sugar_level in ['Pre-diabetic','Diabetic','Low']: _m -= 3
    _m = max(0, _m)
    _l = 12
    if smoking == 'Regular': _l -= 5
    elif smoking == 'Occasional': _l -= 3
    elif smoking == 'Former': _l -= 1
    if alcohol == 'Heavy': _l -= 5
    elif alcohol == 'Regular': _l -= 3
    elif alcohol in ['Moderate','Occasional']: _l -= 1
    _l = max(0, _l)
    _e = 0
    if exercise_freq == 'Daily': _e += 5
    elif exercise_freq == 'Regular': _e += 4
    elif exercise_freq == 'Sometimes': _e += 3
    elif exercise_freq == 'Rarely': _e += 1
    if exercise_type in ['Gym','Swimming','Mixed','Running']: _e += 3
    elif exercise_type in ['Cycling','Sports','Yoga']: _e += 2
    elif exercise_type == 'Walking': _e += 1
    if daily_steps >= 10000: _e += 5
    elif daily_steps >= 7500: _e += 4
    elif daily_steps >= 5000: _e += 3
    elif daily_steps >= 3000: _e += 2
    elif daily_steps >= 1000: _e += 1
    _e = min(13, _e)
    _sw = 10
    if stress_level == 'Very High': _sw -= 4
    elif stress_level == 'High': _sw -= 3
    elif stress_level == 'Moderate': _sw -= 1
    if work_hours > 12: _sw -= 3
    elif work_hours > 10: _sw -= 2
    elif work_hours > 8: _sw -= 1
    if attendance < 60: _sw -= 2
    elif attendance < 75: _sw -= 1
    _sw = max(0, _sw)
    _pv = 0
    try:
        _lc = datetime.strptime(last_checkup, '%Y-%m-%d').date()
        days_since = (date.today() - _lc).days
        if days_since <= 90: _pv += 4
        elif days_since <= 180: _pv += 3
        elif days_since <= 365: _pv += 2
    except Exception:
        days_since = 9999
    try:
        _nc = datetime.strptime(next_checkup, '%Y-%m-%d').date()
        days_to_next = (_nc - date.today()).days
        if _nc >= date.today(): _pv += 2
    except Exception:
        days_to_next = -1
    if health_status == 'Excellent': _pv += 4
    elif health_status == 'Good': _pv += 3
    elif health_status == 'Average': _pv += 2
    _pv = min(10, _pv)
    wellness_score_calc = min(100, max(0, int(_bmi_sc + _bp_sc + _w_sc + _m + _l + _e + _sw + _pv)))
    if wellness_score_calc >= 80:
        risk_cat = 'Low Risk'
    elif wellness_score_calc >= 50:
        risk_cat = 'Moderate Risk'
    else:
        risk_cat = 'High Risk'

    # ── Keyword-based intent matching ────────────────────────────────────
    q = question

    def has(keywords):
        return any(kw in q for kw in keywords)

    reply = None

    # ── GENERAL HEALTH QUERY ROUTING ──────────────────────────────────────
    general_health_indicators = [
        'prevent a cold', 'prevent cold', 'prevent flu', 'how to prevent',
        'foods improve immunity', 'improve immunity', 'boost immunity', 'immunity foods',
        'water should i drink every day', 'water should i drink', 'water to drink every day', 'daily water intake', 'how much water',
        'what is diabetes', 'causes of diabetes', 'prevent diabetes',
        'causes high blood pressure', 'what causes high blood pressure', 'what causes bp', 'causes of bp', 'hypertension causes',
        'symptoms of vitamin d deficiency', 'vitamin d deficiency symptoms', 'lack of vitamin d',
        'hours should adults sleep', 'how much sleep', 'how many hours should adults sleep',
        'healthy eating habits', 'healthy eating', 'eating habits', 'healthy diet',
        'how can i reduce stress', 'how to reduce stress', 'reduce stress', 'stress reduction',
        'exercises are good for beginners', 'exercises for beginners', 'beginner exercise', 'good exercises for beginners',
        'what causes high', 'prevent a', 'preventing a', 'preventing cold', 'preventing flu'
    ]
    is_general_health = any(indicator in q for indicator in general_health_indicators)
    is_personal = any(kw in q for kw in ['my', 'me', 'own', 'profile', 'record', 'i have', 'i am', 'my next', 'my attendance', 'my work', 'my reminder'])

    if is_general_health or (not is_personal and any(kw in q for kw in ['cold', 'immunity', 'diabetes', 'hypertension', 'vitamin d', 'sleep', 'eating', 'diet', 'stress', 'exercise', 'prevention', 'prevent', 'allergy', 'fever', 'pain', 'headache', 'cure', 'symptom'])):
        reply = get_general_health_answer(original_question)

    if reply is not None:
        return jsonify({'success': True, 'reply': reply})

    # ── HEALTH SUMMARY ────────────────────────────────────────────────────
    if has(['summary', 'health summary', 'summarize', 'summarise', 'overview', 'all info', 'complete health', 'full health']):
        reply = (
            f"📋 <b>Health Summary for {full_name}</b><br><br>"
            f"🩺 <b>BMI:</b> {bmi_val:.1f} ({bmi_cat})<br>"
            f"💉 <b>Blood Pressure:</b> {bp_str} mmHg<br>"
            f"🍬 <b>Blood Sugar:</b> {sugar_level or 'Not specified'}<br>"
            f"❤️ <b>Heart Rate:</b> {hd.get('heart_rate', 'Not recorded') or 'Not recorded'}<br>"
            f"💧 <b>Water Intake:</b> {water}<br>"
            f"🏃 <b>Exercise:</b> {exercise_freq} ({exercise_type})<br>"
            f"👟 <b>Daily Steps:</b> {daily_steps:,}<br>"
            f"😰 <b>Stress Level:</b> {stress_level}<br>"
            f"📅 <b>Attendance:</b> {attendance:.1f}%<br>"
            f"⏰ <b>Work Hours/Day:</b> {work_hours:.1f} hrs<br>"
            f"🏥 <b>Last Check-up:</b> {last_checkup}<br>"
            f"🗓️ <b>Next Check-up:</b> {next_checkup}<br>"
            f"⚠️ <b>Risk Level:</b> {risk_cat}<br>"
            f"⭐ <b>Health Score:</b> {score}/100 ({score_status})<br>"
            f"👨‍⚕️ <b>Doctor Remarks:</b> {dr_remarks if dr_remarks else 'None'}"
        )

    # ── BMI ───────────────────────────────────────────────────────────────
    elif has(['bmi', 'body mass', 'weight status', 'underweight', 'overweight', 'obese']):
        bmi_advice = {
            'Normal': 'Your BMI is in the healthy normal range. Keep maintaining your balanced diet and active lifestyle.',
            'Overweight': 'Your BMI indicates you are overweight. Try to include more aerobic exercises and reduce calorie intake.',
            'Obese': 'Your BMI is in the obese range. It is important to consult a doctor and start a supervised weight management plan.',
            'Underweight': 'You are underweight. Focus on a nutrient-rich diet and strength training to build healthy mass.'
        }.get(bmi_cat, 'Please consult your doctor for BMI advice.')
        reply = (
            f"⚖️ <b>Your BMI is {bmi_val:.1f}</b> — classified as <b>{bmi_cat}</b>.<br><br>"
            f"📐 Height: {height_val} cm | Weight: {weight_val} kg<br><br>"
            f"💡 {bmi_advice}"
        )

    # ── BLOOD PRESSURE ────────────────────────────────────────────────────
    elif has(['blood pressure', 'bp', 'hypertension', 'systolic', 'diastolic']):
        if systolic <= 120 and diastolic <= 80:
            bp_status = 'Normal ✅'
            bp_advice = 'Your blood pressure is excellent. Keep up the healthy habits!'
        elif systolic <= 130 and diastolic <= 85:
            bp_status = 'Elevated ⚠️'
            bp_advice = 'Slightly elevated. Reduce salt intake and manage stress.'
        elif systolic <= 140 or diastolic <= 90:
            bp_status = 'Stage 1 Hypertension ⚠️'
            bp_advice = 'You have Stage 1 Hypertension. Consult your doctor and consider lifestyle changes.'
        else:
            bp_status = 'Stage 2 Hypertension 🚨'
            bp_advice = 'Your blood pressure is dangerously high. Please seek medical attention immediately.'
        reply = (
            f"💉 <b>Blood Pressure: {bp_str} mmHg</b> — {bp_status}<br><br>"
            f"💡 {bp_advice}"
        )

    # ── BLOOD SUGAR ───────────────────────────────────────────────────────
    elif has(['blood sugar', 'sugar', 'glucose', 'diabetic', 'diabetes', 'pre-diabetic', 'prediabetic']):
        sugar_advice = {
            'Normal': 'Your blood sugar is in the normal range. Keep your diet balanced.',
            'Pre-diabetic': 'You are pre-diabetic. Reduce sugar intake, exercise regularly, and monitor your blood sugar often.',
            'Diabetic': 'You are diabetic. Strictly follow your doctor\'s medication plan and dietary guidelines.',
            'Low': 'Your blood sugar is low. Eat frequent small meals and avoid skipping meals.'
        }.get(sugar_level, 'Not specified — please record your blood sugar level in your health data.')
        reply = (
            f"🍬 <b>Blood Sugar Level: {sugar_level or 'Not recorded'}</b><br><br>"
            f"💡 {sugar_advice}"
        )

    # ── HEART RATE ────────────────────────────────────────────────────────
    elif has(['heart rate', 'pulse', 'heartbeat', 'heart']):
        reply = (
            f"❤️ <b>Heart Rate</b><br><br>"
            f"Your heart rate data is linked to your wellness profile. "
            f"A normal resting heart rate for adults is 60–100 bpm.<br><br>"
            f"Your current wellness score is <b>{score}/100</b> ({score_status}), which reflects your overall cardiovascular health. "
            f"Regular aerobic exercise helps maintain a healthy heart rate."
        )

    # ── HEALTH SCORE ──────────────────────────────────────────────────────
    elif has(['health score', 'wellness score', 'score', 'rating', 'health rating']):
        reply = (
            f"⭐ <b>Your Health Score is {score}/100</b> — {score_status}<br><br>"
            f"{'🟢 Excellent! Your health indicators are outstanding.' if score >= 80 else '🟡 Good standing — a few healthy habits can push you higher.' if score >= 60 else '🟠 Average — focus on improving your weakest health areas.' if score >= 40 else '🔴 Needs Improvement — please follow your personalized recommendations and consult a healthcare provider.'}<br><br>"
            f"Your risk level is: <b>{risk_cat}</b>"
        )

    # ── RISK LEVEL ────────────────────────────────────────────────────────
    elif has(['risk', 'risk level', 'at risk', 'high risk', 'low risk', 'moderate risk', 'am i at risk', 'wellness risk', 'prediction']):
        if risk_cat == 'Low Risk':
            risk_detail = '🟢 Great news! Your wellness indicators are healthy. Keep up the great work!'
        elif risk_cat == 'Moderate Risk':
            risk_detail = '🟡 You have a moderate risk level. A few lifestyle improvements can significantly boost your wellness score.'
        else:
            risk_detail = '🔴 Your wellness assessment indicates a High Risk level. Please follow your personalized recommendations and consult a healthcare professional as soon as possible.'
        reply = (
            f"⚠️ <b>Wellness Risk Prediction: {risk_cat}</b><br>"
            f"📊 Wellness Score: {wellness_score_calc}/100<br><br>"
            f"{risk_detail}"
        )

    # ── WHY HIGH/MODERATE RISK ────────────────────────────────────────────
    elif has(['why', 'reason', 'cause', 'because', 'explain risk', 'explain my risk']):
        reasons = []
        if bmi_cat in ['Obese', 'Overweight', 'Underweight']:
            reasons.append(f"BMI classified as <b>{bmi_cat}</b> ({bmi_val:.1f})")
        if systolic > 130 or diastolic > 85:
            reasons.append(f"Blood pressure elevated at <b>{bp_str} mmHg</b>")
        if sugar_level in ['Diabetic', 'Pre-diabetic']:
            reasons.append(f"Blood sugar level: <b>{sugar_level}</b>")
        if smoking == 'Regular':
            reasons.append("Regular smoking habit")
        if alcohol in ['Heavy', 'Regular']:
            reasons.append(f"Alcohol consumption: <b>{alcohol}</b>")
        if stress_level in ['High', 'Very High']:
            reasons.append(f"High stress level: <b>{stress_level}</b>")
        if exercise_freq in ['Never', 'Rarely', '']:
            reasons.append("Insufficient physical activity")
        if daily_steps < 5000:
            reasons.append(f"Low daily step count: <b>{daily_steps:,} steps</b>")
        if water == 'Less than 2 Litres':
            reasons.append("Low water intake")
        if condition != 'None':
            reasons.append(f"Medical condition: <b>{cond_label}</b>")
        if days_since > 365:
            reasons.append("Last health check-up was over 1 year ago")
        if reasons:
            reason_list = '<br>'.join([f"• {r}" for r in reasons])
            reply = (
                f"🔍 <b>Reasons contributing to your {risk_cat} level:</b><br><br>"
                f"{reason_list}<br><br>"
                f"💡 Follow your personalized recommendations to improve each of these areas."
            )
        else:
            reply = f"Your risk level is <b>{risk_cat}</b> with a wellness score of {wellness_score_calc}/100. Your overall health indicators are looking reasonable — maintain your current habits!"

    # ── RECOMMENDATIONS ───────────────────────────────────────────────────
    elif has(['recommendation', 'suggest', 'advice', 'tips', 'what should i do', 'improve health', 'improve my health']):
        recs = []
        if bmi_cat in ['Obese', 'Overweight']:
            recs.append("🏃 Aim for 30–45 minutes of aerobic exercise daily to manage weight.")
        if bmi_cat == 'Underweight':
            recs.append("🍽️ Increase calorie intake with nutrient-dense foods and strength training.")
        if systolic > 130:
            recs.append("🧘 Reduce sodium intake and practice stress-reduction techniques for BP control.")
        if sugar_level in ['Diabetic', 'Pre-diabetic']:
            recs.append("🍬 Limit sugar and refined carbs. Monitor blood glucose regularly.")
        if smoking == 'Regular':
            recs.append("🚭 Consider a smoking cessation program immediately.")
        if alcohol in ['Heavy', 'Regular']:
            recs.append("🍷 Reduce alcohol consumption significantly.")
        if stress_level in ['High', 'Very High']:
            recs.append("🧘 Practice meditation, deep breathing, or yoga for stress management.")
        if exercise_freq in ['Never', 'Rarely', '']:
            recs.append("🏋️ Start with a 20-minute walk daily and gradually increase intensity.")
        if daily_steps < 8000:
            recs.append(f"👟 Increase your daily steps toward 8,000–10,000. Currently at {daily_steps:,}.")
        if water == 'Less than 2 Litres':
            recs.append("💧 Drink at least 2–3 litres of water every day.")
        if work_hours > 10:
            recs.append("⏰ Set boundaries on work hours — aim for no more than 8–9 hours daily.")
        if dr_remarks:
            recs.append(f"👨‍⚕️ Follow your doctor's advice: <i>\"{dr_remarks}\"</i>")
        if not recs:
            recs.append("✅ Your health metrics look good! Continue with your current wellness routine.")
        reply = "<b>💡 Personalized Recommendations:</b><br><br>" + "<br>".join(recs)

    # ── EXERCISE ──────────────────────────────────────────────────────────
    elif has(['exercise', 'workout', 'fitness', 'gym', 'yoga', 'running', 'walking', 'steps', 'step count', 'activity']):
        reply = (
            f"🏃 <b>Your Exercise Profile</b><br><br>"
            f"• Frequency: <b>{exercise_freq or 'Not specified'}</b><br>"
            f"• Type: <b>{exercise_type or 'Not specified'}</b><br>"
            f"• Daily Steps: <b>{daily_steps:,}</b><br><br>"
        )
        if daily_steps < 5000:
            reply += "⚠️ Your step count is quite low. Try to walk at least 8,000–10,000 steps per day.<br>"
        elif daily_steps >= 10000:
            reply += "✅ Excellent step count! You are meeting the recommended daily goal.<br>"
        else:
            reply += "💡 You're doing well — try to push toward 10,000 steps daily for optimal health.<br>"
        if exercise_freq in ['Never', 'Rarely', '']:
            reply += "<br>🏋️ Start with 20–30 minutes of light cardio 3 times a week and gradually increase."
        else:
            reply += f"<br>Keep it up with {exercise_type} exercises — consistency is key!"

    # ── WATER INTAKE ──────────────────────────────────────────────────────
    elif has(['water', 'hydration', 'drink', 'fluid', 'litres', 'liters']):
        water_advice = {
            'Less than 2 Litres': '⚠️ You are not drinking enough water. Aim for at least 2–3 litres daily. Dehydration can cause fatigue, headaches, and kidney issues.',
            '2 Litres': '💧 You are meeting the minimum recommendation. Try to increase to 2.5–3 litres for better hydration.',
            '2.5 Litres': '✅ Good hydration! Keep it consistent every day.',
            '3 Litres': '✅ Excellent! You are well-hydrated.',
            '3.5 Litres': '✅ Great hydration level — your body will thank you!',
            '4 Litres': '✅ Very well hydrated. Perfect for active individuals.',
            'More than 4 Litres': '💡 Make sure you are not over-hydrating — balance is important.'
        }.get(water, f'Your water intake is recorded as: {water}.')
        reply = f"💧 <b>Water Intake: {water}</b><br><br>{water_advice}"

    # ── STRESS ────────────────────────────────────────────────────────────
    elif has(['stress', 'stress level', 'mental health', 'anxiety', 'burnout', 'mental', 'relax', 'calm']):
        stress_advice = {
            'Low': '✅ Your stress level is low. Keep a balanced routine to maintain this.',
            'Moderate': '💛 Moderate stress detected. Consider mindfulness exercises, short breaks, and better sleep hygiene.',
            'High': '⚠️ High stress level! Practice deep breathing, meditation, or yoga daily. Consider speaking to a wellness counselor.',
            'Very High': '🚨 Very High stress is seriously impacting your health. Please seek professional mental wellness support immediately.'
        }.get(stress_level, 'Stress level not recorded. Please update your health data.')
        reply = (
            f"😰 <b>Stress Level: {stress_level or 'Not recorded'}</b><br><br>"
            f"{stress_advice}<br><br>"
            f"⏰ Work hours per day: <b>{work_hours:.0f} hrs</b> — {'High workload can worsen stress levels.' if work_hours > 9 else 'Manageable workload.'}"
        )

    # ── DOCTOR REMARKS ────────────────────────────────────────────────────
    elif has(['doctor', "doctor's", 'remarks', 'physician', 'medical advice', 'doctor advice', 'doctor recommend']):
        if dr_remarks:
            reply = (
                f"👨‍⚕️ <b>Doctor's Remarks</b><br><br>"
                f"<i>\"{dr_remarks}\"</i><br><br>"
                f"{'Current Medication: ' + current_med if current_med else 'No current medication recorded.'}<br><br>"
                f"💡 Please ensure you are following your doctor's advice. If you have concerns, schedule a follow-up."
            )
        else:
            reply = "👨‍⚕️ No doctor remarks have been recorded yet. Please update your health data after your next consultation."

    # ── CHECK-UP DATES ────────────────────────────────────────────────────
    elif has(['checkup', 'check-up', 'check up', 'next appointment', 'appointment', 'next visit', 'last checkup', 'last check-up']):
        last_msg = f"📅 Last check-up: <b>{last_checkup}</b>" if last_checkup else "📅 Last check-up: Not recorded"
        next_msg = f"🗓️ Next check-up: <b>{next_checkup}</b>" if next_checkup else "🗓️ Next check-up: Not scheduled"
        urgency = ""
        if days_to_next != -1:
            if days_to_next < 0:
                urgency = "<br>🚨 <b>Your next health check-up is overdue!</b> Please schedule one immediately."
            elif days_to_next <= 30:
                urgency = f"<br>⚠️ Your next check-up is in <b>{days_to_next} days</b>. Please confirm your appointment."
            else:
                urgency = f"<br>✅ Your next check-up is in <b>{days_to_next} days</b>. All scheduled."
        reply = f"{last_msg}<br>{next_msg}{urgency}"

    # ── SMOKING ───────────────────────────────────────────────────────────
    elif has(['smoking', 'smoke', 'cigarette', 'tobacco']):
        smoke_msg = {
            'Never': '✅ Great — you have never smoked. Keep it that way!',
            'Former': '💪 Well done on quitting smoking! Your body continues to recover over time.',
            'Occasional': '⚠️ Even occasional smoking damages lung tissue and arteries. Consider eliminating this habit.',
            'Regular': '🚨 Regular smoking significantly increases risk of lung cancer, heart disease, and stroke. Please seek a cessation program.'
        }.get(smoking, 'Not recorded.')
        reply = f"🚬 <b>Smoking Habit: {smoking or 'Not recorded'}</b><br><br>{smoke_msg}"

    # ── ALCOHOL ───────────────────────────────────────────────────────────
    elif has(['alcohol', 'drinking', 'drink alcohol', 'wine', 'beer']):
        alc_msg = {
            'Never': '✅ Excellent — you do not consume alcohol.',
            'Occasional': '💡 Occasional drinking is low risk, but be mindful of frequency.',
            'Moderate': '⚠️ Moderate consumption can impact liver function over time. Consider reducing.',
            'Regular': '⚠️ Regular alcohol intake affects your liver, BP, and sleep quality.',
            'Heavy': '🚨 Heavy alcohol consumption is a serious health risk. Please seek medical guidance.'
        }.get(alcohol, 'Not recorded.')
        reply = f"🍷 <b>Alcohol Consumption: {alcohol or 'Not recorded'}</b><br><br>{alc_msg}"

    # ── MEDICAL CONDITIONS / ALLERGIES ────────────────────────────────────
    elif has(['medical condition', 'condition', 'allergy', 'allergies', 'medication', 'disease', 'illness', 'disability']):
        cond_msg = f"🏥 Medical Condition: <b>{cond_label if condition != 'None' else 'None reported'}</b>"
        allergy_msg = f"🤧 Allergies: <b>{'Yes — ' + allergies_det if allergies == 'Yes' else 'No known allergies'}</b>"
        med_msg = f"💊 Current Medication: <b>{current_med if current_med else 'None'}</b>"
        dis_msg = f"♿ Disability: <b>{hd.get('disability_detail','') if disability == 'Yes' else 'None reported'}</b>"
        reply = f"{cond_msg}<br>{allergy_msg}<br>{med_msg}<br>{dis_msg}"

    # ── ATTENDANCE ───────────────────────────────────────────────────────
    elif has(['attendance', 'attendance percentage', 'absent', 'present']):
        att_msg = (
            '🚨 Your attendance is critically low. This may affect your wellness assessment and work performance.'
            if attendance < 60 else
            '⚠️ Your attendance is below average. Try to improve consistency.'
            if attendance < 75 else
            '💛 Attendance is moderate. A bit more consistency will help.'
            if attendance < 85 else
            '✅ Good attendance record! Keep it up.'
        )
        reply = f"📅 <b>Attendance: {attendance:.1f}%</b><br><br>{att_msg}"

    # ── WORK HOURS ────────────────────────────────────────────────────────
    elif has(['work hours', 'working hours', 'overtime', 'hours per day', 'work time']):
        wh_msg = (
            '🚨 Working more than 12 hours/day is dangerous for your health. Set firm boundaries.'
            if work_hours > 12 else
            '⚠️ You are overworking. Try to limit to 8–9 hours per day for sustained health.'
            if work_hours > 9 else
            '✅ Your work hours are within a healthy range.'
        )
        reply = f"⏰ <b>Work Hours per Day: {work_hours:.1f} hrs</b><br><br>{wh_msg}"

    # ── HELLO / GREET ─────────────────────────────────────────────────────
    elif has(['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'greet', 'namaste']):
        reply = (
            f"{greeting_emoji} {greeting_text}, <b>{full_name}</b>! 😊<br><br>"
            f"I'm your AI Wellness Assistant. How can I help you today?<br><br>"
            f"📊 Your current health score is <b>{score}/100</b> ({score_status}) and your risk level is <b>{risk_cat}</b>.<br><br>"
            f"You can ask me about your BMI, blood pressure, blood sugar, exercise, stress, doctor remarks, check-up dates, wellness risk, recommendations, and more!<br><br>"
            f"💡 You can also say things like:<br>"
            f"• \"Remind me to take my tablet at 8 AM\"<br>"
            f"• \"How can I prevent cold?\"<br>"
            f"• \"What should I eat for better health?\"<br><br>"
            f"💙 I'm always here to help!"
        )

    # ── THANK YOU ─────────────────────────────────────────────────────────
    elif has(['thank', 'thanks', 'thank you', 'thx', 'ty']):
        reply = f"😊 You're welcome, {full_name}! Stay healthy and take care. Feel free to ask me anything about your wellness anytime! 💙"

    # ── GENERAL HEALTH Q&A ────────────────────────────────────────────────
    elif has(['cold', 'flu', 'cough', 'fever', 'sore throat', 'runny nose', 'sneeze', 'congestion']):
        recs_for_cold = []
        if allergies == 'Yes':
            recs_for_cold.append(f"🤧 Since you have allergies ({allergies_det}), cold symptoms may be allergy-related. Consult your doctor.")
        if stress_level in ['High', 'Very High']:
            recs_for_cold.append("😰 Your high stress levels can weaken your immune system, making you more vulnerable to colds.")
        if water == 'Less than 2 Litres':
            recs_for_cold.append("💧 Increase your water intake. Staying hydrated helps your body fight infections.")
        if exercise_freq in ['Never', 'Rarely', '']:
            recs_for_cold.append("🏃 Regular moderate exercise boosts your immune system and helps prevent colds.")
        reply = (
            f"🤒 <b>Cold & Flu Prevention Tips</b><br><br>"
            f"Here are some tips to prevent and manage cold symptoms:<br><br>"
            f"✅ Wash your hands frequently with soap and water<br>"
            f"✅ Get adequate sleep (7-8 hours per night)<br>"
            f"✅ Drink warm fluids like herbal tea, warm water with lemon & honey<br>"
            f"✅ Eat Vitamin C rich foods (oranges, lemons, amla, guava)<br>"
            f"✅ Avoid cold drinks and ice cream<br>"
            f"✅ Use steam inhalation for congestion relief<br>"
            f"✅ Gargle with warm salt water for sore throat<br>"
            f"✅ Boost immunity with turmeric milk (golden milk)<br><br>"
        )
        if recs_for_cold:
            reply += "<b>Based on your health profile:</b><br>" + "<br>".join(recs_for_cold) + "<br><br>"
        reply += f"💙 Take care, {full_name}! If symptoms persist beyond 3-5 days, please consult your doctor. 😊"

    elif has(['headache', 'migraine', 'head pain', 'head ache']):
        reply = (
            f"🤕 <b>Headache & Migraine Tips</b><br><br>"
            f"Here are some tips to manage headaches:<br><br>"
            f"✅ Stay well hydrated — drink plenty of water<br>"
            f"✅ Take regular screen breaks (20-20-20 rule)<br>"
            f"✅ Practice deep breathing and relaxation techniques<br>"
            f"✅ Get adequate sleep (7-8 hours)<br>"
            f"✅ Avoid excessive caffeine consumption<br>"
            f"✅ Apply a cold or warm compress to your forehead<br>"
        )
        if stress_level in ['High', 'Very High']:
            reply += f"<br>😰 Your stress level is <b>{stress_level}</b>, which is a common trigger for headaches. Consider meditation or yoga.<br>"
        if work_hours > 9:
            reply += f"<br>⏰ Working {work_hours:.0f} hours/day can cause tension headaches. Try to take regular breaks.<br>"
        reply += f"<br>💙 Feel better soon, {full_name}! 😊"

    elif has(['diet', 'food', 'eat', 'nutrition', 'meal', 'breakfast', 'lunch', 'dinner', 'snack', 'weight loss', 'weight gain']):
        reply = (
            f"🥗 <b>Nutrition & Diet Tips</b><br><br>"
            f"Based on your BMI of <b>{bmi_val:.1f} ({bmi_cat})</b>:<br><br>"
        )
        if bmi_cat in ['Obese', 'Overweight']:
            reply += (
                "✅ Focus on portion control and balanced meals<br>"
                "✅ Include more vegetables, lean protein, and whole grains<br>"
                "✅ Reduce processed foods, sugar, and fried items<br>"
                "✅ Eat smaller, frequent meals instead of 3 large meals<br>"
                "✅ Avoid late-night snacking<br>"
            )
        elif bmi_cat == 'Underweight':
            reply += (
                "✅ Increase your calorie intake with nutrient-dense foods<br>"
                "✅ Include healthy fats (nuts, avocado, ghee)<br>"
                "✅ Eat protein-rich foods (eggs, paneer, dal, chicken)<br>"
                "✅ Have milkshakes, smoothies, and dry fruits as snacks<br>"
            )
        else:
            reply += (
                "✅ Continue with your balanced diet<br>"
                "✅ Include colorful fruits and vegetables daily<br>"
                "✅ Stay hydrated with 2-3 litres of water<br>"
            )
        if sugar_level in ['Diabetic', 'Pre-diabetic']:
            reply += "<br>🍬 Since your blood sugar is <b>{}</b>, limit sugar and refined carbs.<br>".format(sugar_level)
        reply += f"<br>💙 Healthy eating is the foundation of wellness! 😊"

    elif has(['sleep', 'insomnia', 'tired', 'fatigue', 'rest', 'sleepy', 'nap']):
        reply = (
            f"😴 <b>Sleep & Rest Tips</b><br><br>"
            f"Getting quality sleep is essential for your health!<br><br>"
            f"✅ Aim for 7-8 hours of sleep every night<br>"
            f"✅ Maintain a consistent sleep schedule<br>"
            f"✅ Avoid screens 1 hour before bedtime<br>"
            f"✅ Keep your bedroom dark, cool, and quiet<br>"
            f"✅ Avoid caffeine after 4 PM<br>"
            f"✅ Try relaxation techniques like deep breathing before bed<br>"
        )
        if stress_level in ['High', 'Very High']:
            reply += f"<br>😰 Your stress level (<b>{stress_level}</b>) may be affecting your sleep. Consider meditation before bed.<br>"
        if work_hours > 10:
            reply += f"<br>⏰ Long work hours ({work_hours:.0f} hrs/day) can disrupt sleep patterns. Set firm boundaries.<br>"
        reply += f"<br>💙 Good sleep = Good health! Make sure you get at least 7-8 hours of sleep. 😊"

    elif has(['back pain', 'body pain', 'muscle pain', 'joint pain', 'knee pain', 'neck pain', 'shoulder pain']):
        reply = (
            f"💪 <b>Pain Management Tips</b><br><br>"
            f"Here are some tips for managing body pain:<br><br>"
            f"✅ Maintain proper posture while working<br>"
            f"✅ Take regular breaks and stretch every 30-45 minutes<br>"
            f"✅ Apply hot or cold compress to the affected area<br>"
            f"✅ Practice gentle stretching exercises or yoga<br>"
            f"✅ Stay active with low-impact exercises like walking or swimming<br>"
            f"✅ Ensure your workspace is ergonomically setup<br>"
        )
        if exercise_freq in ['Never', 'Rarely', '']:
            reply += "<br>🏃 Regular exercise can help prevent and reduce body pain. Start with gentle walks.<br>"
        reply += f"<br>💙 If pain persists, please consult your doctor, {full_name}. 😊"

    elif has(['skin', 'acne', 'pimple', 'rash', 'eczema', 'dry skin']):
        reply = (
            f"✨ <b>Skin Health Tips</b><br><br>"
            f"✅ Drink plenty of water (at least 2-3 litres daily)<br>"
            f"✅ Eat foods rich in Vitamin C and E<br>"
            f"✅ Protect your skin from sun exposure<br>"
            f"✅ Follow a gentle skincare routine<br>"
            f"✅ Get adequate sleep for skin repair<br>"
            f"✅ Manage stress — it affects skin health<br>"
        )
        if water == 'Less than 2 Litres':
            reply += "<br>💧 Your water intake is low. Hydration is key for healthy skin!<br>"
        reply += f"<br>💙 Healthy skin starts from within! 😊"

    elif has(['eye', 'eyes', 'vision', 'eye strain', 'eyesight', 'spectacles', 'glasses']):
        reply = (
            f"👁️ <b>Eye Health Tips</b><br><br>"
            f"✅ Follow the 20-20-20 rule: Every 20 mins, look at something 20 feet away for 20 seconds<br>"
            f"✅ Adjust screen brightness and use blue light filters<br>"
            f"✅ Keep your screen at arm's length<br>"
            f"✅ Blink frequently to prevent dry eyes<br>"
            f"✅ Eat carrots, spinach, and foods rich in Vitamin A<br>"
            f"✅ Get regular eye check-ups<br>"
        )
        if work_hours > 8:
            reply += f"<br>⏰ Working {work_hours:.0f} hours/day on screens can strain your eyes. Take frequent breaks!<br>"
        reply += f"<br>💙 Protect your precious eyes, {full_name}! 😊"

    elif has(['immunity', 'immune', 'prevent', 'protection', 'boost', 'strong', 'healthy life', 'stay healthy']):
        reply = (
            f"🛡️ <b>Immunity Boosting Tips</b><br><br>"
            f"Here's how you can strengthen your immunity:<br><br>"
            f"✅ Eat a balanced diet rich in fruits, vegetables, and whole grains<br>"
            f"✅ Exercise regularly (at least 30 mins daily)<br>"
            f"✅ Get 7-8 hours of quality sleep<br>"
            f"✅ Stay well hydrated<br>"
            f"✅ Manage stress through meditation or yoga<br>"
            f"✅ Include Vitamin C, Zinc, and Vitamin D in your diet<br>"
            f"✅ Maintain hygiene — wash hands regularly<br>"
            f"✅ Avoid smoking and limit alcohol consumption<br>"
        )
        if smoking in ['Regular', 'Occasional']:
            reply += f"<br>🚭 Your smoking habit ({smoking}) weakens immunity. Consider quitting.<br>"
        if alcohol in ['Heavy', 'Regular']:
            reply += f"<br>🍷 Your alcohol consumption ({alcohol}) can impair immune function. Consider reducing.<br>"
        reply += f"<br>💙 A strong immune system is your best defense! 😊"

    elif has(['medicine', 'tablet', 'pill', 'capsule', 'drug', 'dosage', 'prescription']):
        if current_med:
            reply = (
                f"💊 <b>Your Current Medication</b><br><br>"
                f"You are currently taking: <b>{current_med}</b><br><br>"
                f"✅ Take your medicines on time as prescribed<br>"
                f"✅ Never skip doses or self-medicate<br>"
                f"✅ Store medicines properly<br>"
                f"✅ Inform your doctor about any side effects<br><br>"
                f"💡 Tip: You can say \"Remind me to take my tablet at 8 AM\" and I'll set a reminder for you! 😊"
            )
        else:
            reply = (
                f"💊 <b>Medication Tips</b><br><br>"
                f"No current medication is recorded in your profile.<br><br>"
                f"✅ Always consult your doctor before taking any medicine<br>"
                f"✅ Never self-medicate<br>"
                f"✅ Keep a record of all your medications<br><br>"
                f"💡 Tip: You can say \"Remind me to take my tablet at 8 AM\" and I'll set a reminder for you! 😊"
            )

    elif has(['my reminder', 'my reminders', 'show reminder', 'list reminder', 'upcoming reminder', 'pending reminder']):
        reminders = database.get_reminders(user['id'])
        if reminders:
            rem_list = ""
            for r in reminders[:5]:
                status_icon = '⏳' if r['status'] == 'Pending' else ('⏰' if r['status'] == 'Snoozed' else '✅')
                rem_list += f"{status_icon} <b>{r['title']}</b> — {r['reminder_time']} on {r['reminder_date']} ({r['status']})<br>"
            reply = (
                f"🔔 <b>Your Upcoming Reminders</b><br><br>"
                f"{rem_list}<br>"
                f"You have <b>{len(reminders)}</b> active reminder(s). 😊"
            )
        else:
            reply = (
                f"🔔 <b>No Active Reminders</b><br><br>"
                f"You don't have any pending reminders right now.<br><br>"
                f"💡 You can create one by saying something like:<br>"
                f"• \"Remind me to take my tablet at 8 AM\"<br>"
                f"• \"Remind me to drink water every 2 hours\"<br>"
                f"• \"Remind me to exercise at 6 PM\" 😊"
            )

    # ── GREAT/AWESOME/NICE ─────────────────────────────────────────────────
    elif has(['great', 'awesome', 'nice', 'good', 'wonderful', 'amazing', 'fantastic', 'cool', 'perfect']):
        reply = f"😊 Glad to hear that, {full_name}! Keep up the healthy habits! 💙"

    # ── HOW ARE YOU ────────────────────────────────────────────────────────
    elif has(['how are you', 'how r u', 'whats up', "what's up", 'how do you do']):
        reply = (
            f"😊 I'm doing great, {full_name}! Thank you for asking!<br><br>"
            f"I'm here to help you with your health and wellness. How can I assist you today? 💙"
        )

    # ── WHO ARE YOU ────────────────────────────────────────────────────────
    elif has(['who are you', 'what are you', 'your name', 'introduce yourself']):
        reply = (
            f"🤖 I'm your <b>AI Wellness Assistant</b>! 😊<br><br>"
            f"I'm designed to help you with your health and wellness journey. I can:<br><br>"
            f"📊 Analyze your health data<br>"
            f"💡 Give personalized recommendations<br>"
            f"🔔 Set health reminders<br>"
            f"🗣️ Answer your health questions<br>"
            f"📋 Summarize your health profile<br><br>"
            f"💙 I'm always here for you, {full_name}!"
        )

    # ── HELP ──────────────────────────────────────────────────────────────
    elif has(['help', 'what can you do', 'features', 'options', 'commands', 'how to use']):
        reply = (
            f"ℹ️ <b>Here's what I can help you with:</b><br><br>"
            f"📊 <b>Health Data:</b> BMI, Blood Pressure, Blood Sugar, Heart Rate<br>"
            f"🏥 <b>Medical Info:</b> Conditions, Allergies, Medications<br>"
            f"🏃 <b>Lifestyle:</b> Exercise, Steps, Water Intake<br>"
            f"😰 <b>Wellness:</b> Stress Level, Work Hours, Attendance<br>"
            f"⚠️ <b>Risk:</b> Wellness Risk Prediction & Analysis<br>"
            f"💡 <b>Tips:</b> Personalized Recommendations<br>"
            f"🔔 <b>Reminders:</b> Set personal health reminders<br>"
            f"📋 <b>Summary:</b> Complete health summary<br><br>"
            f"💬 <b>General Health:</b> Cold, Flu, Diet, Sleep, Pain, Skin, Eyes, Immunity<br><br>"
            f"Just type or speak your question! 😊 💙"
        )

    # ── OUT OF SCOPE ──────────────────────────────────────────────────────
    else:
        fallback_generated = False
        if gemini_api_key:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash', system_instruction="You are a professional Employee Wellness AI Assistant. Answer the user's question concisely in a helpful, supportive tone. Keep the answer under 3-4 short paragraphs and use HTML formatting (<br> for newlines, <b> for bold). Do NOT use markdown. Start the response warmly.")
                response = model.generate_content(original_question)
                if response and response.text:
                    reply = response.text
                    # Fallback cleanup to ensure newlines are converted to <br> if the model ignores the instruction
                    reply = reply.replace('\n', '<br>')
                    fallback_generated = True
            except Exception as e:
                print(f"Gemini API Error: {e}")
                
        if not fallback_generated:
            # Try to give a helpful general response instead of "I can't help"
            reply = (
                f"{greeting_emoji} {greeting_text}, {full_name}! 😊<br><br>"
                f"I appreciate your question! While I specialize in wellness topics, here's what I can help you with:<br><br>"
                f"📊 Health Data (BMI, BP, Blood Sugar, Heart Rate)<br>"
                f"🏥 Medical Conditions & Allergies<br>"
                f"🚬 Smoking & Alcohol Habits<br>"
                f"🏃 Exercise, Steps & Water Intake<br>"
                f"😰 Stress Level & Work Hours<br>"
                f"📅 Attendance & Check-up Dates<br>"
                f"👨‍⚕️ Doctor Remarks & Medication<br>"
                f"⚠️ Wellness Risk Prediction<br>"
                f"💡 Personalized Health Recommendations<br>"
                f"🔔 Personal Health Reminders<br>"
                f"🤒 General Health Tips (Cold, Diet, Sleep, Pain, etc.)<br><br>"
                f"Try asking me something like:<br>"
                f"• \"What is my BMI?\"<br>"
                f"• \"How can I prevent cold?\"<br>"
                f"• \"Remind me to take my tablet at 8 AM\"<br>"
                f"• \"Give me health recommendations\"<br><br>"
                f"💙 I'm always here to help with your wellness journey!"
            )

    return jsonify({'success': True, 'reply': reply})


# ─────────────────────────────────────────────────────────────
# REMINDER API ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.route('/api/reminders', methods=['GET'])
def api_get_reminders():
    """Fetch all active reminders for the logged-in employee."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    reminders = database.get_reminders(user['id'])
    return jsonify({'success': True, 'reminders': reminders})

@app.route('/api/reminders', methods=['POST'])
def api_create_reminder():
    """Create a new reminder via direct API (not chatbot)."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    reminder_date = data.get('reminder_date', '').strip()
    reminder_time = data.get('reminder_time', '').strip()
    repeat_type = data.get('repeat_type', 'Once').strip()
    if not title or not reminder_date or not reminder_time:
        return jsonify({'success': False, 'message': 'Title, date and time are required.'}), 400
    success, msg, rid = database.create_reminder(
        user['id'], title, description, reminder_date, reminder_time, repeat_type
    )
    if success:
        return jsonify({'success': True, 'message': msg, 'reminder_id': rid})
    return jsonify({'success': False, 'message': msg}), 500

@app.route('/api/reminders/<int:reminder_id>/action', methods=['POST'])
def api_reminder_action(reminder_id):
    """Mark a reminder as Done or Snooze it."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    data = request.get_json(silent=True) or {}
    action = data.get('action', '').strip().lower()
    if action == 'done':
        success, msg = database.update_reminder_status(reminder_id, user['id'], 'Done')
    elif action == 'snooze':
        minutes = int(data.get('minutes', 10))
        success, msg = database.snooze_reminder(reminder_id, user['id'], minutes)
    elif action == 'delete':
        success, msg = database.delete_reminder(reminder_id, user['id'])
    else:
        return jsonify({'success': False, 'message': 'Invalid action. Use done, snooze, or delete.'}), 400
    if success:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400

@app.route('/api/reminders/due', methods=['GET'])
def api_due_reminders():
    """Fetch reminders that are currently due for the logged-in employee."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    due = database.get_due_reminders(user['id'])
    return jsonify({'success': True, 'due_reminders': due})


# ─────────────────────────────────────────────────────────────
# END MODULE 6
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# MODULE 4: MENTAL HEALTH & SENTIMENT ANALYTICS
# ─────────────────────────────────────────────────────────────

@app.route('/sentiment-analytics')
def sentiment_analytics_page():
    """Employee-facing Sentiment Analytics page."""
    if 'username' not in session:
        return redirect(url_for('index'))
    user = database.get_user_by_username(session['username'])
    if not user or user['job_role'] == 'admin' or user['username'] == 'admin':
        return redirect(url_for('index'))

    # Fetch this employee's previous sentiment records
    history = database.get_sentiment_history(user['id']) or []
    return render_template(
        'sentiment_analytics.html',
        username=session['username'],
        profile_photo=user['profile_photo'] if user else None,
        history=history
    )


@app.route('/api/sentiment/submit', methods=['POST'])
def api_sentiment_submit():
    """Analyse submitted feedback text with VADER and persist to DB."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401

    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    data = request.get_json(silent=True) or {}
    feedback = (data.get('feedback') or '').strip()
    if not feedback:
        return jsonify({'success': False, 'message': 'Feedback text is required.'}), 400

    # VADER sentiment analysis
    sia = SentimentIntensityAnalyzer()
    scores = sia.polarity_scores(feedback)
    compound   = round(scores['compound'], 4)
    pos        = round(scores['pos'], 4)
    neg        = round(scores['neg'], 4)
    neu        = round(scores['neu'], 4)

    # Simple classification
    if compound >= 0.05:
        sentiment = 'Positive'
    elif compound <= -0.05:
        sentiment = 'Negative'
    else:
        sentiment = 'Neutral'

    # Mental health status
    if compound >= 0.5:
        mental_health_status = 'Excellent'
    elif compound >= 0.05:
        mental_health_status = 'Good'
    elif compound >= -0.05:
        mental_health_status = 'Moderate'
    elif compound >= -0.5:
        mental_health_status = 'At Risk'
    else:
        mental_health_status = 'Critical'

    # Risk level
    if compound >= 0.05:
        risk_level = 'Low'
    elif compound >= -0.3:
        risk_level = 'Moderate'
    else:
        risk_level = 'High'

    # Build recommendations text
    if sentiment == 'Positive':
        rec_text = (
            "Great outlook detected! Keep up the positive mindset. "
            "Consider mentoring peers or joining team wellness initiatives to spread the positivity."
        )
    elif sentiment == 'Neutral':
        rec_text = (
            "A balanced sentiment was detected. Engage in light mindfulness exercises daily. "
            "Share your feelings with a trusted colleague or wellness counsellor."
        )
    else:
        rec_text = (
            "Negative sentiment detected. We strongly recommend speaking with a wellness counsellor or HR. "
            "Practice 10 minutes of mindfulness breathing daily. Take short outdoor breaks to reset."
        )

    analysis_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    ok = database.save_sentiment_analysis(
        user_id=user['id'],
        employee_name=dict(user).get('full_name') or user['username'],
        feedback=feedback,
        positive_score=pos,
        negative_score=neg,
        neutral_score=neu,
        compound_score=compound,
        sentiment=sentiment,
        mental_health_status=mental_health_status,
        risk_level=risk_level,
        recommendations=rec_text,
        analysis_date=analysis_date
    )

    if not ok:
        return jsonify({'success': False, 'message': 'Failed to save analysis.'}), 500

    return jsonify({
        'success': True,
        'sentiment': sentiment,
        'mental_health_status': mental_health_status,
        'risk_level': risk_level,
        'compound': compound,
        'pos': pos,
        'neg': neg,
        'neu': neu,
        'recommendations': rec_text
    })


@app.route('/api/sentiment/history', methods=['GET'])
def api_sentiment_history():
    """Return this employee's sentiment history as JSON."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    history = database.get_sentiment_history(user['id']) or []
    return jsonify({'success': True, 'history': history})


@app.route('/api/admin/sentiment-reports', methods=['GET'])
def api_admin_sentiment_reports():
    """Admin-only: return all employees' sentiment analytics summary."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    user = database.get_user_by_username(session['username'])
    if not user or (user['job_role'] != 'admin' and user['username'] != 'admin'):
        return jsonify({'success': False, 'message': 'Forbidden.'}), 403
    reports = database.get_all_sentiment_reports() or []
    return jsonify({'success': True, 'reports': reports})


# PDF Sentiment Report Generation
class SentimentReportPDF(FPDF):
    """Custom FPDF subclass with branded header/footer for sentiment analysis reports."""

    def __init__(self, employee_name='Employee', employee_id='N/A'):
        super().__init__()
        self.employee_name = employee_name
        self.employee_id_str = employee_id
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        # Top brand bar - Indigo color matching Module 4 theme
        self.set_fill_color(99, 102, 241)  # Indigo
        self.rect(0, 0, 210, 14, 'F')
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 3)
        self.cell(0, 8, 'Employee Wellness Management Analytics', align='L')
        self.set_font('Helvetica', '', 8)
        self.set_xy(-85, 3)
        self.cell(75, 8, 'Confidential Mental Health & Sentiment Report', align='R')
        self.ln(16)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(140, 140, 140)
        self.cell(0, 6, f'Employee: {self.employee_name}  |  ID: {self.employee_id_str}  |  Page {self.page_no()}/{{nb}}', align='C')

    def section_heading(self, title, r=99, g=102, b=241):
        """Draws a coloured section heading bar."""
        self.ln(4)
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 11)
        self.cell(0, 9, f'  {title}', ln=True, fill=True)
        self.set_text_color(40, 40, 40)
        self.ln(3)

    def add_kv_row(self, key, value, shade=False):
        """Adds a key-value row (two-column table row)."""
        if shade:
            self.set_fill_color(245, 247, 250)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(70, 70, 70)
        self.cell(65, 7, f'  {key}', border=0, fill=True)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(40, 40, 40)
        val_str = str(value) if value not in (None, '', 'None') else 'N/A'
        self.cell(0, 7, f'  {val_str}', border=0, ln=True, fill=True)


@app.route('/api/sentiment/download-pdf/<int:report_id>')
def api_sentiment_download_pdf(report_id):
    """Download mental health & sentiment report as PDF."""
    if 'username' not in session:
        return redirect(url_for('index'))

    user = database.get_user_by_username(session['username'])
    if not user:
        return redirect(url_for('index'))

    # Check admin status
    is_admin = (user['job_role'] == 'admin' or user['username'] == 'admin')

    # Fetch the report by ID
    if is_admin:
        report = database.get_sentiment_report_by_id(report_id)
    else:
        report = database.get_sentiment_report_by_id(report_id, user_id=user['id'])

    if not report:
        return "<h3>Error: Report Not Found</h3><p>The requested sentiment report could not be found or you do not have permission to access it.</p>", 404

    # Fetch report owner details
    report_user = database.get_user_by_id(report['user_id'])
    if not report_user:
        return "<h3>Error: User Not Found</h3><p>The employee associated with this report no longer exists.</p>", 404

    try:
        emp_name = report_user.get('full_name') or report_user['username']
        emp_id = report_user.get('employee_id') or str(report_user['id'])

        pdf = SentimentReportPDF(employee_name=emp_name, employee_id=emp_id)
        pdf.alias_nb_pages()
        pdf.add_page()

        # --- Title Block ---
        pdf.set_font('Helvetica', 'B', 18)
        pdf.set_text_color(99, 102, 241) # Indigo
        pdf.cell(0, 12, 'Employee Mental Health & Sentiment Report', ln=True, align='C')
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(120, 120, 120)
        now_str = datetime.now().strftime('%B %d, %Y  |  %I:%M %p')
        pdf.cell(0, 7, f'Generated on: {now_str}', ln=True, align='C')
        pdf.ln(6)
        pdf.set_draw_color(99, 102, 241)
        pdf.set_line_width(0.6)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)

        # ==== Section 1: Employee Details ====
        pdf.section_heading('1.  Employee Details')
        details = [
            ('Employee ID', emp_id),
            ('Full Name', emp_name),
            ('Username', report_user['username']),
            ('Email', report_user['email']),
            ('Department', report_user.get('department')),
            ('Designation', report_user.get('designation')),
            ('Gender', report_user.get('gender')),
        ]
        for i, (k, v) in enumerate(details):
            pdf.add_kv_row(k, v, shade=(i % 2 == 0))

        # ==== Section 2: Journal Log Feedback ====
        pdf.section_heading('2.  Journal Log / Feedback Details')
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(0, 6, '  Submitted Journal Entry:', ln=True)
        pdf.ln(2)
        pdf.set_fill_color(245, 247, 250)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(40, 40, 40)
        feedback_text = report['feedback']
        pdf.multi_cell(0, 5, f'  "{feedback_text}"', border=0, fill=True)
        pdf.ln(4)

        # ==== Section 3: Sentiment Score Analysis ====
        pdf.section_heading('3.  VADER Sentiment & Risk Metrics')
        metrics = [
            ('VADER Sentiment Categorization', report['sentiment']),
            ('Derived Mental Health Status', report['mental_health_status']),
            ('Workforce Burnout Risk Level', f"{report['risk_level']} Risk"),
            ('VADER Compound Polarity Score', f"{report['compound_score']:.4f} (Range: -1.0 to +1.0)"),
            ('Positivity Ratio (Positive Score)', f"{report['positive_score']:.4f}"),
            ('Neutrality Ratio (Neutral Score)', f"{report['neutral_score']:.4f}"),
            ('Negativity Ratio (Negative Score)', f"{report['negative_score']:.4f}"),
            ('Journal Analysis Date', report['analysis_date']),
        ]
        for i, (k, v) in enumerate(metrics):
            pdf.add_kv_row(k, v, shade=(i % 2 == 0))

        # ==== Section 4: Actionable Recommendations ====
        pdf.section_heading('4.  Actionable Recommendations')
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(0, 6, '  Personalized Recommendations:', ln=True)
        pdf.ln(2)
        pdf.set_fill_color(245, 247, 250)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(40, 40, 40)
        rec_desc = report['recommendations']
        pdf.multi_cell(0, 5, f'  {rec_desc}', border=0, fill=True)

        # --- Disclaimer ---
        pdf.ln(10)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
        pdf.set_font('Helvetica', 'I', 7)
        pdf.set_text_color(150, 150, 150)
        pdf.multi_cell(0, 4, 'Disclaimer: This report is generated by the Employee Wellness Management Analytics system based on VADER (Valence Aware Dictionary and sEntiment Reasoner) sentiment analyzer. This is for informational and stress-tracking purposes only and does not constitute professional medical/psychological advice. Please consult a qualified mental health provider for clinical decisions.')

        # Generate and send
        pdf_string = pdf.output(dest='S')
        pdf_bytes = pdf_string.encode('latin-1') if isinstance(pdf_string, str) else pdf_string
        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)
        filename = f'Employee_{emp_id}_Mental_Health_Report_{report_id}.pdf'
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

    except Exception as e:
        return f"<h3>Error Generating PDF</h3><p>An error occurred: {str(e)}</p>", 500


# ─────────────────────────────────────────────────────────────
# END MODULE 4
# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Run server locally on port 5000
    app.run(debug=True, host='0.0.0.0', port=5000)