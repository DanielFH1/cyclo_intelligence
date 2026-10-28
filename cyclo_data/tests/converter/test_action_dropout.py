"""Action streams must hold independently when a hand stops publishing."""

import pickle

import numpy as np
import pytest

from cyclo_data.converter import base_converter
from cyclo_data.converter.base_converter import (
    ConversionConfig,
    EpisodeData,
    RosbagToLerobotConverterBase,
)


def make_converter(tmp_path):
    converter = RosbagToLerobotConverterBase(
        ConversionConfig(repo_id="test/dropout", output_dir=tmp_path, fps=30)
    )
    converter._action_topic_key_map = {
        "/left": "leader_hand_left",
        "/right": "leader_hand_right",
    }
    return converter


def stream(stop=2.0, offset=0):
    return [
        (i / 100, np.array([offset + i], dtype=np.float32))
        for i in range(round(stop * 100) + 1)
    ]


def merge(converter, topics):
    return converter._merge_action_messages(
        topics, {"/left": ["left"], "/right": ["right"]}
    )


def assert_causal_values(converter, topics):
    actions = merge(converter, topics)
    episode, _ = converter._resample_to_fps(
        EpisodeData(episode_index=0), stream(), actions, 0.0
    )
    for t, actual in zip(episode.grid_log_times_sec, episode.action):
        expected = np.concatenate([
            [value for timestamp, value in topics[side] if timestamp <= t][-1]
            for side in ("/left", "/right")
        ])
        np.testing.assert_array_equal(actual, expected)
    assert episode.length > 0
    return episode


@pytest.mark.parametrize("stopped", ["/left", "/right"])
def test_stopped_hand_holds_while_live_hand_updates(tmp_path, stopped):
    converter = make_converter(tmp_path)
    topics = {"/left": stream(), "/right": stream(offset=1000)}
    topics[stopped] = topics[stopped][:51]
    episode = assert_causal_values(converter, topics)
    assert episode.length == 61
    np.testing.assert_array_equal(
        episode.action[-1], [50, 1200] if stopped == "/left" else [200, 1050]
    )


@pytest.mark.parametrize("stopped", ["/left", "/right"])
def test_reconnected_hand_resumes_without_freezing_other_hand(tmp_path, stopped):
    converter = make_converter(tmp_path)
    topics = {"/left": stream(), "/right": stream(offset=1000)}
    topics[stopped] = [(t, v) for t, v in topics[stopped] if not 0.5 < t < 1.5]
    episode = assert_causal_values(converter, topics)
    assert episode.length == 61
    np.testing.assert_array_equal(episode.action[-1], [200, 1200])


def test_asynchronous_topics_use_latest_value_without_looking_ahead(tmp_path):
    converter = make_converter(tmp_path)
    topics = {"/left": stream(), "/right": [(t + 0.003, v) for t, v in stream(offset=1000)]}
    assert_causal_values(converter, topics)


def test_no_backfill_before_each_topic_has_first_command(tmp_path):
    converter = make_converter(tmp_path)
    topics = {"/left": stream(), "/right": stream(offset=1000)[100:]}
    actions = merge(converter, topics)
    assert actions[0][0] == 1.0
    np.testing.assert_array_equal(actions[0][1], [100, 1100])


def test_empty_topic_does_not_invent_commands(tmp_path):
    converter = make_converter(tmp_path)
    assert merge(converter, {"/left": stream(), "/right": []}) == []


def test_both_hands_stop_and_hold_their_own_last_values(tmp_path):
    converter = make_converter(tmp_path)
    topics = {"/left": stream(stop=0.5), "/right": stream(stop=1.0, offset=1000)}
    episode = assert_causal_values(converter, topics)
    np.testing.assert_array_equal(episode.action[-1], [50, 1100])


def test_joint_order_is_preserved_during_dropout(tmp_path):
    converter = make_converter(tmp_path)
    converter._joint_order_by_group = {
        "leader_hand_left": ["left_b", "left_a"],
        "leader_hand_right": ["right"],
    }
    actions = converter._merge_action_messages(
        {"/left": [(0.0, np.array([10, 20]))], "/right": stream(offset=1000)},
        {"/left": ["left_a", "left_b"], "/right": ["right"]},
    )
    assert converter._action_joint_names == ["left_b", "left_a", "right"]
    np.testing.assert_array_equal(actions[-1][1], [20, 10, 1200])


def test_healthy_synchronous_streams_are_unchanged(tmp_path):
    converter = make_converter(tmp_path)
    episode = assert_causal_values(
        converter, {"/left": stream(), "/right": stream(offset=1000)}
    )
    assert episode.length == 61


@pytest.mark.parametrize("kind", ["extract", "prepared"])
def test_old_cache_is_rejected_and_current_cache_is_readable(tmp_path, kind):
    converter = make_converter(tmp_path)
    cache = tmp_path / "episode.pkl"
    current_version = (
        base_converter._EXTRACT_CACHE_VERSION if kind == "extract"
        else base_converter._PREPARED_EPISODE_CACHE_VERSION
    )
    old_version = 2 if kind == "extract" else 3
    assert current_version > old_version
    for version, should_load in ((old_version, False), (current_version, True)):
        with cache.open("wb") as handle:
            pickle.dump({"version": version, "episode": EpisodeData(0),
                         "video_file_stats": {}}, handle)
        if kind == "extract":
            result = converter._load_episode_extract_cache(cache, episode_index=0)
        else:
            result = converter._load_prepared_episode_cache(
                cache, episode_index=0, bag_path=tmp_path
            )
        assert (result is not None) == should_load
