import threading
from picamera2 import Picamera2
import os
import cv2
import time

from flask import Flask, render_template, Response, request

os.environ['FLASK_ENV'] = 'development'
app = Flask(__name__)


def gen():
    while True:
        frame = cv2.flip(Cam.frame, -1)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.imencode('.jpg', frame)[1].tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    response = Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
    return response


@app.route('/requests', methods=['POST', 'GET'])
def tasks():
    if request.method == 'POST':
        if request.form.get('left') == 'Left':
            print('left')
            pass
        elif request.form.get('right') == 'Right':
            print('right')
            pass
        elif request.form.get('up') == 'Up':
            print('up')
            pass
        elif request.form.get('down') == 'Down':
            print('down')
            pass

    elif request.method == 'GET':
        return render_template('index.html')
    return render_template('index.html')


def web_camera_start():
    try:
        app.run(host='0.0.0.0', port=9000, threaded=True, debug=False)
    except Exception as e:
        print(e)


class Cam:
    frame = None

    @staticmethod
    def camera_start():
        flask_thread = None
        picam2 = Picamera2()
        picam2.start()
        while True:
            frame = picam2.capture_array()
            if flask_thread is None or not flask_thread.is_alive():
                flask_thread = threading.Thread(name='flask_thread', target=web_camera_start)
                flask_thread.setDaemon(True)
                flask_thread.start()
            Cam.frame = frame


if __name__ == '__main__':
    Cam().camera_start()
