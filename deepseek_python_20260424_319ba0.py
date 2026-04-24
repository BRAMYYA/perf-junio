import os, subprocess, threading, uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader

# ---------- Templates (all HTML/CSS/JS as strings) ----------
BASE_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Junior Performance Engineer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
        .animate-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    </style>
    <link rel="icon" href="data:image/svg+xml,{{ logo_svg }}" type="image/svg+xml">
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-white shadow-md p-4 flex justify-between items-center">
        <a href="/dashboard" class="flex items-center space-x-2">
            <img src="data:image/svg+xml,{{ logo_svg }}" alt="logo" class="h-8 w-8">
            <span class="text-xl font-bold text-indigo-600">PerfJunior</span>
        </a>
        <div class="space-x-4">
            <a href="/dashboard" class="text-gray-700 hover:text-indigo-600">Dashboard</a>
            <a href="/upload" class="text-gray-700 hover:text-indigo-600">New JMeter Test</a>
            <a href="/lighthouse" class="text-gray-700 hover:text-indigo-600">Lighthouse Audit</a>
            <a href="/tools" class="text-gray-700 hover:text-indigo-600">Tools</a>
            <a href="/logout" class="text-red-500 hover:text-red-700">Logout</a>
        </div>
    </nav>
    <main class="container mx-auto p-6">
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            <div class="mb-4">
              {% for msg in messages %}
                <div class="bg-yellow-100 border-l-4 border-yellow-500 text-yellow-700 p-4" role="alert">{{ msg }}</div>
              {% endfor %}
            </div>
          {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
</body>
</html>'''

LOGIN_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto bg-white p-8 shadow-lg rounded mt-20">
    <h2 class="text-2xl font-bold mb-6 text-center">Login</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="Username" required class="w-full p-3 border rounded mb-4">
        <input type="password" name="password" placeholder="Password" required class="w-full p-3 border rounded mb-6">
        <button type="submit" class="w-full bg-indigo-600 text-white p-3 rounded font-semibold hover:bg-indigo-700">Login</button>
    </form>
    <p class="text-center mt-4">Don't have an account? <a href="/register" class="text-indigo-600">Register</a></p>
</div>
{% endblock %}'''

REGISTER_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto bg-white p-8 shadow-lg rounded mt-20">
    <h2 class="text-2xl font-bold mb-6 text-center">Register</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="Username" required class="w-full p-3 border rounded mb-4">
        <input type="password" name="password" placeholder="Password" required class="w-full p-3 border rounded mb-6">
        <button type="submit" class="w-full bg-green-600 text-white p-3 rounded font-semibold hover:bg-green-700">Register</button>
    </form>
    <p class="text-center mt-4">Already registered? <a href="/login" class="text-indigo-600">Login</a></p>
</div>
{% endblock %}'''

DASHBOARD_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">Your Performance Tests</h1>
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    {% for test in tests %}
    <div class="bg-white p-5 rounded shadow">
        <h3 class="font-semibold text-lg">{{ test.original_filename }}</h3>
        <p class="text-sm text-gray-500">{{ test.created_at.strftime('%Y-%m-%d %H:%M') }}</p>
        <span class="inline-block px-2 py-1 mt-2 text-xs font-bold rounded 
            {% if test.status == 'completed' %}bg-green-200 text-green-800
            {% elif test.status == 'running' %}bg-blue-200 text-blue-800 animate-pulse
            {% elif test.status == 'failed' %}bg-red-200 text-red-800
            {% else %}bg-gray-200 text-gray-800{% endif %}">
            {{ test.status }}
        </span>
        <div class="mt-4 space-x-2">
            <a href="/test/{{ test.id }}" class="text-indigo-600 hover:underline">Live Log</a>
            {% if test.status == 'completed' %}
            <a href="/test/{{ test.id }}/report" class="text-green-600 hover:underline" target="_blank">View Report</a>
            {% endif %}
        </div>
    </div>
    {% else %}
    <p class="text-gray-600">No tests yet. <a href="/upload" class="text-indigo-600 underline">Upload a JMX file</a> to start.</p>
    {% endfor %}
</div>
{% endblock %}'''

UPLOAD_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<div class="max-w-xl mx-auto bg-white p-8 shadow-lg rounded mt-10">
    <h2 class="text-2xl font-bold mb-4">Upload JMeter Test Plan</h2>
    <p class="text-gray-600 mb-6">Choose a .jmx file. It will be executed on the server and you'll get the full dashboard.</p>
    <form method="POST" enctype="multipart/form-data">
        <label class="block mb-2 font-semibold">JMX File</label>
        <input type="file" name="jmx_file" accept=".jmx" required class="w-full p-3 border rounded mb-6">
        <button type="submit" class="w-full bg-indigo-600 text-white p-3 rounded font-semibold hover:bg-indigo-700">Upload & Run</button>
    </form>
</div>
{% endblock %}'''

TEST_STATUS_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<div class="bg-white p-6 shadow rounded">
    <h2 class="text-2xl font-bold mb-2">Test: {{ test.original_filename }}</h2>
    <p>Status: <span id="statusBadge" class="font-bold px-2 py-1 rounded 
        {% if test.status == 'running' %}bg-blue-200 text-blue-800 animate-pulse
        {% elif test.status == 'completed' %}bg-green-200 text-green-800
        {% elif test.status == 'failed' %}bg-red-200 text-red-800
        {% else %}bg-gray-200 text-gray-800{% endif %}">
        {{ test.status }}
    </span></p>
    <div class="mt-6 bg-gray-900 text-green-400 p-4 rounded h-80 overflow-y-auto font-mono text-sm" id="logArea">
    </div>
    <div class="mt-4">
        <a href="/dashboard" class="text-indigo-600 underline">Back to Dashboard</a>
        {% if test.status == 'completed' %}
        <a href="/test/{{ test.id }}/report" class="ml-4 bg-green-600 text-white px-4 py-2 rounded" target="_blank">View HTML Report</a>
        {% endif %}
    </div>
</div>
<script src="https://cdn.socket.io/4.4.1/socket.io.min.js"></script>
<script>
    const socket = io("/test");
    const testId = {{ test.id }};
    socket.emit('join_room', { test_id: testId });
    const logArea = document.getElementById('logArea');
    const statusBadge = document.getElementById('statusBadge');
    socket.on('log_output', function(msg) {
        logArea.innerHTML += '<div>' + msg.data + '</div>';
        logArea.scrollTop = logArea.scrollHeight;
    });
    socket.on('test_complete', function(data) {
        if (data.status === 'completed') {
            statusBadge.className = 'font-bold px-2 py-1 rounded bg-green-200 text-green-800';
            statusBadge.textContent = 'completed';
        } else {
            statusBadge.className = 'font-bold px-2 py-1 rounded bg-red-200 text-red-800';
            statusBadge.textContent = 'failed';
        }
    });
</script>
{% endblock %}'''

LIGHTHOUSE_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<div class="max-w-xl mx-auto bg-white p-8 shadow rounded">
    <h2 class="text-2xl font-bold mb-4">Lighthouse Performance Audit</h2>
    <form method="POST">
        <input type="url" name="url" placeholder="https://example.com" required class="w-full p-3 border rounded mb-4">
        <button type="submit" class="w-full bg-orange-500 text-white p-3 rounded font-semibold hover:bg-orange-600">Run Audit</button>
    </form>
    {% if report_file %}
    <div class="mt-6 p-4 bg-green-50 border border-green-200 rounded">
        <p class="text-green-800 font-semibold">Audit completed for <span class="underline">{{ url }}</span></p>
        <a href="/lighthouse/report/{{ report_file }}" target="_blank" class="mt-2 inline-block bg-green-600 text-white px-4 py-2 rounded">Open Full Report</a>
    </div>
    {% endif %}
</div>
{% endblock %}'''

TOOLS_TEMPLATE = r'''{% extends "base.html" %}
{% block content %}
<h1 class="text-3xl font-bold mb-8">Performance Testing Tools</h1>
<div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <div class="bg-white p-6 rounded shadow"><h3 class="text-xl font-bold mb-2">Apache JMeter</h3><p class="text-gray-600">Open-source load testing tool for web apps. Supports full protocol simulation and distributed testing.</p></div>
    <div class="bg-white p-6 rounded shadow"><h3 class="text-xl font-bold mb-2">LoadRunner</h3><p class="text-gray-600">Enterprise performance testing suite by Micro Focus. Supports numerous protocols.</p></div>
    <div class="bg-white p-6 rounded shadow"><h3 class="text-xl font-bold mb-2">BlazeMeter</h3><p class="text-gray-600">Cloud-based continuous testing platform, JMeter-compatible, with huge scalability.</p></div>
    <div class="bg-white p-6 rounded shadow"><h3 class="text-xl font-bold mb-2">k6</h3><p class="text-gray-600">Modern open-source tool, scriptable in JavaScript, perfect for DevOps and CI/CD.</p></div>
    <div class="bg-white p-6 rounded shadow"><h3 class="text-xl font-bold mb-2">Gatling</h3><p class="text-gray-600">High-performance load testing tool written in Scala, with powerful DSL and HTML reports.</p></div>
    <div class="bg-white p-6 rounded shadow"><h3 class="text-xl font-bold mb-2">Google Lighthouse</h3><p class="text-gray-600">Automated auditing for performance, accessibility, SEO – essential for frontend.</p></div>
</div>
{% endblock %}'''

LOGO_SVG = r'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="%234F46E5" stroke-width="4">
    <circle cx="32" cy="32" r="28"/><path d="M32 8 v12 M32 44 v12 M8 32 h12 M44 32 h12 M10.5 10.5 l8.5 8.5 M45 19 l8.5-8.5 M10.5 53.5 l8.5-8.5 M45 45 l8.5 8.5"/>
</svg>'''

# ---------- Models ----------
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    def is_active(self): return True
    def get_id(self): return str(self.id)

class TestRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(300))
    original_filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='queued')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    report_path = db.Column(db.String(300))

