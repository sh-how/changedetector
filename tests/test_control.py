from pathlib import Path

from changedetector.control import (
    pause_file_path,
    is_paused,
    set_paused,
    clear_paused,
    stop_file_path,
    request_stop,
    is_stop_requested,
    clear_stop,
    run_file_path,
    write_heartbeat,
    clear_heartbeat,
    is_running,
)


class TestPauseFilePath:
    def test_derived_from_config_stem_in_same_dir(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        p = pause_file_path(cfg)
        assert p == (tmp_path / "config.pause").resolve()

    def test_distinct_per_config(self, tmp_path):
        a = pause_file_path(tmp_path / "work.yaml")
        b = pause_file_path(tmp_path / "home.yaml")
        assert a != b
        assert a.name == "work.pause"
        assert b.name == "home.pause"


class TestPauseState:
    def test_absent_means_not_paused(self, tmp_path):
        assert is_paused(tmp_path / "x.pause") is False

    def test_set_then_paused(self, tmp_path):
        p = tmp_path / "x.pause"
        set_paused(p)
        assert is_paused(p) is True

    def test_clear_then_not_paused(self, tmp_path):
        p = tmp_path / "x.pause"
        set_paused(p)
        clear_paused(p)
        assert is_paused(p) is False

    def test_clear_when_absent_is_noop(self, tmp_path):
        clear_paused(tmp_path / "missing.pause")  # must not raise


class TestControlFileNames:
    def test_stop_and_run_paths(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        assert stop_file_path(cfg).name == "config.stop"
        assert run_file_path(cfg).name == "config.run"
        # pause/stop/run are distinct files for the same config
        assert len({pause_file_path(cfg), stop_file_path(cfg), run_file_path(cfg)}) == 3


class TestStopRequest:
    def test_absent_means_no_stop(self, tmp_path):
        assert is_stop_requested(tmp_path / "x.stop") is False

    def test_request_then_requested(self, tmp_path):
        p = tmp_path / "x.stop"
        request_stop(p)
        assert is_stop_requested(p) is True

    def test_clear_then_not_requested(self, tmp_path):
        p = tmp_path / "x.stop"
        request_stop(p)
        clear_stop(p)
        assert is_stop_requested(p) is False


class TestHeartbeat:
    def test_absent_is_not_running(self, tmp_path):
        assert is_running(tmp_path / "x.run", max_age=10) is False

    def test_fresh_heartbeat_is_running(self, tmp_path):
        p = tmp_path / "x.run"
        write_heartbeat(p)
        assert is_running(p, max_age=100) is True

    def test_stale_heartbeat_is_not_running(self, tmp_path):
        p = tmp_path / "x.run"
        write_heartbeat(p)
        mtime = p.stat().st_mtime
        assert is_running(p, max_age=5, now=mtime + 3) is True
        assert is_running(p, max_age=5, now=mtime + 10) is False

    def test_clear_heartbeat_stops_running(self, tmp_path):
        p = tmp_path / "x.run"
        write_heartbeat(p)
        clear_heartbeat(p)
        assert is_running(p, max_age=100) is False


class TestStaleness:
    def test_floor_at_ten_seconds(self):
        from changedetector.control import staleness_seconds
        assert staleness_seconds(1) == 10.0
        assert staleness_seconds(3) == 10.0  # 3*3=9 -> floored to 10

    def test_scales_with_poll_interval(self):
        from changedetector.control import staleness_seconds
        assert staleness_seconds(5) == 15.0
        assert staleness_seconds(60) == 180.0
