#!/usr/bin/env python3

from __future__ import annotations

from collections import deque
import importlib.util
from pathlib import Path
import sys
import threading
import time
import types
import unittest

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[4]
ROBOT_CLIENT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = REPO_ROOT / "shared" / "shared" / "robot_configs"
for path in (ROBOT_CLIENT_ROOT, SCHEMA_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

zenoh_stub = types.ModuleType("zenoh_ros2_sdk")
zenoh_stub.ROS2Publisher = object
zenoh_stub.ROS2Subscriber = object
zenoh_stub.ROS2ServiceServer = object
zenoh_stub.get_message_class = lambda _name: object
sys.modules.setdefault("zenoh_ros2_sdk", zenoh_stub)

cv2_stub = types.ModuleType("cv2")
cv2_stub.IMREAD_COLOR = 1
cv2_stub.COLOR_BGR2RGB = 4
sys.modules.setdefault("cv2", cv2_stub)

MODULE_PATH = ROBOT_CLIENT_ROOT / "robot_client" / "robot_client.py"
spec = importlib.util.spec_from_file_location(
    "robot_client_joint_history_module",
    MODULE_PATH,
)
robot_client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(robot_client_module)
RobotClient = robot_client_module.RobotClient


class JointPositionHistoryTests(unittest.TestCase):
    def _robot(self, samples) -> RobotClient:
        robot = RobotClient.__new__(RobotClient)
        robot._lock = threading.Lock()
        # These tests exercise a data-only object without live subscriptions.
        robot._closed = True
        robot._config = {
            "joint_groups": {
                "follower_upper_body": {
                    "joint_names": ["joint_a", "joint_b", "joint_c"],
                },
            },
        }
        robot._joint_history_samples = {
            "follower_upper_body": deque(samples, maxlen=512),
        }
        return robot

    def test_resamples_causally_and_preserves_requested_joint_order(self) -> None:
        now = time.monotonic()
        samples = [
            (
                now - 0.1 * (5 - index),
                np.asarray([index, index + 10, index + 20], dtype=np.float32),
            )
            for index in range(6)
        ]
        robot = self._robot(samples)

        history = robot.get_joint_position_history(
            ["joint_c", "joint_a"],
            history_size=6,
            sample_hz=10.0,
        )

        np.testing.assert_allclose(
            history,
            np.asarray([[20, 0], [21, 1], [22, 2], [23, 3], [24, 4], [25, 5]]),
        )
        self.assertEqual(history.dtype, np.float32)

    def test_rejects_incomplete_history_window(self) -> None:
        now = time.monotonic()
        robot = self._robot(
            [
                (now - 0.1, np.asarray([0, 1, 2], dtype=np.float32)),
                (now, np.asarray([3, 4, 5], dtype=np.float32)),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "warmup incomplete"):
            robot.get_joint_position_history(
                ["joint_a"],
                history_size=6,
                sample_hz=10.0,
            )

    def test_rejects_stale_latest_sample(self) -> None:
        now = time.monotonic()
        robot = self._robot(
            [
                (
                    now - 1.0 + index * 0.1,
                    np.asarray([index, index, index], dtype=np.float32),
                )
                for index in range(6)
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "stale"):
            robot.get_joint_position_history(
                ["joint_a"],
                history_size=6,
                sample_hz=10.0,
            )


if __name__ == "__main__":
    unittest.main()
