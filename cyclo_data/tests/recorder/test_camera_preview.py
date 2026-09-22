import time
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from cyclo_data.camera_preview_node import Camera, encode_preview


def jpeg(width, height):
    image = np.random.default_rng(1).integers(0, 255, (height, width, 3), dtype=np.uint8)
    return cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()


def test_preview_resize_recompresses_without_modifying_source():
    original = jpeg(672, 376)
    before = bytes(original)
    preview = encode_preview(original)
    decoded = cv2.imdecode(np.frombuffer(preview, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (237, 424)
    assert len(preview) < len(original) / 3
    assert original == before


def test_small_wrist_image_is_not_upscaled():
    decoded = cv2.imdecode(np.frombuffer(encode_preview(jpeg(424, 240)), np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (240, 424)


def test_camera_keeps_latest_only_and_shares_encoded_result():
    camera = Camera()
    first = SimpleNamespace(data=jpeg(672, 376))
    newest = SimpleNamespace(data=jpeg(424, 240))
    camera.receive(first); camera.receive(newest)
    assert camera.latest is newest
    encoded, _ = camera.snapshot()
    assert camera.snapshot()[0] is encoded
    assert camera.latest.data is newest.data


def test_stale_camera_is_not_served_as_live():
    camera = Camera()
    with pytest.raises(TimeoutError): camera.snapshot()
    camera.receive(SimpleNamespace(data=jpeg(424, 240)))
    camera.received_at = time.monotonic() - 2
    with pytest.raises(TimeoutError): camera.snapshot()


def test_invalid_frame_does_not_replace_good_cached_preview():
    with pytest.raises(ValueError): encode_preview(b'not jpeg')


def test_encoding_time_does_not_halve_preview_refresh_rate(monkeypatch):
    import cyclo_data.camera_preview_node as preview
    clock = [10.0]
    calls = []
    monkeypatch.setattr(preview.time, 'monotonic', lambda: clock[0])
    def encode(data):
        calls.append(data)
        clock[0] += .04
        return b'jpeg'
    monkeypatch.setattr(preview, 'encode_preview', encode)
    camera = Camera()
    camera.receive(SimpleNamespace(data=b'original'))
    camera.snapshot()
    clock[0] = 10.085
    camera.snapshot()
    assert calls == [b'original', b'original']
