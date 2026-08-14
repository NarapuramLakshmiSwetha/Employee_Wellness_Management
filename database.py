import sqlite3
import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash

# On Vercel (serverless), use /tmp/ which is the only writable directory.
# Locally, use the project directory.
if os.environ.get('VERCEL'):
    DB_FILE = '/tmp/wellness.db'
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_db = os.path.join(base_dir, 'wellness.db')
    if not os.path.exists(DB_FILE) and os.path.exists(bundled_db):
        import shutil
        try:
            shutil.copyfile(bundled_db, DB_FILE)
        except Exception as e:
            print(f"Failed to copy bundled database to /tmp: {e}")
else:
    DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wellness.db')

def get_db_connection():
    if os.environ.get('VERCEL') and not os.path.exists(DB_FILE):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        bundled_db = os.path.join(base_dir, 'wellness.db')
        if os.path.exists(bundled_db):
            import shutil
            try:
                shutil.copyfile(bundled_db, DB_FILE)
            except Exception as e:
                print(f"Failed to copy bundled database to /tmp: {e}")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            failed_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP DEFAULT NULL,
            job_role TEXT DEFAULT 'Employee',
            profile_photo TEXT DEFAULT NULL,
            full_name TEXT DEFAULT NULL,
            employee_id TEXT DEFAULT NULL,
            mobile_number TEXT DEFAULT NULL,
            gender TEXT DEFAULT NULL,
            dob TEXT DEFAULT NULL,
            department TEXT DEFAULT 'Engineering',
            designation TEXT DEFAULT 'Staff',
            two_factor_enabled INTEGER DEFAULT 0,
            last_active TIMESTAMP DEFAULT NULL,
            login_time TIMESTAMP DEFAULT NULL,
            logout_time TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migrations to add columns dynamically if the database already exists
    for col in [
        ('job_role', "TEXT DEFAULT 'Employee'"),
        ('profile_photo', "TEXT DEFAULT NULL"),
        ('full_name', "TEXT DEFAULT NULL"),
        ('employee_id', "TEXT DEFAULT NULL"),
        ('mobile_number', "TEXT DEFAULT NULL"),
        ('gender', "TEXT DEFAULT NULL"),
        ('dob', "TEXT DEFAULT NULL"),
        ('department', "TEXT DEFAULT 'Engineering'"),
        ('designation', "TEXT DEFAULT 'Staff'"),
        ('two_factor_enabled', "INTEGER DEFAULT 0"),
        ('last_active', "TIMESTAMP DEFAULT NULL"),
        ('login_time', "TIMESTAMP DEFAULT NULL"),
        ('logout_time', "TIMESTAMP DEFAULT NULL")
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    
    # Create login_logs table to track logins
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            status TEXT NOT NULL, -- 'SUCCESS' or 'FAILED'
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            employee_id TEXT,
            full_name TEXT,
            job_role TEXT,
            logout_time TIMESTAMP,
            last_active_time TIMESTAMP,
            session_duration INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Migrate login_logs for existing databases
    for col in [
        ('employee_id', 'TEXT'),
        ('full_name', 'TEXT'),
        ('job_role', 'TEXT'),
        ('logout_time', 'TIMESTAMP'),
        ('last_active_time', 'TIMESTAMP'),
        ('session_duration', 'INTEGER')
    ]:
        try:
            cursor.execute(f"ALTER TABLE login_logs ADD COLUMN {col[0]} {col[1]}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Create health_data table
    # Check if we need to migrate the existing database first
    try:
        cursor.execute("PRAGMA table_info(health_data)")
        cols = cursor.fetchall()
        is_user_id_pk = False
        for c in cols:
            if c['name'] == 'user_id' and c['pk'] == 1:
                is_user_id_pk = True
                break
        if is_user_id_pk:
            # Execute inline migration
            cursor.execute("ALTER TABLE health_data RENAME TO health_data_old")
            cursor.execute('''
                CREATE TABLE health_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    blood_group TEXT,
                    height REAL,
                    weight REAL,
                    bmi REAL,
                    bmi_category TEXT,
                    blood_pressure TEXT,
                    water_intake TEXT,
                    emergency_name TEXT,
                    emergency_relation TEXT,
                    emergency_phone TEXT,
                    last_checkup TEXT,
                    next_checkup TEXT,
                    health_status TEXT,
                    medical_cert_path TEXT,
                    has_allergies TEXT,
                    allergies_detail TEXT,
                    medical_condition TEXT,
                    medical_condition_other TEXT,
                    current_medication TEXT,
                    has_disability TEXT,
                    disability_detail TEXT,
                    smoking_habit TEXT DEFAULT '',
                    alcohol_consumption TEXT DEFAULT '',
                    exercise_frequency TEXT DEFAULT '',
                    exercise_type TEXT DEFAULT '',
                    daily_step_count INTEGER DEFAULT 0,
                    stress_level TEXT DEFAULT '',
                    attendance_percentage REAL DEFAULT 0,
                    work_hours_per_day REAL DEFAULT 0,
                    doctor_remarks TEXT DEFAULT '',
                    sugar_level TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                INSERT INTO health_data (
                    user_id, blood_group, height, weight, bmi, bmi_category,
                    blood_pressure, water_intake, emergency_name, emergency_relation,
                    emergency_phone, last_checkup, next_checkup, health_status,
                    medical_cert_path, has_allergies, allergies_detail,
                    medical_condition, medical_condition_other, current_medication,
                    has_disability, disability_detail, smoking_habit, alcohol_consumption,
                    exercise_frequency, exercise_type, daily_step_count, stress_level,
                    attendance_percentage, work_hours_per_day, doctor_remarks, sugar_level, updated_at
                ) SELECT 
                    user_id, blood_group, height, weight, bmi, bmi_category,
                    blood_pressure, water_intake, emergency_name, emergency_relation,
                    emergency_phone, last_checkup, next_checkup, health_status,
                    medical_cert_path, has_allergies, allergies_detail,
                    medical_condition, medical_condition_other, current_medication,
                    has_disability, disability_detail, smoking_habit, alcohol_consumption,
                    exercise_frequency, exercise_type, daily_step_count, stress_level,
                    attendance_percentage, work_hours_per_day, doctor_remarks, sugar_level, updated_at
                FROM health_data_old
            ''')
            cursor.execute("DROP TABLE health_data_old")
            conn.commit()
    except Exception:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS health_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            blood_group TEXT,
            height REAL,
            weight REAL,
            bmi REAL,
            bmi_category TEXT,
            blood_pressure TEXT,
            water_intake TEXT,
            emergency_name TEXT,
            emergency_relation TEXT,
            emergency_phone TEXT,
            last_checkup TEXT,
            next_checkup TEXT,
            health_status TEXT,
            medical_cert_path TEXT,
            has_allergies TEXT,
            allergies_detail TEXT,
            medical_condition TEXT,
            medical_condition_other TEXT,
            current_medication TEXT,
            has_disability TEXT,
            disability_detail TEXT,
            smoking_habit TEXT DEFAULT '',
            alcohol_consumption TEXT DEFAULT '',
            exercise_frequency TEXT DEFAULT '',
            exercise_type TEXT DEFAULT '',
            daily_step_count INTEGER DEFAULT 0,
            stress_level TEXT DEFAULT '',
            attendance_percentage REAL DEFAULT 0,
            work_hours_per_day REAL DEFAULT 0,
            doctor_remarks TEXT DEFAULT '',
            sugar_level TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Health data column migrations for existing databases
    for col in [
        ('smoking_habit', "TEXT DEFAULT ''"),
        ('alcohol_consumption', "TEXT DEFAULT ''"),
        ('exercise_frequency', "TEXT DEFAULT ''"),
        ('exercise_type', "TEXT DEFAULT ''"),
        ('daily_step_count', "INTEGER DEFAULT 0"),
        ('stress_level', "TEXT DEFAULT ''"),
        ('attendance_percentage', "REAL DEFAULT 0"),
        ('work_hours_per_day', "REAL DEFAULT 0"),
        ('doctor_remarks', "TEXT DEFAULT ''"),
        ('sugar_level', "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE health_data ADD COLUMN {col[0]} {col[1]}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    
    # Create reminders table for AI Chatbot personal reminders
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            reminder_date TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            reminder_datetime TEXT NOT NULL,
            repeat_type TEXT DEFAULT 'Once',
            status TEXT DEFAULT 'Pending',
            snoozed_until TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Migrations for reminders table
    for col in [
        ('snoozed_until', "TEXT DEFAULT NULL"),
        ('updated_at', "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE reminders ADD COLUMN {col[0]} {col[1]}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Create sentiment_analysis table for Mental Health Module
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentiment_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            employee_name TEXT NOT NULL,
            feedback TEXT NOT NULL,
            positive_score REAL NOT NULL,
            negative_score REAL NOT NULL,
            neutral_score REAL NOT NULL,
            compound_score REAL NOT NULL,
            sentiment TEXT NOT NULL,
            mental_health_status TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            recommendations TEXT NOT NULL,
            analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()

    # Check if admin user already exists
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    admin_exists = cursor.fetchone()
    
    if not admin_exists:
        # Pre-seed default admin credentials: admin / Admin@123
        admin_hashed = generate_password_hash('Admin@123')
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, job_role) VALUES (?, ?, ?, 'admin')",
            ('admin', 'admin@wellness.com', admin_hashed)
        )
        conn.commit()
        print("Database initialized and default admin user pre-seeded.")
    else:
        print("Database already initialized.")
        
    conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    """Retrieve user details by user ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"Error fetching user by ID: {e}")
        return None
    finally:
        conn.close()


def check_uniqueness(username=None, email=None, employee_id=None, mobile_number=None, exclude_user_id=None):
    """
    Check if username, email, employee_id, or mobile_number are already taken.
    Returns a dict: { 'username': bool, 'email': bool, 'employee_id': bool, 'mobile_number': bool }
    where True means the value is already in use.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    result = {'username': False, 'email': False, 'employee_id': False, 'mobile_number': False}

    base_cond = 'AND id != ?' if exclude_user_id else ''
    params_extra = (exclude_user_id,) if exclude_user_id else ()

    if username:
        cursor.execute(
            f'SELECT 1 FROM users WHERE LOWER(username) = LOWER(?) {base_cond}',
            (username,) + params_extra
        )
        result['username'] = cursor.fetchone() is not None

    if email:
        cursor.execute(
            f'SELECT 1 FROM users WHERE LOWER(email) = LOWER(?) {base_cond}',
            (email,) + params_extra
        )
        result['email'] = cursor.fetchone() is not None

    if employee_id:
        cursor.execute(
            f'SELECT 1 FROM users WHERE LOWER(employee_id) = LOWER(?) {base_cond}',
            (employee_id,) + params_extra
        )
        result['employee_id'] = cursor.fetchone() is not None

    if mobile_number:
        cursor.execute(
            f'SELECT 1 FROM users WHERE mobile_number = ? {base_cond}',
            (mobile_number,) + params_extra
        )
        result['mobile_number'] = cursor.fetchone() is not None

    conn.close()
    return result

def register_user(username, email, password, job_role='Employee', profile_photo=None,
                  full_name=None, employee_id=None, mobile_number=None, gender=None, dob=None):
    # Pre-check uniqueness with specific messages before attempting insert
    dup = check_uniqueness(username=username, email=email, employee_id=employee_id, mobile_number=mobile_number)
    if dup['username']:
        return False, 'Username is already taken. Please choose a different username.'
    if dup['email']:
        return False, 'Email address is already registered. Please use a different email.'
    if dup['employee_id']:
        return False, 'Employee ID is already in use. Please check your Employee ID.'
    if dup['mobile_number']:
        return False, 'Phone Number is already registered. Please use a different number.'

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed_password = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, job_role, profile_photo,
                               full_name, employee_id, mobile_number, gender, dob)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (username, email, hashed_password, job_role, profile_photo,
              full_name, employee_id, mobile_number, gender, dob))
        conn.commit()
        return True, "Registration successful."
    except sqlite3.IntegrityError:
        return False, "Registration failed due to a duplicate value. Please review your details."
    finally:
        conn.close()

def update_user_profile(user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE users SET
                full_name = ?,
                employee_id = ?,
                email = ?,
                mobile_number = ?,
                department = ?,
                designation = ?,
                profile_photo = COALESCE(?, profile_photo)
            WHERE id = ?
        ''', (
            data.get('full_name'),
            data.get('employee_id'),
            data.get('email'),
            data.get('mobile_number'),
            data.get('department'),
            data.get('designation'),
            data.get('profile_photo'),
            user_id
          ))
        conn.commit()
        return True, "Profile updated successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def update_username_and_photo(user_id, new_username=None, new_photo=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if new_username:
            cursor.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user_id))
            cursor.execute('UPDATE login_logs SET username = ? WHERE user_id = ?', (new_username, user_id))
            cursor.execute('UPDATE sentiment_analysis SET employee_name = ? WHERE user_id = ?', (new_username, user_id))
        if new_photo:
            cursor.execute('UPDATE users SET profile_photo = ? WHERE id = ?', (new_photo, user_id))
        conn.commit()
        return True, "Profile updated successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def update_user_password(user_id, new_password_hash):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, user_id))
        conn.commit()
        return True, "Password updated successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def update_user_2fa(user_id, enabled):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET two_factor_enabled = ? WHERE id = ?', (1 if enabled else 0, user_id))
        conn.commit()
        return True, "2FA status updated."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def get_recent_user_logins(username, limit=5):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT status, login_time FROM login_logs
            WHERE username = ?
            ORDER BY login_time DESC LIMIT ?
        ''', (username, limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()

def log_login(username, status="SUCCESS"):
    """
    Inserts a login attempt record into the login_logs table, with comprehensive employee details.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, employee_id, full_name, job_role FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        user_id = user['id'] if user else None
        emp_id = user['employee_id'] if user else None
        full_name = user['full_name'] if user else None
        job_role = user['job_role'] if user else None
        
        cursor.execute(
            'INSERT INTO login_logs (user_id, username, status, employee_id, full_name, job_role, last_active_time) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)',
            (user_id, username, status, emp_id, full_name, job_role)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Failed to log login: {e}")
    finally:
        conn.close()

def get_login_history(limit=50):
    """
    Retrieves the recent login logs.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT * FROM login_logs ORDER BY login_time DESC LIMIT ?',
            (limit,)
        )
        logs = cursor.fetchall()
        return [dict(log) for log in logs]
    finally:
        conn.close()

def login_user(username, password):
    """
    Handles user login.
    Checks for lockouts, verifies passwords, and logs the attempt.
    """
    is_locked, cooldown, locked_until = check_user_lock(username)
    if is_locked:
        log_login(username, status="FAILED (LOCKED)")
        return False, f"Account is locked. Try again in {cooldown} seconds."
        
    user = get_user_by_username(username)
    if not user:
        log_login(username, status="FAILED (UNKNOWN USER)")
        return False, "Invalid username or password."
        
    if check_password_hash(user['password_hash'], password):
        reset_failed_attempts(username)
        log_login(username, status="SUCCESS")
        return True, "Login successful."
    else:
        locked_until, remaining = increment_failed_attempts(username)
        log_login(username, status="FAILED (WRONG PASSWORD)")
        if locked_until:
            return False, f"Invalid password. Account has been locked until {locked_until}."
        else:
            return False, f"Invalid password. Remaining attempts before lock: {remaining}."

def increment_failed_attempts(username, max_attempts=3, lock_duration_minutes=5):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, failed_attempts FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return None, 0
    
    new_attempts = user['failed_attempts'] + 1
    locked_until = None
    
    if new_attempts >= max_attempts:
        now = datetime.datetime.now()
        locked_until = (now + datetime.timedelta(minutes=lock_duration_minutes)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?',
            (new_attempts, locked_until, username)
        )
    else:
        cursor.execute(
            'UPDATE users SET failed_attempts = ? WHERE username = ?',
            (new_attempts, username)
        )
        
    conn.commit()
    conn.close()
    
    remaining = max(0, max_attempts - new_attempts)
    return locked_until, remaining

def reset_failed_attempts(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?',
        (username,)
    )
    conn.commit()
    conn.close()

def check_user_lock(username):
    user = get_user_by_username(username)
    if not user:
        return False, 0, None
        
    if user['locked_until']:
        locked_until_dt = datetime.datetime.strptime(user['locked_until'], '%Y-%m-%d %H:%M:%S')
        if datetime.datetime.now() < locked_until_dt:
            cooldown_seconds = int((locked_until_dt - datetime.datetime.now()).total_seconds())
            return True, cooldown_seconds, user['locked_until']
        else:
            reset_failed_attempts(username)
            
    return False, 0, None

def reset_password(username, new_password):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if not user:
            return False, "Username does not match our records."
            
        hashed_password = generate_password_hash(new_password)
        cursor.execute(
            'UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE username = ?',
            (hashed_password, username)
        )
        conn.commit()
        return True, "Password has been reset successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def get_all_users():
    """
    Retrieves all registered users.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT * FROM users ORDER BY id ASC'
        )
        users = cursor.fetchall()
        return [dict(user) for user in users]
    finally:
        conn.close()

def clear_login_logs():
    """
    Deletes all records from the login_logs table.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM login_logs')
        conn.commit()
        return True, "All login logs have been cleared successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def get_health_data(user_id):
    """
    Retrieves the latest health data record for a specific user.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM health_data WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"Error fetching health data: {e}")
        return None
    finally:
        conn.close()

def save_health_data(user_id, data):
    """
    Saves a new health data record for a user to preserve history.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO health_data (
                user_id, blood_group, height, weight, bmi, bmi_category,
                blood_pressure, water_intake, emergency_name, emergency_relation,
                emergency_phone, last_checkup, next_checkup, health_status,
                medical_cert_path, has_allergies, allergies_detail,
                medical_condition, medical_condition_other, current_medication,
                has_disability, disability_detail,
                smoking_habit, alcohol_consumption, exercise_frequency,
                exercise_type, daily_step_count, stress_level,
                attendance_percentage, work_hours_per_day, doctor_remarks,
                sugar_level, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            data.get('blood_group'),
            data.get('height'),
            data.get('weight'),
            data.get('bmi'),
            data.get('bmi_category'),
            data.get('blood_pressure'),
            data.get('water_intake'),
            data.get('emergency_name'),
            data.get('emergency_relation'),
            data.get('emergency_phone'),
            data.get('last_checkup'),
            data.get('next_checkup'),
            data.get('health_status'),
            data.get('medical_cert_path'),
            data.get('has_allergies'),
            data.get('allergies_detail'),
            data.get('medical_condition'),
            data.get('medical_condition_other'),
            data.get('current_medication'),
            data.get('has_disability'),
            data.get('disability_detail'),
            data.get('smoking_habit'),
            data.get('alcohol_consumption'),
            data.get('exercise_frequency'),
            data.get('exercise_type'),
            data.get('daily_step_count'),
            data.get('stress_level'),
            data.get('attendance_percentage'),
            data.get('work_hours_per_day'),
            data.get('doctor_remarks'),
            data.get('sugar_level'),
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        return True, "Health data saved successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def get_health_history(user_id):
    """
    Retrieves all health history records for a user sorted by latest first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM health_data WHERE user_id = ? ORDER BY updated_at DESC, id DESC', (user_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching health history: {e}")
        return []
    finally:
        conn.close()

def update_last_active(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        # Also update the login history active session
        cursor.execute('UPDATE login_logs SET last_active_time = CURRENT_TIMESTAMP WHERE user_id = ? AND logout_time IS NULL AND status = "SUCCESS"', (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error updating last active: {e}")
    finally:
        conn.close()

def update_login_time(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET login_time = CURRENT_TIMESTAMP, last_active = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error updating login time: {e}")
    finally:
        conn.close()

def update_logout_time(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET logout_time = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        # Calculate session duration securely
        cursor.execute("""
            UPDATE login_logs 
            SET logout_time = CURRENT_TIMESTAMP,
                session_duration = CAST((julianday(CURRENT_TIMESTAMP) - julianday(login_time)) * 86400 AS INTEGER)
            WHERE user_id = ? AND logout_time IS NULL AND status = 'SUCCESS'
        """, (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error updating logout time: {e}")
    finally:
        conn.close()

def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM health_data WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM login_logs WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM reminders WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM sentiment_analysis WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True, "Employee deleted successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def compute_score_for_row(row):
    score = 0
    # BMI (max 15)
    bmi_cat = row['bmi_category'] or ''
    if bmi_cat == 'Normal':
        score += 15
    elif bmi_cat in ['Overweight', 'Underweight']:
        score += 10
    else:
        score += 4
    # Blood Pressure (max 15)
    bp_str = row['blood_pressure'] or '120/80'
    try:
        sys_bp, dia_bp = map(int, bp_str.split('/'))
    except Exception:
        sys_bp, dia_bp = 120, 80
    if sys_bp <= 120 and dia_bp <= 80:
        score += 15
    elif sys_bp <= 130 and dia_bp <= 85:
        score += 11
    elif sys_bp <= 140 or dia_bp <= 90:
        score += 7
    else:
        score += 3
    # Hydration (max 10)
    water = row['water_intake'] or ''
    if water in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres']:
        score += 10
    elif water in ['2 Litres', 'More than 4 Litres']:
        score += 7
    else:
        score += 3
    # Medical history (max 15)
    med_pts = 15
    cond = row['medical_condition'] or 'None'
    allergy = row['has_allergies'] or ''
    disability = row['has_disability'] or ''
    sugar = row['sugar_level'] or ''
    if cond != 'None':
        med_pts -= 5
    if allergy == 'Yes':
        med_pts -= 2
    if disability == 'Yes':
        med_pts -= 2
    if sugar in ['Pre-diabetic', 'Diabetic', 'Low']:
        med_pts -= 3
    if sugar == 'Diabetic':
        med_pts -= 1
    score += max(0, med_pts)
    # Lifestyle: smoking & alcohol (max 12)
    life_pts = 12
    smoking = row['smoking_habit'] or ''
    alcohol = row['alcohol_consumption'] or ''
    if smoking == 'Regular':
        life_pts -= 5
    elif smoking == 'Occasional':
        life_pts -= 3
    elif smoking == 'Former':
        life_pts -= 1
    if alcohol == 'Heavy':
        life_pts -= 5
    elif alcohol == 'Regular':
        life_pts -= 3
    elif alcohol == 'Occasional':
        life_pts -= 1
    score += max(0, life_pts)
    # Exercise frequency (max 10)
    exer = row['exercise_frequency'] or ''
    if exer == 'Daily':
        score += 10
    elif exer == 'Weekly':
        score += 7
    elif exer == 'Monthly':
        score += 4
    else:
        score += 2
    # Daily step count (max 8)
    steps = row['daily_step_count'] or 0
    if steps >= 10000:
        score += 8
    elif steps >= 8000:
        score += 6
    elif steps >= 5000:
        score += 4
    elif steps >= 3000:
        score += 2
    else:
        score += 1
    # Stress level (max 6)
    stress = row['stress_level'] or ''
    if stress == 'Low':
        score += 6
    elif stress == 'Moderate':
        score += 4
    elif stress == 'High':
        score += 2
    else:
        score += 1
    # Attendance percentage (max 4)
    attendance = row['attendance_percentage'] or 0
    if attendance >= 95:
        score += 4
    elif attendance >= 90:
        score += 3
    elif attendance >= 80:
        score += 2
    else:
        score += 1
    # Work hours per day (max 3)
    work_hours = row['work_hours_per_day'] or 0
    if work_hours <= 8:
        score += 3
    elif work_hours <= 10:
        score += 2
    else:
        score += 1
    # Doctor remarks (max 5)
    doctor = row['doctor_remarks'] or ''
    if doctor:
        score += 5
    # Cap score to 100
    return min(score, 100)

def calculate_health_score(user_id):
    """Compute health score (0-100) for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM health_data WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1', (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return compute_score_for_row(row)
    finally:
        conn.close()

def get_health_score_breakdown(user_id):
    """Return per-factor breakdown of the health score for a specific user, matching compute_score_for_row."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM health_data WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1', (user_id,))
        row = cursor.fetchone()
        if not row:
            return [], None

        factors = []

        # 1. BMI (max 15)
        bmi_cat = row['bmi_category'] or ''
        bmi_pts = 15 if bmi_cat == 'Normal' else (10 if bmi_cat in ['Overweight', 'Underweight'] else 4)
        factors.append({'name': 'BMI', 'icon': 'fa-weight-scale', 'earned': bmi_pts, 'max': 15, 'value': bmi_cat or 'N/A'})

        # 2. Blood Pressure (max 15)
        bp_str = row['blood_pressure'] or '120/80'
        try:
            sys_bp, dia_bp = map(int, bp_str.split('/'))
        except Exception:
            sys_bp, dia_bp = 120, 80
        if sys_bp <= 120 and dia_bp <= 80:
            bp_pts = 15
        elif sys_bp <= 130 and dia_bp <= 85:
            bp_pts = 11
        elif sys_bp <= 140 or dia_bp <= 90:
            bp_pts = 7
        else:
            bp_pts = 3
        factors.append({'name': 'Blood Pressure', 'icon': 'fa-heart-pulse', 'earned': bp_pts, 'max': 15, 'value': bp_str})

        # 3. Water Intake / Hydration (max 10)
        water = row['water_intake'] or ''
        if water in ['3 Litres', '3.5 Litres', '4 Litres', '2.5 Litres']:
            water_pts = 10
        elif water in ['2 Litres', 'More than 4 Litres']:
            water_pts = 7
        else:
            water_pts = 3
        factors.append({'name': 'Water Intake', 'icon': 'fa-glass-water', 'earned': water_pts, 'max': 10, 'value': water or 'N/A'})

        # 4. Medical Condition & Blood Sugar (max 15)
        cond = row['medical_condition'] or 'None'
        allergy = row['has_allergies'] or ''
        disability = row['has_disability'] or ''
        sugar = row['sugar_level'] or ''
        med_pts = 15
        if cond != 'None':
            med_pts -= 5
        if allergy == 'Yes':
            med_pts -= 2
        if disability == 'Yes':
            med_pts -= 2
        if sugar in ['Pre-diabetic', 'Diabetic', 'Low']:
            med_pts -= 3
        if sugar == 'Diabetic':
            med_pts -= 1
        med_pts = max(0, med_pts)
        factors.append({
            'name': 'Medical History & Blood Sugar',
            'icon': 'fa-droplet',
            'earned': med_pts,
            'max': 15,
            'value': f"Sugar: {sugar or 'Normal'}, Medical: {cond}"
        })

        # 5. Lifestyle: Smoking & Alcohol (max 12)
        smoking = row['smoking_habit'] or ''
        alcohol = row['alcohol_consumption'] or ''
        life_pts = 12
        if smoking == 'Regular':
            life_pts -= 5
        elif smoking == 'Occasional':
            life_pts -= 3
        elif smoking == 'Former':
            life_pts -= 1
        if alcohol == 'Heavy':
            life_pts -= 5
        elif alcohol == 'Regular':
            life_pts -= 3
        elif alcohol == 'Occasional':
            life_pts -= 1
        life_pts = max(0, life_pts)
        factors.append({
            'name': 'Smoking & Alcohol Habits',
            'icon': 'fa-smoking',
            'earned': life_pts,
            'max': 12,
            'value': f"Smoking: {smoking or 'Never'}, Alcohol: {alcohol or 'Never'}"
        })

        # 6. Exercise Frequency (max 10)
        exer = row['exercise_frequency'] or ''
        if exer == 'Daily':
            ex_pts = 10
        elif exer == 'Weekly':
            ex_pts = 7
        elif exer == 'Monthly':
            ex_pts = 4
        else:
            ex_pts = 2
        factors.append({'name': 'Exercise Frequency', 'icon': 'fa-dumbbell', 'earned': ex_pts, 'max': 10, 'value': exer or 'N/A'})

        # 7. Daily Step Count (max 8)
        steps = row['daily_step_count'] or 0
        if steps >= 10000:
            step_pts = 8
        elif steps >= 8000:
            step_pts = 6
        elif steps >= 5000:
            step_pts = 4
        elif steps >= 3000:
            step_pts = 2
        else:
            step_pts = 1
        factors.append({'name': 'Daily Step Count', 'icon': 'fa-shoe-prints', 'earned': step_pts, 'max': 8, 'value': f"{steps:,} steps"})

        # 8. Stress Level (max 6)
        stress = row['stress_level'] or ''
        if stress == 'Low':
            stress_pts = 6
        elif stress == 'Moderate':
            stress_pts = 4
        elif stress == 'High':
            stress_pts = 2
        else:
            stress_pts = 1
        factors.append({'name': 'Stress Level', 'icon': 'fa-brain', 'earned': stress_pts, 'max': 6, 'value': stress or 'N/A'})

        # 9. Attendance Percentage (max 4)
        attendance = row['attendance_percentage'] or 0
        if attendance >= 95:
            att_pts = 4
        elif attendance >= 90:
            att_pts = 3
        elif attendance >= 80:
            att_pts = 2
        else:
            att_pts = 1
        factors.append({'name': 'Attendance Percentage', 'icon': 'fa-calendar-check', 'earned': att_pts, 'max': 4, 'value': f"{attendance}%"})

        # 10. Work Hours per Day (max 3)
        work_hours = row['work_hours_per_day'] or 0
        if work_hours <= 8:
            wh_pts = 3
        elif work_hours <= 10:
            wh_pts = 2
        else:
            wh_pts = 1
        factors.append({'name': 'Work Hours per Day', 'icon': 'fa-clock', 'earned': wh_pts, 'max': 3, 'value': f"{work_hours} hrs/day"})

        # 11. Doctor Remarks (max 5)
        doctor = row['doctor_remarks'] or ''
        doc_pts = 5 if doctor else 0
        factors.append({
            'name': 'Doctor Remarks',
            'icon': 'fa-user-md',
            'earned': doc_pts,
            'max': 5,
            'value': doctor or 'No Remarks'
        })

        return factors, row['updated_at']
    finally:
        conn.close()


def get_dashboard_stats():
    """
    Returns aggregated statistics for the employee dashboard summary cards:
    - total_employees: All non-admin users
    - healthy_employees: Employees whose computed wellness score >= 80 (Low Risk)
    - high_risk_employees: Employees whose computed wellness score < 50 (High Risk)
    - pending_assessments: Employees who have NOT submitted health data yet
    - at_risk_mental_health: Employees whose latest mental health status is 'At Risk' or 'Critical'
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- Total employees (exclude admin) ---
    cursor.execute("SELECT COUNT(*) FROM users WHERE job_role != 'admin' AND username != 'admin'")
    total_employees = cursor.fetchone()[0]

    # --- Pending assessments: employees with no health_data record ---
    cursor.execute("""
        SELECT COUNT(*) FROM users u
        LEFT JOIN health_data h ON u.id = h.user_id
        WHERE u.job_role != 'admin' AND u.username != 'admin'
        AND h.user_id IS NULL
    """)
    pending_assessments = cursor.fetchone()[0]

    # --- At-Risk Mental Health: users whose latest journal is 'At Risk' or 'Critical' ---
    try:
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) FROM sentiment_analysis s1
            WHERE s1.id = (SELECT MAX(id) FROM sentiment_analysis s2 WHERE s2.user_id = s1.user_id)
            AND s1.mental_health_status IN ('At Risk', 'Critical')
        """)
        at_risk_mental_health = cursor.fetchone()[0]
    except sqlite3.Error:
        at_risk_mental_health = 0

    # --- Fetch all health data to compute wellness scores ---
    cursor.execute("""
        SELECT h.*
        FROM health_data h
        JOIN users u ON h.user_id = u.id
        WHERE u.job_role != 'admin' AND u.username != 'admin'
    """)
    rows = cursor.fetchall()
    conn.close()

    healthy = 0
    high_risk = 0

    import datetime as dt

    for row in rows:
        score = compute_score_for_row(row)
        if score >= 80:
            healthy += 1
        elif score < 50:
            high_risk += 1

    return {
        'total_employees': total_employees,
        'healthy_employees': healthy,
        'high_risk_employees': high_risk,
        'pending_assessments': pending_assessments,
        'at_risk_mental_health': at_risk_mental_health
    }

# ─────────────────────────────────────────────────────────────
# REMINDER CRUD FUNCTIONS
# ─────────────────────────────────────────────────────────────

def create_reminder(user_id, title, description='', reminder_date='', reminder_time='', repeat_type='Once'):
    """Create a new personal reminder for an employee."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        reminder_datetime = f"{reminder_date} {reminder_time}" if reminder_date and reminder_time else ''
        cursor.execute('''
            INSERT INTO reminders (user_id, title, description, reminder_date, reminder_time, reminder_datetime, repeat_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')
        ''', (user_id, title, description, reminder_date, reminder_time, reminder_datetime, repeat_type))
        conn.commit()
        return True, "Reminder created successfully.", cursor.lastrowid
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}", None
    finally:
        conn.close()

def get_reminders(user_id, status=None, include_done=False):
    """Retrieve reminders for a user, optionally filtered by status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if status:
            cursor.execute(
                'SELECT * FROM reminders WHERE user_id = ? AND status = ? ORDER BY reminder_datetime ASC',
                (user_id, status)
            )
        elif include_done:
            cursor.execute(
                'SELECT * FROM reminders WHERE user_id = ? ORDER BY reminder_datetime DESC',
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT * FROM reminders WHERE user_id = ? AND status != 'Done' ORDER BY reminder_datetime ASC",
                (user_id,)
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching reminders: {e}")
        return []
    finally:
        conn.close()

def update_reminder_status(reminder_id, user_id, new_status):
    """Update a reminder's status (e.g., 'Done', 'Snoozed', 'Pending')."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE reminders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (new_status, reminder_id, user_id)
        )
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Reminder not found."
        return True, f"Reminder marked as {new_status}."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def snooze_reminder(reminder_id, user_id, snooze_minutes=10):
    """Snooze a reminder by pushing its datetime forward by snooze_minutes."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM reminders WHERE id = ? AND user_id = ?', (reminder_id, user_id))
        row = cursor.fetchone()
        if not row:
            return False, "Reminder not found."

        # Calculate new snoozed time
        now = datetime.datetime.now()
        snoozed_until = (now + datetime.timedelta(minutes=snooze_minutes)).strftime('%Y-%m-%d %H:%M')
        new_date = (now + datetime.timedelta(minutes=snooze_minutes)).strftime('%Y-%m-%d')
        new_time = (now + datetime.timedelta(minutes=snooze_minutes)).strftime('%H:%M')
        new_datetime = f"{new_date} {new_time}"

        cursor.execute(
            """UPDATE reminders SET status = 'Snoozed', snoozed_until = ?, 
               reminder_date = ?, reminder_time = ?, reminder_datetime = ?,
               updated_at = CURRENT_TIMESTAMP 
               WHERE id = ? AND user_id = ?""",
            (snoozed_until, new_date, new_time, new_datetime, reminder_id, user_id)
        )
        conn.commit()
        return True, f"Reminder snoozed for {snooze_minutes} minutes until {snoozed_until}."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

def get_due_reminders(user_id):
    """Get reminders that are due (reminder_datetime <= now) and still Pending or Snoozed."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        cursor.execute(
            """SELECT * FROM reminders 
               WHERE user_id = ? AND status IN ('Pending', 'Snoozed') 
               AND reminder_datetime <= ?
               ORDER BY reminder_datetime ASC""",
            (user_id, now_str)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching due reminders: {e}")
        return []
    finally:
        conn.close()

def delete_reminder(reminder_id, user_id):
    """Delete a specific reminder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM reminders WHERE id = ? AND user_id = ?', (reminder_id, user_id))
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Reminder not found."
        return True, "Reminder deleted successfully."
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────
# MENTAL HEALTH & SENTIMENT ANALYTICS
# ─────────────────────────────────────────────────────────────

def save_sentiment_report(user_id, employee_name, feedback, positive_score, negative_score, sentiment, status, risk, recommendations):
    """Save a new sentiment analysis report."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO sentiment_analysis 
            (user_id, employee_name, feedback, positive_score, negative_score, sentiment, mental_health_status, risk_level, recommendations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, employee_name, feedback, positive_score, negative_score, sentiment, status, risk, recommendations))
        conn.commit()
        return True, "Analysis saved successfully.", cursor.lastrowid
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}", None
    finally:
        conn.close()

