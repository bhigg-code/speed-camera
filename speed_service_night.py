"""
Speed Camera Service - Night Vision Enhanced
Adjusts detection parameters based on time of day for better IR/night vision performance
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

CONFIG_FILE = Path('C:/speedcamera/config.json')
LOG_FILE = Path('C:/speedcamera/vehicle_log.csv')
OUTPUT_DIR = Path('C:/speedcamera/captures')
OUTPUT_DIR.mkdir(exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def is_night_time():
    """Determine if it's night time (IR camera mode)"""
    hour = datetime.now().hour
    return hour >= 20 or hour <= 6

def get_detection_params():
    """Get detection parameters optimized for current lighting conditions"""
    if is_night_time():
        return {
            'confidence': 0.25,  # Lower for IR detection
            'iou_threshold': 0.4,  # Lower for IR tracking
            'track_distance': 400,  # Higher tolerance for IR
            'min_detections': 6,   # Fewer required for IR
            'preprocessing': 'ir'
        }
    else:
        return {
            'confidence': 0.4,     # Standard for daylight
            'iou_threshold': 0.5,  
            'track_distance': 350,
            'min_detections': 8,
            'preprocessing': 'standard'
        }

def preprocess_frame_ir(frame):
    """Enhanced preprocessing for infrared/night vision imagery"""
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
    with open(CONFIG_FILE) as f:
        return json.load(f)

log("SPEED CAMERA SERVICE - Night Vision Enhanced")

CONFIG = load_config()
last_config_load = time.time()
CONFIG_RELOAD_INTERVAL = 60

device = 'cuda' if torch.cuda.is_available() else 'cpu'
gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'

model = YOLO('yolov8n.pt')
model.to(device)

def init_csv():
    if not LOG_FILE.exists():
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'date', 'time', 'vehicle_type', 'speed_mph', 
                           'speeding', 'track_duration_sec', 'track_points', 'detection_mode'])

def log_vehicle(vehicle_type, speed, track_duration, track_points, threshold, detection_mode):
    now = datetime.now()
    speeding = 'YES' if speed > threshold else 'NO'
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            now.isoformat(), now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
            vehicle_type, round(speed, 1), speeding, round(track_duration, 2), 
            track_points, detection_mode
        ])

def send_telegram(token, chat_id, text=None, photo_path=None):
    try:
        if text:
            requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                          data={'chat_id': chat_id, 'text': text}, timeout=10)
        if photo_path and Path(photo_path).exists():
            with open(photo_path, 'rb') as f:
                requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                              data={'chat_id': chat_id}, files={'photo': f}, timeout=30)
    except Exception as e:
        log(f"Telegram error: {e}")

init_csv()

# Startup with mode detection
mode = "NIGHT" if is_night_time() else "DAY"
params = get_detection_params()
log(f"GPU: {gpu_name}")
log(f"Mode: {mode} (confidence: {params['confidence']})")

send_telegram(CONFIG['telegram_bot_token'], CONFIG['telegram_chat_id'],
    f"🟢 Speed Camera Started - {mode} Mode\n\nGPU: {gpu_name}\nDetection: Optimized for {mode.lower()} vision\nConfidence: {params['confidence']}\n\n🌙 Night vision enhancements active!" if mode == "NIGHT" else f"🟢 Speed Camera Started - {mode} Mode\n\nGPU: {gpu_name}\nStandard daylight detection active")

vehicle_classes = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
scale = 0.5
session_start = datetime.now()
total_vehicles = 0
total_speeders = 0

