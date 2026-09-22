"""Latest-frame HTTP previews. Original ROS images and recording are untouched."""

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

MAX_WIDTH = 424
JPEG_QUALITY = 45
PREVIEW_FPS = 12
MAX_FRAME_AGE = 0.75


def encode_preview(data):
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Invalid camera image')
    height, width = image.shape[:2]
    if width > MAX_WIDTH:
        image = cv2.resize(image, (MAX_WIDTH, max(1, round(height * MAX_WIDTH / width))),
                           interpolation=cv2.INTER_AREA)
    success, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not success:
        raise ValueError('Could not encode preview')
    return jpeg.tobytes()


@dataclass
class Camera:
    subscription: object = None
    latest: object = None
    received_at: float = 0
    requested_at: float = 0
    encoded_at: float = 0
    jpeg: bytes = b''
    jpeg_received_at: float = 0
    lock: object = field(default_factory=threading.Lock)
    encode_lock: object = field(default_factory=threading.Lock)

    def receive(self, message):
        with self.lock:
            # Replace the previous frame; never enqueue camera images.
            self.latest = message
            self.received_at = time.monotonic()

    def snapshot(self):
        with self.encode_lock:
            now = time.monotonic()
            with self.lock:
                message, received = self.latest, self.received_at
            if message is None or now - received > MAX_FRAME_AGE:
                raise TimeoutError('Waiting for a fresh camera frame')
            if not self.jpeg or now - self.encoded_at >= 1 / PREVIEW_FPS:
                self.jpeg = encode_preview(message.data)
                self.encoded_at = now
                self.jpeg_received_at = received
            age = time.monotonic() - self.jpeg_received_at
            if age > MAX_FRAME_AGE:
                raise TimeoutError('Preview frame expired')
            return self.jpeg, age


class PreviewNode(Node):
    def __init__(self):
        super().__init__('camera_preview')
        self.declare_parameter('port', 7086)
        self.cameras = {}
        self.cameras_lock = threading.Lock()
        self.create_timer(5.0, self.expire_subscriptions)
        # One OpenCV thread per request avoids competing with recorder workers.
        cv2.setNumThreads(1)

    def camera(self, topic):
        with self.cameras_lock:
            camera = self.cameras.get(topic)
            if camera is None:
                available = dict(self.get_topic_names_and_types())
                if 'sensor_msgs/msg/CompressedImage' not in available.get(topic, []):
                    raise ValueError('Compressed camera topic unavailable')
                camera = Camera()
                camera.subscription = self.create_subscription(
                    CompressedImage, topic, camera.receive,
                    QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
                self.cameras[topic] = camera
            camera.requested_at = time.monotonic()
            return camera

    def expire_subscriptions(self):
        with self.cameras_lock:
            for topic, camera in list(self.cameras.items()):
                if time.monotonic() - camera.requested_at > 30:
                    self.destroy_subscription(camera.subscription)
                    del self.cameras[topic]


def handler_for(node):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != '/snapshot':
                self.reply(404, b'Not found', 'text/plain')
                return
            try:
                topic = parse_qs(parsed.query).get('topic', [''])[0]
                jpeg, age = node.camera(topic).snapshot()
                self.reply(200, jpeg, 'image/jpeg', age)
            except (ValueError, TimeoutError) as exc:
                self.reply(503, str(exc).encode(), 'text/plain')
            except Exception as exc:
                node.get_logger().error(f'Preview failed: {exc}')
                self.reply(500, b'Preview unavailable', 'text/plain')

        def reply(self, status, body, content_type, age=0):
            try:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Expose-Headers', 'X-Frame-Age-Ms')
                self.send_header('X-Frame-Age-Ms', str(round(age * 1000, 1)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def log_message(self, *args):
            pass
    return Handler


def main(args=None):
    rclpy.init(args=args)
    node = PreviewNode()
    server = ThreadingHTTPServer(('0.0.0.0', node.get_parameter('port').value), handler_for(node))
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    node.get_logger().info(f'Camera previews ready on {server.server_port}; width <=424, JPEG 45, max 12fps')
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception:
        # SIGINT may invalidate the ROS wait set before spin raises KeyboardInterrupt.
        if rclpy.ok():
            raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
