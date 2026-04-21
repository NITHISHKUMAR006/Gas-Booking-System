"""
GasBook Backend  |  Flask + MySQL
File: app.py  (self-contained — config.py merged in)
"""

from flask import Flask, request, jsonify, session, render_template_string, send_from_directory, redirect
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error, IntegrityError
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
import logging
import os
from dotenv import load_dotenv

# ── Load config.env ───────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, 'config.env'))

# ── Inline Config ────────────────────────────────────────────────────────────
def _bool(val: str, default: bool = False) -> bool:
    return val.lower() in ('1', 'true', 'yes') if val else default

_cors_raw = os.environ.get(
    'CORS_ORIGINS',
    'http://localhost:5002,http://127.0.0.1:5002,http://localhost:3000,'
    'http://127.0.0.1:3000,http://localhost:5500,null'
)

class Config:
    SECRET_KEY     = os.environ.get('SECRET_KEY', 'gasbook-secret-key-2024')
    DEBUG          = _bool(os.environ.get('DEBUG', 'false'))
    FLASK_ENV      = os.environ.get('FLASK_ENV', 'production')
    FLASK_PORT     = int(os.environ.get('FLASK_PORT', 5002))
    JSON_SORT_KEYS = False
    MYSQL_HOST     = os.environ.get('MYSQL_HOST',     'db')
    MYSQL_USER     = os.environ.get('MYSQL_USER',     'gasbook_user')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'gasbook_pass')
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'gasbook')
    MYSQL_PORT     = int(os.environ.get('MYSQL_PORT', 3306))
    CORS_ORIGINS   = [o.strip() for o in _cors_raw.split(',') if o.strip()]

app = Flask(__name__)
app.config.from_object(Config)

# ── Session cookie config (must be BEFORE CORS) ─────────────────────────────
app.config['SESSION_COOKIE_SAMESITE']    = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY']    = True
app.config['SESSION_COOKIE_SECURE']      = False   # True only under HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = 86400   # 24 hours
app.config['TIMEZONE']                   = os.environ.get('TIMEZONE', 'Asia/Kolkata')

