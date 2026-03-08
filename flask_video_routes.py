"""
Integration code to add video upload feature to existing speed camera Flask app
Add this code to your existing web.py or main Flask application
"""

# Add these imports to your existing Flask app
import os
import json
import uuid
import threading
import tempfile
from pathlib import Path
from flask import request, render_template_string, jsonify, send_file, flash
from video_speed_processor import VideoSpeedProcessor, process_uploaded_video

# Global dictionary to track processing jobs (add this to your existing globals)
processing_jobs = {}

# Add this to your existing admin page HTML template
ADMIN_PAGE_VIDEO_BUTTON = '''
<!-- Add this button to your existing admin page -->
<div class="admin-section">
    <h3>📹 Video Analysis</h3>
    <p>Upload recorded videos to analyze vehicle speeds and generate violation evidence.</p>
    <a href="/admin/video-upload" class="admin-button">🎬 Video Speed Analysis</a>
</div>
'''

# ADD THESE ROUTES TO YOUR EXISTING FLASK APP:

@app.route('/admin/video-upload')
@login_required  # Use your existing login decorator
def video_upload_page():
    """Video upload and processing interface"""
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Video Speed Analysis - Speed Camera Admin</title>
    <style>
        /* Use your existing CSS styling - this matches your current admin theme */
        body { 
            font-family: Arial; 
            background: #1a1a1a; 
            color: white; 
            margin: 20px;
        }
        .container { 
            max-width: 1000px; 
            margin: 0 auto; 
        }
        .upload-section { 
            background: rgba(255,255,255,0.1); 
            padding: 20px; 
            border-radius: 10px; 
            margin-bottom: 20px; 
        }
        .form-group { 
            margin-bottom: 15px; 
        }
        label { 
            display: block; 
            margin-bottom: 5px; 
            color: #ff6b6b; 
            font-weight: bold;
        }
        input[type="file"], input[type="number"], select { 
            padding: 10px; 
            border-radius: 5px; 
            border: none; 
            background: rgba(255,255,255,0.2); 
            color: white; 
            width: 100%; 
            max-width: 400px;
        }
        button { 
            background: #ff6b6b; 
            color: white; 
            padding: 12px 25px; 
            border: none; 
            border-radius: 5px; 
            cursor: pointer; 
            font-size: 16px; 
            margin-right: 10px;
        }
        button:hover { background: #ff5252; }
        button:disabled { background: #666; cursor: not-allowed; }
        .progress-bar {
            width: 100%;
            background: rgba(255,255,255,0.2);
            border-radius: 5px;
            margin: 10px 0;
            display: none;
        }
        .progress-fill {
            height: 20px;
            background: #4caf50;
            border-radius: 5px;
            width: 0%;
            transition: width 0.3s;
            text-align: center;
            line-height: 20px;
            color: white;
            font-size: 12px;
        }
        .results-section {
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            display: none;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #ff6b6b;
        }
        .vehicle-list {
            max-height: 400px;
            overflow-y: auto;
        }
        .vehicle-item {
            background: rgba(255,255,255,0.1);
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            border-left: 4px solid;
        }
        .vehicle-legal { border-left-color: #4caf50; }
        .vehicle-speeding { border-left-color: #ff6b6b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Video Speed Analysis</h1>
        <p>Upload a video file to analyze vehicle speeds using the same detection system as your live speed camera.</p>
        
        <!-- Back to Admin Link -->
        <div style="margin-bottom: 20px;">
            <a href="/admin" style="color: #4fc3f7; text-decoration: none;">← Back to Admin Panel</a>
        </div>
        
        <div class="upload-section">
            <h3>📤 Upload Video for Analysis</h3>
            <form id="videoUploadForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Select Video File (MP4, AVI, MOV):</label>
                    <input type="file" id="videoFile" name="video" accept=".mp4,.avi,.mov,.mkv" required>
                </div>
                
                <div class="form-group">
                    <label>Speed Threshold (mph):</label>
                    <input type="number" id="speedThreshold" name="speed_threshold" value="35" min="1" max="100">
                    <small style="color: #ccc;">Vehicles above this speed will be flagged as violations</small>
                </div>
                
                <div class="form-group">
                    <label>Detection Confidence:</label>
                    <select id="confidence" name="confidence">
                        <option value="0.3">High Sensitivity (0.3)</option>
                        <option value="0.4" selected>Balanced (0.4)</option>
                        <option value="0.5">High Precision (0.5)</option>
                    </select>
                    <small style="color: #ccc;">Lower values detect more vehicles but may have false positives</small>
                </div>
                
                <button type="submit" id="uploadBtn">🚀 Upload & Analyze Video</button>
                <button type="button" id="cancelBtn" disabled onclick="cancelProcessing()">❌ Cancel</button>
            </form>
            
            <div class="progress-bar" id="progressBar">
                <div class="progress-fill" id="progressFill">0%</div>
            </div>
            
            <div id="statusMessage"></div>
        </div>
        
        <div class="results-section" id="resultsSection">
            <h3>📊 Analysis Results</h3>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="totalVehicles">0</div>
                    <div>Total Vehicles</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="totalSpeeders">0</div>
                    <div>Speeders</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="avgSpeed">0</div>
                    <div>Average Speed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="maxSpeed">0</div>
                    <div>Top Speed</div>
                </div>
            </div>
            
            <h4>🚗 Detected Vehicles</h4>
            <div class="vehicle-list" id="vehicleList"></div>
            
            <div style="margin-top: 20px;">
                <button onclick="downloadResults()" id="downloadBtn">📄 Download Report (JSON)</button>
                <button onclick="downloadAnnotatedVideo()" id="downloadVideoBtn" style="display: none;">🎬 Download Annotated Video</button>
            </div>
        </div>
    </div>

    <script>
        let currentJobId = null;
        let pollInterval = null;
        
        document.getElementById('videoUploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            uploadVideo();
        });
        
        function uploadVideo() {
            const fileInput = document.getElementById('videoFile');
            const file = fileInput.files[0];
            
            if (!file) {
                showStatus('Please select a video file', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('video', file);
            formData.append('speed_threshold', document.getElementById('speedThreshold').value);
            formData.append('confidence', document.getElementById('confidence').value);
            
            document.getElementById('uploadBtn').disabled = true;
            document.getElementById('cancelBtn').disabled = false;
            document.getElementById('progressBar').style.display = 'block';
            
            showStatus('Uploading video...', 'info');
            
            fetch('/admin/video-process', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentJobId = data.job_id;
                    showStatus('Upload successful. Processing video...', 'success');
                    startPolling();
                } else {
                    showStatus('Upload failed: ' + data.error, 'error');
                    resetForm();
                }
            })
            .catch(error => {
                showStatus('Error: ' + error.message, 'error');
                resetForm();
            });
        }
        
        function startPolling() {
            pollInterval = setInterval(checkProgress, 2000);
        }
        
        function checkProgress() {
            if (!currentJobId) return;
            
            fetch(`/admin/video-status/${currentJobId}`)
            .then(response => response.json())
            .then(data => {
                updateProgress(data.progress);
                
                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    showResults(data.results);
                    resetForm();
                    showStatus('Analysis completed successfully!', 'success');
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    showStatus('Processing failed: ' + data.error, 'error');
                    resetForm();
                }
            });
        }
        
        function updateProgress(percent) {
            document.getElementById('progressFill').style.width = percent + '%';
            document.getElementById('progressFill').textContent = Math.round(percent) + '%';
        }
        
        function showResults(results) {
            document.getElementById('resultsSection').style.display = 'block';
            
            document.getElementById('totalVehicles').textContent = results.total_vehicles;
            document.getElementById('totalSpeeders').textContent = results.speeders;
            document.getElementById('avgSpeed').textContent = results.processing_info.avg_speed || 0;
            document.getElementById('maxSpeed').textContent = results.processing_info.max_speed || 0;
            
            const vehicleList = document.getElementById('vehicleList');
            vehicleList.innerHTML = '';
            
            results.vehicles_detected.forEach(vehicle => {
                const vehicleItem = document.createElement('div');
                vehicleItem.className = `vehicle-item ${vehicle.is_speeding ? 'vehicle-speeding' : 'vehicle-legal'}`;
                
                const status = vehicle.is_speeding ? '🚨 SPEEDING' : '✅ Legal';
                const timestamp = formatTime(vehicle.timestamp);
                
                vehicleItem.innerHTML = `
                    <strong>${vehicle.type.toUpperCase()}</strong> - ${vehicle.speed_mph} mph ${status}
                    <br><small>Time: ${timestamp} | Duration: ${vehicle.duration}s</small>
                `;
                
                vehicleList.appendChild(vehicleItem);
            });
            
            if (results.annotated_video_path) {
                document.getElementById('downloadVideoBtn').style.display = 'inline-block';
            }
        }
        
        function formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        }
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('statusMessage');
            statusDiv.innerHTML = `<div style="background: ${type === 'error' ? '#f44336' : type === 'success' ? '#4caf50' : '#2196f3'}; padding: 10px; border-radius: 5px; margin: 10px 0;">${message}</div>`;
        }
        
        function resetForm() {
            document.getElementById('uploadBtn').disabled = false;
            document.getElementById('cancelBtn').disabled = true;
            document.getElementById('progressBar').style.display = 'none';
        }
        
        function cancelProcessing() {
            if (pollInterval) clearInterval(pollInterval);
            resetForm();
            showStatus('Processing cancelled', 'info');
        }
        
        function downloadResults() {
            if (currentJobId) {
                window.open(`/admin/video-download-results/${currentJobId}`, '_blank');
            }
        }
        
        function downloadAnnotatedVideo() {
            if (currentJobId) {
                window.open(`/admin/video-download-annotated/${currentJobId}`, '_blank');
            }
        }
    </script>
