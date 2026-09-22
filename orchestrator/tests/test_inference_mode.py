#!/usr/bin/env python3

from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace

HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "orchestrator"
    / "internal"
    / "communication"
    / "inference_mode.py"
)

spec = importlib.util.spec_from_file_location("inference_mode", HELPER_PATH)
inference_mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inference_mode)
inference_runtime_signature = inference_mode.inference_runtime_signature
inference_timing_from_task_info = inference_mode.inference_timing_from_task_info
publish_to_robot_from_task_info = inference_mode.publish_to_robot_from_task_info
publish_to_robot_override_from_task_info = (
    inference_mode.publish_to_robot_override_from_task_info
)


class InferenceModeTests(unittest.TestCase):
    def test_defaults_to_simulation(self) -> None:
        self.assertFalse(publish_to_robot_from_task_info(SimpleNamespace()))

    def test_robot_mode_enables_robot_publish(self) -> None:
        task_info = SimpleNamespace(inference_mode="robot")

        self.assertTrue(publish_to_robot_from_task_info(task_info))

    def test_simulation_mode_blocks_robot_publish(self) -> None:
        task_info = SimpleNamespace(inference_mode="simulation")

        self.assertFalse(publish_to_robot_from_task_info(task_info))

    def test_tags_support_backward_compatible_mode(self) -> None:
        task_info = SimpleNamespace(tags=["inference_mode:robot"])

        self.assertTrue(publish_to_robot_from_task_info(task_info))

    def test_timing_uses_task_info_values(self) -> None:
        task_info = SimpleNamespace(
            control_hz=80,
            inference_hz=20,
            chunk_align_window_s=0.25,
        )

        self.assertEqual(
            inference_timing_from_task_info(task_info),
            (80, 20, 0.25),
        )

    def test_timing_falls_back_for_missing_or_invalid_values(self) -> None:
        self.assertEqual(
            inference_timing_from_task_info(SimpleNamespace()),
            (100, 15, 0.3),
        )
        self.assertEqual(
            inference_timing_from_task_info(SimpleNamespace(
                control_hz=0,
                inference_hz=-1,
                chunk_align_window_s=float("nan"),
            )),
            (100, 15, 0.3),
        )

    def test_runtime_signature_changes_with_each_timing_value(self) -> None:
        base = inference_runtime_signature(
            "/models/policy", "pytorch", "", "async", 100, 15, 0.3
        )

        self.assertEqual(
            base,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 100, 15, 0.3
            ),
        )
        self.assertNotEqual(
            base,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 80, 15, 0.3
            ),
        )
        self.assertNotEqual(
            base,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 100, 20, 0.3
            ),
        )
        self.assertNotEqual(
            base,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 100, 15, 0.2
            ),
        )

    def test_runtime_signature_changes_with_initial_pose_sync(self) -> None:
        base = inference_runtime_signature(
            "/models/policy", "pytorch", "", "async", 100, 15, 0.3,
            False, 5.0,
        )

        self.assertNotEqual(
            base,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 100, 15, 0.3,
                True, 5.0,
            ),
        )
        self.assertEqual(
            base,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 100, 15, 0.3,
                False, 7.5,
            ),
        )
        enabled = inference_runtime_signature(
            "/models/policy", "pytorch", "", "async", 100, 15, 0.3,
            True, 5.0,
        )
        self.assertNotEqual(
            enabled,
            inference_runtime_signature(
                "/models/policy", "pytorch", "", "async", 100, 15, 0.3,
                True, 7.5,
            ),
        )
    def test_resume_override_accepts_explicit_robot_and_simulation(self) -> None:
        self.assertTrue(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(inference_mode="robot")
            )
        )
        self.assertFalse(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(inference_mode="simulation")
            )
        )

    def test_start_defaults_completely_absent_mode_to_simulation(self) -> None:
        override = publish_to_robot_override_from_task_info(SimpleNamespace())

        self.assertIsNone(override)
        self.assertFalse(bool(override))

    def test_start_accepts_current_ui_matching_field_and_tag(self) -> None:
        self.assertTrue(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(
                    inference_mode="robot",
                    tags=["inference_mode:robot"],
                )
            )
        )
        self.assertFalse(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(
                    inference_mode="simulation",
                    tags=["inference_mode:simulation"],
                )
            )
        )

    def test_resume_override_preserves_loaded_mode_for_legacy_payload(self) -> None:
        self.assertIsNone(
            publish_to_robot_override_from_task_info(SimpleNamespace())
        )
        self.assertIsNone(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(inference_mode="")
            )
        )

    def test_resume_override_accepts_backward_compatible_tags(self) -> None:
        self.assertTrue(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(
                    inference_mode="",
                    tags=["inference_mode:robot"],
                )
            )
        )
        self.assertFalse(
            publish_to_robot_override_from_task_info(
                SimpleNamespace(
                    inference_mode="",
                    tags=["publish_to_robot:false"],
                )
            )
        )

    def test_resume_override_rejects_invalid_explicit_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid inference_mode"):
            publish_to_robot_override_from_task_info(
                SimpleNamespace(inference_mode="simulaton")
            )
        with self.assertRaisesRegex(ValueError, "Invalid inference mode tag"):
            publish_to_robot_override_from_task_info(
                SimpleNamespace(
                    inference_mode="",
                    tags=["inference_mode:simulaton"],
                )
            )

    def test_resume_override_rejects_conflicting_field_and_tag(self) -> None:
        with self.assertRaisesRegex(ValueError, "Conflicting inference modes"):
            publish_to_robot_override_from_task_info(
                SimpleNamespace(
                    inference_mode="robot",
                    tags=["inference_mode:simulation"],
                )
            )


if __name__ == "__main__":
    unittest.main()