CORS(app,
     origins=app.config.get('CORS_ORIGINS', ['null', 'http://localhost:5002']),
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization', 'X-User-Id'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

class ISTFormatter(logging.Formatter):
    """Custom log formatter that stamps every log line with Asia/Kolkata (IST) time."""
    _tz = ZoneInfo(os.getenv('TIMEZONE', 'Asia/Kolkata'))

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        return dt.strftime(datefmt or '%d %b %Y %I:%M:%S %p')

    def format(self, record):
        record.asctime = self.formatTime(record)
        return f"[{record.asctime}] [{record.levelname}] {record.getMessage()}"

class WerkzeugISTFormatter(ISTFormatter):
    """Same IST formatter but strips Werkzeug's embedded UTC bracket timestamp."""
    def format(self, record):
        record.asctime = self.formatTime(record)
        import re
        msg = record.getMessage()
        # Remove Werkzeug's own [dd/Mon/yyyy hh:mm:ss] bracket so only IST time shows
        msg = re.sub(r'\[[\d]{2}/\w+/[\d]{4} [\d:]+\] ', '', msg)
        # Clean up double dashes and trailing dashes in the access log
        msg = re.sub(r'\s+-\s+-\s+', ' - ', msg)
        msg = re.sub(r'\s+-\s*$', '', msg)
        return f"[{record.asctime}] [{record.levelname}] {msg}"

_handler = logging.StreamHandler()
_handler.setFormatter(ISTFormatter())
logging.root.setLevel(logging.INFO)
logging.root.handlers = [_handler]

# Apply IST formatter to werkzeug so HTTP access logs show Indian time only
_wz_logger = logging.getLogger('werkzeug')
_wz_handler = logging.StreamHandler()
_wz_handler.setFormatter(WerkzeugISTFormatter())
_wz_logger.handlers = [_wz_handler]
_wz_logger.propagate = False

logger = logging.getLogger(__name__)

# ── Web Status Page ───────────────────────────────────────────────────────────
STATUS_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/><title>GasBook API</title>
<style>body{font-family:sans-serif;background:#0f1117;color:#eee;padding:2rem;}
.card{background:#1a1d27;padding:2rem;border-radius:12px;max-width:700px;margin:auto;}
h1{color:#ff6b2b;}table{width:100%;border-collapse:collapse;}
td,th{padding:8px;border-bottom:1px solid #333;text-align:left;}
.ok{color:#00d084}.err{color:#ff4d4f}</style></head>
<body><div class="card"><h1>⛽ GasBook API</h1>
<p class="{{ 'ok' if db_ok else 'err' }}">● {{ 'MySQL Connected' if db_ok else 'MySQL Disconnected' }}</p>
<p>Port: {{ port }} | {{ now }}</p></div></body></html>"""

_HTML_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/', methods=['GET'])
@app.route('/login', methods=['GET'])
@app.route('/signup', methods=['GET'])
def index():
    return send_from_directory(_HTML_DIR, 'src/index.html')

@app.route('/dashboard', methods=['GET'])
def dashboard_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/customers', methods=['GET'])
def customers_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/bookings', methods=['GET'])
def bookings_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/deliveries', methods=['GET'])
def deliveries_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/inventory', methods=['GET'])
def inventory_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/warehouses', methods=['GET'])
def warehouses_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/reports', methods=['GET'])
def reports_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/create-account', methods=['GET'])
def create_account_page():
    if not session.get('user_id'):
        return redirect('/?redirect=/create-account')
    if session.get('role') != 'admin':
        return redirect('/dashboard')
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

PAGE_404 = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>404 - Page Not Found | GasBook</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 38 38'%3E%3Crect x='13.5' y='3' width='11' height='3' rx='1.5' fill='%23ff6b2b'/%3E%3Crect x='15.5' y='6' width='7' height='2' rx='1' fill='%23ff9a3c'/%3E%3Cellipse cx='19' cy='8' rx='10' ry='3.5' fill='%23ff6b2b' opacity='0.8'/%3E%3Crect x='9' y='8' width='20' height='22' rx='10' fill='%23ff6b2b' opacity='0.5'/%3E%3Cellipse cx='19' cy='30' rx='10' ry='3.5' fill='%23ff6b2b' opacity='0.6'/%3E%3Cpath d='M14 19 Q16 14 19 19 Q22 24 24 19' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' fill='none'/%3E%3C/svg%3E">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0d0f14;
      --card: #161a24;
      --border: #232840;
      --text: #eef0f8;
      --muted: #6b7499;
      --flame: #ff6b2b;
      --flame2: #ff9a3c;
      --glow: rgba(255, 107, 43, 0.35);
      --shadow: rgba(0, 0, 0, 0.5);
    }
    
    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      overflow-x: hidden;
      overflow-y: auto;
      padding: 40px 20px;
    }
    
    .bg-grid {
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255, 107, 43, 0.045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 107, 43, 0.045) 1px, transparent 1px);
      background-size: 48px 48px;
      animation: gridShift 25s linear infinite;
      z-index: 0;
    }
    
    @keyframes gridShift {
      to { background-position: 48px 48px; }
    }
    
    .orb {
      position: fixed;
      border-radius: 50%;
      pointer-events: none;
      filter: blur(90px);
      animation: orbFloat 9s ease-in-out infinite;
      z-index: 0;
    }
    
    .orb1 {
      width: 450px; height: 450px;
      background: rgba(255, 107, 43, 0.10);
      top: -130px; right: -100px;
    }
    
    .orb2 {
      width: 320px; height: 320px;
      background: rgba(255, 154, 60, 0.08);
      bottom: -100px; left: -90px;
      animation-delay: -4.5s;
    }
    
    @keyframes orbFloat {
      0%, 100% { transform: translate(0, 0); }
      50% { transform: translate(22px, -22px); }
    }

    .card {
      position: relative;
      z-index: 10;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 50px 40px;
      width: 100%;
      max-width: 440px;
      margin: auto;
      text-align: center;
      box-shadow: 0 0 0 1px rgba(255, 107, 43, 0.07), 0 40px 80px var(--shadow);
      animation: cardIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      opacity: 0;
      transform: translateY(30px);
    }
    
    @keyframes cardIn {
      to { opacity: 1; transform: translateY(0); }
    }

    .logo-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 72px;
      height: 72px;
      border-radius: 20px;
      margin-bottom: 24px;
      background: linear-gradient(135deg, var(--flame), var(--flame2));
      box-shadow: 0 0 36px var(--glow);
      animation: float 4s ease-in-out infinite;
    }

    @keyframes float {
      0%, 100% { transform: translateY(0); box-shadow: 0 0 36px var(--glow); }
      50% { transform: translateY(-10px); box-shadow: 0 15px 45px var(--glow); }
    }

    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: clamp(60px, 15vw, 90px);
      font-weight: 800;
      margin: 0 0 5px;
      background: linear-gradient(135deg, #fff 30%, var(--flame2));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1;
      letter-spacing: -2px;
    }
    
    h2 {
      font-family: 'Outfit', sans-serif;
      font-size: 20px;
      font-weight: 600;
      color: var(--flame);
      margin-bottom: 16px;
      text-transform: uppercase;
      letter-spacing: 2px;
    }

    p {
      color: var(--muted);
      font-size: 15px;
      line-height: 1.6;
      margin-bottom: 36px;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      background: linear-gradient(135deg, var(--flame), var(--flame2));
      color: white;
      text-decoration: none;
      padding: 14px 32px;
      border-radius: 14px;
      font-weight: 600;
      font-size: 15px;
      transition: all 0.3s ease;
      box-shadow: 0 10px 24px var(--glow);
    }
    
    .btn svg {
      width: 18px; height: 18px;
      transition: transform 0.3s ease;
    }

    .btn:hover {
      transform: translateY(-3px);
      box-shadow: 0 14px 32px rgba(255, 107, 43, 0.45);
    }
    
    .btn:hover svg {
      transform: translateX(-4px);
    }
    
    .btn:active {
      transform: translateY(0);
    }

  </style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="orb orb1"></div>
  <div class="orb orb2"></div>
  
  <div class="card">
    <div class="logo-icon">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </div>
    
    <h1>404</h1>
    <h2>Page Not Found</h2>
    
    <p>The page you are looking for doesn't exist or has been moved.</p>
    
    <a href="/" class="btn">
      <svg fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
        <path d="M19 12H5M12 19l-7-7 7-7"/>
      </svg>
      Return to Home
    </a>
  </div>
</body>
</html>"""

@app.errorhandler(404)
def page_not_found(e):
    return render_template_string(PAGE_404), 404

@app.route('/settings', methods=['GET'])
def settings_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/status', methods=['GET'])
def status_page():
    conn = get_db()
    db_ok = conn is not None
    if conn: conn.close()
    return render_template_string(STATUS_PAGE, db_ok=db_ok,
        port=app.config.get('FLASK_PORT', 5002),
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

from zoneinfo import ZoneInfo
from datetime import datetime, date

ist = ZoneInfo(app.config.get('TIMEZONE', 'Asia/Kolkata'))

def format_ist_datetime(v):
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=ZoneInfo('UTC')).astimezone(ist)
        else:
            v = v.astimezone(ist)
        # If time is midnight (00:00:00) treat as date-only (e.g. delivery_date)
        if v.hour == 0 and v.minute == 0 and v.second == 0:
            return v.strftime('%d %b %Y')
        return v.strftime('%d %b %Y %I:%M %p')
    elif isinstance(v, date):
        return v.strftime('%d %b %Y')
    return v

def format_name(s):
    return ' '.join(w[0].upper() + w[1:] if w else '' for w in str(s).strip().split(' ')) if s else ""

# ── DB connection ─────────────────────────────────────────────────────────────
def get_db():
    try:
        return mysql.connector.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DATABASE'],
            port=app.config['MYSQL_PORT'],
            autocommit=False,
            connection_timeout=10,
            auth_plugin='caching_sha2_password'
        )
    except Error as e:
        logger.error(f"DB connection failed: {e}")
        return None

def db_error(msg='Database connection failed'):
    return jsonify({'success': False, 'message': msg}), 500


def ensure_member_role():
    conn = get_db()
    if not conn: return
    try:
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE users MODIFY COLUMN role ENUM('admin','staff','member') NOT NULL DEFAULT 'staff'")
            conn.commit()
        except Exception: pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN customer_id VARCHAR(20) DEFAULT NULL")
            conn.commit()
        except Exception: pass
        try:
            cur.execute("UPDATE users u JOIN customers c ON c.email = u.username SET u.customer_id = c.customer_id WHERE u.customer_id IS NULL")
            conn.commit()
        except Exception: pass
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()


# ── Auth helper ───────────────────────────────────────────────────────────────
def _get_current_user_id():
    """Get logged-in user ID from session OR X-User-Id header (fallback)"""
    uid = session.get('user_id')
    if uid:
        return uid
    hdr = request.headers.get('X-User-Id')
    if hdr and hdr.isdigit():
        return int(hdr)
    return None

# ── Health ────────────────────────────────────────────────────────────────────
@app.route('/api/health', methods=['GET'])
def health():
    conn = get_db()
    if conn:
        conn.close()
        return jsonify({'success': True, 'status': 'healthy', 'db': 'connected'})
    return jsonify({'success': False, 'status': 'unhealthy', 'db': 'disconnected'}), 500

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400

    conn = get_db()
    if not conn: return db_error()

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            'SELECT users.user_id, users.username, users.role, customers.email AS c_email, '
            'COALESCE(users.customer_id, customers.customer_id) AS c_id FROM users '
            'LEFT JOIN customers ON customers.customer_id = users.customer_id OR customers.email = %s OR customers.email = users.username '
            'WHERE (users.username=%s OR customers.email=%s) AND users.password=%s AND users.status="active" LIMIT 1',
            (username, username, username, password)
        )
        user = cur.fetchone()
        cur.close(); conn.close()

        if user:
            session.permanent = True
            session['user_id']  = user['user_id']
            session['username'] = user['username']
            session['role']     = user['role']
            session['c_email']  = user['c_email']
            session['c_id']     = user['c_id']
            return jsonify({
                'success':  True,
                'user_id':  user['user_id'],
                'username': user['username'],
                'c_id':     user['c_id'],
                'role':     user['role'],
                'message':  'Login successful'
            })
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
    except Error as e:
        conn.close()
        logger.error(f"Login error: {e}")
        return db_error(str(e))

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out'})

@app.route('/api/check-availability', methods=['POST'])
def check_availability():
    data = request.get_json(force=True, silent=True) or {}
    field = data.get('field')
    value = data.get('value', '').strip()
    exclude_c_id = data.get('exclude_c_id')
    if not field or not value: return jsonify({'available': False})
    
    conn = get_db()
    if not conn: return jsonify({'available': False})
    try:
        cur = conn.cursor()
        exists = False
        
        # Helper to append exclude constraint if provided
        def get_exclude_sql(base_sql):
            return base_sql + ' AND customer_id != %s' if exclude_c_id else base_sql
        def get_params():
            return (value, exclude_c_id) if exclude_c_id else (value,)
            
        if field == 'username':
            cur.execute('SELECT user_id FROM users WHERE username=%s', (value,))
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(get_exclude_sql('SELECT customer_id FROM customers WHERE email=%s'), get_params())
                exists = cur.fetchone() is not None
        elif field == 'email':
            cur.execute(get_exclude_sql('SELECT customer_id FROM customers WHERE email=%s'), get_params())
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute('SELECT user_id FROM users WHERE username=%s', (value,))
                exists = cur.fetchone() is not None
        elif field == 'phone':
            cur.execute(get_exclude_sql('SELECT customer_id FROM customers WHERE phone=%s'), get_params())
            exists = cur.fetchone() is not None
        elif field == 'aadhar':
            cur.execute(get_exclude_sql('SELECT customer_id FROM customers WHERE aadhar_no=%s'), get_params())
            exists = cur.fetchone() is not None
            
        cur.close(); conn.close()
        return jsonify({'available': not exists})
    except:
        return jsonify({'available': False})

@app.route('/api/register', methods=['POST'])
def register():
    data      = request.get_json(force=True, silent=True) or {}
    username  = (data.get('username') or '').strip()
    password  = (data.get('password') or '').strip()
    email     = (data.get('email')    or '').strip()

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
    if not username: username = email

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT user_id FROM users WHERE username=%s', (username,))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'This username is already taken. Please choose another.'}), 409
            
        cur.execute('SELECT customer_id FROM customers WHERE email=%s', (email,))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'This email is already registered. Please log in.'}), 409

        cur.execute('INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
            (username, password, 'member', 'active'))
        user_id = cur.lastrowid

        cur.execute('SELECT COUNT(*) AS c FROM customers')
        count = cur.fetchone()['c'] + 1
        cid = f'CUST{count:04d}'
        cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))
        while cur.fetchone():
            count += 1
            cid = f'CUST{count:04d}'
            cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))

        cur.execute('INSERT INTO customers (customer_id, name, phone, email, status) VALUES (%s, %s, %s, %s, %s)',
            (cid, None, None, email, 'active'))
        cur.execute('UPDATE users SET customer_id=%s WHERE user_id=%s', (cid, user_id))

        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Account created!', 'user_id': user_id}), 201
    except IntegrityError as e:
        conn.rollback(); conn.close()
        return jsonify({'success': False, 'message': f'Account constraint issue: {e}'}), 409
    except Error as e:
        conn.rollback(); conn.close()
        return db_error(str(e))