</body>
</html>
    """)

@app.route('/admin/video-process', methods=['POST'])
@login_required  # Use your existing login decorator
def process_video():
    """Handle video upload and start processing"""
    try:
        if 'video' not in request.files:
            return jsonify({'success': False, 'error': 'No video file provided'})
        
        video_file = request.files['video']
        if video_file.filename == '':
            return jsonify({'success': False, 'error': 'No video file selected'})
        
        # Create unique job ID
        job_id = str(uuid.uuid4())
        
        # Save to your existing captures directory
        upload_dir = Path('C:/speedcamera/uploads')
        upload_dir.mkdir(exist_ok=True)
        
        file_ext = os.path.splitext(video_file.filename)[1]
        video_path = upload_dir / f"{job_id}{file_ext}"
        video_file.save(str(video_path))
        
        # Use same configuration as your live system
        config = {
            'speed_threshold_mph': float(request.form.get('speed_threshold', 35)),
            'confidence_threshold': float(request.form.get('confidence', 0.4)),
            'pixels_per_foot': 31.94  # Same as your live system
        }
        
        # Initialize job tracking
        processing_jobs[job_id] = {
            'status': 'processing',
            'progress': 0,
            'video_path': str(video_path),
            'config': config,
            'results': None,
            'error': None
        }
        
        # Start processing in background thread
        def process_worker():
            try:
                def progress_callback(percent):
                    processing_jobs[job_id]['progress'] = percent
                
                results = process_uploaded_video(str(video_path), config)
                processing_jobs[job_id]['results'] = results
                processing_jobs[job_id]['status'] = 'completed'
                processing_jobs[job_id]['progress'] = 100
                
            except Exception as e:
                processing_jobs[job_id]['status'] = 'error'
                processing_jobs[job_id]['error'] = str(e)
        
        thread = threading.Thread(target=process_worker)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'job_id': job_id})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/video-status/<job_id>')
@login_required
def video_status(job_id):
    """Get processing status for a job"""
    if job_id not in processing_jobs:
        return jsonify({'status': 'not_found'})
    
    job = processing_jobs[job_id]
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'results': job['results'],
        'error': job['error']
    })

@app.route('/admin/video-download-results/<job_id>')
@login_required
def download_results(job_id):
    """Download processing results as JSON"""
    if job_id not in processing_jobs or not processing_jobs[job_id]['results']:
        return "Results not available", 404
    
    results = processing_jobs[job_id]['results']
    
    # Create temporary file with results
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(results, temp_file, indent=2)
    temp_file.close()
    
    return send_file(temp_file.name, as_attachment=True, 
                    download_name=f'video_analysis_{job_id}.json')

# Add this HTML to your existing admin page template
ADMIN_PAGE_INTEGRATION = '''
<!-- Add this section to your existing admin.html template -->
<div class="admin-section" style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin: 15px 0;">
    <h3 style="color: #ff6b6b;">📹 Video Analysis</h3>
    <p style="color: #ccc;">Upload recorded videos to analyze vehicle speeds and generate violation evidence using the same detection system as your live camera.</p>
    <a href="/admin/video-upload" style="background: #ff6b6b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 10px;">🎬 Analyze Video</a>
</div>
'''

print("=== Integration Instructions ===")
print()
print("1. Add the above routes to your existing Flask app (web.py)")
print("2. Copy video_speed_processor.py to C:/speedcamera/")
print("3. Add the ADMIN_PAGE_INTEGRATION HTML to your admin page template")
print("4. Install: pip install ultralytics")
print("5. Create uploads directory: mkdir C:/speedcamera/uploads")
print()
print("The video feature will integrate seamlessly with your existing:")
print("✅ Same admin interface styling")
print("✅ Same authentication (@login_required)")
print("✅ Same calibration settings (31.94 pixels/foot)")
print("✅ Same YOLO detection system")
print("✅ Same GPU hardware (GTX 1080)")
print()
print("Result: One unified speed camera system with both live and video analysis!")