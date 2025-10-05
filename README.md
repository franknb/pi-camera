# pi-camera
Personalized deployment of SunFounder Pan-Tilt module/camera/CV application

# ssh to pi:

same network connection:
```bash
ssh frank@raspberrypi.local
```
general ip connection (yields to change)
```bash
ssh frank@192.168.68.123
```

password is same as this laptop

if this does not work, use 
```bash
hostname -I
```
on raspberry pi to get updated IP address

# run service
```python
cd pi-camera
python cam.py
```

## Object detection (optional)

The app can overlay lightweight YOLOv5n detections using OpenCV DNN with an ONNX model.

1) Install dependencies on the Pi (CPU only):
```bash
sudo apt-get update
sudo apt-get install -y python3-opencv
pip install numpy
```

2) Download the YOLOv5n ONNX model (about ~7MB) and place it under `models/yolov5n.onnx`:
```bash
mkdir -p models
wget -O models/yolov5n.onnx https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5n.onnx
```

3) Start the app normally. If the model file exists, detections run every few frames and boxes/labels are drawn on the stream.

Notes:
- If performance is low, reduce `detection_every_n_frames` or set a smaller `input_size` (e.g., 320).
- To disable detection, remove the model file or set `Cam.detector = None` early in `camera_start()`.