# ── Admin: Check username availability ────────────────────────────────────────
@app.route('/api/users/check', methods=['GET'])
def check_username():
    if session.get('role') not in ('admin', 'staff'):
        return jsonify({'exists': False}), 403
    username = request.args.get('username', '').strip().lower()
    if not username:
        return jsonify({'exists': False})
    conn = get_db()
    if not conn: return jsonify({'exists': False})
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT user_id FROM users WHERE LOWER(username)=%s LIMIT 1', (username,))
        exists = cur.fetchone() is not None
        cur.close(); conn.close()
        return jsonify({'exists': exists})
    except Error:
        conn.close()
        return jsonify({'exists': False})

# ── Admin: Create Staff/Admin User ────────────────────────────────────────────
@app.route('/api/users/create', methods=['POST'])
def create_user():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    data      = request.get_json(force=True, silent=True) or {}
    username  = (data.get('username') or '').strip()
    password  = (data.get('password') or '').strip()
    role      = (data.get('role') or 'staff').strip()
    full_name = format_name(data.get('full_name') or username)

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
    if role not in ('admin', 'staff'):
        return jsonify({'success': False, 'message': 'Role must be admin or staff'}), 400

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        # Check uniqueness
        cur.execute('SELECT user_id FROM users WHERE LOWER(username)=%s LIMIT 1', (username.lower(),))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Username "{username}" is already taken'}), 409

        cur.execute('INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
                    (username, password, role, 'active'))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': f'{role.capitalize()} account created for {username}'}), 201
    except IntegrityError as e:
        conn.rollback(); conn.close()
        return jsonify({'success': False, 'message': f'Username already exists: {e}'}), 409
    except Error as e:
        conn.rollback(); conn.close()
        return db_error(str(e))


