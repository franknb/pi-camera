import threading
import time
from picamera2 import Picamera2, Preview
from libcamera import Transform
import cv2
import numpy as np
from servo import Servo
from flask import Flask, render_template, Response, request, jsonify, make_response

app = Flask(__name__)


def gen():
    # MJPEG generator
    while True:
        with Cam.frame_lock:
            frame = Cam.frame
        if frame is None:
            time.sleep(0.01)
            continue
        # frame must be BGR for cv2.imencode
        jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])[1]
        jpg_bytes = jpg.tobytes()
        headers = (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            + f'Content-Length: {len(jpg_bytes)}\r\n'.encode('ascii') +
            b'\r\n'
        )
        yield headers + jpg_bytes + b'\r\n'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    response = Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame', direct_passthrough=True)
    return response


@app.route('/requests', methods=['POST', 'GET'])
def tasks():
    # Legacy form controls (kept for backward compatibility)
    if request.method == 'POST':
        if request.form.get('left') == 'Left':
            Cam.adjust_angles(delta_pan=5, delta_tilt=0)
        elif request.form.get('right') == 'Right':
            Cam.adjust_angles(delta_pan=-5, delta_tilt=0)
        elif request.form.get('up') == 'Up':
            Cam.adjust_angles(delta_pan=0, delta_tilt=-5)
        elif request.form.get('down') == 'Down':
            Cam.adjust_angles(delta_pan=0, delta_tilt=5)
        return render_template('index.html')
    return render_template('index.html')


@app.route('/api/state', methods=['GET'])
def api_state():
    return jsonify(Cam.get_state())


@app.route('/api/center', methods=['POST'])
def api_center():
    Cam.center()
    return jsonify(Cam.get_state())


@app.route('/api/control', methods=['POST'])
def api_control():
    payload = request.get_json(silent=True) or {}
    if 'pan' in payload or 'tilt' in payload:
        Cam.set_angles(pan=payload.get('pan'), tilt=payload.get('tilt'))
    else:
        Cam.adjust_angles(delta_pan=payload.get('deltaPan', 0), delta_tilt=payload.get('deltaTilt', 0))
    return jsonify(Cam.get_state())


def web_camera_start():
    try:
        app.run(host='0.0.0.0', port=9000, threaded=True, debug=False)
    except Exception as e:
        print(e)


@app.after_request
def add_stream_headers(response):
    # Improve compatibility with browsers/reverse proxies buffering MJPEG
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Accel-Buffering'] = 'no'  # nginx
    return response


