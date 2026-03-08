# Speed Camera — Raspberry Pi 5 + Hailo-8 AI Hat

Runs on Raspberry Pi 5 with Hailo-8 AI Hat (26 TOPS hardware inference).

## Hardware Required
- Raspberry Pi 5 (8GB recommended)
- Hailo-8 AI Hat+ (not Hailo-8L)

## Setup
```bash
# Install Hailo drivers
sudo apt install hailort hailort-pcie-driver python3-hailort hailo-models
# Reboot to load PCIe driver
sudo reboot

# Python environment
python3 -m venv /opt/speedcamera/venv
source /opt/speedcamera/venv/bin/activate
pip install -r requirements.txt

# Make hailo_platform available in venv
HAILO_PATH=$(python3 -c 'import hailo_platform, os; print(os.path.dirname(hailo_platform.__file__))')
echo "$HAILO_PATH/.." >> $(python3 -c 'import site; print(site.getsitepackages()[0])')/hailo_system.pth

cp ../shared/config.example.json /opt/speedcamera/config.json
# Edit config.json
```

## Systemd Services
```bash
sudo cp speedcamera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now speedcamera
```

## Performance
- YOLOv8s on Hailo-8: ~82 FPS (vs 3.7 FPS CPU)
- Model: /usr/share/hailo-models/yolov8s_h8.hef (installed with hailo-models)
- Web dashboard at http://pi-ip:8080