# ── Admin: Create Account (any role, full fields) ─────────────────────────────
@app.route('/api/create-user', methods=['POST'])
def create_user_full():
    actor_role = session.get('role')
    if actor_role not in ('admin', 'staff'):
        return jsonify({'success': False, 'message': 'Admin/Staff access required'}), 403
    data      = request.get_json(force=True, silent=True) or {}
    username  = (data.get('username') or '').strip()
    email     = (data.get('email') or '').strip()
    password  = (data.get('password') or '').strip()
    role      = (data.get('role') or 'staff').strip()
    name      = (data.get('name') or '').strip()
    phone     = (data.get('phone') or '').strip()
    address   = (data.get('address') or '').strip()
    aadhar    = (data.get('aadhar_no') or '').replace('-', '').strip()

    if not username or not email or not password:
        return jsonify({'success': False, 'message': 'Username, email and password are required'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
    if role not in ('admin', 'staff', 'member'):
        return jsonify({'success': False, 'message': 'Role must be admin, staff, or customer'}), 400
    # Staff can only create customer/member accounts.
    if actor_role == 'staff':
        role = 'member'

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT user_id FROM users WHERE LOWER(username)=%s LIMIT 1', (username.lower(),))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Username "{username}" is already taken'}), 409
        cur.execute('SELECT customer_id FROM customers WHERE email=%s LIMIT 1', (email,))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Email "{email}" is already registered'}), 409

        # Optional field validations
        if phone and (not phone.isdigit() or len(phone) != 10):
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'Phone must be exactly 10 digits'}), 400
        if aadhar and (not aadhar.isdigit() or len(aadhar) != 12):
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'Aadhaar must be exactly 12 digits'}), 400

        if phone:
            cur.execute('SELECT customer_id FROM customers WHERE phone=%s LIMIT 1', (phone,))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Phone "{phone}" is already registered'}), 409
        if aadhar:
            cur.execute('SELECT customer_id FROM customers WHERE aadhar_no=%s LIMIT 1', (aadhar,))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Aadhaar number already registered'}), 409

        cur.execute('INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
                    (username, password, role, 'active'))
        user_id = cur.lastrowid

        # Create customer profile for all roles
        cur.execute('SELECT COUNT(*) AS c FROM customers')
        count = cur.fetchone()['c'] + 1
        cid = f'CUST{count:04d}'
        cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))
        while cur.fetchone():
            count += 1
            cid = f'CUST{count:04d}'
            cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))

        cur.execute(
            'INSERT INTO customers (customer_id, name, phone, email, address, aadhar_no, status) VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (cid, format_name(name) if name else None, phone or None, email, address or None, aadhar or None, 'active')
        )
        cur.execute('UPDATE users SET customer_id=%s WHERE user_id=%s', (cid, user_id))

        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': f'{role.capitalize()} account created for {username}', 'user_id': user_id, 'customer_id': cid}), 201
    except IntegrityError as e:
        conn.rollback(); conn.close()
        return jsonify({'success': False, 'message': f'Duplicate entry: {e}'}), 409
    except Error as e:
        conn.rollback(); conn.close()
        return db_error(str(e))