def get_sentiment_reports(user_id):
    """Retrieve all sentiment reports for a specific user, newest first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM sentiment_analysis WHERE user_id = ? ORDER BY analysis_date DESC', (user_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching sentiment reports: {e}")
        return []
    finally:
        conn.close()

def get_sentiment_report_by_id(report_id, user_id=None):
    """Retrieve a specific sentiment report by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if user_id:
            cursor.execute('SELECT * FROM sentiment_analysis WHERE id = ? AND user_id = ?', (report_id, user_id))
        else:
            # For admin use
            cursor.execute('SELECT * FROM sentiment_analysis WHERE id = ?', (report_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"Error fetching sentiment report: {e}")
        return None
    finally:
        conn.close()

def get_all_sentiment_reports(limit=100):
    """Retrieve the latest sentiment reports across all employees (for Admin Dashboard)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT s.*, u.profile_photo, u.department 
            FROM sentiment_analysis s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.analysis_date DESC LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching all sentiment reports: {e}")
        return []
    finally:
        conn.close()

def save_sentiment_analysis(user_id, employee_name, feedback, positive_score, negative_score, neutral_score, compound_score, sentiment, mental_health_status, risk_level, recommendations, analysis_date):
    """Insert a sentiment analysis record into the sentiment_analysis table.
    Returns True on successful insertion, False on error.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            INSERT INTO sentiment_analysis (
                user_id, employee_name, feedback, positive_score, negative_score, neutral_score, compound_score, sentiment, mental_health_status, risk_level, recommendations, analysis_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                employee_name,
                feedback,
                positive_score,
                negative_score,
                neutral_score,
                compound_score,
                sentiment,
                mental_health_status,
                risk_level,
                recommendations,
                analysis_date,
            )
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error inserting sentiment analysis: {e}")
        return False
    finally:
        conn.close()


def get_sentiment_history(user_id):
    """Return all sentiment analysis records for a given user, newest first."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, employee_name, feedback, positive_score, negative_score,
                   neutral_score, compound_score, sentiment, mental_health_status,
                   risk_level, recommendations, analysis_date
            FROM sentiment_analysis
            WHERE user_id = ?
            ORDER BY analysis_date DESC
            ''',
            (user_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching sentiment history: {e}")
        return []
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()