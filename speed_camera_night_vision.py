"""
Speed Camera Service - Night Vision Enhanced
==========================================

An intelligent speed detection system that automatically adjusts detection parameters
for day and night conditions, optimized for infrared/night vision cameras.

Features:
- Dynamic confidence adjustment (day/night modes)
- IR-optimized image preprocessing
- Automatic mode switching based on time of day
- Enhanced tracking for challenging lighting conditions
- Comprehensive vehicle logging with detection mode tracking

Author: OpenClaw Assistant
License: MIT
"""

import cv2
import numpy as np
import json
import requests
import time
import torch
import csv
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO

# Configuration files - these paths can be customized
CONFIG_FILE = Path('config.json')
LOG_FILE = Path('vehicle_log.csv')
OUTPUT_DIR = Path('captures')
OUTPUT_DIR.mkdir(exist_ok=True)

def log(msg):
    """Log messages with timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def is_night_time():
    """
    Determine if it's night time (IR camera mode)
    Customize these hours based on your local sunset/sunrise times
    """
    hour = datetime.now().hour
    return hour >= 20 or hour <= 6

def get_detection_params():
    """
    Get detection parameters optimized for current lighting conditions
    
    Returns dict with confidence, tracking, and preprocessing settings
    """
    if is_night_time():
        return {
            'confidence': 0.25,        # Lower confidence for IR detection
            'iou_threshold': 0.4,      # Lower IoU for IR tracking
            'track_distance': 400,     # Higher tolerance for IR
            'min_detections': 6,       # Fewer required for IR
            'preprocessing': 'ir'
        }
    else:
        return {
            'confidence': 0.4,         # Standard for daylight
            'iou_threshold': 0.5,      
            'track_distance': 350,
            'min_detections': 8,
            'preprocessing': 'standard'
        }

def preprocess_frame_ir(frame):
    """
    Enhanced preprocessing for infrared/night vision imagery
    
    Applies histogram equalization and gamma correction to improve
    vehicle detection in IR imagery
    """
    # Convert to grayscale for processing
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Histogram equalization for better contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    equalized = clahe.apply(gray)
    
    # Gamma correction for IR imagery
    gamma = 1.5
    lookupTable = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in np.arange(0, 256)]).astype("uint8")
    gamma_corrected = cv2.LUT(equalized, lookupTable)
    
    # Convert back to BGR
    enhanced = cv2.cvtColor(gamma_corrected, cv2.COLOR_GRAY2BGR)
    
    # Blend with original for better detection
    return cv2.addWeighted(frame, 0.6, enhanced, 0.4, 0)

def load_config():
    """Load configuration from JSON file"""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        log(f"Config file {CONFIG_FILE} not found. Please create it with required settings.")
        return {}

def init_csv():
    """Initialize CSV log file with headers"""
    if not LOG_FILE.exists():
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'date', 'time', 'vehicle_type', 'speed_mph', 
                           'speeding', 'track_duration_sec', 'track_points', 'detection_mode'])

def log_vehicle(vehicle_type, speed, track_duration, track_points, threshold, detection_mode):
    """Log detected vehicle to CSV"""
    now = datetime.now()
    speeding = 'YES' if speed > threshold else 'NO'
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            now.isoformat(), now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
            vehicle_type, round(speed, 1), speeding, round(track_duration, 2), 
            track_points, detection_mode
        ])

def send_telegram(config, text=None, photo_path=None):
    """
    Send Telegram notifications (if configured)
    
    Requires config to have:
    - telegram_bot_token
    - telegram_chat_id
    """
    if not config.get('telegram_bot_token') or not config.get('telegram_chat_id'):
        return
    
    try:
        token = config['telegram_bot_token']
        chat_id = config['telegram_chat_id']
        
        if text:
            requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                          data={'chat_id': chat_id, 'text': text}, timeout=10)
        if photo_path and Path(photo_path).exists():
            with open(photo_path, 'rb') as f:
                requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                              data={'chat_id': chat_id}, files={'photo': f}, timeout=30)
    except Exception as e:
        log(f"Telegram notification error: {e}")

def main():
    """Main speed camera detection loop"""
    log("SPEED CAMERA SERVICE - Night Vision Enhanced")
    
    # Load initial configuration
    CONFIG = load_config()
    if not CONFIG:
        log("ERROR: No valid configuration found. Exiting.")
        return
    
    last_config_load = time.time()
    CONFIG_RELOAD_INTERVAL = 60
    
    # Initialize YOLO model
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'
    
    try:
        model = YOLO('yolov8n.pt')
        model.to(device)
    except Exception as e:
        log(f"ERROR: Could not load YOLO model: {e}")
        return
    
    init_csv()
    
    # Startup notification
    mode = "NIGHT" if is_night_time() else "DAY"
    params = get_detection_params()
    log(f"GPU: {gpu_name}")
    log(f"Mode: {mode} (confidence: {params['confidence']})")
    
    send_telegram(CONFIG, 
        f"🟢 Speed Camera Started - {mode} Mode\n\nGPU: {gpu_name}\nDetection: Optimized for {mode.lower()} vision\nConfidence: {params['confidence']}\n\n{'🌙 Night vision enhancements active!' if mode == 'NIGHT' else '☀️ Standard daylight detection active'}")
    
    # Vehicle classification mapping
    vehicle_classes = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
    scale = 0.5  # Resize factor for faster processing
    
    # Statistics
    session_start = datetime.now()
    total_vehicles = 0
    total_speeders = 0
    
    while True:
        try:
            # Connect to camera stream
            camera_url = CONFIG.get('camera_rtsp', 'rtsp://localhost/stream')
            cap = cv2.VideoCapture(camera_url)
            
            if not cap.isOpened():
                log("Camera connection failed, retrying in 30s...")
                time.sleep(30)
                continue
            
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            middle_x_min, middle_x_max = width * 0.25, width * 0.75
            
            log(f"Camera connected: {width}x{height}")
            
            # Initialize tracking
            tracks = {}
            next_id = 0
            captured_ids = set()
            frame_count = 0
            last_mode_check = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    log("Frame read failed, reconnecting...")
                    break
                
                frame_count += 1
                frame_time = time.time()
                
                # Check for day/night mode changes every 5 minutes
                if frame_time - last_mode_check > 300:
                    new_params = get_detection_params()
                    if new_params['confidence'] != params['confidence']:
                        mode = "NIGHT" if is_night_time() else "DAY"
                        params = new_params
                        log(f"🔄 Switched to {mode} mode (confidence: {params['confidence']})")
                    last_mode_check = frame_time
                
                # Reload configuration periodically
                if frame_time - last_config_load > CONFIG_RELOAD_INTERVAL:
                    try:
                        updated_config = load_config()
                        CONFIG.update(updated_config)
                        last_config_load = frame_time
                    except Exception as e:
                        log(f"Config reload error: {e}")
                
                # Get current settings
                PIXELS_PER_FOOT = CONFIG.get('pixels_per_foot', 31.94)
                SPEED_THRESHOLD = CONFIG.get('speed_threshold_mph', 35)
                
                # Skip every other frame for performance
                if frame_count % 2 != 0:
                    continue
                
                # Apply preprocessing based on detection mode
                if params['preprocessing'] == 'ir':
                    processed_frame = preprocess_frame_ir(frame)
                else:
                    processed_frame = frame
                
                # Resize for faster inference
                small = cv2.resize(processed_frame, None, fx=scale, fy=scale)
                
                # Run YOLO detection
                results = model(small, verbose=False, conf=params['confidence'])
                
                # Process detections
                for r in results:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        if cls not in vehicle_classes:
                            continue
                        
                        # Get bounding box coordinates (scaled back up)
                        x1, y1, x2, y2 = [int(c / scale) for c in box.xyxy[0].cpu().numpy()]
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        
                        # Match detection to existing track
                        best_id = None
                        best_dist = params['track_distance']
                        for tid, t in tracks.items():
                            if frame_time - t['last'] > 2.5:
                                continue
                            dist = np.sqrt((cx - t['cx'])**2 + (cy - t['cy'])**2)
                            if dist < best_dist:
                                best_dist = dist
                                best_id = tid
                        
                        # Create new track if no match found
                        if best_id is None:
                            best_id = next_id
                            tracks[best_id] = {
                                'positions': [], 'last': frame_time, 'cx': cx, 'cy': cy,
                                'class': vehicle_classes[cls], 'best_frame': None, 'best_box': None
                            }
                            next_id += 1
                        
                        # Update track
                        t = tracks[best_id]
                        t['positions'].append((cx, cy, frame_time))
                        t['last'] = frame_time
                        t['cx'], t['cy'] = cx, cy
                        
                        # Save best frame when vehicle is in middle of screen
                        if middle_x_min < cx < middle_x_max:
                            t['best_frame'] = frame.copy()  # Use original frame for photos
                            t['best_box'] = (x1, y1, x2, y2)
                
                # Process completed tracks (vehicles that left the frame)
                for tid in list(tracks.keys()):
                    t = tracks[tid]
                    if frame_time - t['last'] > 2.0:  # Track is considered complete
                        positions = t['positions']
                        if len(positions) >= params['min_detections'] and tid not in captured_ids:
                            # Calculate speed
                            total_px = sum(np.sqrt((positions[i][0]-positions[i-1][0])**2 + 
                                          (positions[i][1]-positions[i-1][1])**2) for i in range(1, len(positions)))
                            dt = positions[-1][2] - positions[0][2]
                            
                            if dt > 0.3:  # Minimum track duration
                                # Convert pixel/second to mph
                                speed = (total_px / dt) / PIXELS_PER_FOOT * 0.681818
                                
                                if speed > 5:  # Filter out very slow/stationary objects
                                    captured_ids.add(tid)
                                    total_vehicles += 1
                                    
                                    detection_mode = mode.lower()
                                    log_vehicle(t['class'], speed, dt, len(positions), SPEED_THRESHOLD, detection_mode)
                                    
                                    is_speeding = speed > SPEED_THRESHOLD
                                    
                                    if is_speeding:
                                        total_speeders += 1
                                        log(f"🚨 SPEEDER #{total_speeders}: {t['class']} @ {speed:.1f} mph ({mode} mode)")
                                        
                                        # Create speeder photo with overlay
                                        if t['best_frame'] is not None:
                                            img = t['best_frame']
                                            x1, y1, x2, y2 = t['best_box']
                                            color = (0, 0, 255)  # Red
                                            
                                            # Draw bounding box
                                            cv2.rectangle(img, (x1, y1), (x2, y2), color, 4)
                                            
                                            # Speed label above vehicle
                                            label = f"{speed:.1f} MPH"
                                            font_scale, thickness = 2.5, 5
                                            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
                                            label_x = x1 + (x2 - x1 - label_size[0]) // 2
                                            label_y = y1 - 25
                                            
                                            # Label background
                                            cv2.rectangle(img, (label_x - 15, label_y - label_size[1] - 20),
                                                         (label_x + label_size[0] + 15, label_y + 15), color, -1)
                                            cv2.putText(img, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 
                                                       font_scale, (255, 255, 255), thickness)
                                            
                                            # Vehicle type label
                                            cv2.putText(img, t['class'].upper(), (x1, y2 + 45), 
                                                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)
                                            
                                            # Info bar at top
                                            info = f"SPEEDER | {t['class'].upper()} | {speed:.1f} mph | {mode} | {datetime.now().strftime('%H:%M:%S')}"
                                            cv2.rectangle(img, (0, 0), (900, 55), (0, 0, 0), -1)
                                            cv2.putText(img, info, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
                                            
                                            # Save image
                                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                            path = OUTPUT_DIR / f'speeder_{timestamp}_{speed:.0f}mph_{mode.lower()}.jpg'
                                            cv2.imwrite(str(path), img)
                                            
                                            # Send notifications
                                            send_telegram(CONFIG, 
                                                f"🚨 SPEEDER DETECTED! ({mode} mode)\n\n{t['class'].upper()}: {speed:.1f} mph\nLimit: {SPEED_THRESHOLD} mph\nTime: {datetime.now().strftime('%H:%M:%S')}")
                                            send_telegram(CONFIG, photo_path=str(path))
                                    else:
                                        # Log normal vehicle periodically
                                        if total_vehicles % 10 == 0:
                                            log(f"📊 Vehicle #{total_vehicles}: {t['class']} @ {speed:.1f} mph ({mode})")
                        
                        # Remove completed track
                        del tracks[tid]
            
            cap.release()
            
        except KeyboardInterrupt:
            log("Shutting down...")
            send_telegram(CONFIG, f"🔴 Speed Camera Stopped\n\nSession stats:\nTotal vehicles: {total_vehicles}\nSpeeders: {total_speeders}")
            break
        except Exception as e:
            log(f"Error in main loop: {e}")
            time.sleep(10)  # Wait before retrying
    
    log("Service stopped.")

if __name__ == "__main__":
    main()