# Speed Camera

Residential speed camera system using YOLOv8 object detection to track and log vehicle speeds.
Supports Windows/CUDA and Raspberry Pi 5/Hailo-8 platforms.

## Platforms

| Platform | Directory | Inference | FPS |
|----------|-----------|-----------|-----|
| Windows + NVIDIA GPU | `windows/` | CUDA (YOLOv8n) | ~60 |
| Raspberry Pi 5 + Hailo-8 AI Hat | `pi/` | Hailo NPU (YOLOv8s) | ~82 |

## Features
- Real-time vehicle detection and speed measurement
- Day/night mode with IR preprocessing (8 PM – 6 AM)
- Detection accuracy fixes:
  - Bounding box merge (truck cab+body split)
  - Occlusion jump filter (tree/obstruction handling)
  - Outlier segment filter (frame artifact removal)
  - Stopped vehicle filter (prevents false positives from parked/reversing vehicles)
- Flask web dashboard with speeder gallery and admin controls
- Telegram alerts with photo on speeder detection
- Video file upload and batch processing

## Configuration
Copy `shared/config.example.json` to `config.json` in your platform directory and fill in:
- `camera_rtsp`: RTSP stream URL
- `telegram_bot_token` / `telegram_chat_id`: For alerts
- `pixels_per_foot`: Camera calibration value
- `speed_threshold_mph`: Alert threshold (default 35)

## Environment Variables
```bash
FLASK_SECRET_KEY=<random-string>
SPEED_CAMERA_PASSWORD=<dashboard-password>
```

## Calibration
Use `shared/calibration_frame.py` to capture a frame and measure pixel distances for `pixels_per_foot`.
