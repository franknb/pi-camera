import threading
from picamera2 import Picamera2
from multiprocessing import Process, Manager
import os
import cv2
import time

from flask import Flask, render_template, Response

os.environ['FLASK_ENV'] = 'development'
app = Flask(__name__)


def gen():
    """Video streaming generator function."""
    while True:
        frame = cv2.imencode('.jpg', Cam.frame)[1].tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.03)


@app.route('/mjpg')
def video_feed():
    # from camera import Camera
    """Video streaming route. Put this in the src attribute of an img tag."""
    response = Response(gen(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


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
