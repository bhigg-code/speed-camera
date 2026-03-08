"""
Speed Camera Service - Raspberry Pi 5 + Hailo-8 AI Hat
Night Vision Enhanced with hardware-accelerated inference
"""
import cv2
import numpy as np
import json
import requests
import time
import csv
import sys
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path('/opt/speedcamera')
CONFIG_FILE = BASE_DIR / 'config.json'
LOG_FILE    = BASE_DIR / 'vehicle_log.csv'
OUTPUT_DIR  = BASE_DIR / 'captures'
HEF_MODEL   = Path('/usr/share/hailo-models/yolov8s_h8.hef')
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── Hailo inference wrapper ────────────────────────────────────────────────
class HailoDetector:
    """Wraps Hailo-8 inference for YOLOv8s object detection."""

    VEHICLE_CLASSES = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
    INPUT_SIZE = (640, 640)

    def __init__(self, hef_path):
        from hailo_platform import (HEF, VDevice, HailoStreamInterface,
                                     ConfigureParams, InputVStreamParams,
                                     OutputVStreamParams, FormatType, InferVStreams)
        self._InferVStreams = InferVStreams
        self._FormatType    = FormatType

        hef = HEF(str(hef_path))
        self._target  = VDevice(VDevice.create_params())
        cfg_params    = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
        ngs           = self._target.configure(hef, cfg_params)
        self._ng      = ngs[0]
        self._in_p    = InputVStreamParams.make(self._ng,  format_type=FormatType.UINT8)
        self._out_p   = OutputVStreamParams.make(self._ng, format_type=FormatType.FLOAT32)
        self._in_name = hef.get_input_vstream_infos()[0].name
        log(f"Hailo-8 initialised — model: {hef_path.name}")

    def start(self):
        """Open persistent inference pipeline. Call once before the main loop."""
        self._active_ctx = self._ng.activate()
        self._active_ctx.__enter__()
        self._pipe = self._InferVStreams(self._ng, self._in_p, self._out_p)
        self._pipe.__enter__()
        log("Hailo-8 inference pipeline open (persistent)")

    def stop(self):
        """Close persistent pipeline on shutdown."""
        try:
            self._pipe.__exit__(None, None, None)
            self._active_ctx.__exit__(None, None, None)
        except Exception:
            pass

    def infer(self, frame, conf_threshold=0.4):
        """Run detection on a BGR frame using persistent pipeline.

        Hailo NMS post-processed output format:
          outputs[key]         -> list (batch)
          outputs[key][0]      -> list of 80 per-class arrays
          outputs[key][0][cls] -> ndarray shape (N, 5): [x1, y1, x2, y2, conf]
          Coordinates are in INPUT_SIZE (640x640) pixel space.
        """
        h_orig, w_orig = frame.shape[:2]
        resized = cv2.resize(frame, self.INPUT_SIZE)
        # Model requires UINT8 input (raw pixel values 0-255, not normalized)
        inp = np.expand_dims(resized, 0)  # shape (1, 640, 640, 3) uint8
        outputs = self._pipe.infer({self._in_name: inp})

        # Hailo NMS output coords are normalized 0-1 — scale to original frame size
        detections = []

        for key, batch in outputs.items():
            for cls_idx, boxes in enumerate(batch[0]):
                if cls_idx not in self.VEHICLE_CLASSES:
                    continue
                if boxes is None or len(boxes) == 0:
                    continue
                for box in boxes:
                    if len(box) < 5:
                        continue
                    x1, y1, x2, y2, conf = box[0], box[1], box[2], box[3], box[4]
                    if conf < conf_threshold:
                        continue
                    detections.append({
                        'cls':  cls_idx,
                        'x1':   int(x1 * w_orig),
                        'y1':   int(y1 * h_orig),
                        'x2':   int(x2 * w_orig),
                        'y2':   int(y2 * h_orig),
                        'conf': float(conf),
                    })
        return detections


# ── Day/night helpers ──────────────────────────────────────────────────────
def is_night_time():
    hour = datetime.now().hour
    return hour >= 20 or hour <= 6

