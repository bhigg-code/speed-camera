# Speed Camera Night Vision Enhancement

An intelligent speed detection system that automatically adjusts detection parameters for day and night conditions, optimized for infrared/night vision cameras.

## 🌙 Night Vision Problem Solved

Standard YOLO models struggle with infrared/night vision imagery because they're trained on visible light photos. This enhancement automatically:

- **Reduces detection confidence** for IR mode (25% vs 40% day)
- **Applies IR-optimized preprocessing** (histogram equalization, gamma correction)
- **Adjusts tracking tolerance** for challenging IR conditions
- **Switches modes automatically** based on time of day

## Features

✅ **Dynamic Day/Night Detection**
- Automatic mode switching (8 PM - 6 AM = night mode)
- Different confidence thresholds for each mode
- Mode-aware logging and notifications

✅ **IR Image Enhancement**
- Histogram equalization for better contrast
- Gamma correction optimized for IR imagery
- Adaptive preprocessing pipeline

✅ **Improved Tracking**
- Higher distance tolerance for IR mode
- Fewer minimum detections required in challenging conditions
- Enhanced vehicle identification in low light

✅ **Comprehensive Logging**
- CSV logging with detection mode tracking
- Speed calculations with calibration support
- Photo capture with overlay information

✅ **Telegram Integration**
- Real-time speeder notifications
- Photo attachments with speed overlays
- Mode switching announcements

## Installation

1. **Install Dependencies**
   ```bash
   pip install ultralytics opencv-python torch requests numpy
   ```

2. **Download YOLO Model**
   ```python
   from ultralytics import YOLO
   model = YOLO('yolov8n.pt')  # Downloads automatically
   ```

3. **Create Configuration**
   ```bash
   cp config.example.json config.json
   # Edit config.json with your settings
   ```

4. **Run the System**
   ```bash
   python speed_camera_night_vision.py
   ```

## Configuration

### Required Settings

```json
{
  "camera_rtsp": "rtsp://username:password@camera_ip:554/stream",
  "pixels_per_foot": 31.94,
  "speed_threshold_mph": 35
}
```

### Optional Settings

```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

## Calibration

To calibrate `pixels_per_foot`:

1. Measure a known distance in your camera view (e.g., 10 feet)
2. Count pixels for that distance
3. Calculate: `pixels_per_foot = pixels_measured / feet_measured`

Example: 320 pixels = 10 feet → `pixels_per_foot = 32.0`

## Mode Settings

| Mode | Time | Confidence | Tracking | Min Detections |
|------|------|------------|----------|----------------|
| **Day** | 6 AM - 8 PM | 40% | 350px | 8 frames |
| **Night** | 8 PM - 6 AM | 25% | 400px | 6 frames |

## Output Files

- `vehicle_log.csv` - All vehicle detections with metadata
- `captures/speeder_*.jpg` - Photos of speed violations
- Console logs with timestamped events

## Hardware Requirements

- **GPU Recommended** - NVIDIA CUDA for faster inference
- **Camera** - RTSP stream with IR/night vision capability
- **Python 3.8+** - With OpenCV and PyTorch support

## Troubleshooting

### No Night Detections
- Check if camera is in IR mode (look for infrared illumination)
- Verify time-based mode switching is working
- Consider lowering confidence further (edit `get_detection_params()`)

### False Positives
- Increase confidence threshold
- Adjust minimum detection frames
- Check camera positioning and calibration

### Performance Issues
- Reduce frame processing (increase skip frames)
- Use smaller YOLO model (yolov8s.pt → yolov8n.pt)
- Lower camera resolution

## License

MIT License - Feel free to modify and distribute!

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly with your camera setup
4. Submit a pull request

## Security Note

Never commit actual configuration files with credentials to version control. Always use the example configuration and add `config.json` to `.gitignore`.