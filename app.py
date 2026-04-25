"""
Gas Booking System - Backend  |  Flask + MySQL
"""

from flask import Flask, request, jsonify, session, render_template_string, send_from_directory, redirect, Response
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error, IntegrityError
from datetime import datetime, date, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import logging
import os
import re
import requests
import time
import threading
from urllib.parse import quote
from dotenv import load_dotenv

# ── Load config.env ───────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, 'config.env'))

# ── Inline Config ────────────────────────────────────────────────────────────
def _bool(val: str, default: bool = False) -> bool:
    return val.lower() in ('1', 'true', 'yes') if val else default

_cors_raw = os.environ.get(
    'CORS_ORIGINS',
    'http://localhost:5002, http://127.0.0.1:5002, http://localhost:3000,'
    'http://127.0.0.1:3000, http://localhost:5500, null'
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

@app.after_request
def add_no_cache_headers(response):
    """Disable all caching for realtime data."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

logger = logging.getLogger(__name__)
ADMINER_UPSTREAM = os.environ.get('ADMINER_UPSTREAM', 'http://phpmyadmin:80')

# Reuse upstream TCP connections and cache static assets for faster /mysql loads.
_UPSTREAM_HTTP = requests.Session()
_UPSTREAM_HTTP.mount('http://', requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50))
_UPSTREAM_HTTP.mount('https://', requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50))
_MYSQL_STATIC_CACHE = {}
_MYSQL_CACHE_LOCK = threading.Lock()
_MYSQL_CACHE_TTL_SECONDS = 120
_MYSQL_CACHE_MAX_ITEMS = 300


def _is_mysql_static_asset(subpath: str) -> bool:
    if not subpath:
        return False
    p = subpath.lower()
    if p.startswith(('themes/', 'js/', 'css/', 'vendor/')):
        return True
    return p.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.map'))


def _mysql_cache_get(key: str):
    now = time.time()
    with _MYSQL_CACHE_LOCK:
        item = _MYSQL_STATIC_CACHE.get(key)
        if not item:
            return None
        if now - item['ts'] > _MYSQL_CACHE_TTL_SECONDS:
            _MYSQL_STATIC_CACHE.pop(key, None)
            return None
        return item


def _mysql_cache_set(key: str, status_code: int, headers, body: bytes):
    if len(body) > 1024 * 1024 * 2:
        return
    with _MYSQL_CACHE_LOCK:
        if len(_MYSQL_STATIC_CACHE) >= _MYSQL_CACHE_MAX_ITEMS:
            oldest_key = min(_MYSQL_STATIC_CACHE.items(), key=lambda kv: kv[1]['ts'])[0]
            _MYSQL_STATIC_CACHE.pop(oldest_key, None)
        _MYSQL_STATIC_CACHE[key] = {
            'ts': time.time(),
            'status_code': status_code,
            'headers': headers,
            'body': body,
        }

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

MYSQL_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MySQL Console | GasBook</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --flame: #ff6b2b;
            --flame2: #ff9a3c;
            --bg: #0d0f14;
            --card: #161a24;
            --border: #232840;
            --text: #eef0f8;
            --muted: #6b7499;
            --ok: #28d18f;
            --err: #ff5c68;
            --glow: rgba(255, 107, 43, 0.35);
            --shadow: rgba(0, 0, 0, 0.5);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', sans-serif;
            color: var(--text);
            background: var(--bg);
            min-height: 100vh;
            padding: 30px 18px 40px;
            overflow-x: hidden;
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
            width: 420px;
            height: 420px;
            background: rgba(255, 107, 43, 0.10);
            top: -130px;
            right: -120px;
        }

        .orb2 {
            width: 320px;
            height: 320px;
            background: rgba(255, 154, 60, 0.08);
            bottom: -110px;
            left: -80px;
            animation-delay: -4.5s;
        }

        @keyframes orbFloat {
            0%, 100% { transform: translate(0, 0); }
            50% { transform: translate(22px, -22px); }
        }

        .wrap {
            position: relative;
            z-index: 10;
            max-width: 1100px;
            margin: 0 auto;
            display: grid;
            gap: 18px;
        }

        .panel {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 20px;
            box-shadow: 0 0 0 1px rgba(255, 107, 43, 0.07), 0 24px 50px var(--shadow);
        }

        .hero {
            padding: 24px;
            display: grid;
            gap: 14px;
        }

        h1 {
            font-family: 'Outfit', sans-serif;
            font-size: clamp(28px, 5vw, 42px);
            line-height: 1.1;
            background: linear-gradient(135deg, #fff 25%, var(--flame2));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .meta {
            color: var(--muted);
            display: flex;
            flex-wrap: wrap;
            gap: 8px 14px;
            font-size: 14px;
        }

        .status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            width: fit-content;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 13px;
            border: 1px solid var(--border);
            background: rgba(255, 255, 255, 0.02);
        }

        .status-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: {{ 'var(--ok)' if connected else 'var(--err)' }};
            box-shadow: 0 0 12px {{ 'rgba(40, 209, 143, 0.55)' if connected else 'rgba(255, 92, 104, 0.55)' }};
        }

        .table-wrap {
            overflow: auto;
            border-top: 1px solid var(--border);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 640px;
        }

        th, td {
            text-align: left;
            padding: 12px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            font-size: 14px;
            white-space: nowrap;
        }

        th {
            position: sticky;
            top: 0;
            background: #131724;
            color: #ffd5bf;
            font-weight: 600;
            z-index: 2;
        }

        tr:hover td {
            background: rgba(255, 107, 43, 0.04);
        }

        .muted {
            color: var(--muted);
            font-size: 13px;
            padding: 16px;
        }

        .home-link {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
            width: fit-content;
            color: #fff;
            background: linear-gradient(135deg, var(--flame), var(--flame2));
            border-radius: 12px;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: 600;
            box-shadow: 0 10px 24px var(--glow);
        }

        @media (max-width: 720px) {
            .hero {
                padding: 18px;
            }

            th, td {
                padding: 10px 12px;
                font-size: 13px;
            }
        }
    </style>
</head>
<body>
    <div class="bg-grid"></div>
    <div class="orb orb1"></div>
    <div class="orb orb2"></div>

    <main class="wrap">
        <section class="panel hero">
            <a href="/" class="home-link">Back to App</a>
            <h1>MySQL Overview</h1>
            <p class="status"><span class="status-dot"></span>{{ 'Connected to MySQL' if connected else 'MySQL is not reachable' }}</p>
            <div class="meta">
                <span>Host: {{ host }}</span>
                <span>Port: {{ port }}</span>
                <span>Database: {{ db_name }}</span>
                <span>Updated: {{ now }}</span>
            </div>
        </section>

        <section class="panel">
            {% if connected and tables %}
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>Table Name</th>
                                <th>Rows (Approx)</th>
                                <th>Size (MB)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for row in tables %}
                                <tr>
                                    <td>{{ row.table_name }}</td>
                                    <td>{{ row.table_rows }}</td>
                                    <td>{{ row.size_mb }}</td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            {% elif connected %}
                <p class="muted">Connected, but no tables were found in this database.</p>
            {% else %}
                <p class="muted">Database connection failed. Check MySQL container health and `config.env` values.</p>
            {% endif %}
        </section>
    </main>
</body>
</html>"""

_HTML_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/', methods=['GET'])
@app.route('/login', methods=['GET'])
@app.route('/signin', methods=['GET'])
@app.route('/signup', methods=['GET'])
def index():
    # If user is already logged in, redirect to dashboard
    if session.get('user_id') and session.get('role'):
        return redirect('/dashboard')
    
    # If Adminer-style login params arrive at root, forward to /mysql proxy route.
    adminer_query_keys = {'server', 'username', 'db'}
    if request.path == '/' and adminer_query_keys.intersection(request.args.keys()):
        query = request.query_string.decode('utf-8')
        target = '/mysql/'
        if query:
            target = f"{target}?{query}"
        return redirect(target, code=302)
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
def ware_houses_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/reports', methods=['GET'])
def reports_page():
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/admin-accounts', methods=['GET'])
def admin_accounts_page():
    if not session.get('user_id'):
        return redirect('/?redirect=/admin-accounts')
    if session.get('role') != 'admin':
        return redirect('/dashboard')
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

@app.route('/create-account', methods=['GET'])
def create_account_page():
    if not session.get('user_id'):
        return redirect('/?redirect=/create-account')
    if session.get('role') != 'admin':
        return redirect('/dashboard')
    return send_from_directory(_HTML_DIR, 'src/dashboard.html')

PAGE_404 = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>404 - Page Not Found | GasBook</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 38 38'%3E%3Crect x='13.5' y='3' width='11' height='3' rx='1.5' fill='%23ff6b2b'/%3E%3Crect x='15.5' y='6' width='7' height='2' rx='1' fill='%23ff9a3c'/%3E%3Cellipse cx='19' cy='8' rx='10' ry='3.5' fill='%23ff6b2b' opacity='0.8'/%3E%3Crect x='9' y='8' width='20' height='22' rx='10' fill='%23ff6b2b' opacity='0.5'/%3E%3Cellipse cx='19' cy='30' rx='10' ry='3.5' fill='%23ff6b2b' opacity='0.6'/%3E%3Cpath d='M14 19 Q16 14 19 19 Q22 24 24 19' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' fill='none'/%3E%3C/svg%3E">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
        :root {
            --flame: #ff6b2b;
            --flame2: #ff9a3c;
            --trans: 0.35s cubic-bezier(.4, 0, .2, 1);
        }

        [data-theme="dark"] {
            --bg: #0d0f14;
            --card: #161a24;
            --border: #232840;
            --text: #eef0f8;
            --muted: #6b7499;
            --glow: rgba(255, 107, 43, 0.35);
            --shadow: rgba(0, 0, 0, 0.5);
            --glass: rgba(255, 255, 255, 0.04);
            --glass-bdr: rgba(255, 255, 255, 0.1);
        }

        [data-theme="light"] {
            --bg: #f3f6fc;
            --card: #ffffff;
            --border: #cfd8ea;
            --text: #0f172a;
            --muted: #475569;
            --glow: rgba(255, 107, 43, 0.22);
            --shadow: rgba(70, 85, 130, 0.16);
            --glass: rgba(255, 255, 255, 0.72);
            --glass-bdr: rgba(17, 24, 39, 0.1);
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

        [data-theme="light"] .bg-grid {
            opacity: 0.45;
        }

        [data-theme="light"] .orb1 {
            background: rgba(255, 107, 43, 0.07);
        }

        [data-theme="light"] .orb2 {
            background: rgba(255, 154, 60, 0.06);
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

        .theme-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 100;
            width: 46px;
            height: 46px;
            border-radius: 14px;
            background: var(--glass);
            border: 1px solid var(--glass-bdr);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all var(--trans);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 4px 16px var(--shadow);
            overflow: hidden;
        }

        .theme-toggle::before {
            content: '';
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at center, var(--glow), transparent 70%);
            opacity: 0;
            transition: opacity 0.35s;
            pointer-events: none;
        }

        .theme-toggle:hover {
            border-color: var(--flame);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px var(--glow);
        }

        .theme-toggle:hover::before {
            opacity: 0.6;
        }

        .theme-toggle:active {
            transform: translateY(0) scale(0.94);
        }

        .theme-toggle .sun-icon,
        .theme-toggle .moon-icon {
            position: absolute;
            transition: all 0.55s cubic-bezier(.68, -0.55, .27, 1.55);
        }

        .theme-toggle .sun-icon {
            opacity: 1;
            transform: rotate(0deg) scale(1);
            color: #ffb703;
            filter: drop-shadow(0 0 8px rgba(255, 183, 3, 0.6));
        }

        .theme-toggle .moon-icon {
            opacity: 0;
            transform: rotate(-180deg) scale(0.3);
            color: #93c5fd;
        }

        [data-theme="light"] .theme-toggle .sun-icon {
            opacity: 0;
            transform: rotate(180deg) scale(0.3);
        }

        [data-theme="light"] .theme-toggle .moon-icon {
            opacity: 1;
            transform: rotate(0deg) scale(1);
            color: #4a5578;
            filter: drop-shadow(0 0 6px rgba(74, 85, 120, 0.3));
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

        [data-theme="light"] h1 {
            background: linear-gradient(135deg, #0f172a 25%, #ff8f3a 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
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

        [data-theme="light"] h2 {
            color: #ea580c;
        }

    p {
      color: var(--muted);
      font-size: 15px;
      line-height: 1.6;
      margin-bottom: 36px;
    }

        [data-theme="light"] .card {
            box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.05), 0 40px 80px var(--shadow);
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
    <button class="theme-toggle" id="themeToggle" title="Toggle theme" onclick="toggleTheme()">
        <svg class="sun-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="4.5" fill="currentColor" fill-opacity="0.25" />
            <line x1="12" y1="2" x2="12" y2="4.5" />
            <line x1="12" y1="19.5" x2="12" y2="22" />
            <line x1="2" y1="12" x2="4.5" y2="12" />
            <line x1="19.5" y1="12" x2="22" y2="12" />
            <line x1="5.64" y1="5.64" x2="7.41" y2="7.41" />
            <line x1="16.59" y1="16.59" x2="18.36" y2="18.36" />
            <line x1="5.64" y1="18.36" x2="7.41" y2="16.59" />
            <line x1="16.59" y1="7.41" x2="18.36" y2="5.64" />
        </svg>
        <svg class="moon-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="currentColor" fill-opacity="0.18" />
            <circle cx="17" cy="4" r="0.9" fill="currentColor" stroke="none" />
            <circle cx="20" cy="7.5" r="0.6" fill="currentColor" stroke="none" />
            <circle cx="19.5" cy="2.5" r="0.5" fill="currentColor" stroke="none" />
        </svg>
    </button>
  
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
    <script>
        function toggleTheme() {
            const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
            document.documentElement.dataset.theme = next;
            localStorage.setItem('gasbook_theme', next);
        }

        (function initTheme() {
            const saved = localStorage.getItem('gasbook_theme') || 'dark';
            document.documentElement.dataset.theme = saved;
        })();
    </script>
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

def _rewrite_adminer_location(location: str) -> str:
    if not location:
        return location

    # Rewrite any absolute URL from upstream to our proxied /mysql path.
    if location.startswith('http://') or location.startswith('https://'):
        m = re.search(r'^https?://[^/]+(?P<path>/.*)?$', location)
        location = m.group('path') if (m and m.group('path')) else '/'

        return '/mysql' + location
    return location

def _rewrite_mysql_cookie(cookie_str, scheme):
    parts = cookie_str.split(';')
    new_parts = []
    for p in parts:
        pl = p.lower().strip()
        if pl.startswith('path='):
            new_parts.append('Path=/mysql')
        elif pl == 'secure':
            if scheme == 'https':
                new_parts.append(p)
            continue
        elif pl.startswith('domain='):
            continue
        else:
            new_parts.append(p)
    return '; '.join(new_parts)


def _extract_csp_nonce(csp_header: str) -> str:
    if not csp_header:
        return ''
    m = re.search(r"'nonce-([^']+)'", csp_header)
    return m.group(1) if m else ''


def _inject_mysql_theme(html: str, nonce: str = '') -> str:
    if 'gasbook-adminer-theme' in html:
        return html

    theme_link = '<link id="gasbook-adminer-theme" rel="stylesheet" href="/mysql-theme.css">'
    head_inject = theme_link

    toolbar_html = (
        '<div id="gasbook-adminer-toolbar" '
        'style="position:fixed;top:16px;left:16px;z-index:9999;display:flex;gap:10px;align-items:center;">'
        '<a href="/" style="background:linear-gradient(135deg,#ff6b2b,#ff9a3c);color:#fff;text-decoration:none;'
        'padding:10px 14px;border-radius:12px;font-weight:700;font-family:Inter,sans-serif;box-shadow:0 8px 20px rgba(255,107,43,.28);">'
        'Back to GasBook</a>'
        '</div>'
    )

    nonce_attr = f' nonce="{nonce}"' if nonce else ''
    theme_script = (
        f'<script{nonce_attr}>'
        '(function(){'
        'document.documentElement.setAttribute("data-theme","dark");'
        'var t=document.querySelector("title");'
        'if(t && !String(t.textContent||"").includes("GasBook")){t.textContent=t.textContent+" | GasBook";}'
        '})();'
        '</script>'
    )

    if '</head>' in html:
        html = html.replace('</head>', head_inject + '</head>', 1)
    else:
        html = head_inject + html

    if '</body>' in html:
        html = html.replace('</body>', toolbar_html + theme_script + '</body>', 1)
    else:
        html = html + toolbar_html + theme_script

    return html




@app.route('/mysql', defaults={'subpath': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/mysql/', defaults={'subpath': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/mysql/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def mysql_page(subpath):
    # ── Authentication Check: Only admin can access ──────────────────────────
    user_id = session.get('user_id')
    username = session.get('username')
    role = session.get('role')
    
    if not user_id or role != 'admin':
        _log_audit(user_id, username or 'anonymous', 'mysql_access', 'failed')
        redirect_target = request.full_path if request.query_string else request.path
        if redirect_target.endswith('?'):
            redirect_target = redirect_target[:-1]
        return redirect(f"/mysql-login?redirect={quote(redirect_target, safe='/?:=&')}")
    
    _log_audit(user_id, username, 'mysql_access', 'success')
    
    upstream_url = f"{ADMINER_UPSTREAM}/{subpath}"
    if subpath == '':
        upstream_url = f"{ADMINER_UPSTREAM}/"

    is_static_asset = request.method == 'GET' and _is_mysql_static_asset(subpath)
    cache_key = request.full_path if request.query_string else request.path
    if cache_key.endswith('?'):
        cache_key = cache_key[:-1]

    if is_static_asset:
        cached = _mysql_cache_get(cache_key)
        if cached is not None:
            return Response(cached['body'], status=cached['status_code'], headers=cached['headers'])

    req_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ('host', 'content-length', 'accept-encoding', 'connection')
    }
    req_headers['X-Forwarded-Host'] = request.host
    req_headers['X-Forwarded-Proto'] = request.scheme
    req_headers['X-Forwarded-For'] = request.remote_addr
    req_headers['X-Forwarded-Prefix'] = '/mysql'

    req_cookies = request.cookies if not is_static_asset else None

    try:
        upstream_resp = _UPSTREAM_HTTP.request(
            method=request.method,
            url=upstream_url,
            params=request.args,
            headers=req_headers,
            cookies=req_cookies,
            data=request.get_data(),
            allow_redirects=False,
            timeout=30
        )
    except requests.RequestException as e:
        logger.error(f"Adminer proxy error: {e}")
        error_details = f"Cannot connect to database service at {ADMINER_UPSTREAM}. {str(e)}"
        logger.error(error_details)
        return render_template_string(
            """<!doctype html><html><head><meta charset=\"utf-8\"><title>MySQL Error</title></head>
            <body style=\"font-family:Inter,sans-serif;background:#0d0f14;color:#eef0f8;padding:2rem;\">
            <h2 style=\"color:#ff6b2b;\">⚠ Database Service Error</h2>
            <p>The MySQL admin panel is temporarily unavailable.</p>
            <p><strong>Error:</strong> """ + error_details + """</p>
            <p><strong>Upstream URL:</strong> """ + ADMINER_UPSTREAM + """</p>
            <p><a href="/mysql-login" style=\"color:#ff9a3c;\">Try again</a> or <a href="/" style=\"color:#ff9a3c;\">return home</a></p>
            </body></html>"""
        ), 502

    resp_headers = []
    csp_header = upstream_resp.headers.get('Content-Security-Policy', '')
    for k, v in upstream_resp.headers.items():
        kl = k.lower()
        if kl in ('content-encoding', 'transfer-encoding', 'connection', 'keep-alive'):
            continue
        if kl == 'content-length':
            continue
        if kl == 'location':
            v = _rewrite_adminer_location(v)
        if kl == 'set-cookie':
            v = _rewrite_mysql_cookie(v, request.scheme)
        resp_headers.append((k, v))

    body = upstream_resp.content
    content_type = upstream_resp.headers.get('Content-Type', '').lower()

    resp_headers.append(('Content-Length', str(len(body))))

    if is_static_asset and upstream_resp.status_code == 200:
        _mysql_cache_set(cache_key, upstream_resp.status_code, resp_headers, body)

    return Response(body, status=upstream_resp.status_code, headers=resp_headers)

# ── MySQL Admin Login Page ─────────────────────────────────────────────────────
MYSQL_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Database Login | GasBook</title>
  <link rel="icon" type="image/svg+xml"
    href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 38 38'%3E%3Crect x='13.5' y='3' width='11' height='3' rx='1.5' fill='%23ff6b2b'/%3E%3Crect x='15.5' y='6' width='7' height='2' rx='1' fill='%23ff9a3c'/%3E%3Cellipse cx='19' cy='8' rx='10' ry='3.5' fill='%23ff6b2b' opacity='0.8'/%3E%3Crect x='9' y='8' width='20' height='22' rx='10' fill='%23ff6b2b' opacity='0.5'/%3E%3Cellipse cx='19' cy='30' rx='10' ry='3.5' fill='%23ff6b2b' opacity='0.6'/%3E%3Cpath d='M14 19 Q16 14 19 19 Q22 24 24 19' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' fill='none'/%3E%3C/svg%3E">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --flame: #ff6b2b;
      --flame2: #ff9a3c;
      --flame3: #ffbe7d;
      --trans: 0.35s cubic-bezier(.4, 0, .2, 1);
    }

    [data-theme="dark"] {
      --bg: #0d0f14;
      --surface: #111520;
      --card: #161a24;
      --border: #232840;
      --text: #eef0f8;
      --muted: #6b7499;
      --input-bg: rgba(255, 255, 255, 0.04);
      --input-focus: rgba(255, 107, 43, 0.06);
      --shadow: rgba(0, 0, 0, 0.5);
      --glow: rgba(255, 107, 43, 0.35);
      --glass: rgba(255, 255, 255, 0.04);
      --glass-bdr: rgba(255, 255, 255, 0.1);
    }

        [data-theme="light"] {
            --bg: #f3f6fc;
            --surface: #ffffff;
            --card: #ffffff;
            --border: #dbe2f0;
            --text: #1a1e2b;
            --muted: #6f7692;
            --input-bg: rgba(15, 23, 42, 0.03);
            --input-focus: rgba(255, 107, 43, 0.08);
            --shadow: rgba(70, 85, 130, 0.16);
            --glow: rgba(255, 107, 43, 0.22);
            --glass: rgba(255, 255, 255, 0.72);
            --glass-bdr: rgba(17, 24, 39, 0.1);
        }

    *,
    *::before,
    *::after {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    html,
    body {
      min-height: 100vh;
    }

    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px 20px;
      position: relative;
      transition: background var(--trans), color var(--trans);
      color: var(--text);
      overflow-x: hidden;
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
      transition: opacity var(--trans);
    }

    @keyframes gridShift {
      to {
        background-position: 48px 48px;
      }
    }

    .orb {
      position: fixed;
      border-radius: 50%;
      pointer-events: none;
      filter: blur(90px);
      animation: orbFloat 9s ease-in-out infinite;
    }

    .orb1 {
      width: 450px;
      height: 450px;
      background: rgba(255, 107, 43, 0.10);
      top: -130px;
      right: -100px;
    }

    .orb2 {
      width: 320px;
      height: 320px;
      background: rgba(255, 154, 60, 0.08);
      bottom: -100px;
      left: -90px;
      animation-delay: -4.5s;
    }

        [data-theme="light"] .bg-grid {
            opacity: 0.45;
        }

        [data-theme="light"] .orb1 {
            background: rgba(255, 107, 43, 0.07);
        }

        [data-theme="light"] .orb2 {
            background: rgba(255, 154, 60, 0.06);
        }

    @keyframes orbFloat {
      0%,
      100% {
        transform: translate(0, 0);
      }

      50% {
        transform: translate(22px, -22px);
      }
    }

    .card {
      position: relative;
      z-index: 10;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 44px 40px 40px;
      width: 100%;
      max-width: 430px;
      margin: auto;
      box-shadow: 0 0 0 1px rgba(255, 107, 43, 0.07), 0 40px 80px var(--shadow);
      transition: background var(--trans), border-color var(--trans), box-shadow var(--trans);
      animation: cardIn 0.65s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      opacity: 0;
      transform: translateY(28px);
      overflow: hidden;
    }

        .theme-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 100;
            width: 46px;
            height: 46px;
            border-radius: 14px;
            background: var(--glass);
            border: 1px solid var(--glass-bdr);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all var(--trans);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 4px 16px var(--shadow);
            overflow: hidden;
        }

        .theme-toggle::before {
            content: '';
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at center, var(--glow), transparent 70%);
            opacity: 0;
            transition: opacity 0.35s;
            pointer-events: none;
        }

        .theme-toggle:hover {
            border-color: var(--flame);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px var(--glow);
        }

        .theme-toggle:hover::before {
            opacity: 0.6;
        }

        .theme-toggle:active {
            transform: translateY(0) scale(0.94);
        }

        .theme-toggle .sun-icon,
        .theme-toggle .moon-icon {
            position: absolute;
            transition: all 0.55s cubic-bezier(.68, -0.55, .27, 1.55);
        }

        .theme-toggle .sun-icon {
            opacity: 1;
            transform: rotate(0deg) scale(1);
            color: #ffb703;
            filter: drop-shadow(0 0 8px rgba(255, 183, 3, 0.6));
        }

        .theme-toggle .moon-icon {
            opacity: 0;
            transform: rotate(-180deg) scale(0.3);
            color: #93c5fd;
        }

        [data-theme="light"] .theme-toggle .sun-icon {
            opacity: 0;
            transform: rotate(180deg) scale(0.3);
        }

        [data-theme="light"] .theme-toggle .moon-icon {
            opacity: 1;
            transform: rotate(0deg) scale(1);
            color: #4a5578;
            filter: drop-shadow(0 0 6px rgba(74, 85, 120, 0.3));
        }

    @keyframes cardIn {
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .logo {
      text-align: center;
      margin-bottom: 36px;
    }

    .logo-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 68px;
      height: 68px;
      border-radius: 20px;
      margin-bottom: 16px;
      background: linear-gradient(135deg, var(--flame), var(--flame2));
      box-shadow: 0 0 36px var(--glow);
      animation: logoPulse 2.8s ease-in-out infinite;
      position: relative;
      overflow: hidden;
      font-size: 36px;
    }

    .logo-icon::before {
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at 30% 20%, rgba(255, 255, 255, 0.25), transparent 60%);
      pointer-events: none;
    }

    @keyframes logoPulse {
      0%,
      100% {
        box-shadow: 0 0 30px var(--glow);
      }

      50% {
        box-shadow: 0 0 55px var(--glow), 0 0 80px rgba(255, 107, 43, 0.15);
      }
    }

    .logo h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 28px;
      font-weight: 700;
      background: linear-gradient(135deg, var(--text) 30%, var(--flame2));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: -0.02em;
      text-align: center;
    }

    .logo p {
      font-size: 13px;
      color: var(--muted);
      margin-top: 5px;
      text-align: center;
    }

    .form-group {
      margin-bottom: 18px;
    }

    .form-group label {
      display: block;
      font-size: 11px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.09em;
      margin-bottom: 8px;
    }

    .input-wrap {
      position: relative;
      display: flex;
      align-items: center;
    }

        .input-wrap > svg {
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      width: 16px;
      height: 16px;
      color: var(--muted);
      pointer-events: none;
      transition: color 0.2s;
    }

    .input-wrap input {
      width: 100%;
      padding: 13px 14px 13px 44px;
      background: var(--input-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text);
      font-family: 'Inter', sans-serif;
      font-size: 14px;
      outline: none;
      transition: all 0.25s;
    }

    .input-wrap input[type="password"] {
      padding-right: 44px;
    }

    .input-wrap input:focus {
      border-color: var(--flame);
      background: var(--input-focus);
      box-shadow: 0 0 0 3px rgba(255, 107, 43, 0.14);
    }

        .input-wrap:focus-within > svg {
      color: var(--flame);
    }

    .password-toggle {
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      cursor: pointer;
      color: var(--muted);
      padding: 6px;
      transition: color 0.2s;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10;
    }

    .password-toggle:hover {
      color: var(--flame);
    }

    .password-toggle svg {
      width: 18px;
      height: 18px;
      stroke-width: 2;
    }

    .btn-login {
      width: 100%;
      padding: 14px;
      margin-top: 8px;
      background: linear-gradient(135deg, var(--flame), var(--flame2));
      border: none;
      border-radius: 12px;
      color: #fff;
      font-family: 'Outfit', sans-serif;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.03em;
      cursor: pointer;
      transition: all 0.25s;
      position: relative;
      overflow: hidden;
    }

    .btn-login::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.18), transparent);
      opacity: 0;
      transition: opacity 0.25s;
    }

    .btn-login:hover::after {
      opacity: 1;
    }

    .btn-login:hover {
      transform: translateY(-2px);
      box-shadow: 0 10px 32px rgba(255, 107, 43, 0.42);
    }

    .btn-login:active {
      transform: translateY(0);
    }

    .error-msg {
      margin-top: 12px;
      text-align: center;
      font-size: 13px;
      padding: 10px 12px;
      border-radius: 10px;
      margin-bottom: 18px;
      display: none;
      opacity: 0;
      transform: translateY(-8px);
      transition: all 0.3s;
      border: 1px solid;
    }

    .error-msg.show {
      display: block;
      opacity: 1;
      transform: translateY(0);
    }

    .error-msg.error {
      background: rgba(255, 92, 104, 0.15);
      border-color: #ff5c68;
      color: #ff8f95;
    }

    .error-msg.success {
      background: rgba(34, 197, 94, 0.15);
      border-color: #22c55e;
      color: #22c55e;
    }

    .back-link {
      margin-top: 24px;
      text-align: center;
      font-size: 13px;
    }

    .back-link a {
      color: var(--flame);
      text-decoration: none;
      transition: all 0.25s;
    }

    .back-link a:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="orb orb1"></div>
  <div class="orb orb2"></div>
    <button class="theme-toggle" id="themeToggle" title="Toggle theme" onclick="toggleTheme()">
        <svg class="sun-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="4.5" fill="currentColor" fill-opacity="0.25" />
            <line x1="12" y1="2" x2="12" y2="4.5" />
            <line x1="12" y1="19.5" x2="12" y2="22" />
            <line x1="2" y1="12" x2="4.5" y2="12" />
            <line x1="19.5" y1="12" x2="22" y2="12" />
            <line x1="5.64" y1="5.64" x2="7.41" y2="7.41" />
            <line x1="16.59" y1="16.59" x2="18.36" y2="18.36" />
            <line x1="5.64" y1="18.36" x2="7.41" y2="16.59" />
            <line x1="16.59" y1="7.41" x2="18.36" y2="5.64" />
        </svg>
        <svg class="moon-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="currentColor" fill-opacity="0.18" />
            <circle cx="17" cy="4" r="0.9" fill="currentColor" stroke="none" />
            <circle cx="20" cy="7.5" r="0.6" fill="currentColor" stroke="none" />
            <circle cx="19.5" cy="2.5" r="0.5" fill="currentColor" stroke="none" />
        </svg>
    </button>
  
  <div class="card">
    <div class="logo">
      <div class="logo-icon">🔐</div>
      <h1>Database Login</h1>
      <p>Admin credentials required</p>
    </div>
    
    <div class="error-msg" id="errorMsg"></div>
    
    <form id="loginForm" onsubmit="handleLogin(event)">
      <div class="form-group">
        <label for="username">Username / Email</label>
        <div class="input-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
          <input type="text" id="username" name="username" placeholder="Enter username or email" required autofocus>
        </div>
      </div>
      
      <div class="form-group">
        <label for="password">Password</label>
        <div class="input-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
          </svg>
          <input type="password" id="password" name="password" placeholder="Enter password" required>
          <button type="button" class="password-toggle" onclick="togglePasswordVisibility()">
            <svg id="eye-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
          </button>
        </div>
      </div>
      
      <button type="submit" class="btn-login">Sign In</button>
    </form>
    
    <div class="back-link">
      <a href="/">← Back to Home</a>
    </div>
  </div>

  <script>
    function toggleTheme() {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('gasbook_theme', next);
    }

    (function initTheme() {
      const saved = localStorage.getItem('gasbook_theme') || 'dark';
      document.documentElement.dataset.theme = saved;
    })();

    function togglePasswordVisibility() {
      const input = document.getElementById('password');
      const icon = document.getElementById('eye-icon');
      
      if (input.type === 'password') {
        input.type = 'text';
        icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>';
      } else {
        input.type = 'password';
        icon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>';
      }
    }

    async function handleLogin(e) {
      e.preventDefault();
      const username = document.getElementById('username').value;
      const password = document.getElementById('password').value;
      const errorMsg = document.getElementById('errorMsg');
      
      errorMsg.classList.remove('show', 'error', 'success');
      
      try {
        const res = await fetch('/api/mysql-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        
        const data = await res.json();
        
        if (data.success && data.role === 'admin') {
          errorMsg.textContent = '✓ Login Successful!';
          errorMsg.classList.add('show', 'success');
          const redirect = new URLSearchParams(window.location.search).get('redirect') || '/mysql';
          setTimeout(() => { window.location.href = redirect; }, 700);
        } else if (data.success) {
          errorMsg.textContent = '❌ Database access requires admin role';
          errorMsg.classList.add('show', 'error');
        } else {
          errorMsg.textContent = '❌ ' + (data.message || 'Login failed');
          errorMsg.classList.add('show', 'error');
        }
      } catch (err) {
        errorMsg.textContent = '❌ Network error: ' + err.message;
        errorMsg.classList.add('show', 'error');
      }
    }
  </script>
</body>
</html>"""

@app.route('/mysql-login', methods=['GET'])
def mysql_login():
    """MySQL admin login page"""
    user_id = session.get('user_id')
    role = session.get('role')
    if user_id and role == 'admin':
        return redirect(request.args.get('redirect', '/mysql'))
    return render_template_string(MYSQL_LOGIN_PAGE)


@app.route('/api/mysql-login', methods=['POST'])
def mysql_login_api():
    """Dedicated login for phpMyAdmin access (admin only)."""
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400

    conn = get_db()
    if not conn:
        return db_error()

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            'SELECT user_id, username, role FROM users '
            'WHERE username=%s AND password=%s AND status="active" AND role="admin" LIMIT 1',
            (username, password)
        )
        user = cur.fetchone()
        cur.close(); conn.close()

        if not user:
            _log_audit(None, username, 'mysql_login', 'failed')
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

        session.permanent = True
        session['user_id'] = user['user_id']
        session['username'] = user['username']
        session['role'] = user['role']
        _log_audit(user['user_id'], user['username'], 'mysql_login', 'success')
        return jsonify({'success': True, 'role': user['role'], 'message': 'MySQL login successful'})
    except Error as e:
        conn.close()
        logger.error(f"MySQL login error: {e}")
        return db_error(str(e))


@app.route('/mysql-logout', methods=['GET', 'POST'])
def mysql_logout_page():
    """Logout route for phpMyAdmin access."""
    user_id = session.get('user_id')
    username = session.get('username', 'unknown')
    _log_audit(user_id, username, 'mysql_logout', 'success')

    session.clear()
    resp = redirect('/mysql-login')
    for cookie_name in request.cookies.keys():
        if cookie_name.lower().startswith('pma'):
            resp.delete_cookie(cookie_name, path='/')
            resp.delete_cookie(cookie_name, path='/mysql')
    return resp


@app.route('/api/mysql-logout', methods=['POST'])
def mysql_logout_api():
    """API logout for phpMyAdmin access."""
    user_id = session.get('user_id')
    username = session.get('username', 'unknown')
    _log_audit(user_id, username, 'mysql_logout', 'success')
    session.clear()
    return jsonify({'success': True, 'message': 'MySQL session logged out'})

@app.route('/api/mysql-health', methods=['GET'])
def mysql_health():
    """Check if phpmyadmin service is up"""
    try:
        resp = requests.get(f"{ADMINER_UPSTREAM}/", timeout=5)
        return jsonify({'success': True, 'status': 'up', 'code': resp.status_code})
    except Exception as e:
        logger.error(f"phpmyadmin health check failed: {e}")
        return jsonify({'success': False, 'status': 'down', 'error': str(e)}), 503

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

def _serialize_db_data(data):
    """Recursively converts datetimes, dates, and Decimals to JSON-serializable formats."""
    if data is None:
        return None
    if isinstance(data, list):
        for item in data:
            _serialize_db_data(item)
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (datetime, date)):
                data[k] = format_ist_datetime(v)
            elif isinstance(v, Decimal):
                data[k] = float(v)
    return data

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


def ensure_customer_role():
    conn = get_db()
    if not conn: return
    try:
        cur = conn.cursor(dictionary=True)
        # 1. Ensure schema patches
        try:
            cur.execute("ALTER TABLE users MODIFY COLUMN role ENUM('admin','staff','customer') NOT NULL DEFAULT 'staff'")
            conn.commit()
        except Exception: pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN customer_id VARCHAR(20) DEFAULT NULL")
            conn.commit()
        except Exception: pass

        # 2. Seed default customer user if missing
        cur.execute("SELECT user_id, customer_id FROM users WHERE username = 'customer'")
        u_row = cur.fetchone()
        if not u_row:
            cur.execute("INSERT INTO users (username, password, role) VALUES ('customer', 'customer123', 'customer')")
            user_id = cur.lastrowid
            conn.commit()
        else:
            user_id = u_row['user_id']
            
        # 3. Ensure default customer has a linked profile
        cur.execute("SELECT customer_id FROM users WHERE user_id = %s", (user_id,))
        cid = cur.fetchone()['customer_id']
        if not cid:
            # Generate next CUST ID
            cur.execute('SELECT COUNT(*) AS c FROM customers')
            count = cur.fetchone()['c'] + 1
            cid = f'CUST{count:04d}'
            cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))
            while cur.fetchone():
                count += 1
                cid = f'CUST{count:04d}'
                cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))
            
            # Create profile
            cur.execute("INSERT INTO customers (customer_id, name, email, status, source) VALUES (%s, %s, %s, %s, %s)",
                       (cid, 'Default Customer', 'customer@example.com', 'active', 'signup'))
            # Link to user
            cur.execute("UPDATE users SET customer_id = %s WHERE user_id = %s", (cid, user_id))
            conn.commit()

        # 4. Patch any other missing links based on email match
        try:
            cur.execute("UPDATE users u JOIN customers c ON c.email = u.username SET u.customer_id = c.customer_id WHERE u.customer_id IS NULL")
            conn.commit()
        except Exception: pass
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()


# ── Auth helper ───────────────────────────────────────────────────────────────
def _get_user_context():
    """Returns (user_id, role, c_id, c_email) by checking session then X-User-Id header."""
    uid = session.get('user_id')
    role = session.get('role')
    c_id = session.get('c_id')
    c_em = session.get('c_email')

    # If session is empty, try X-User-Id header
    if not uid:
        hdr = request.headers.get('X-User-Id')
        if hdr and hdr.isdigit():
            uid = int(hdr)
            # Fetch context from DB
            conn = get_db()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    cur.execute(
                        'SELECT u.role, u.customer_id, c.email '
                        'FROM users u LEFT JOIN customers c ON u.customer_id = c.customer_id '
                        'WHERE u.user_id = %s LIMIT 1', (uid,)
                    )
                    user = cur.fetchone()
                    if user:
                        role = user['role']
                        c_id = user['customer_id']
                        c_em = user['email']
                    cur.close()
                except Exception as e:
                    logger.error(f"Error fetching user context: {e}")
                finally:
                    conn.close()

    # Defaults
    if not role: role = 'customer'
    return uid, role, c_id, c_em

def _get_current_user_id():
    uid, _, _, _ = _get_user_context()
    return uid

def _log_audit(user_id, username, action, status='success'):
    """Audit logging removed by requirement; keep no-op for compatibility."""
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
            'WHERE (users.username=%s OR customers.email=%s) AND users.password=%s '
            'AND users.status="active" AND users.role IN ("admin","staff","customer") LIMIT 1',
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
            _log_audit(user['user_id'], user['username'], 'login', 'success')
            return jsonify({
                'success':  True,
                'user_id':  user['user_id'],
                'username': user['username'],
                'c_id':     user['c_id'],
                'role':     user['role'],
                'message':  'Login successful'
            })
        _log_audit(None, username, 'login', 'failed')
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
    except Error as e:
        conn.close()
        logger.error(f"Login error: {e}")
        return db_error(str(e))

@app.route('/logout', methods=['GET'])
def logout_get():
    session.clear()
    return redirect('/')

@app.route('/api/logout', methods=['POST'])
def logout():
    user_id = session.get('user_id')
    username = session.get('username', 'unknown')
    _log_audit(user_id, username, 'logout', 'success')
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
            base_sql += ' AND c.customer_id IN (SELECT customer_id FROM users WHERE role="customer" OR role IS NULL)'
            return base_sql + ' AND c.customer_id != %s' if exclude_c_id else base_sql
        def get_params():
            return (value, exclude_c_id) if exclude_c_id else (value,)
            
        if field == 'username':
            cur.execute('SELECT user_id FROM users WHERE username=%s AND role="customer"', (value,))
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(get_exclude_sql('SELECT c.customer_id FROM customers c WHERE c.email=%s'), get_params())
                exists = cur.fetchone() is not None
        elif field == 'email':
            cur.execute(get_exclude_sql('SELECT c.customer_id FROM customers c WHERE c.email=%s'), get_params())
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute('SELECT user_id FROM users WHERE username=%s AND role="customer"', (value,))
                exists = cur.fetchone() is not None
        elif field == 'phone':
            cur.execute(get_exclude_sql('SELECT c.customer_id FROM customers c WHERE c.phone=%s'), get_params())
            exists = cur.fetchone() is not None
        elif field == 'aadhar':
            cur.execute(get_exclude_sql('SELECT c.customer_id FROM customers c WHERE c.aadhar_no=%s'), get_params())
            exists = cur.fetchone() is not None
            
        cur.close(); conn.close()
        return jsonify({'available': not exists})
    except Exception as e:
        print("CHECK AVAILABILITY ERROR:", str(e), flush=True)
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
        cur.execute('SELECT user_id FROM users WHERE username=%s AND role="customer"', (username,))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'This username is already taken. Please choose another.'}), 409
            
        cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.email=%s AND (u.role="customer" OR u.role IS NULL)', (email,))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'This email is already registered. Please log in.'}), 409

        cur.execute('INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
            (username, password, 'customer', 'active'))
        user_id = cur.lastrowid

        cur.execute('SELECT COUNT(*) AS c FROM customers')
        count = cur.fetchone()['c'] + 1
        cid = f'CUST{count:04d}'
        cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))
        while cur.fetchone():
            count += 1
            cid = f'CUST{count:04d}'
            cur.execute('SELECT customer_id FROM customers WHERE customer_id=%s', (cid,))

        cur.execute('INSERT INTO customers (customer_id, name, phone, email, status, source) VALUES (%s, %s, %s, %s, %s, %s)',
            (cid, None, None, email, 'active', 'signup'))
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
    if role not in ('admin', 'staff', 'customer'):
        return jsonify({'success': False, 'message': 'Role must be admin, staff, or customer'}), 400
    # Staff can only create customer/customer accounts.
    if actor_role == 'staff':
        role = 'customer'

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT user_id FROM users WHERE LOWER(username)=%s AND role="customer" LIMIT 1', (username.lower(),))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Username "{username}" is already taken'}), 409
        cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.email=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (email,))
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
            cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.phone=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (phone,))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Phone "{phone}" is already registered'}), 409
        if aadhar:
            cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.aadhar_no=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (aadhar,))
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
            'INSERT INTO customers (customer_id, name, phone, email, address, aadhar_no, status, source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (cid, format_name(name) if name else None, phone or None, email, address or None, aadhar or None, 'active', 'signup')
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

# ── Admin: List Staff & Admins ────────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
def get_users():
    user_id, role, _, _ = _get_user_context()
    if not user_id or role != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        # Show staff and admins (using their own columns)
        cur.execute(
            'SELECT user_id, username, role, status, created_at, full_name, email, phone '
            'FROM users '
            'WHERE role IN ("admin", "staff") '
            'ORDER BY role ASC, username ASC'
        )
        rows = cur.fetchall()
        _serialize_db_data(rows)
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/users/<int:uid>', methods=['GET'])
def get_user_single(uid):
    user_id, role, _, _ = _get_user_context()
    if not user_id or role != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            'SELECT user_id, username, role, status, created_at, full_name, email, phone '
            'FROM users '
            'WHERE user_id = %s LIMIT 1', (uid,)
        )
        row = cur.fetchone()
        _serialize_db_data(row)
        cur.close(); conn.close()
        if not row: return jsonify({'success': False, 'message': 'User not found'}), 404
        return jsonify({'success': True, 'data': row})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/users/<int:uid>', methods=['PUT'])
def update_user_api(uid):
    user_id, role, _, _ = _get_user_context()
    if not user_id or role != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    data = request.get_json(force=True, silent=True) or {}
    new_role = (data.get('role') or '').strip()
    status   = (data.get('status') or 'active').strip()
    name     = (data.get('name') or '').strip()
    email    = (data.get('email') or '').strip().lower()
    phone    = (data.get('phone') or '').strip()
    address  = (data.get('address') or '').strip()
    aadhar   = (data.get('aadhar_no') or '').replace('-', '').strip()

    if new_role and new_role not in ('admin', 'staff'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT customer_id FROM users WHERE user_id=%s', (uid,))
        usr = cur.fetchone()
        if not usr:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        cid = usr['customer_id']

        # Update user table with profile fields
        up_u = "UPDATE users SET role=%s, status=%s, full_name=%s, email=%s, phone=%s WHERE user_id=%s"
        cur.execute(up_u, (new_role, status, format_name(name) if name else None, email or None, phone or None, uid))
        
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'Account updated successfully'})
    except Error as e:
        conn.rollback(); conn.close(); return db_error(str(e))

@app.route('/api/users/<int:uid>', methods=['DELETE'])
def delete_user_api(uid):
    user_id, role, _, _ = _get_user_context()
    if not user_id or role != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    if uid == user_id:
        return jsonify({'success': False, 'message': 'Cannot delete yourself'}), 400

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT customer_id FROM users WHERE user_id=%s', (uid,))
        usr = cur.fetchone()
        if not usr:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        cid = usr['customer_id']

        # Delete user
        cur.execute('DELETE FROM users WHERE user_id=%s', (uid,))
        if cid:
            cur.execute('DELETE FROM customers WHERE customer_id=%s', (cid,))
        
        conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Error as e:
        conn.rollback(); conn.close(); return db_error(str(e))




# ── AUDIT LOG ─────────────────────────────────────────────────────────────────
@app.route('/api/audit-log', methods=['GET'])
def get_audit_log():
    """Audit logging has been removed from this system."""
    return jsonify({'success': False, 'message': 'audit_log removed'}), 410

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
                   c.address, c.aadhar_no, c.customer_since,
                   c.total_bookings, c.total_spent, c.status
            FROM users u
            LEFT JOIN customers c ON c.customer_id = u.customer_id
            WHERE u.user_id = %s LIMIT 1
        ''', (user_id,))
        row = cur.fetchone()

        if not row:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404

        row['is_impersonating'] = 'impersonator_id' in session
        row['impersonator_name'] = session.get('impersonator_name')

        # Fallback: if no customer linked, try matching by username/email
        if not row.get('c_id'):
            cur.execute('''
                SELECT customer_id AS c_id, customer_id, name, phone, email,
                       address, aadhar_no, customer_since, total_bookings,
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

        # Serialize datetime and Decimal fields
        _serialize_db_data(row)

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
            cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.phone=%s AND c.customer_id != %s AND (u.role="customer" OR u.role IS NULL)', (phone, cust_id))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Phone number already in use'}), 409
                
            # Check email uniqueness
            cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.email=%s AND c.customer_id != %s AND (u.role="customer" OR u.role IS NULL)', (email, cust_id))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Email address already in use'}), 409
                
            # Check aadhar uniqueness
            cur.execute('SELECT c.customer_id FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.aadhar_no=%s AND c.customer_id != %s AND (u.role="customer" OR u.role IS NULL)', (aadhar, cust_id))
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

        user_id, role, c_id, c_em = _get_user_context()
        if not user_id:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401

        join_clause = " LEFT JOIN users u ON c.customer_id = u.customer_id"
        params = []

        # Always exclude admin/staff accounts — only show customer-role users
        customer_filter = "(u.role = 'customer' OR u.role IS NULL)"

        if role == 'customer':
            where_clause_c = f"WHERE (c.customer_id = %s OR c.email = %s) AND {customer_filter} "
            params.extend([c_id, c_em])
        elif q:
            like = f'%{q}%'
            where_clause_c = f"WHERE (c.name LIKE %s OR c.phone LIKE %s OR c.customer_id LIKE %s) AND {customer_filter} "
            params.extend([like, like, like])
        else:
            where_clause_c = f"WHERE {customer_filter} "

        # Count total matching rows (with the join for role filter)
        cur.execute(
            f"SELECT COUNT(*) as c FROM customers c{join_clause} {where_clause_c}",
            tuple(params)
        )
        total = cur.fetchone()['c']

        cur.execute(
            f"SELECT c.*, u.username, u.role FROM customers c{join_clause} {where_clause_c} ORDER BY c.customer_since DESC LIMIT %s OFFSET %s",
            tuple(params + [limit, offset])
        )
        rows = cur.fetchall()
        _serialize_db_data(rows)
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
        cur.execute('SELECT c.customer_id, c.name FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.phone=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (phone,))
        dup = cur.fetchone()
        if dup:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': f'Phone {phone} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if email:
            cur.execute('SELECT c.customer_id, c.name FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.email=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (email,))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Email {email} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if aadhar:
            cur.execute('SELECT c.customer_id, c.name FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.aadhar_no=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (aadhar,))
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

        cur.execute('INSERT INTO customers (customer_id,name,phone,email,address,aadhar_no,source) VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (cid, name, phone, email, address, aadhar or None, 'admin'))
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
        _serialize_db_data(row)
        return jsonify({'success': True, 'data': row})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/customers/<customer_id>', methods=['PUT'])
def update_customer(customer_id):
    if session.get('role') == 'customer' and session.get('c_id') != customer_id:
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
            cur.execute('SELECT c.customer_id, c.name FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.phone=%s AND c.customer_id!=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (phone, customer_id))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Phone {phone} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if email:
            cur.execute('SELECT c.customer_id, c.name FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.email=%s AND c.customer_id!=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (email, customer_id))
            dup = cur.fetchone()
            if dup:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': f'Email {email} is already registered to {dup["name"]} ({dup["customer_id"]})'}), 409

        if aadhar:
            cur.execute('SELECT c.customer_id, c.name FROM customers c LEFT JOIN users u ON c.customer_id=u.customer_id WHERE c.aadhar_no=%s AND c.customer_id!=%s AND (u.role="customer" OR u.role IS NULL) LIMIT 1', (aadhar, customer_id))
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
        cur.execute('SELECT * FROM cylinder_types WHERE is_active=1 ORDER BY type_id')
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

        user_id, role, c_id, c_em = _get_user_context()
        if not user_id:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401

        base_sql = '''
            SELECT b.*, c.name AS customer_name, c.phone AS customer_phone,
                   c.address AS customer_address,
                   ct.type_name, ct.price AS unit_price, ct.weight,
                   db.name AS delivery_boy_name
            FROM bookings b
            JOIN customers c ON b.customer_id = c.customer_id
            JOIN cylinder_types ct ON b.type_id = ct.type_id
            LEFT JOIN delivery_boys db ON b.delivery_boy_id = db.boy_id
        '''
        conds = []; params = []
        if status: conds.append("b.status=%s"); params.append(status)
        if role == 'customer': conds.append("b.customer_id=%s"); params.append(c_id)
        where_clause = " WHERE " + " AND ".join(conds) if conds else ""

        cur.execute(base_sql + where_clause + ' ORDER BY b.booking_date DESC LIMIT %s OFFSET %s',
            tuple(params + [limit, offset]))
        rows = cur.fetchall()
        _serialize_db_data(rows)

        cur.execute('SELECT COUNT(*) as c FROM bookings b' + where_clause, tuple(params))
        total = cur.fetchone()['c']
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows, 'total': total, 'page': page, 'limit': limit})
    except Error as e:
        conn.close(); return db_error(str(e))

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    data = request.get_json(force=True, silent=True) or {}
    user_id, role, c_id, c_em = _get_user_context()
    if not user_id:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    if role == 'customer':
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

        cur.execute('SELECT price FROM cylinder_types WHERE type_id=%s AND is_active=1', (data['type_id'],))
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
            cur.execute('''SELECT db.boy_id FROM delivery_boys db 
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
    role = session.get('role', 'customer')
    if role == 'customer' and status != 'cancelled':
        return jsonify({'success': False, 'message': 'customers can only cancel bookings.'}), 403
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
    if session.get('role') == 'customer':
        return jsonify({'success': False, 'message': 'customers cannot delete bookings'}), 403
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
    user_id, role, _, _ = _get_user_context()
    if not user_id:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('''SELECT i.*, ct.type_name, ct.weight, ct.price,
                   w.name AS warehouse_name, w.location
            FROM inventory i
            JOIN cylinder_types ct ON i.type_id = ct.type_id
            JOIN ware_houses w ON i.warehouse_id = w.warehouse_id
            ORDER BY w.name, ct.type_name''')
        rows = cur.fetchall()
        _serialize_db_data(rows)
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

# ── ware_houses ────────────────────────────────────────────────────────────────
@app.route('/api/ware-houses', methods=['GET'])
def get_ware_houses():
    user_id, _, _, _ = _get_user_context()
    if not user_id:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM ware_houses ORDER BY name')
        rows = cur.fetchall()
        _serialize_db_data(rows)
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── DELIVERY BOYS ─────────────────────────────────────────────────────────────
@app.route('/api/delivery_boys', methods=['GET'])
def get_delivery_boys():
    user_id, _, _, _ = _get_user_context()
    if not user_id:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM delivery_boys WHERE status='active' ORDER BY name")
        rows = cur.fetchall()
        _serialize_db_data(rows)
        cur.close(); conn.close()
        return jsonify({'success': True, 'data': rows})
    except Error as e:
        conn.close(); return db_error(str(e))

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@app.route('/api/analytics/dashboard', methods=['GET'])
def dashboard_metrics():
    user_id, role, c_id, c_em = _get_user_context()
    
    if not user_id:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        if role == 'customer':
            # For customers, c_id is mandatory. If missing, try to find it.
            if not c_id:
                 cur.execute("SELECT customer_id FROM users WHERE user_id = %s", (user_id,))
                 row = cur.fetchone()
                 if row: c_id = row['customer_id']
            
            if not c_id:
                cur.close(); conn.close()
                return jsonify({'success': False, 'message': 'Customer profile not linked'}), 400

            cur.execute('SELECT COUNT(*) as c FROM bookings WHERE customer_id=%s', (c_id,))
            total_bookings = cur.fetchone()['c']
            total_customers = 1
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
                JOIN cylinder_types ct ON b.type_id=ct.type_id
                LEFT JOIN delivery_boys db ON b.delivery_boy_id = db.boy_id
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
            cur.execute('''SELECT COUNT(*) as c FROM customers c 
                           LEFT JOIN users u ON c.customer_id = u.customer_id 
                           WHERE c.status="active" AND (u.role = 'customer' OR u.role IS NULL)''')
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
                JOIN cylinder_types ct ON b.type_id=ct.type_id
                LEFT JOIN delivery_boys db ON b.delivery_boy_id = db.boy_id
                ORDER BY b.booking_date DESC LIMIT 5''')
            recent = cur.fetchall()
            cur.execute('''SELECT DATE_FORMAT(booking_date,'%Y-%m') as month,
                       COUNT(*) as bookings, COALESCE(SUM(amount),0) as revenue
                FROM bookings
                WHERE booking_date >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 6 MONTH)
                GROUP BY DATE_FORMAT(booking_date,'%Y-%m')
                ORDER BY month ASC''')
            monthly = cur.fetchall()

        # Serialize all database results using the centralized helper
        _serialize_db_data(recent)
        _serialize_db_data(monthly)
                
        cur.close(); conn.close()
        return jsonify({
            'success': True, 
            'total_bookings': total_bookings,
            'total_customers': total_customers,
            'total_revenue': round(float(total_revenue), 2),
            'pending': pending, 
            'confirmed': confirmed,
            'recent_bookings': recent, 
            'monthly': monthly,
        })
    except Exception as e:
        logger.error(f"Dashboard metrics error: {e}", exc_info=True)
        if 'conn' in locals() and conn: conn.close()
        return jsonify({'success': False, 'message': f"Dashboard error: {str(e)}"}), 500


@app.route('/api/admin/reset-db', methods=['POST'])
def reset_database_api():
    user_id, role, _, _ = _get_user_context()
    if not user_id or role != 'admin':
        return jsonify({'success': False, 'message': 'Admin privileges required'}), 403

    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor()
        # Drop all tables in reverse dependency order
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS bookings")
        cur.execute("DROP TABLE IF EXISTS inventory")
        cur.execute("DROP TABLE IF EXISTS delivery_boys")
        cur.execute("DROP TABLE IF EXISTS customers")
        cur.execute("DROP TABLE IF EXISTS ware_houses")
        cur.execute("DROP TABLE IF EXISTS cylinder_types")
        cur.execute("DROP TABLE IF EXISTS users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        cur.close(); conn.close()
        initialize_database()
        return jsonify({'success': True, 'message': 'System reset to default successfully. Refresh page.'})
    except Error as e:
        if 'conn' in locals() and conn: conn.close()
        return db_error(str(e))

# ── Impersonation API ────────────────────────────────────────────────────────
@app.route('/api/admin/impersonate', methods=['POST'])
def impersonate_customer():
    user_id, role, _, _ = _get_user_context()
    if role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    data = request.get_json()
    target_c_id = data.get('customer_id')
    if not target_c_id:
        return jsonify({'success': False, 'message': 'Customer ID required'}), 400
    
    conn = get_db()
    if not conn: return db_error()
    try:
        cur = conn.cursor(dictionary=True)
        # Find user linked to this customer
        cur.execute("SELECT u.*, c.email FROM users u LEFT JOIN customers c ON u.customer_id = c.customer_id WHERE u.customer_id = %s LIMIT 1", (target_c_id,))
        target_user = cur.fetchone()
        if not target_user:
            cur.close(); conn.close()
            return jsonify({'success': False, 'message': 'No user account found for this customer'}), 404
        
        # Save original admin info if not already impersonating
        if 'impersonator_id' not in session:
            session['impersonator_id'] = user_id
            session['impersonator_role'] = role
            session['impersonator_name'] = session.get('username', 'Admin')
        
        # Switch session
        session['user_id'] = target_user['user_id']
        session['username'] = target_user['username']
        session['role'] = target_user['role']
        session['c_id'] = target_user['customer_id']
        session['c_email'] = target_user['email']
        
        cur.close(); conn.close()
        return jsonify({
            'success': True, 
            'message': f"Impersonating {target_user['username']}",
            'user': {
                'user_id': target_user['user_id'],
                'username': target_user['username'],
                'role': target_user['role'],
                'c_id': target_user['customer_id']
            }
        })
    except Error as e:
        if 'conn' in locals() and conn: conn.close()
        return db_error(str(e))

@app.route('/api/admin/unimpersonate', methods=['POST'])
def unimpersonate():
    if 'impersonator_id' not in session:
        return jsonify({'success': False, 'message': 'Not currently impersonating'}), 400
    
    orig_id = session['impersonator_id']
    orig_role = session['impersonator_role']
    orig_name = session['impersonator_name']
    
    # Restore original session
    session.clear()
    session['user_id'] = orig_id
    session['role'] = orig_role
    session['username'] = orig_name
    
    return jsonify({
        'success': True, 
        'message': 'Restored original session',
        'user': {
            'user_id': orig_id,
            'username': orig_name,
            'role': orig_role
        }
    })




def initialize_database():
    conn = get_db()
    if not conn:
        logger.error("Could not connect to DB for init.")
        return
    try:
        cur = conn.cursor()
        
        # ── Clean up pma__ tables ──────────────────
        try:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute("SHOW TABLES LIKE 'pma__%'")
            pma_tables = [r[0] for r in cur.fetchall()]
            for tbl in pma_tables:
                cur.execute(f"DROP TABLE IF EXISTS `{tbl}`")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            conn.commit()
            if pma_tables: logger.info(f"Purged {len(pma_tables)} pma__ utility tables.")
        except Exception as e:
            logger.warning(f"Could not purge pma__ tables: {e}")

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

        # Add source column to track signup vs admin-created customers
        try:
            cur.execute("ALTER TABLE customers ADD COLUMN source ENUM('signup','admin') NOT NULL DEFAULT 'admin'")
            conn.commit()
            # Retroactively mark customers linked to users as signup
            cur.execute("UPDATE customers c JOIN users u ON c.customer_id=u.customer_id SET c.source='signup'")
            conn.commit()
        except Error:
            pass  # already exists
            
        # Patch users table for management fields
        try:
            cur.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(100) NULL AFTER status")
            cur.execute("ALTER TABLE users ADD COLUMN email VARCHAR(100) NULL AFTER full_name")
            cur.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(15) NULL AFTER email")
            conn.commit()
        except Error:
            pass # ignore if already altered

        # Remove audit_log table by requirement.
        try:
            cur.execute("DROP TABLE IF EXISTS audit_log")
            conn.commit()
        except Error:
            pass
            
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
    ensure_customer_role()
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=port)