def get_detection_params():
    if is_night_time():
        return {'confidence': 0.25, 'iou_threshold': 0.4,
                'track_distance': 400, 'min_detections': 6, 'preprocessing': 'ir'}
    return {'confidence': 0.4, 'iou_threshold': 0.5,
            'track_distance': 350, 'min_detections': 8, 'preprocessing': 'standard'}

def preprocess_frame_ir(frame):
    gray      = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe     = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(gray)
    gamma     = 1.5
    lut       = np.array([((i / 255.0) ** (1.0 / gamma)) * 255
                          for i in range(256)]).astype('uint8')
    corrected = cv2.LUT(equalized, lut)
    enhanced  = cv2.cvtColor(corrected, cv2.COLOR_GRAY2BGR)
    return cv2.addWeighted(frame, 0.6, enhanced, 0.4, 0)


# ── CSV helpers ────────────────────────────────────────────────────────────
def init_csv():
    if not LOG_FILE.exists():
        with open(LOG_FILE, 'w', newline='') as f:
            csv.writer(f).writerow(['timestamp', 'date', 'time', 'vehicle_type',
                                    'speed_mph', 'speeding', 'track_duration_sec',
                                    'track_points', 'detection_mode'])

def log_vehicle(vehicle_type, speed, track_duration, track_points, threshold, detection_mode):
    now = datetime.now()
    speeding = 'YES' if speed > threshold else 'NO'
    with open(LOG_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([
            now.isoformat(), now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
            vehicle_type, round(speed, 1), speeding,
            round(track_duration, 2), track_points, detection_mode,
        ])


# ── Telegram ───────────────────────────────────────────────────────────────
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


# ── Bounding-box merge (truck cab+body) ────────────────────────────────────
def merge_overlapping(dets, proximity=80):
    if not dets:
        return []
    merged = True
    while merged:
        merged = False
        result, used = [], set()
        for i, d1 in enumerate(dets):
            if i in used:
                continue
            group = [d1]
            for j, d2 in enumerate(dets):
                if j <= i or j in used:
                    continue
                h_gap     = max(d1['x1'], d2['x1']) - min(d1['x2'], d2['x2'])
                v_overlap = min(d1['y2'], d2['y2']) - max(d1['y1'], d2['y1'])
                if h_gap < proximity and v_overlap > 0:
                    group.append(d2)
                    used.add(j)
            used.add(i)
            if len(group) > 1:
                best = max(group, key=lambda g: g['conf'])
                result.append({'cls': best['cls'],
                               'x1': min(g['x1'] for g in group),
                               'y1': min(g['y1'] for g in group),
                               'x2': max(g['x2'] for g in group),
                               'y2': max(g['y2'] for g in group),
                               'conf': best['conf']})
                merged = True
            else:
                result.append(group[0])
        dets = result
    return dets


# ── Main ───────────────────────────────────────────────────────────────────
log("SPEED CAMERA SERVICE - Raspberry Pi 5 + Hailo-8")

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

CONFIG = load_config()
init_csv()

# Initialise Hailo detector with persistent inference pipeline
detector = HailoDetector(HEF_MODEL)
detector.start()

mode   = "NIGHT" if is_night_time() else "DAY"
params = get_detection_params()
log(f"Mode: {mode} (confidence: {params['confidence']})")
log(f"Camera: {CONFIG['camera_rtsp'].split('@')[-1]}")  # log IP only, not password

send_telegram(CONFIG['telegram_bot_token'], CONFIG['telegram_chat_id'],
    f"🟢 Speed Camera Started (Pi 5 + Hailo-8)\n\nMode: {mode}\nConfidence: {params['confidence']}\n"
    f"{'🌙 Night vision enhancements active' if mode == 'NIGHT' else '☀️ Daylight detection active'}")

vehicle_classes        = HailoDetector.VEHICLE_CLASSES
last_config_load       = time.time()
CONFIG_RELOAD_INTERVAL = 60
session_start          = datetime.now()
total_vehicles         = 0
total_speeders         = 0

while True:
    try:
        cap = cv2.VideoCapture(CONFIG['camera_rtsp'])
        if not cap.isOpened():
            log("Camera connection failed, retrying in 30s...")
            time.sleep(30)
            continue

        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        middle_x_min = width  * 0.25
        middle_x_max = width  * 0.75
        log(f"Camera connected: {width}x{height}")

        tracks       = {}
        next_id      = 0
        captured_ids = set()
        frame_count  = 0
        last_mode_check = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                log("Frame read failed, reconnecting...")
                break

            frame_count += 1
            frame_time   = time.time()

            if frame_count % 2 != 0:
                continue

            # Heartbeat log every ~33 seconds so monitor can confirm active processing
            if frame_count % 1000 == 0:
                active_tracks = len([t for t in tracks.values() if frame_time - t['last'] < 2.5])
                log(f"♥ Processing — vehicles: {total_vehicles}, speeders: {total_speeders}, mode: {mode}, active_tracks: {active_tracks}")

            # Day/night mode switch check (every 5 min)
            if frame_time - last_mode_check > 300:
                new_params = get_detection_params()
                if new_params['confidence'] != params['confidence']:
                    mode   = "NIGHT" if is_night_time() else "DAY"
                    params = new_params
                    log(f"🔄 Switched to {mode} mode (confidence: {params['confidence']})")
                last_mode_check = frame_time

            # Config hot-reload
            if frame_time - last_config_load > CONFIG_RELOAD_INTERVAL:
                try:
                    CONFIG.update(load_config())
                    last_config_load = frame_time
                except Exception as e:
                    log(f"Config reload error: {e}")

            PIXELS_PER_FOOT = CONFIG.get('pixels_per_foot', 31.94)
            SPEED_THRESHOLD = CONFIG.get('speed_threshold_mph', 35)

            processed = preprocess_frame_ir(frame) if params['preprocessing'] == 'ir' else frame

            # ── Hailo inference ────────────────────────────────────────────
            frame_detections = detector.infer(processed, conf_threshold=params['confidence'])
            frame_detections = merge_overlapping(frame_detections, proximity=80)

            # Debug: log detections every 500 frames (~16s) so we know Hailo is seeing vehicles
            if frame_count % 500 == 0 and frame_detections:
                det_summary = [(vehicle_classes.get(d['cls'], d['cls']), round(d['conf'], 2)) for d in frame_detections]
                log(f"🔍 DEBUG dets: {det_summary}")

            # ── Tracking ───────────────────────────────────────────────────
            for det in frame_detections:
                cls            = det['cls']
                x1, y1, x2, y2 = det['x1'], det['y1'], det['x2'], det['y2']
                cx, cy         = (x1 + x2) // 2, (y1 + y2) // 2

                best_id, best_dist = None, params['track_distance']
                for tid, t in tracks.items():
                    if frame_time - t['last'] > 2.5:
                        continue
                    dist = np.sqrt((cx - t['cx'])**2 + (cy - t['cy'])**2)
                    if dist < best_dist:
                        best_dist, best_id = dist, tid

                if best_id is None:
                    best_id = next_id
                    tracks[best_id] = {'positions': [], 'last': frame_time,
                                       'cx': cx, 'cy': cy,
                                       'class': vehicle_classes[cls],
                                       'best_frame': None, 'best_box': None}
                    next_id += 1

                t = tracks[best_id]

                # Occlusion jump filter (~75 mph max)
                MAX_PX_PER_FRAME = 350
                if t['positions']:
                    last_cx, last_cy, last_t = t['positions'][-1]
                    jump     = np.sqrt((cx - last_cx)**2 + (cy - last_cy)**2)
                    elapsed  = frame_time - last_t
                    max_jump = MAX_PX_PER_FRAME * max(1, elapsed / 0.08)
                    if jump > max_jump:
                        t['last'], t['cx'], t['cy'] = frame_time, cx, cy
                        continue

                t['positions'].append((cx, cy, frame_time))
                t['last'], t['cx'], t['cy'] = frame_time, cx, cy

                if middle_x_min < cx < middle_x_max:
                    t['best_frame'] = frame.copy()
                    t['best_box']   = (x1, y1, x2, y2)

            # ── Speed calculation when track ends ──────────────────────────
            for tid in list(tracks.keys()):
                t = tracks[tid]
                if frame_time - t['last'] > 2.0:
                    positions = t['positions']
                    if len(positions) >= params['min_detections'] and tid not in captured_ids:

                        segments = []
                        for i in range(1, len(positions)):
                            seg_px = np.sqrt((positions[i][0] - positions[i-1][0])**2 +
                                            (positions[i][1] - positions[i-1][1])**2)
                            seg_dt = positions[i][2] - positions[i-1][2]
                            if seg_dt > 0:
                                segments.append((seg_px, seg_dt))

                        if segments:
                            seg_speeds = [px / dt for px, dt in segments]
                            median_spd = sorted(seg_speeds)[len(seg_speeds) // 2]
                            segments   = [(px, dt) for (px, dt), spd in zip(segments, seg_speeds)
                                          if spd <= median_spd * 2.5]

                        total_px = sum(px for px, dt in segments) if segments else 0
                        dt       = sum(dt for px, dt in segments) if segments else 0

                        if dt > 0.3:
                            speed = (total_px / dt) / PIXELS_PER_FOOT * 0.681818

                            # Stopped vehicle filter (< 30% movement efficiency)
                            net_x      = abs(positions[-1][0] - positions[0][0])
                            net_y      = abs(positions[-1][1] - positions[0][1])
                            net_disp   = np.sqrt(net_x**2 + net_y**2)
                            efficiency = net_disp / total_px if total_px > 0 else 0
                            min_dur    = 0.5 if len(positions) >= 15 else 0.8

                            if speed > 5 and dt >= min_dur and efficiency >= 0.3:
                                captured_ids.add(tid)
                                total_vehicles += 1

                                log_vehicle(t['class'], speed, dt, len(positions),
                                            SPEED_THRESHOLD, mode.lower())

                                if speed > SPEED_THRESHOLD:
                                    total_speeders += 1
                                    log(f"🚨 SPEEDER #{total_speeders}: {t['class']} @ {speed:.1f} mph ({mode})")

                                    if t['best_frame'] is not None:
                                        img  = t['best_frame']
                                        bx1, by1, bx2, by2 = t['best_box']
                                        color = (0, 0, 255)

                                        cv2.rectangle(img, (bx1, by1), (bx2, by2), color, 4)
                                        label = f"{speed:.1f} MPH"
                                        fs, thick = 2.5, 5
                                        lsz = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, thick)[0]
                                        lx, ly = bx1 + (bx2 - bx1 - lsz[0]) // 2, by1 - 25
                                        cv2.rectangle(img, (lx - 15, ly - lsz[1] - 20),
                                                      (lx + lsz[0] + 15, ly + 15), color, -1)
                                        cv2.putText(img, label, (lx, ly),
                                                    cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), thick)
                                        cv2.putText(img, t['class'].upper(), (bx1, by2 + 45),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)
                                        info = (f"SPEEDER | {t['class'].upper()} | {speed:.1f} mph | "
                                                f"{mode} | {datetime.now().strftime('%H:%M:%S')}")
                                        cv2.rectangle(img, (0, 0), (900, 55), (0, 0, 0), -1)
                                        cv2.putText(img, info, (10, 40),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)

                                        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
                                        path = OUTPUT_DIR / f'speeder_{ts}_{speed:.0f}mph_{mode.lower()}.jpg'
                                        cv2.imwrite(str(path), img)

                                        send_telegram(CONFIG['telegram_bot_token'],
                                                      CONFIG['telegram_chat_id'],
                                            f"🚨 SPEEDER DETECTED! ({mode} mode)\n\n"
                                            f"{t['class'].upper()}: {speed:.1f} mph\n"
                                            f"Limit: {SPEED_THRESHOLD} mph\n"
                                            f"Time: {datetime.now().strftime('%H:%M:%S')}")
                                        send_telegram(CONFIG['telegram_bot_token'],
                                                      CONFIG['telegram_chat_id'],
                                                      photo_path=str(path))
                                else:
                                    if total_vehicles % 10 == 0:
                                        log(f"📊 Vehicle #{total_vehicles}: {t['class']} @ {speed:.1f} mph ({mode})")

                    del tracks[tid]

        cap.release()

    except KeyboardInterrupt:
        log("Shutting down...")
        detector.stop()
        send_telegram(CONFIG['telegram_bot_token'], CONFIG['telegram_chat_id'],
            f"🔴 Speed Camera Stopped\n\nTotal vehicles: {total_vehicles}\nSpeeders: {total_speeders}")
        break
    except Exception as e:
        log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        time.sleep(10)

log("Service stopped.")
