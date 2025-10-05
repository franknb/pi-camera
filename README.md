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

## Object detection (YOLOv5n ONNX)

The app overlays YOLOv5n detections using OpenCV DNN (ONNX) on CPU.

1) Install dependencies on the Pi (CPU only):
```bash
sudo apt-get update
sudo apt-get install -y python3-opencv
pip install numpy
```

2) Download the YOLOv5n ONNX model (~7MB):
```bash
mkdir -p models
wget -O models/yolov5n.onnx https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5n.onnx
```

3) Start the app normally. If the file exists, detections run every few frames and boxes/labels are drawn on the stream.

Notes:
- Use the v6.0 YOLOv5n ONNX linked above; some ONNX exports may not be compatible with OpenCV DNN. The code uses 640x640 input size.
- If performance is low, increase `detection_every_n_frames` or reduce camera resolution.
- To disable detection, remove the model file or set `Cam.detector = None` early in `camera_start()`.