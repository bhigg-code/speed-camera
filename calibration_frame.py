import cv2
import json
import requests
from pathlib import Path

with open('C:/speedcamera/config.json') as f:
    CONFIG = json.load(f)

cap = cv2.VideoCapture(CONFIG['camera_rtsp'])
ret, frame = cap.read()
cap.release()

if ret:
    h, w = frame.shape[:2]
    
    # Draw grid for measurement reference
    # Vertical lines every 200 pixels
    for x in range(0, w, 200):
        cv2.line(frame, (x, 0), (x, h), (255, 255, 0), 1)
        cv2.putText(frame, str(x), (x+5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    
    # Horizontal lines every 200 pixels  
    for y in range(0, h, 200):
        cv2.line(frame, (0, y), (w, y), (255, 255, 0), 1)
        cv2.putText(frame, str(y), (5, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    
    cv2.putText(frame, "CALIBRATION FRAME - Use grid to measure known distances", 
                (10, h-20), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    
    output = Path("C:/speedcamera/calibration_frame.jpg")
    cv2.imwrite(str(output), frame)
    
    # Send to Telegram
    token = CONFIG['telegram_bot_token']
    chat_id = CONFIG['telegram_chat_id']
    
    msg = """CALIBRATION FRAME

Yellow grid lines are 200 pixels apart.
Numbers show pixel coordinates.

Please identify:
1. A known distance (lane width, car, etc.)
2. The pixel coordinates spanning that distance

Example: "Lane is from x=1200 to x=1600, width is 12 feet"

This will let me calculate accurate speed!"""
    
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat_id, "text": msg}, timeout=10)
    
    with open(output, 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                      data={"chat_id": chat_id, "caption": "Calibration grid - identify a known distance"},
                      files={"photo": f}, timeout=30)
    
    print("Calibration frame sent!")
