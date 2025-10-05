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

## Object detection (MobileNet-SSD)

The app overlays MobileNet-SSD detections using OpenCV DNN (Caffe models) on CPU.

1) Install dependencies on the Pi (CPU only):
```bash
sudo apt-get update
sudo apt-get install -y python3-opencv
pip install numpy
```

2) Download the MobileNet-SSD model and prototxt (note: the repo has no Releases, so use direct raw links):
```bash
mkdir -p models
wget -O models/MobileNetSSD_deploy.caffemodel https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel
wget -O models/MobileNetSSD_deploy.prototxt.txt https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt
```

3) Start the app normally. If the files exist, detections run every few frames and boxes/labels are drawn on the stream.

Notes:
- If performance is low, increase `detection_every_n_frames` or reduce image size.
- To disable detection, remove the files or set `Cam.detector = None` early in `camera_start()`.