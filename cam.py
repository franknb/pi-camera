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

        # Try to initialize detector (optional)
        if Cam.detector is None:
            try:
                Cam.detector = YoloV5OnnxDetector(model_path='models/yolov5n.onnx', conf_threshold=0.35, iou_threshold=0.45, input_size=416)
                print('YOLOv5n ONNX detector loaded')
            except Exception as e:
                print('Detector not available:', e)
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
            'detector': 'yolov5n' if Cam.detector is not None else 'none',
        }


class YoloV5OnnxDetector:
    # COCO class names (80 classes)
    COCO_CLASSES = [
        'person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light',
        'fire hydrant','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow',
        'elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase',
        'frisbee','skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket',
        'bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich',
        'orange','broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant',
        'bed','dining table','toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave',
        'oven','toaster','sink','refrigerator','book','clock','vase','scissors','teddy bear','hair drier','toothbrush'
    ]

    def __init__(self, model_path: str, conf_threshold: float = 0.35, iou_threshold: float = 0.45, input_size: int = 416):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.input_size = input_size  # square size

    def detect(self, image_bgr):
        h, w = image_bgr.shape[:2]
        size = self.input_size
        blob = cv2.dnn.blobFromImage(image_bgr, scalefactor=1/255.0, size=(size, size), mean=(0,0,0), swapRB=True, crop=False)
        self.net.setInput(blob)
        preds = self.net.forward()  # shape: (1, N, 85) for yolov5
        preds = np.squeeze(preds, axis=0)

        boxes = []
        confidences = []
        class_ids = []

        for det in preds:
            cx, cy, bw, bh = det[0:4]
            obj_conf = det[4]
            class_scores = det[5:]
            class_id = int(np.argmax(class_scores))
            class_conf = class_scores[class_id]
            score = obj_conf * class_conf
            if score < self.conf_threshold:
                continue
            # Convert from center-based to top-left
            x = int((cx - bw / 2) * w / self.input_size)
            y = int((cy - bh / 2) * h / self.input_size)
            width = int(bw * w / self.input_size)
            height = int(bh * h / self.input_size)
            boxes.append([x, y, width, height])
            confidences.append(float(score))
            class_ids.append(class_id)

        idxs = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.iou_threshold)
        results = []
        if len(idxs) > 0:
            for i in idxs.flatten():
                x, y, width, height = boxes[i]
                results.append({
                    'bbox': [x, y, width, height],
                    'score': confidences[i],
                    'class_id': class_ids[i],
                    'label': self.COCO_CLASSES[class_ids[i]] if class_ids[i] < len(self.COCO_CLASSES) else str(class_ids[i])
                })
        return results

    def draw(self, image_bgr, detections):
        for det in detections:
            x, y, w_, h_ = det['bbox']
            x2, y2 = x + w_, y + h_
            color = (0, 170, 255)
            cv2.rectangle(image_bgr, (x, y), (x2, y2), color, 2)
            label = f"{det['label']} {det['score']:.2f}"
            ((tw, th), _) = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(image_bgr, (x, y - th - 6), (x + tw + 6, y), color, -1)
            cv2.putText(image_bgr, label, (x + 3, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)


if __name__ == '__main__':
    Cam().camera_start()