# ---------- App init ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['REPORT_FOLDER'] = 'reports'
app.config['LIGHTHOUSE_FOLDER'] = 'lighthouse_reports'
db.init_app(app)

# Jinja2 loader with all templates + logo
TEMPLATES = {
    'base.html': BASE_TEMPLATE.replace('{{ logo_svg }}', LOGO_SVG),
    'login.html': LOGIN_TEMPLATE,
    'register.html': REGISTER_TEMPLATE,
    'dashboard.html': DASHBOARD_TEMPLATE,
    'upload.html': UPLOAD_TEMPLATE,
    'test_status.html': TEST_STATUS_TEMPLATE,
    'lighthouse.html': LIGHTHOUSE_TEMPLATE,
    'tools.html': TOOLS_TEMPLATE,
}
app.jinja_loader = DictLoader(TEMPLATES)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app, async_mode='eventlet')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['REPORT_FOLDER'], exist_ok=True)
os.makedirs(app.config['LIGHTHOUSE_FOLDER'], exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ---------- Background runner ----------
def run_jmeter_thread(test_run_id, jmx_path, report_folder):
    with app.app_context():
        test = db.session.get(TestRun, test_run_id)
        if not test: return
        test.status = 'running'
        db.session.commit()
        cmd = ['jmeter', '-n', '-t', jmx_path, '-l', os.path.join(report_folder, 'result.jtl'), '-e', '-o', report_folder]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in iter(proc.stdout.readline, ''):
                socketio.emit('log_output', {'data': line.strip()}, room=str(test_run_id))
            proc.wait()
            test.status = 'completed' if proc.returncode == 0 else 'failed'
        except Exception as e:
            test.status = 'failed'
            socketio.emit('log_output', {'data': f'Error: {str(e)}'}, room=str(test_run_id))
        finally:
            db.session.commit()
            socketio.emit('test_complete', {'status': test.status}, room=str(test_run_id))

# ---------- Routes ----------
@app.route('/')
@login_required
def index(): return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists')
            return render_template('register.html')
        user = User(username=request.form['username'], password_hash=generate_password_hash(request.form['password']))
        db.session.add(user); db.session.commit()
        flash('Registration successful, please login')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    tests = TestRun.query.filter_by(user_id=current_user.id).order_by(TestRun.created_at.desc()).all()
    return render_template('dashboard.html', tests=tests)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files.get('jmx_file')
        if not file or file.filename == '': flash('No file'); return redirect(request.url)
        fname = secure_filename(file.filename)
        uname = f"{uuid.uuid4()}_{fname}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], uname)
        file.save(upload_path)
        report_folder_name = f"report_{uuid.uuid4().hex}"
        report_path = os.path.join(app.config['REPORT_FOLDER'], report_folder_name)
        test_run = TestRun(user_id=current_user.id, filename=uname, original_filename=fname, status='queued', report_path=report_folder_name)
        db.session.add(test_run); db.session.commit()
        threading.Thread(target=run_jmeter_thread, args=(test_run.id, upload_path, report_path), daemon=True).start()
        return redirect(url_for('test_status', test_id=test_run.id))
    return render_template('upload.html')

@app.route('/test/<int:test_id>')
@login_required
def test_status(test_id):
    test = db.session.get(TestRun, test_id)
    if not test or test.user_id != current_user.id: flash('Not found'); return redirect(url_for('dashboard'))
    return render_template('test_status.html', test=test)

@app.route('/test/<int:test_id>/report')
@login_required
def view_report(test_id):
    test = db.session.get(TestRun, test_id)
    if not test or test.user_id != current_user.id: flash('Not found'); return redirect(url_for('dashboard'))
    if test.status != 'completed': flash('Report not ready'); return redirect(url_for('test_status', test_id=test.id))
    return send_from_directory(os.path.join(app.config['REPORT_FOLDER'], test.report_path), 'index.html')

@app.route('/lighthouse', methods=['GET', 'POST'])
@login_required
def lighthouse():
    report_file = None
    url = ''
    if request.method == 'POST':
        url = request.form.get('url').strip()
        if not url: flash('Enter URL'); return redirect(request.url)
        report_id = uuid.uuid4().hex
        output_path = os.path.join(app.config['LIGHTHOUSE_FOLDER'], f'{report_id}.html')
        cmd = ['lighthouse', url, '--output', 'html', '--output-path', output_path, '--chrome-flags="--headless"']
        try:
            subprocess.run(cmd, check=True, timeout=120)
            flash('Lighthouse audit completed')
            report_file = report_id + '.html'
        except subprocess.CalledProcessError:
            flash('Lighthouse failed. Make sure Node.js and Lighthouse are installed.')
        except subprocess.TimeoutExpired:
            flash('Audit timed out')
    return render_template('lighthouse.html', report_file=report_file, url=url)

@app.route('/lighthouse/report/<filename>')
@login_required
def lighthouse_report(filename):
    return send_from_directory(app.config['LIGHTHOUSE_FOLDER'], filename)

@app.route('/tools')
@login_required
def tools():
    return render_template('tools.html')

@socketio.on('join_room', namespace='/test')
def handle_join(data):
    join_room(str(data['test_id']))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)