class Cam:
    frame = None
    frame_lock = threading.Lock()
    pan = Servo(pin=13, max_angle=90, min_angle=-90)
    tilt = Servo(pin=12, max_angle=30, min_angle=-90)
    panAngle = 0
    tiltAngle = 0
    pan_step = 3
    tilt_step = 3
    detector = None
    detection_every_n_frames = 3

    @staticmethod
    def camera_start():
        flask_thread = None
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(main={"size": (1296, 972)}, transform=Transform(hflip=1, vflip=1))
        picam2.configure(config)
        picam2.start_preview()
        picam2.start()
        last_servo_apply = 0
        frame_idx = 0

        # Initialize detector (MobileNet-SSD only)
        if Cam.detector is None:
            try:
                Cam.detector = SsdCaffeDetector(
                    prototxt_path='models/MobileNetSSD_deploy.prototxt.txt',
                    model_path='models/MobileNetSSD_deploy.caffemodel',
                    conf_threshold=0.4,
                    input_size=300
                )
                print('MobileNet-SSD detector loaded')
            except Exception as e2:
                print('SSD not available:', e2)
                Cam.detector = None
        while True:
            # Picamera2 capture_array returns RGB; convert to BGR for OpenCV JPEG encoding
            rgb = picam2.capture_array()
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            # Object detection (throttled)
            if Cam.detector is not None:
                if frame_idx % Cam.detection_every_n_frames == 0:
                    detections = Cam.detector.detect(bgr)
                    Cam.detector.draw(bgr, detections)
                frame_idx += 1
            if flask_thread is None or not flask_thread.is_alive():
                flask_thread = threading.Thread(name='flask_thread', target=web_camera_start)
                flask_thread.daemon = True
                flask_thread.start()
            with Cam.frame_lock:
                Cam.frame = bgr

            # Throttle servo updates to reduce jitter
            now = time.time()
            if now - last_servo_apply >= 0.02:
                Cam.pan.set_angle(Cam.panAngle)
                Cam.tilt.set_angle(Cam.tiltAngle)
                last_servo_apply = now

    @staticmethod
    def clamp(value, min_value, max_value):
        return max(min_value, min(max_value, value))

    @staticmethod
    def adjust_angles(delta_pan=0, delta_tilt=0):
        Cam.panAngle = Cam.clamp(Cam.panAngle + int(delta_pan), Cam.pan.min_angle, Cam.pan.max_angle)
        Cam.tiltAngle = Cam.clamp(Cam.tiltAngle + int(delta_tilt), Cam.tilt.min_angle, Cam.tilt.max_angle)

    @staticmethod
    def set_angles(pan=None, tilt=None):
        if pan is not None:
            Cam.panAngle = Cam.clamp(int(pan), Cam.pan.min_angle, Cam.pan.max_angle)
        if tilt is not None:
            Cam.tiltAngle = Cam.clamp(int(tilt), Cam.tilt.min_angle, Cam.tilt.max_angle)

    @staticmethod
    def center():
        Cam.panAngle = 0
        Cam.tiltAngle = 0

    @staticmethod
    def get_state():
        return {
            'pan': Cam.panAngle,
            'tilt': Cam.tiltAngle,
            'panMin': Cam.pan.min_angle,
            'panMax': Cam.pan.max_angle,
            'tiltMin': Cam.tilt.min_angle,
            'tiltMax': Cam.tilt.max_angle,
            'detector': 'mobilenet-ssd' if Cam.detector is not None else 'none',
        }


class SsdCaffeDetector:
    # 20-class PASCAL VOC label set used by MobileNet-SSD
    CLASSES = [
        "background", "aeroplane", "bicycle", "bird", "boat",
        "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
        "dog", "horse", "motorbike", "person", "pottedplant",
        "sheep", "sofa", "train", "tvmonitor"
    ]

    def __init__(self, prototxt_path: str, model_path: str, conf_threshold: float = 0.4, input_size: int = 300):
        self.net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
        try:
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        except Exception:
            pass
        self.conf_threshold = conf_threshold
        self.input_size = input_size

    def detect(self, image_bgr):
        h, w = image_bgr.shape[:2]
        size = self.input_size
        blob = cv2.dnn.blobFromImage(cv2.resize(image_bgr, (size, size)), 0.007843, (size, size), 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()
        results = []
        # detections shape: (1, 1, N, 7): [image_id, class_id, confidence, x1, y1, x2, y2]
        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            if confidence < self.conf_threshold:
                continue
            class_id = int(detections[0, 0, i, 1])
            x1 = int(detections[0, 0, i, 3] * w)
            y1 = int(detections[0, 0, i, 4] * h)
            x2 = int(detections[0, 0, i, 5] * w)
            y2 = int(detections[0, 0, i, 6] * h)
            results.append({
                'bbox': [x1, y1, x2 - x1, y2 - y1],
                'score': confidence,
                'class_id': class_id,
                'label': self.CLASSES[class_id] if class_id < len(self.CLASSES) else str(class_id)
            })
        return results

    def draw(self, image_bgr, detections):
        for det in detections:
            x, y, w_, h_ = det['bbox']
            x2, y2 = x + w_, y + h_
            color = (0, 255, 0)
            cv2.rectangle(image_bgr, (x, y), (x2, y2), color, 2)
            label = f"{det['label']} {det['score']:.2f}"
            ((tw, th), _) = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            y_label = y - th - 6 if y - th - 6 > 0 else y + th + 6
            cv2.rectangle(image_bgr, (x, y_label - th - 2), (x + tw + 6, y_label + 2), color, -1)
            cv2.putText(image_bgr, label, (x + 3, y_label), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)


if __name__ == '__main__':
    Cam().camera_start()