# ── PROFILE (Current logged-in user) ──────────────────────────────────────────
@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Returns the currently logged-in user's profile data"""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('''
            SELECT u.user_id, u.username, u.role, u.customer_id,
                   c.customer_id AS c_id, c.name, c.phone, c.email,
                   c.address, c.aadhar_no, c.member_since,
                   c.total_bookings, c.total_spent, c.status
            FROM users u
            LEFT JOIN customers c ON c.customer_id = u.customer_id
            WHERE u.user_id = %s LIMIT 1
        ''', (user_id,))
        row = cur.fetchone()

        if not row:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Fallback: if no customer linked, try matching by username/email
        if not row.get('c_id'):
            cur.execute('''
                SELECT customer_id AS c_id, customer_id, name, phone, email,
                       address, aadhar_no, member_since, total_bookings,
                       total_spent, status
                FROM customers
                WHERE email = %s LIMIT 1
            ''', (row['username'],))
            cust = cur.fetchone()
            if cust:
                cur.execute('UPDATE users SET customer_id=%s WHERE user_id=%s',
                            (cust['customer_id'], user_id))
                conn.commit()
                row.update(cust)

        cur.close(); conn.close()

        # Hide dummy placeholder phones
        if row.get('phone') and str(row['phone']).startswith('00'):
            row['phone'] = ''

        # Serialize datetime fields
        for k, v in list(row.items()):
            if isinstance(v, datetime):
                row[k] = v.strftime('%Y-%m-%d %H:%M:%S')

        return jsonify({'success': True, 'data': row})
    except Error as e:
        conn.close()
        logger.error(f"Profile fetch: {e}")
        return db_error(str(e))


@app.route('/api/profile', methods=['PUT'])
def update_profile():
    """Updates currently logged-in user's profile"""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json(force=True, silent=True) or {}
    name    = format_name(data.get('name')      or '')
    phone   = (data.get('phone')     or '').strip()
    email   = (data.get('email')     or '').strip()
    address = (data.get('address')   or '').strip()
    aadhar  = (data.get('aadhar_no') or '').strip()

    # ── Validation ──
    if not name:
        return jsonify({'success': False, 'message': 'Name is required'}), 400
    if not phone or not phone.isdigit() or len(phone) != 10:
        return jsonify({'success': False, 'message': 'Phone must be exactly 10 digits'}), 400
    if email and '@' not in email:
        return jsonify({'success': False, 'message': 'Invalid email format'}), 400
    if aadhar and (not aadhar.isdigit() or len(aadhar) != 12):
        return jsonify({'success': False, 'message': 'Aadhaar must be exactly 12 digits'}), 400

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)

        cur.execute('SELECT username, customer_id FROM users WHERE user_id=%s', (user_id,))
        user_row = cur.fetchone()
        if not user_row:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404

        cust_id = user_row.get('customer_id')

        # If no customer row exists, auto-create one
        if not cust_id:
            cur.execute('SELECT COUNT(*) AS c FROM customers')
            count = cur.fetchone()['c'] + 1
            cust_id = f'CUST{count:04d}'
            cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cust_id,))
            while cur.fetchone():
                count += 1
                cust_id = f'CUST{count:04d}'
                cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cust_id,))

            cur.execute(
                'INSERT INTO customers (customer_id, name, phone, email, address, aadhar_no, status) '
                'VALUES (%s,%s,%s,%s,%s,%s,"active")',
                (cust_id, name, phone, email, address, aadhar)
            )
            cur.execute('UPDATE users SET customer_id=%s WHERE user_id=%s', (cust_id, user_id))
            session['c_id'] = cust_id
        else:
            # Check phone uniqueness
            cur.execute('SELECT customer_id FROM customers WHERE phone=%s AND customer_id != %s', (phone, cust_id))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Phone number already in use'}), 409
                
            # Check email uniqueness
            cur.execute('SELECT customer_id FROM customers WHERE email=%s AND customer_id != %s', (email, cust_id))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Email address already in use'}), 409
                
            # Check aadhar uniqueness
            cur.execute('SELECT customer_id FROM customers WHERE aadhar_no=%s AND customer_id != %s', (aadhar, cust_id))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Aadhaar number already in use'}), 409

            cur.execute(
                'UPDATE customers SET name=%s, phone=%s, email=%s, address=%s, aadhar_no=%s '
                'WHERE customer_id=%s',
                (name, phone, email, address, aadhar, cust_id)
            )

        conn.commit(); cur.close(); conn.close()
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'customer_id': cust_id
        })
    except IntegrityError as e:
        conn.rollback(); conn.close()
        return jsonify({'success': False, 'message': f'Duplicate entry: {str(e)}'}), 409
    except Error as e:
        conn.rollback(); conn.close()
        logger.error(f"Profile update: {e}")
        return db_error(str(e))


# ── CUSTOMERS ─────────────────────────────────────────────────────────────────
@app.route('/api/customers', methods=['GET'])
def get_customers():
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        page  = request.args.get('page',  1,  type=int)
        limit = request.args.get('limit', 10, type=int)
        q     = request.args.get('q',     '', type=str).strip()
        offset = (page - 1) * limit

        role = session.get('role', 'member')
        c_id = session.get('c_id')
        c_em = session.get('c_email')

        join_clause = " LEFT JOIN users u ON c.customer_id = u.customer_id"
        params = []

        # Always exclude admin/staff accounts — only show customer-role users
        member_filter = "(u.role = 'member' OR u.role IS NULL)"

        if role == 'member':
            where_clause_c = f"WHERE (c.customer_id = %s OR c.email = %s) AND {member_filter} "
            params.extend([c_id, c_em])
        elif q:
            like = f'%{q}%'
            where_clause_c = f"WHERE (c.name LIKE %s OR c.phone LIKE %s OR c.customer_id LIKE %s) AND {member_filter} "
            params.extend([like, like, like])
        else:
            where_clause_c = f"WHERE {member_filter} "

        # Count total matching rows (with the join for role filter)
        cur.execute(
            f"SELECT COUNT(*) as c FROM customers c{join_clause} {where_clause_c}",
            tuple(params)
        )
        total = cur.fetchone()['c']

        cur.execute(
            f"SELECT c.*, u.username, u.role FROM customers c{join_clause} {where_clause_c} ORDER BY c.member_since DESC LIMIT %s OFFSET %s",
            tuple(params + [limit, offset])
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows, 'total': total, 'page': page, 'limit': limit})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/customers', methods=['POST'])
def create_customer():
    data = request.get_json(force=True, silent=True) or {}
    name    = format_name(data.get('name')      or '')
    phone   = (data.get('phone')     or '').strip()
    email   = (data.get('email')     or '').strip().lower()
    address = (data.get('address')   or '').strip()
    aadhar  = (data.get('aadhar_no') or '').strip().replace(' ', '').replace('-', '')

    if not name or not phone:
        return jsonify({'success': False, 'message': 'Name and phone are required'}), 400
    if not phone.isdigit() or len(phone) != 10:
        return jsonify({'success': False, 'message': 'Phone must be exactly 10 digits'}), 400
    if aadhar and (not aadhar.isdigit() or len(aadhar) != 12):
        return jsonify({'success': False, 'message': 'Aadhaar must be exactly 12 digits'}), 400

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)

        # ── Duplicate checks ──────────────────────────────────────────
        cur.execute('SELECT customer_id, name FROM customers WHERE phone=%s LIMIT 1', (phone,))
        dup = cur.fetchone()
        if dup:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Phone {phone} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if email:
            cur.execute('SELECT customer_id, name FROM customers WHERE email=%s LIMIT 1', (email,))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Email {email} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if aadhar:
            cur.execute('SELECT customer_id, name FROM customers WHERE aadhar_no=%s LIMIT 1', (aadhar,))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Aadhaar number is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        # ── Generate unique ID ────────────────────────────────────────
        cur.execute('SELECT COUNT(*) as c FROM customers')
        count = cur.fetchone()['c'] + 1
        cid = f'CUST{count:04d}'
        cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))
        while cur.fetchone():
            count += 1
            cid = f'CUST{count:04d}'
            cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))

        cur.execute('INSERT INTO customers (customer_id,name,phone,email,address,aadhar_no) VALUES (%s,%s,%s,%s,%s,%s)',
            (cid, name, phone, email, address, aadhar or None))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Customer registered', 'customer_id': cid}), 201
    except IntegrityError as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Duplicate value conflict: {str(e)}'}), 409
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/customers/<customer_id>', methods=['GET'])
def get_customer(customer_id):
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('''
            SELECT c.*, u.username, u.role 
            FROM customers c 
            LEFT JOIN users u ON c.customer_id = u.customer_id 
            WHERE c.customer_id=%s
        ''', (customer_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row: return jsonify({'success': False, 'message': 'Not found'}), 404
        return jsonify({'success': True, 'data': row})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/customers/<customer_id>', methods=['PUT'])
def update_customer(customer_id):
    if session.get('role') == 'member' and session.get('c_id') != customer_id:
        return jsonify({'success': False, 'message': 'Forbidden'}), 403
    data = request.get_json(force=True, silent=True) or {}
    phone   = (data.get('phone')     or '').strip()
    email   = (data.get('email')     or '').strip().lower()
    aadhar  = (data.get('aadhar_no') or '').strip().replace(' ', '').replace('-', '')

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)

        # ── Duplicate checks (exclude self) ───────────────────────────
        if phone:
            cur.execute('SELECT customer_id, name FROM customers WHERE phone=%s AND customer_id!=%s LIMIT 1', (phone, customer_id))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Phone {phone} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if email:
            cur.execute('SELECT customer_id, name FROM customers WHERE email=%s AND customer_id!=%s LIMIT 1', (email, customer_id))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Email {email} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if aadhar:
            cur.execute('SELECT customer_id, name FROM customers WHERE aadhar_no=%s AND customer_id!=%s LIMIT 1', (aadhar, customer_id))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Aadhaar number is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        cur.execute('UPDATE customers SET name=%s, phone=%s, email=%s, address=%s, aadhar_no=%s WHERE customer_id=%s',
            (format_name(data.get('name')) if data.get('name') else None, phone or None, email or None, data.get('address'), aadhar or None, customer_id))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Customer updated'})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/customers/<customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    if session.get('role') not in ('admin', 'staff'):
        return jsonify({'success': False, 'message': 'Admin/Staff access required'}), 403
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor()
        # 1) Delete all bookings belonging to this customer first (FK constraint)
        cur.execute('DELETE FROM bookings WHERE customer_id=%s', (customer_id,))
        # 2) Unlink any user account pointing to this customer
        cur.execute('UPDATE users SET customer_id=NULL WHERE customer_id=%s', (customer_id,))
        # 3) Now safe to delete the customer row
        cur.execute('DELETE FROM customers WHERE customer_id=%s', (customer_id,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Customer and related bookings deleted'})
    except Error as e:
        conn.rollback(); conn.close(); return db_error(str(e))

# ── CYLINDER TYPES ────────────────────────────────────────────────────────────
@app.route('/api/cylinder-types', methods=['GET'])
def get_cylinder_types():
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM cylindertypes WHERE is_active=1 ORDER BY type_id')
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── BOOKINGS ──────────────────────────────────────────────────────────────────
@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        page   = request.args.get('page',  1,  type=int)
        limit  = request.args.get('limit', 10, type=int)
        status = request.args.get('status','', type=str).strip()
        offset = (page - 1) * limit

        role = session.get('role', 'member')
        c_id = session.get('c_id')

        base_sql = '''
            SELECT b.*, c.name AS customer_name, c.phone AS customer_phone,
                   c.address AS customer_address,
                   ct.type_name, ct.price AS unit_price, ct.weight,
                   db.name AS delivery_boy_name
            FROM bookings b
            JOIN customers c ON b.customer_id = c.customer_id
            JOIN cylindertypes ct ON b.type_id = ct.type_id
            LEFT JOIN deliveryboys db ON b.delivery_boy_id = db.boy_id
        '''
        conds = []; params = []
        if status: conds.append("b.status=%s"); params.append(status)
        if role == 'member': conds.append("b.customer_id=%s"); params.append(c_id)
        where_clause = " WHERE " + " AND ".join(conds) if conds else ""

        cur.execute(base_sql + where_clause + ' ORDER BY b.booking_date DESC LIMIT %s OFFSET %s',
            tuple(params + [limit, offset]))
        rows = cur.fetchall()
        for r in rows:
            for k, v in r.items():
                if isinstance(v, (datetime, date)):
                    r[k] = format_ist_datetime(v)

        cur.execute('SELECT COUNT(*) as c FROM bookings b' + where_clause, tuple(params))
        total = cur.fetchone()['c']
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows, 'total': total, 'page': page, 'limit': limit})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    data = request.get_json(force=True, silent=True) or {}
    role = session.get('role', 'member')

    if role == 'member':
        c_id = session.get('c_id')
        if not c_id:
            conn = get_db()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    cur.execute(
                        "SELECT customer_id FROM customers WHERE email = %s LIMIT 1",
                        (session.get('c_email') or session.get('username'),)
                    )
                    row = cur.fetchone()
                    if row:
                        c_id = row['customer_id']
                        session['c_id'] = c_id
                    cur.close()
                except Exception as e:
                    logger.error(f"c_id recovery: {e}")
                finally:
                    conn.close()
        if c_id:
            data['customer_id'] = c_id
        else:
            return jsonify({'success': False, 'message': 'Your customer profile is not linked. Contact admin.'}), 400

    if not data.get('customer_id') or not data.get('type_id'):
        return jsonify({'success': False, 'message': 'Customer and cylinder type are required'}), 400

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)

        cur.execute('SELECT * FROM customers WHERE customer_id=%s', (data['customer_id'],))
        cust = cur.fetchone()
        if not cust:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Customer {data["customer_id"]} not found'}), 400
            
        missing = []
        if not cust.get('name') or not str(cust.get('name')).strip(): missing.append('Name')
        if not cust.get('phone') or not str(cust.get('phone')).strip(): missing.append('Phone')
        if not cust.get('email') or not str(cust.get('email')).strip(): missing.append('Email')
        if not cust.get('address') or not str(cust.get('address')).strip(): missing.append('Address')
        if not cust.get('aadhar_no') or not str(cust.get('aadhar_no')).strip(): missing.append('Aadhaar')

        if missing:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Customer profile is incomplete. Please fill: {", ".join(missing)} before booking.'}), 400

        cur.execute('SELECT price FROM cylindertypes WHERE type_id=%s AND is_active=1', (data['type_id'],))
        ct = cur.fetchone()
        if not ct:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'Invalid cylinder type'}), 400

        qty    = int(data.get('quantity', 1))
        amount = float(ct['price']) * qty

        cur.execute('SELECT COUNT(*) as c FROM bookings')
        count = cur.fetchone()['c'] + 1
        bid = f"BK{datetime.now().strftime('%Y%m')}{count:04d}"
        cur.execute('SELECT booking_id FROM bookings WHERE booking_id=%s', (bid,))
        while cur.fetchone():
            count += 1
            bid = f"BK{datetime.now().strftime('%Y%m')}{count:04d}"
            cur.execute('SELECT booking_id FROM bookings WHERE booking_id=%s', (bid,))

        dboy = data.get('delivery_boy_id') or None
        if not dboy:
            cur.execute('''SELECT db.boy_id FROM deliveryboys db 
                           LEFT JOIN bookings b ON db.boy_id = b.delivery_boy_id AND b.status IN ('pending', 'confirmed', 'out_for_delivery')
                           WHERE db.status="active" GROUP BY db.boy_id 
                           ORDER BY COUNT(b.booking_id) ASC, RAND() LIMIT 1''')
            row = cur.fetchone()
            if row: dboy = row['boy_id']

        cur.execute('''INSERT INTO bookings (booking_id,customer_id,type_id,quantity,booking_date,delivery_date,amount,delivery_boy_id,status)
            VALUES (%s,%s,%s,%s,UTC_TIMESTAMP(),%s,%s,%s,'pending')''',
            (bid, data['customer_id'], data['type_id'], qty,
             data.get('delivery_date') or None, amount, dboy))

        cur.execute('UPDATE customers SET total_bookings=total_bookings+1, total_spent=total_spent+%s WHERE customer_id=%s',
            (amount, data['customer_id']))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Booking created', 'booking_id': bid, 'amount': amount}), 201
    except Error as e:
        conn.rollback(); conn.close()
        logger.error(f"Booking error: {e}")
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    except Exception as e:
        conn.close()
        logger.error(f"Booking unexpected: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/bookings/<booking_id>/status', methods=['PUT'])
def update_booking_status(booking_id):
    data = request.get_json(force=True, silent=True) or {}
    status = data.get('status')
    valid = ('pending','confirmed','out_for_delivery','delivered','cancelled')
    role = session.get('role', 'member')
    if role == 'member' and status != 'cancelled':
        return jsonify({'success': False, 'message': 'Members can only cancel bookings.'}), 403
    if status not in valid:
        return jsonify({'success': False, 'message': f'status must be one of {valid}'}), 400
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor()
        if status == 'delivered':
            cur.execute('UPDATE bookings SET status=%s, delivery_date=CURDATE() WHERE booking_id=%s', (status, booking_id))
        else:
            cur.execute('UPDATE bookings SET status=%s WHERE booking_id=%s', (status, booking_id))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Status updated'})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def delete_booking(booking_id):
    if session.get('role') == 'member':
        return jsonify({'success': False, 'message': 'Members cannot delete bookings'}), 403
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM bookings WHERE booking_id=%s', (booking_id,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Booking deleted'})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── INVENTORY ─────────────────────────────────────────────────────────────────
@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('''SELECT i.*, ct.type_name, ct.weight, ct.price,
                   w.name AS warehouse_name, w.location
            FROM inventory i
            JOIN cylindertypes ct ON i.type_id = ct.type_id
            JOIN warehouses w ON i.warehouse_id = w.warehouse_id
            ORDER BY w.name, ct.type_name''')
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/inventory/restock', methods=['POST'])
def restock():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get('type_id') or not data.get('warehouse_id') or not data.get('quantity'):
        return jsonify({'success': False, 'message': 'type_id, warehouse_id and quantity required'}), 400
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor()
        cur.execute('''UPDATE inventory SET quantity_on_hand = quantity_on_hand + %s,
            last_restocked = UTC_TIMESTAMP() WHERE type_id=%s AND warehouse_id=%s''',
            (int(data['quantity']), data['type_id'], data['warehouse_id']))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Inventory restocked'})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── WAREHOUSES ────────────────────────────────────────────────────────────────
@app.route('/api/warehouses', methods=['GET'])
def get_warehouses():
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM warehouses ORDER BY name')
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── DELIVERY BOYS ─────────────────────────────────────────────────────────────
@app.route('/api/deliveryboys', methods=['GET'])
def get_delivery_boys():
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM deliveryboys WHERE status='active' ORDER BY name")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@app.route('/api/analytics/dashboard', methods=['GET'])
def dashboard_metrics():
    role = session.get('role', 'member')
    c_id = session.get('c_id')
    
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        if role == 'member' and c_id:
            cur.execute('SELECT COUNT(*) as c FROM bookings WHERE customer_id=%s', (c_id,))
            total_bookings = cur.fetchone()['c']
            total_customers = 1  # Members only see their own account
            cur.execute('SELECT COALESCE(SUM(amount),0) as s FROM bookings WHERE status="delivered" AND customer_id=%s', (c_id,))
            total_revenue = float(cur.fetchone()['s'])
            cur.execute('SELECT COUNT(*) as c FROM bookings WHERE status="pending" AND customer_id=%s', (c_id,))
            pending = cur.fetchone()['c']
            cur.execute('SELECT COUNT(*) as c FROM bookings WHERE (status="confirmed" OR status="out_for_delivery") AND customer_id=%s', (c_id,))
            confirmed = cur.fetchone()['c']
            cur.execute('''SELECT b.*, c.name AS customer_name, c.phone AS customer_phone,
                   c.address AS customer_address,
                   ct.type_name, ct.price AS unit_price, ct.weight,
                   db.name AS delivery_boy_name
                FROM bookings b
                JOIN customers c ON b.customer_id=c.customer_id
                JOIN cylindertypes ct ON b.type_id=ct.type_id
                LEFT JOIN deliveryboys db ON b.delivery_boy_id = db.boy_id
                WHERE b.customer_id=%s
                ORDER BY b.booking_date DESC LIMIT 5''', (c_id,))
            recent = cur.fetchall()
            cur.execute('''SELECT DATE_FORMAT(booking_date,'%Y-%m') as month,
                       COUNT(*) as bookings, COALESCE(SUM(amount),0) as revenue
                FROM bookings
                WHERE booking_date >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 6 MONTH) AND customer_id=%s
                GROUP BY DATE_FORMAT(booking_date,'%Y-%m')
                ORDER BY month ASC''', (c_id,))
            monthly = cur.fetchall()
        else:
            cur.execute('SELECT COUNT(*) as c FROM bookings')
            total_bookings = cur.fetchone()['c']
            cur.execute('SELECT COUNT(*) as c FROM customers WHERE status="active"')
            total_customers = cur.fetchone()['c']
            cur.execute('SELECT COALESCE(SUM(amount),0) as s FROM bookings WHERE status="delivered"')
            total_revenue = float(cur.fetchone()['s'])
            cur.execute('SELECT COUNT(*) as c FROM bookings WHERE status="pending"')
            pending = cur.fetchone()['c']
            cur.execute('SELECT COUNT(*) as c FROM bookings WHERE status="confirmed" OR status="out_for_delivery"')
            confirmed = cur.fetchone()['c']
            cur.execute('''SELECT b.*, c.name AS customer_name, c.phone AS customer_phone,
                   c.address AS customer_address,
                   ct.type_name, ct.price AS unit_price, ct.weight,
                   db.name AS delivery_boy_name
                FROM bookings b
                JOIN customers c ON b.customer_id=c.customer_id
                JOIN cylindertypes ct ON b.type_id=ct.type_id
                LEFT JOIN deliveryboys db ON b.delivery_boy_id = db.boy_id
                ORDER BY b.booking_date DESC LIMIT 5''')
            recent = cur.fetchall()
            cur.execute('''SELECT DATE_FORMAT(booking_date,'%Y-%m') as month,
                       COUNT(*) as bookings, COALESCE(SUM(amount),0) as revenue
                FROM bookings
                WHERE booking_date >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 6 MONTH)
                GROUP BY DATE_FORMAT(booking_date,'%Y-%m')
                ORDER BY month ASC''')
            monthly = cur.fetchall()

        for r in recent:
            for k, v in r.items():
                if isinstance(v, (datetime, date)):
                    r[k] = format_ist_datetime(v)
                
        cur.close(); conn.close()
        return jsonify({
            'success': True, 'total_bookings': total_bookings,
            'total_customers': total_customers,
            'total_revenue': round(total_revenue, 2),
            'pending': pending, 'confirmed': confirmed,
            'recent_bookings': recent, 'monthly': monthly,
        })
    except Error as e:
        conn.close(); return db_error(str(e))


def initialize_database():
    conn = get_db()
    if not conn:
        logger.error("Could not connect to DB for init.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SHOW TABLES LIKE 'users'")
        if not cur.fetchone():
            logger.info("Running init.sql...")
            init_file = os.path.join(_BASE_DIR, 'src', 'init.sql')
            if os.path.exists(init_file):
                with open(init_file, 'r', encoding='utf-8') as f:
                    sql_script = f.read()
                statements = [s.strip() + ';' for s in sql_script.split(';') if s.strip()]
                for statement in statements:
                    try:
                        cur.execute(statement)
                    except Error as e:
                        if 'already exists' not in str(e).lower() and 'duplicate entry' not in str(e).lower():
                            logger.error(f"Init query failed: {e}")
                conn.commit()
                logger.info("DB initialized.")
        
        # Patch schema for new users to allow NULL name and phone
        try:
            cur.execute("ALTER TABLE customers MODIFY name VARCHAR(100) NULL, MODIFY phone VARCHAR(15) NULL")
            conn.commit()
        except Error:
            pass # ignore if already altered
            
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"Init error: {e}")

if __name__ == '__main__':
    port = app.config.get('FLASK_PORT', 5002)
    logger.info("=" * 55)
    logger.info(f"  GasBook Backend  |  http://localhost:{port}")
    logger.info(f"  DB: {app.config['MYSQL_HOST']}:{app.config['MYSQL_PORT']}/{app.config['MYSQL_DATABASE']}")
    logger.info("=" * 55)
    initialize_database()
    ensure_member_role()
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=port)