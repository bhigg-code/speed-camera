from flask import Flask, render_template_string, request, redirect, url_for, session, send_from_directory, jsonify
from functools import wraps
import csv
import json
from pathlib import Path
from collections import defaultdict
import os

app = Flask(__name__)
# Security: File upload validation
ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov'}
def allowed_file(filename):
    return filename and '.' in filename and filename.rsplit('.', 1)[1].lower() in {'mp4', 'avi', 'mov'}

app.secret_key = os.environ.get('FLASK_SECRET_KEY', '97098d697ce1418735afe94db89e41e38301b515bc419ee510ca0cf8db9dd911')

PASSWORD = os.environ.get('SPEED_CAMERA_PASSWORD', 'UmbrellaSpeed2026!')
CONFIG_FILE = Path('C:/speedcamera/config.json')
LOG_FILE = Path('C:/speedcamera/vehicle_log.csv')
CAPTURES_DIR = Path('C:/speedcamera/captures')

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        error = 'Invalid password'
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Speed Camera Login</title></head>
    <body style="background:#1a1a2e;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;">
        <div style="background:rgba(255,255,255,0.1);padding:40px;border-radius:15px;text-align:center;">
            <h2>🚗 Speed Camera</h2>
            <form method="post">
                <input type="password" name="password" placeholder="Password" style="padding:15px;border:none;border-radius:8px;width:100%;margin:10px 0;background:rgba(255,255,255,0.1);color:#fff;">
                <button type="submit" style="padding:15px;width:100%;border:none;border-radius:8px;background:#e94560;color:#fff;cursor:pointer;">Login</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    config = load_config()
    message = None
    message_type = None
    
    if request.method == 'POST':
        try:
            # Update config values
            config['speed_threshold_mph'] = float(request.form.get('speed_threshold', 35))
            config['pixels_per_foot'] = float(request.form.get('pixels_per_foot', 31.94))
            config['compliance_speed_mph'] = float(request.form.get('compliance_speed', 25))
            config['confidence_threshold'] = float(request.form.get('confidence', 0.5))
            
            # Optional: calibration distance for easy recalibration
            if request.form.get('calibration_distance'):
                config['calibration_distance_ft'] = float(request.form.get('calibration_distance'))
            
            if request.form.get('calibration_note'):
                config['calibration_note'] = request.form.get('calibration_note')
            
            save_config(config)
            message = "✅ Configuration saved! The speed camera will pick up changes within 60 seconds."
            message_type = "success"
        except Exception as e:
            message = f"❌ Error saving config: {str(e)}"
            message_type = "error"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Speed Camera Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; }}
            body {{ background: linear-gradient(135deg,#0f0c29,#302b63,#24243e); color: #fff; font-family: -apple-system, sans-serif; margin: 0; min-height: 100vh; }}
            .nav {{ background: rgba(0,0,0,0.4); padding: 15px 25px; display: flex; gap: 20px; align-items: center; border-bottom: 2px solid #ff6b6b; }}
            .nav a {{ color: #888; text-decoration: none; padding: 8px 15px; border-radius: 5px; }}
            .nav a:hover {{ background: rgba(255,255,255,0.1); color: #fff; }}
            .nav a.active {{ background: #ff6b6b; color: #fff; }}
            .container {{ max-width: 800px; margin: 30px auto; padding: 0 20px; }}
            h1 {{ color: #ff6b6b; margin-bottom: 10px; }}
            .card {{ background: rgba(0,0,0,0.3); border-radius: 15px; padding: 25px; margin-bottom: 20px; }}
            .card h2 {{ color: #feca57; margin-top: 0; font-size: 1.2em; border-bottom: 1px solid #333; padding-bottom: 10px; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 8px; color: #aaa; }}
            input[type="number"], input[type="text"] {{ 
                width: 100%; padding: 12px; border: none; border-radius: 8px; 
                background: rgba(255,255,255,0.1); color: #fff; font-size: 1em;
            }}
            input:focus {{ outline: 2px solid #ff6b6b; }}
            .hint {{ font-size: 0.85em; color: #666; margin-top: 5px; }}
            button {{ 
                padding: 15px 30px; border: none; border-radius: 8px; 
                background: linear-gradient(90deg, #ff6b6b, #ee5a5a); 
                color: #fff; font-size: 1.1em; cursor: pointer; margin-top: 10px;
            }}
            button:hover {{ transform: scale(1.02); }}
            .message {{ padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
            .message.success {{ background: rgba(46, 204, 113, 0.2); border: 1px solid #2ecc71; }}
            .message.error {{ background: rgba(255, 68, 68, 0.2); border: 1px solid #ff4444; }}
            .current-value {{ color: #ff6b6b; font-weight: bold; }}
            .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            @media (max-width: 600px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/">📊 Dashboard</a>
            <a href="/admin" class="active">⚙️ Admin</a>
            <a href="/logout" style="margin-left:auto;">🚪 Logout</a>
        </div>
        
        <div class="container">
            <h1>⚙️ Speed Camera Configuration</h1>
            <p style="color:#888;">Changes are saved to config and picked up automatically by the detection service.</p>
            
            {f'<div class="message {message_type}">{message}</div>' if message else ''}
            
            <form method="post">
                <div class="card">
                    <h2>🚨 Speed Thresholds</h2>
                    <div class="two-col">
                        <div class="form-group">
                            <label>Photo Capture Threshold (mph)</label>
                            <input type="number" name="speed_threshold" value="{config.get('speed_threshold_mph', 35)}" step="1" min="1" max="100">
                            <div class="hint">Vehicles above this speed will trigger a photo + Telegram alert</div>
                        </div>
                        <div class="form-group">
                            <label>Compliance Speed (mph)</label>
                            <input type="number" name="compliance_speed" value="{config.get('compliance_speed_mph', 25)}" step="1" min="1" max="100">
                            <div class="hint">Used for dashboard statistics - "speeders" count on website</div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>📏 Calibration Settings</h2>
                    <div class="two-col">
                        <div class="form-group">
                            <label>Pixels Per Foot</label>
                            <input type="number" name="pixels_per_foot" value="{config.get('pixels_per_foot', 31.94)}" step="0.01" min="1" max="200">
                            <div class="hint">Current: <span class="current-value">{config.get('pixels_per_foot', 31.94)}</span> - Higher = slower speeds reported</div>
                        </div>
                        <div class="form-group">
                            <label>Calibration Distance (ft) - Optional</label>
                            <input type="number" name="calibration_distance" value="{config.get('calibration_distance_ft', '')}" step="0.1" min="1" max="500" placeholder="e.g., 50">
                            <div class="hint">Reference distance for future recalibration</div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Calibration Notes</label>
                        <input type="text" name="calibration_note" value="{config.get('calibration_note', '')}" placeholder="e.g., Based on test drive at 25mph">
                        <div class="hint">Notes about how calibration was determined</div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>🎯 Detection Settings</h2>
                    <div class="form-group">
                        <label>Detection Confidence (0.1 - 1.0)</label>
                        <input type="number" name="confidence" value="{config.get('confidence_threshold', 0.5)}" step="0.05" min="0.1" max="1.0">
                        <div class="hint">Higher = fewer false detections but may miss some vehicles. Default: 0.5</div>
                    </div>
                </div>
                
                <button type="submit">💾 Save Configuration</button>
            </form>

            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; margin-top: 20px; text-align: center;">
                <h3 style="margin: 0 0 10px 0;">📹 Video Analysis</h3>
                <p style="margin: 0 0 15px 0; opacity: 0.9;">Upload recorded videos to analyze vehicle speeds</p>
                <a href="/admin/video-upload" style="background: white; color: #667eea; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">🎬 Analyze Video</a>
            </div>

            
            <div class="card" style="margin-top:30px;">
                <h2>📋 Current Config (Raw)</h2>
                <pre style="background:rgba(0,0,0,0.3);padding:15px;border-radius:8px;overflow-x:auto;font-size:0.9em;">{json.dumps(config, indent=2)}</pre>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/api/config')
def api_config():
    """API endpoint for the speed camera service to fetch config"""
    return jsonify(load_config())

@app.route('/')
@login_required
def dashboard():
    config = load_config()
    SPEED_THRESHOLD = config.get('compliance_speed_mph', 25)
    
    stats = {'total': 0, 'speeders': 0, 'avg_speed': '0', 'avg_speeder': '0', 'compliance': 100}
    top_speeders = []
    recent = []
    captures = []
    speeds = []
    speeder_speeds = []
    all_rows = []
    
    if LOG_FILE.exists():
        with open(LOG_FILE, 'r') as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
            stats['total'] = len(all_rows)
            
            for row in all_rows:
                speed = float(row['speed_mph'])
                speeds.append(speed)
                if speed > SPEED_THRESHOLD:
                    stats['speeders'] += 1
                    speeder_speeds.append(speed)
            
            if speeds:
                stats['avg_speed'] = f"{sum(speeds)/len(speeds):.1f}"
                stats['compliance'] = int(((stats['total'] - stats['speeders']) / stats['total']) * 100) if stats['total'] > 0 else 100
            
            if speeder_speeds:
                stats['avg_speeder'] = f"{sum(speeder_speeds)/len(speeder_speeds):.1f}"
            
            # Top 10 fastest (speeders only)
            speeder_rows = [r for r in all_rows if float(r['speed_mph']) > SPEED_THRESHOLD]
            sorted_rows = sorted(speeder_rows, key=lambda x: float(x['speed_mph']), reverse=True)[:10]
            for i, row in enumerate(sorted_rows):
                top_speeders.append({
                    'rank': i + 1,
                    'speed': f"{float(row['speed_mph']):.1f}",
                    'type': row['vehicle_type'].upper(),
                    'time': row['time'],
                    'date': row['date']
                })
            
            # Recent
            for row in reversed(all_rows[-15:]):
                speed = float(row['speed_mph'])
                recent.append({
                    'time': row['time'],
                    'type': row['vehicle_type'].upper(),
                    'speed': f"{speed:.1f}",
                    'speeding': speed > SPEED_THRESHOLD
                })
    
    # Captures
    if CAPTURES_DIR.exists():
        for f in sorted(CAPTURES_DIR.glob('speeder_*.jpg'), reverse=True)[:12]:
            parts = f.stem.split('_')
            if len(parts) >= 4:
                captures.append({'filename': f.name, 'speed': parts[-1].replace('mph', '')})
    
    # Build HTML
    top_html = ""
    for t in top_speeders:
        top_html += f'<div style="display:flex;padding:12px;border-bottom:1px solid #333;align-items:center;"><span style="width:40px;color:#ff6b6b;font-weight:bold;">#{t["rank"]}</span><span style="flex:1;">{t["type"]} • {t["date"]} @ {t["time"]}</span><span style="color:#ff6b6b;font-weight:bold;font-size:1.2em;">{t["speed"]} mph</span></div>'
    
    recent_html = ""
    for r in recent:
        color = "#ff4444" if r['speeding'] else "#2ecc71"
        status = "🚨" if r['speeding'] else "✅"
        recent_html += f'<tr><td>{r["time"]}</td><td>{r["type"]}</td><td style="color:{color};">{r["speed"]} mph</td><td>{status}</td></tr>'
    
    gallery_html = ""
    for c in captures:
        gallery_html += f'<div style="background:#222;border-radius:10px;overflow:hidden;"><a href="/captures/{c["filename"]}" target="_blank"><img src="/captures/{c["filename"]}" style="width:100%;"></a><div style="padding:10px;color:#ff4444;font-weight:bold;">{c["speed"]} mph</div></div>'
    
    photo_threshold = config.get('speed_threshold_mph', 35)
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Speed Camera Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="60">
        <style>
            .nav {{ background: rgba(0,0,0,0.4); padding: 15px 25px; display: flex; gap: 20px; align-items: center; border-bottom: 2px solid #ff6b6b; }}
            .nav a {{ color: #888; text-decoration: none; padding: 8px 15px; border-radius: 5px; }}
            .nav a:hover {{ background: rgba(255,255,255,0.1); color: #fff; }}
            .nav a.active {{ background: #ff6b6b; color: #fff; }}
        </style>
    </head>
    <body style="background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:#fff;font-family:-apple-system,sans-serif;margin:0;min-height:100vh;">
        <div class="nav">
            <a href="/" class="active">📊 Dashboard</a>
            <a href="/admin">⚙️ Admin</a>
            <a href="/logout" style="margin-left:auto;">🚪 Logout</a>
        </div>
        
        <div style="background:rgba(0,0,0,0.4);padding:25px;text-align:center;">
            <h1 style="font-size:2.5em;color:#ff6b6b;margin:0;">🚗 SPEED CAMERA</h1>
            <p style="color:#888;">Neighborhood Traffic Monitor</p>
            <span style="background:#ff4444;padding:5px 15px;border-radius:20px;font-size:0.8em;">🔴 LIVE</span>
            <div style="margin-top:10px;color:#666;font-size:0.9em;">
                Compliance: >{SPEED_THRESHOLD}mph | Photo alert: >{photo_threshold}mph
            </div>
        </div>
        
        <div style="display:flex;justify-content:center;gap:20px;padding:30px;flex-wrap:wrap;">
            <div style="background:rgba(255,255,255,0.1);padding:25px 35px;border-radius:15px;text-align:center;">
                <div style="font-size:2.5em;font-weight:bold;color:#ff6b6b;">{stats['total']}</div>
                <div style="color:#888;">Total Vehicles</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);padding:25px 35px;border-radius:15px;text-align:center;">
                <div style="font-size:2.5em;font-weight:bold;color:#ff4444;">{stats['speeders']}</div>
                <div style="color:#888;">Speeders (&gt;{SPEED_THRESHOLD}mph)</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);padding:25px 35px;border-radius:15px;text-align:center;">
                <div style="font-size:2.5em;font-weight:bold;color:#feca57;">{stats['avg_speed']}</div>
                <div style="color:#888;">Avg Speed (mph)</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);padding:25px 35px;border-radius:15px;text-align:center;">
                <div style="font-size:2.5em;font-weight:bold;color:#ff9f43;">{stats['avg_speeder']}</div>
                <div style="color:#888;">Avg Speeder (mph)</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);padding:25px 35px;border-radius:15px;text-align:center;">
                <div style="font-size:2.5em;font-weight:bold;color:#2ecc71;">{stats['compliance']}%</div>
                <div style="color:#888;">Compliance</div>
            </div>
        </div>
        
        <div style="margin:20px;background:rgba(0,0,0,0.3);border-radius:15px;overflow:hidden;">
            <div style="padding:20px;font-size:1.3em;background:rgba(255,107,107,0.2);border-bottom:2px solid rgba(255,107,107,0.3);">🏆 Top 10 Fastest</div>
            {top_html if top_html else '<div style="padding:40px;text-align:center;color:#666;">😇 No speeders recorded yet</div>'}
        </div>
        
        <div style="margin:20px;background:rgba(0,0,0,0.3);border-radius:15px;overflow:hidden;">
            <div style="padding:20px;font-size:1.3em;background:rgba(255,107,107,0.2);border-bottom:2px solid rgba(255,107,107,0.3);">📸 Speeder Photos</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:15px;padding:15px;">
                {gallery_html if gallery_html else '<div style="padding:40px;text-align:center;color:#666;grid-column:1/-1;">✅ No speeder photos yet</div>'}
            </div>
        </div>
        
        <div style="margin:20px;background:rgba(0,0,0,0.3);border-radius:15px;overflow:hidden;">
            <div style="padding:20px;font-size:1.3em;background:rgba(255,107,107,0.2);border-bottom:2px solid rgba(255,107,107,0.3);">📋 Recent Vehicles</div>
            <table style="width:100%;border-collapse:collapse;">
                <tr style="background:rgba(0,0,0,0.3);"><th style="padding:12px;text-align:left;color:#ff6b6b;">Time</th><th style="padding:12px;text-align:left;color:#ff6b6b;">Type</th><th style="padding:12px;text-align:left;color:#ff6b6b;">Speed</th><th style="padding:12px;text-align:left;color:#ff6b6b;">Status</th></tr>
                {recent_html}
            </table>
        </div>
        
        <div style="text-align:center;padding:30px;color:#555;">Auto-refreshes every 60 seconds</div>
    </body>
    </html>
    '''

@app.route('/captures/<filename>')
@login_required
def serve_capture(filename):
    return send_from_directory(CAPTURES_DIR, filename)


# Video Upload Feature - Added by OpenClaw


@app.route('/admin/video-process', methods=['POST'])
@login_required
def video_process():
    import os
    import uuid
    import threading
    from pathlib import Path
    
    if 'video' not in request.files:
        return "No video file provided", 400
    
    video_file = request.files['video']
    if video_file.filename == '':
        return "No video file selected", 400
    
    # Get threshold from form
    threshold = int(request.form.get('threshold', 35))
    
    # Save uploaded file
    upload_dir = Path('C:/speedcamera/uploads')
    upload_dir.mkdir(exist_ok=True)
    
    # Generate unique filename
    file_ext = os.path.splitext(video_file.filename)[1]
    job_id = str(uuid.uuid4())[:8]
    video_path = upload_dir / f"video_{job_id}{file_ext}"
    video_file.save(str(video_path))
    
    # Run the video analysis
    try:
        from video_speed_processor import VideoSpeedProcessor
        
        processor = VideoSpeedProcessor()
        processor.config['speed_threshold_mph'] = threshold
        
        results = processor.process_video(str(video_path))
        
        if results['error']:
            return f"""<!DOCTYPE html>
<html><head><title>Error - Speed Camera</title>
<style>body{{font-family:Arial;background:#1a1a1a;color:white;margin:20px;text-align:center}}
.error{{background:#f44336;padding:20px;border-radius:10px;margin:20px auto;max-width:600px}}
a{{color:#4fc3f7}}</style></head>
<body><div class="error"><h2>❌ Processing Error</h2><p>{results['error']}</p></div>
<a href="/admin/video-upload">Try Again</a></body></html>"""
        
        # Build results HTML
        vehicles_html = ""
        for v in results['vehicles_detected']:
            status = "🚨 SPEEDING" if v['is_speeding'] else "✅ Legal"
            color = "#ff6b6b" if v['is_speeding'] else "#4caf50"
            vehicles_html += f'<tr style="border-bottom:1px solid #333"><td>{v["timestamp"]:.1f}s</td><td>{v["type"].upper()}</td><td style="color:{color};font-weight:bold">{v["speed_mph"]} mph</td><td>{status}</td></tr>'
        
        if not vehicles_html:
            vehicles_html = '<tr><td colspan="4">No vehicles detected in video</td></tr>'
        
        proc_info = results.get('processing_info', {})
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Video Analysis Results - Speed Camera</title>
    <style>
        body {{ font-family: Arial; background: #1a1a1a; color: white; margin: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
        .stat {{ background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #ff6b6b; }}
        .results-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .results-table th {{ background: #ff6b6b; padding: 12px; text-align: left; }}
        .results-table td {{ padding: 12px; }}
        a {{ color: #4fc3f7; }}
        .btn {{ background: #ff6b6b; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 5px; }}
        .success {{ background: #4caf50; padding: 15px; border-radius: 10px; margin: 20px 0; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Video Analysis Results</h1>
        <div class="success">✅ Analysis Complete!</div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{results['total_vehicles']}</div>
                <div>Total Vehicles</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color:#ff6b6b">{results['speeders']}</div>
                <div>Speeders (>{threshold} mph)</div>
            </div>
            <div class="stat">
                <div class="stat-value">{proc_info.get('avg_speed', 'N/A')}</div>
                <div>Avg Speed (mph)</div>
            </div>
            <div class="stat">
                <div class="stat-value">{proc_info.get('max_speed', 'N/A')}</div>
                <div>Top Speed (mph)</div>
            </div>
        </div>
        
        <h3>🚗 Detected Vehicles</h3>
        <table class="results-table">
            <tr><th>Time</th><th>Type</th><th>Speed</th><th>Direction</th><th>Status</th></tr>
            {vehicles_html}
        </table>
        
        <p><strong>Video:</strong> {video_file.filename}</p>
        <p><strong>Duration:</strong> {proc_info.get('duration_seconds', 'N/A')} seconds</p>
        <p><strong>Resolution:</strong> {proc_info.get('resolution', 'N/A')}</p>
        
        <a href="/admin/video-upload" class="btn">📤 Upload Another Video</a>
        <a href="/admin" class="btn">⚙️ Back to Admin</a>
    </div>
</body>
</html>"""
        
    except ImportError as e:
        return f"""<!DOCTYPE html>
<html><head><title>Setup Required</title>
<style>body{{font-family:Arial;background:#1a1a1a;color:white;margin:20px;text-align:center}}
.info{{background:rgba(255,255,255,0.1);padding:20px;border-radius:10px;margin:20px auto;max-width:600px}}
a{{color:#4fc3f7}}</style></head>
<body><div class="info"><h2>⚠️ Video Processor Not Found</h2>
<p>The video_speed_processor.py module needs to be in the speedcamera directory.</p>
<p>Error: {e}</p></div>
<p>File was saved to: {video_path}</p>
<a href="/admin/video-upload">Back</a></body></html>"""
    except Exception as e:
        return f"""<!DOCTYPE html>
<html><head><title>Error</title>
<style>body{{font-family:Arial;background:#1a1a1a;color:white;margin:20px;text-align:center}}
.error{{background:#f44336;padding:20px;border-radius:10px;margin:20px auto;max-width:600px}}
a{{color:#4fc3f7}}</style></head>
<body><div class="error"><h2>❌ Processing Error</h2><p>{str(e)}</p></div>
<p>File was saved to: {video_path}</p>
<a href="/admin/video-upload">Try Again</a></body></html>"""


@app.route('/admin/video-upload')
@login_required
def video_upload():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Video Speed Analysis</title>
    <style>
        body { font-family: Arial; background: #1a1a1a; color: white; margin: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .upload-section { background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; }
        input[type="file"] { padding: 10px; background: rgba(255,255,255,0.2); color: white; border: none; border-radius: 5px; width: 400px; }
        button { background: #ff6b6b; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; color: #ff6b6b; }
        a { color: #4fc3f7; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Video Speed Analysis</h1>
        <p><a href="/admin">Back to Admin Panel</a></p>
        <div class="upload-section">
            <h3>Upload Video for Analysis</h3>
            <form enctype="multipart/form-data" method="post" action="/admin/video-process">
                <div class="form-group">
                    <label>Select Video File:</label>
                    <input type="file" name="video" accept=".mp4,.avi,.mov" required>
                </div>
                <div class="form-group">
                    <label>Speed Threshold (mph):</label>
                    <input type="number" name="threshold" value="35" min="1" max="100">
                </div>
                <button type="submit">Upload and Analyze Video</button>
            </form>
            <div style="margin-top:20px;color:#ccc">
                <p><strong>Features:</strong></p>
                <ul>
                    <li>Same AI detection as live speed camera</li>
                    <li>Uses existing GTX 1080 GPU</li>
                    <li>Same calibration (31.94 pixels/foot)</li>
                    <li>Configurable speed threshold</li>
                </ul>
            </div>
        </div>
    </div>
</body>
</html>"""


if __name__ == '__main__':
    print("Starting Speed Camera Web Dashboard with Admin on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