while True:
    try:
        cap = cv2.VideoCapture(CONFIG['camera_rtsp'])
        if not cap.isOpened():
            log("Camera connection failed, retrying in 30s...")
            time.sleep(30)
            continue
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        middle_x_min, middle_x_max = width * 0.25, width * 0.75
        
        log(f"Camera connected: {width}x{height}")
        
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
            
            # Config reload
            if frame_time - last_config_load > CONFIG_RELOAD_INTERVAL:
                try:
                    CONFIG.update(load_config())
                    last_config_load = frame_time
                except Exception as e:
                    log(f"Config reload error: {e}")
            
            PIXELS_PER_FOOT = CONFIG.get('pixels_per_foot', 31.94)
            SPEED_THRESHOLD = CONFIG.get('speed_threshold_mph', 35)
            
            if frame_count % 2 != 0:
                continue
            
            # Apply preprocessing based on detection mode
            if params['preprocessing'] == 'ir':
                processed_frame = preprocess_frame_ir(frame)
            else:
                processed_frame = frame
            
            small = cv2.resize(processed_frame, None, fx=scale, fy=scale)
            results = model(small, verbose=False, conf=params['confidence'])
            
            # Collect all detections in this frame first
            frame_detections = []
            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    if cls not in vehicle_classes:
                        continue
                    x1, y1, x2, y2 = [int(c / scale) for c in box.xyxy[0].cpu().numpy()]
                    frame_detections.append({
                        'cls': cls, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                        'conf': float(box.conf[0])
                    })

            # Merge nearby/overlapping boxes (handles truck cab+body split)
            def merge_overlapping(dets, proximity=80):
                if not dets:
                    return []
                merged = True
                while merged:
                    merged = False
                    result = []
                    used = set()
                    for i, d1 in enumerate(dets):
                        if i in used:
                            continue
                        group = [d1]
                        for j, d2 in enumerate(dets):
                            if j <= i or j in used:
                                continue
                            # Check horizontal proximity (handles cab+body side by side)
                            h_gap = max(d1['x1'], d2['x1']) - min(d1['x2'], d2['x2'])
                            # Check vertical overlap
                            v_overlap = min(d1['y2'], d2['y2']) - max(d1['y1'], d2['y1'])
                            if h_gap < proximity and v_overlap > 0:
                                group.append(d2)
                                used.add(j)
                        used.add(i)
                        if len(group) > 1:
                            # Merge into one box, keep highest confidence class
                            mx1 = min(g['x1'] for g in group)
                            my1 = min(g['y1'] for g in group)
                            mx2 = max(g['x2'] for g in group)
                            my2 = max(g['y2'] for g in group)
                            best = max(group, key=lambda g: g['conf'])
                            result.append({'cls': best['cls'], 'x1': mx1, 'y1': my1,
                                           'x2': mx2, 'y2': my2, 'conf': best['conf']})
                            merged = True
                        else:
                            result.append(group[0])
                    dets = result
                return dets

            frame_detections = merge_overlapping(frame_detections, proximity=80)

            for det in frame_detections:
                    cls = det['cls']
                    x1, y1, x2, y2 = det['x1'], det['y1'], det['x2'], det['y2']
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    
                    best_id = None
                    best_dist = params['track_distance']
                    for tid, t in tracks.items():
                        if frame_time - t['last'] > 2.5:
                            continue
                        dist = np.sqrt((cx - t['cx'])**2 + (cy - t['cy'])**2)
                        if dist < best_dist:
                            best_dist = dist
                            best_id = tid
                    
                    if best_id is None:
                        best_id = next_id
                        tracks[best_id] = {'positions': [], 'last': frame_time, 'cx': cx, 'cy': cy,
                                           'class': vehicle_classes[cls], 'best_frame': None, 'best_box': None}
                        next_id += 1
                    
                    t = tracks[best_id]
                    # OCCLUSION FIX: Skip position if jump is physically impossible
                    MAX_PX_PER_FRAME = 350  # ~75 mph max at 25fps every 2nd frame
                    if t['positions']:
                        last_cx, last_cy, last_t = t['positions'][-1]
                        jump = ((cx - last_cx)**2 + (cy - last_cy)**2) ** 0.5
                        elapsed = frame_time - last_t
                        max_jump = MAX_PX_PER_FRAME * max(1, elapsed / 0.08)
                        if jump > max_jump:
                            # Position jump too large - vehicle was occluded
                            # Update position reference but don't add to speed calc
                            t['last'] = frame_time
                            t['cx'], t['cy'] = cx, cy
                            continue
                    t['positions'].append((cx, cy, frame_time))
                    t['last'] = frame_time
                    t['cx'], t['cy'] = cx, cy
                    
                    if middle_x_min < cx < middle_x_max:
                        t['best_frame'] = frame.copy()  # Use original frame for photos
                        t['best_box'] = (x1, y1, x2, y2)
            
            for tid in list(tracks.keys()):
                t = tracks[tid]
                if frame_time - t['last'] > 2.0:
                    positions = t['positions']
                    if len(positions) >= params['min_detections'] and tid not in captured_ids:
                        # OCCLUSION FIX: Calculate per-segment speeds, remove outliers
                        segments = []
                        for i in range(1, len(positions)):
                            seg_px = np.sqrt((positions[i][0]-positions[i-1][0])**2 +
                                           (positions[i][1]-positions[i-1][1])**2)
                            seg_dt = positions[i][2] - positions[i-1][2]
                            if seg_dt > 0:
                                segments.append((seg_px, seg_dt))
                        
                        if segments:
                            seg_speeds = [(px/dt) for px, dt in segments]
                            median_speed = sorted(seg_speeds)[len(seg_speeds)//2]
                            # Filter segments where speed is more than 2.5x median (jump artifacts)
                            segments = [(px, dt) for (px, dt), spd in zip(segments, seg_speeds)
                                       if spd <= median_speed * 2.5]
                        
                        total_px = sum(px for px, dt in segments) if segments else 0
                        dt = sum(dt for px, dt in segments) if segments else 0
                        
                        if dt > 0.3:
                            speed = (total_px / dt) / PIXELS_PER_FOOT * 0.681818

                            # STOPPED VEHICLE FIX: Check net displacement vs total movement
                            # A vehicle that stops/reverses has low net displacement
                            net_x = abs(positions[-1][0] - positions[0][0])
                            net_y = abs(positions[-1][1] - positions[0][1])
                            net_displacement = np.sqrt(net_x**2 + net_y**2)
                            
                            # Movement efficiency: net / total distance
                            # Stopped/reversing vehicles have efficiency < 30%
                            efficiency = net_displacement / total_px if total_px > 0 else 0
                            
                            # Also require minimum track duration for speed confidence
                            # Short tracks (< 0.8s) are unreliable for large vehicles
                            min_duration = 0.5 if len(positions) >= 15 else 0.8
                            
                            if speed > 5 and dt >= min_duration and efficiency >= 0.3:
                                captured_ids.add(tid)
                                total_vehicles += 1
                                
                                detection_mode = mode.lower()
                                log_vehicle(t['class'], speed, dt, len(positions), SPEED_THRESHOLD, detection_mode)
                                
                                is_speeding = speed > SPEED_THRESHOLD
                                
                                if is_speeding:
                                    total_speeders += 1
                                    log(f"🚨 SPEEDER #{total_speeders}: {t['class']} @ {speed:.1f} mph ({mode} mode)")
                                    
                                    if t['best_frame'] is not None:
                                        img = t['best_frame']
                                        x1, y1, x2, y2 = t['best_box']
                                        color = (0, 0, 255)
                                        
                                        cv2.rectangle(img, (x1, y1), (x2, y2), color, 4)
                                        
                                        label = f"{speed:.1f} MPH"
                                        font_scale, thickness = 2.5, 5
                                        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
                                        label_x = x1 + (x2 - x1 - label_size[0]) // 2
                                        label_y = y1 - 25
                                        
                                        cv2.rectangle(img, (label_x - 15, label_y - label_size[1] - 20),
                                                     (label_x + label_size[0] + 15, label_y + 15), color, -1)
                                        cv2.putText(img, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 
                                                   font_scale, (255, 255, 255), thickness)
                                        
                                        cv2.putText(img, t['class'].upper(), (x1, y2 + 45), 
                                                   cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)
                                        
                                        info = f"SPEEDER | {t['class'].upper()} | {speed:.1f} mph | {mode} | {datetime.now().strftime('%H:%M:%S')}"
                                        cv2.rectangle(img, (0, 0), (900, 55), (0, 0, 0), -1)
                                        cv2.putText(img, info, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
                                        
                                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                        path = OUTPUT_DIR / f'speeder_{timestamp}_{speed:.0f}mph_{mode.lower()}.jpg'
                                        cv2.imwrite(str(path), img)
                                        
                                        send_telegram(CONFIG['telegram_bot_token'], CONFIG['telegram_chat_id'],
                                            f"🚨 SPEEDER DETECTED! ({mode} mode)\n\n{t['class'].upper()}: {speed:.1f} mph\nLimit: {SPEED_THRESHOLD} mph\nTime: {datetime.now().strftime('%H:%M:%S')}")
                                        send_telegram(CONFIG['telegram_bot_token'], CONFIG['telegram_chat_id'],
                                            photo_path=str(path))
                                else:
                                    if total_vehicles % 10 == 0:
                                        log(f"📊 Vehicle #{total_vehicles}: {t['class']} @ {speed:.1f} mph ({mode})")
                    
                    del tracks[tid]
        
        cap.release()
        
    except KeyboardInterrupt:
        log("Shutting down...")
        send_telegram(CONFIG['telegram_bot_token'], CONFIG['telegram_chat_id'],
            f"🔴 Speed Camera Stopped\n\nTotal vehicles: {total_vehicles}\nSpeeders: {total_speeders}")
        break
    except Exception as e:
        log(f"Error: {e}")
        time.sleep(10)

log("Service stopped.")
