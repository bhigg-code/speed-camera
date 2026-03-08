# Speed Camera — Windows / CUDA

Runs on Windows with NVIDIA GPU (GTX 1080 or better).

## Setup
```batch
pip install -r requirements.txt
set FLASK_SECRET_KEY=your-random-key
set SPEED_CAMERA_PASSWORD=your-password
copy ..\shared\config.example.json config.json
REM Edit config.json with your camera URL and Telegram credentials
```

## Services (via NSSM)
```batch
nssm install SpeedCamera python speed_service.py
nssm install SpeedCameraWeb python speed_web.py
nssm start SpeedCamera
nssm start SpeedCameraWeb
```

## Notes
- Uses CUDA automatically if available, falls back to CPU
- Web dashboard at http://localhost:8080
- YOLOv8n model (yolov8n.pt) — download separately or let ultralytics fetch it
