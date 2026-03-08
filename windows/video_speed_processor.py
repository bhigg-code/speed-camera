"""
Video Speed Processing Module - Version 4
Added direction detection - filters out reversing/backing up vehicles
"""

import cv2
import numpy as np
import os
import json
import time
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO
import torch

class VideoSpeedProcessor:
    def __init__(self, config_file='config.json'):
        """Initialize the video speed processor"""
        self.config = {
            'pixels_per_foot': 31.94,
            'speed_threshold_mph': 35,
            'confidence_threshold': 0.3,
            'expected_direction': 'left_to_right'  # or 'right_to_left' or 'both'
        }
        self.model = None
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.vehicle_classes = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
        
    def load_model(self):
        """Load YOLO model if not already loaded"""
        if self.model is None:
            self.model = YOLO('yolov8n.pt')
            self.model.to(self.device)
    
    def merge_overlapping(self, dets, proximity=80):
        """Merge nearby/overlapping boxes - handles truck cab+body split detection."""
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
                    # Horizontal proximity + vertical overlap
                    h_gap = max(d1['cx'] - d1['w']//2, d2['cx'] - d2['w']//2)
                    h_gap = max(d1['cx'] + d1['w']//2, d2['cx'] + d2['w']//2) - max(d1['cx'] - d1['w']//2, d2['cx'] - d2['w']//2) - d1['w'] - d2['w']
                    x1_1, x2_1 = d1['cx'] - d1['w']//2, d1['cx'] + d1['w']//2
                    x1_2, x2_2 = d2['cx'] - d2['w']//2, d2['cx'] + d2['w']//2
                    y1_1, y2_1 = d1['cy'] - d1['h']//2, d1['cy'] + d1['h']//2
                    y1_2, y2_2 = d2['cy'] - d2['h']//2, d2['cy'] + d2['h']//2
                    h_gap = max(x1_1, x1_2) - min(x2_1, x2_2)  # negative = overlapping
                    v_overlap = min(y2_1, y2_2) - max(y1_1, y1_2)
                    if h_gap < proximity and v_overlap > 0:
                        group.append(d2)
                        used.add(j)
                used.add(i)
                if len(group) > 1:
                    # Merge into one box
                    all_x1 = [g['cx'] - g['w']//2 for g in group]
                    all_y1 = [g['cy'] - g['h']//2 for g in group]
                    all_x2 = [g['cx'] + g['w']//2 for g in group]
                    all_y2 = [g['cy'] + g['h']//2 for g in group]
                    mx1, my1 = min(all_x1), min(all_y1)
                    mx2, my2 = max(all_x2), max(all_y2)
                    best = max(group, key=lambda g: g['conf'])
                    result.append({
                        'cx': (mx1 + mx2) // 2,
                        'cy': (my1 + my2) // 2,
                        'w': mx2 - mx1,
                        'h': my2 - my1,
                        'class': best['class'],
                        'conf': best['conf']
                    })
                    merged = True
                else:
                    result.append(group[0])
            dets = result
        return dets


    def calculate_direction(self, positions):
        """
        Determine the primary direction of travel
        Returns: 'left_to_right', 'right_to_left', 'stationary', or 'erratic'
        """
        if len(positions) < 2:
            return 'unknown'
        
        # Calculate net horizontal movement
        start_x = positions[0][0]
        end_x = positions[-1][0]
        net_x_movement = end_x - start_x
        
        # Calculate total horizontal distance (to detect erratic movement)
        total_x_movement = sum(abs(positions[i][0] - positions[i-1][0]) for i in range(1, len(positions)))
        
        # If net movement is much less than total, vehicle is moving erratically (backing up, etc.)
        if total_x_movement > 0:
            efficiency = abs(net_x_movement) / total_x_movement
        else:
            return 'stationary'
        
        # If efficiency is low, movement is erratic (back and forth)
        if efficiency < 0.5:
            return 'erratic'
        
        # Determine direction based on net movement
        if abs(net_x_movement) < 20:  # Less than 20 pixels = stationary
            return 'stationary'
        elif net_x_movement > 0:
            return 'left_to_right'
        else:
            return 'right_to_left'
    
    def process_video(self, video_path, progress_callback=None):
        """
        Process a video file and detect vehicle speeds
        Now includes direction detection to filter out reversing vehicles
        """
        self.load_model()
        
        results = {
            'vehicles_detected': [],
            'vehicles_filtered': [],  # Vehicles that were filtered out (wrong direction, etc.)
            'total_vehicles': 0,
            'speeders': 0,
            'processing_info': {},
            'error': None
        }
        
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                results['error'] = "Could not open video file"
                return results
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / fps if fps > 0 else 0
            
            results['processing_info'] = {
                'total_frames': total_frames,
                'fps': fps,
                'resolution': f"{width}x{height}",
                'duration_seconds': round(duration, 1),
                'device_used': self.device
            }
            
            # For short videos, process every frame
            frame_skip = 1 if duration < 30 else 2
            
            # Detection parameters
            scale = 0.5
            confidence = self.config.get('confidence_threshold', 0.3)
            pixels_per_foot = self.config.get('pixels_per_foot', 31.94)
            speed_threshold = self.config.get('speed_threshold_mph', 35)
            
            # Tracking parameters
            max_track_distance = min(width, height) * 0.3
            track_timeout = 2.0
            min_detections = 3 if duration < 15 else 4
            
            # Tracking variables
            tracks = {}
            next_id = 0
            frame_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                frame_time = frame_count / fps
                
                if progress_callback:
                    progress = (frame_count / total_frames) * 100
                    progress_callback(progress)
                
                if frame_count % frame_skip != 0:
                    continue
                
                small = cv2.resize(frame, None, fx=scale, fy=scale)
                detections = self.model(small, verbose=False, conf=confidence)
                
                # Get all detections in this frame
                frame_detections = []
                for r in detections:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        if cls not in self.vehicle_classes:
                            continue
                        
                        x1, y1, x2, y2 = [int(c / scale) for c in box.xyxy[0].cpu().numpy()]
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        w, h = x2 - x1, y2 - y1
                        
                        frame_detections.append({
                            'cx': cx, 'cy': cy,
                            'w': w, 'h': h,
                            'class': self.vehicle_classes[cls],
                            'conf': float(box.conf[0])
                        })
                
                # Merge nearby boxes (fixes truck cab+body split detection)
                frame_detections = self.merge_overlapping(frame_detections, proximity=80)
                
                # Match detections to tracks
                used_tracks = set()
                frame_detections.sort(key=lambda x: x['conf'], reverse=True)
                
                for det in frame_detections:
                    best_track_id = None
                    best_score = float('inf')
                    
                    for tid, track in tracks.items():
                        if tid in used_tracks:
                            continue
                        
                        time_since_last = frame_time - track['last_time']
                        if time_since_last > track_timeout:
                            continue
                        
                        dist = np.sqrt((det['cx'] - track['cx'])**2 + (det['cy'] - track['cy'])**2)
                        
                        # Velocity prediction
                        if len(track['positions']) >= 2:
                            p1 = track['positions'][-2]
                            p2 = track['positions'][-1]
                            dt = p2[2] - p1[2]
                            if dt > 0:
                                vx = (p2[0] - p1[0]) / dt
                                vy = (p2[1] - p1[1]) / dt
                                pred_x = track['cx'] + vx * time_since_last
                                pred_y = track['cy'] + vy * time_since_last
                                pred_dist = np.sqrt((det['cx'] - pred_x)**2 + (det['cy'] - pred_y)**2)
                                dist = min(dist, pred_dist)
                        
                        size_penalty = 1.0
                        if 'avg_w' in track:
                            size_ratio = max(det['w'], track['avg_w']) / max(min(det['w'], track['avg_w']), 1)
                            size_penalty = min(size_ratio, 2.0)
                        
                        score = dist * size_penalty
                        
                        if dist < max_track_distance and score < best_score:
                            best_score = score
                            best_track_id = tid
                    
                    if best_track_id is not None:
                        track = tracks[best_track_id]
                        # OCCLUSION FIX: Skip position if jump is physically impossible
                        MAX_PX_PER_FRAME = 350  # ~75 mph max
                        skip_point = False
                        if track['positions']:
                            last_cx, last_cy, last_t = track['positions'][-1]
                            jump = ((det['cx'] - last_cx)**2 + (det['cy'] - last_cy)**2) ** 0.5
                            elapsed = frame_time - last_t
                            max_jump = MAX_PX_PER_FRAME * max(1, elapsed / 0.08)
                            if jump > max_jump:
                                skip_point = True
                        if not skip_point:
                            track['positions'].append((det['cx'], det['cy'], frame_time))
                        track['last_time'] = frame_time
                        track['cx'], track['cy'] = det['cx'], det['cy']
                        track['avg_w'] = (track['avg_w'] * 0.8) + (det['w'] * 0.2)
                        used_tracks.add(best_track_id)
                    else:
                        tracks[next_id] = {
                            'positions': [(det['cx'], det['cy'], frame_time)],
                            'last_time': frame_time,
                            'cx': det['cx'],
                            'cy': det['cy'],
                            'avg_w': det['w'],
                            'class': det['class']
                        }
                        used_tracks.add(next_id)
                        next_id += 1
            
            cap.release()
            
            # Process all tracks and calculate speeds WITH DIRECTION FILTERING
            for tid, track in tracks.items():
                positions = track['positions']
                
                if len(positions) >= min_detections:
                    # CALCULATE DIRECTION
                    direction = self.calculate_direction(positions)
                    
                    # Calculate speed (for reporting purposes)
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
                        segments = [(px, dt) for (px, dt), spd in zip(segments, seg_speeds)
                                   if spd <= median_speed * 2.5]
                    
                    total_px = sum(px for px, dt in segments) if segments else 0
                    dt = sum(dt for px, dt in segments) if segments else 0
                    
                    if dt > 0.3:
                        speed = (total_px / dt) / pixels_per_foot * 0.681818
                        
                        vehicle_data = {
                            'id': tid,
                            'type': track['class'],
                            'speed_mph': round(speed, 1),
                            'timestamp': round(positions[0][2], 1),
                            'end_time': round(positions[-1][2], 1),
                            'duration': round(dt, 2),
                            'track_points': len(positions),
                            'direction': direction,
                            'is_speeding': speed > speed_threshold
                        }
                        
                        # FILTER: Only count vehicles going in a valid direction
                        if direction in ['left_to_right', 'right_to_left']:
                            # Valid forward movement
                            if speed > 2:
                                results['vehicles_detected'].append(vehicle_data)
                                results['total_vehicles'] += 1
                                if speed > speed_threshold:
                                    results['speeders'] += 1
                        else:
                            # Filtered out (stationary, erratic, backing up)
                            vehicle_data['filter_reason'] = f"Direction: {direction} (not valid traffic flow)"
                            results['vehicles_filtered'].append(vehicle_data)
            
            # Sort vehicles by timestamp
            results['vehicles_detected'].sort(key=lambda x: x['timestamp'])
            
            # Add summary statistics
            if results['vehicles_detected']:
                speeds = [v['speed_mph'] for v in results['vehicles_detected']]
                results['processing_info'].update({
                    'avg_speed': round(sum(speeds) / len(speeds), 1),
                    'max_speed': round(max(speeds), 1),
                    'min_speed': round(min(speeds), 1),
                    'speeding_rate': round((results['speeders'] / results['total_vehicles']) * 100, 1),
                    'vehicles_filtered_count': len(results['vehicles_filtered'])
                })
            else:
                results['processing_info']['vehicles_filtered_count'] = len(results['vehicles_filtered'])
            
        except Exception as e:
            results['error'] = str(e)
            import traceback
            results['error'] += '\n' + traceback.format_exc()
        
        return results


def process_uploaded_video(video_path, config=None):
    """Main function to process an uploaded video file"""
    processor = VideoSpeedProcessor()
    if config:
        processor.config.update(config)
    return processor.process_video(video_path)
