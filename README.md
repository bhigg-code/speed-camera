# Speed Camera

Residential speed camera system using YOLOv8 object detection and computer vision to track vehicle speeds.

## Features

- Real-time vehicle detection and speed measurement using YOLOv8
- Day/night mode switching with IR-optimized preprocessing (8 PM – 6 AM)
- Multi-fix detection accuracy:
  - **Bounding box merge**: Combines split cab/cargo detections for large vehicles
  - **Occlusion jump filter**: Discards impossible position jumps (>350px/frame)
  - **Outlier segment filter**: Removes speed outliers >2.5x median at track end
  - **Stopped vehicle filter**: Skips vehicles with <30% movement efficiency (stopped/reversing)
- Flask web dashboard with admin controls, live stats, and speeder photo gallery
- Video file upload and processing for batch analysis
- Telegram alerts for speeders above threshold
- Speeder photo capture with annotated speed overlay

## Files

| File | Description |
|------|-------------|
| `speed_service_night.py` | Main live detection service (active) |
| `speed_web.py` | Flask web dashboard |
| `video_speed_processor.py` | Process recorded video files |
| `flask_video_routes.py` | Video upload/analysis routes |
| `integrate_video_upload.py` | Video integration helpers |
| `calibration_frame.py` | Camera calibration tool |
| `recalibrate.py` | Recalibration utility |
| `config.example.json` | Config template (copy to config.json) |

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
# Edit config.json with your camera RTSP URL, Telegram credentials, calibration
python speed_service_night.py
```

## Configuration

Copy `config.example.json` to `config.json` and fill in:
- `camera_rtsp`: Your camera's RTSP stream URL
- `telegram_bot_token` / `telegram_chat_id`: For speeder alerts
- `pixels_per_foot`: Calibration value (use `calibration_frame.py`)
- `speed_threshold_mph`: Alert threshold (default 35)

## Environment Variables (required for web dashboard)

```bash
export FLASK_SECRET_KEY="your-random-secret-key"
export SPEED_CAMERA_PASSWORD="your-dashboard-password"
```

## Calibration

Run `calibration_frame.py` to capture a reference frame and measure known distances to determine `pixels_per_foot`.

## Raspberry Pi 5 + Hailo

Change `device='cuda'` → `device='hailo'` and convert model:
```bash
yolo export model=yolov8n.pt format=hailo
```
