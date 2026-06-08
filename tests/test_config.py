import pytest

from changedetector.config import build_config, AppConfig, Watcher, Secrets, ConfigError
from changedetector.geometry import Region


def base_data():
    return {
        "watchers": [
            {
                "name": "Inbox",
                "region": {"left": 10, "top": 20, "width": 640, "height": 200, "monitor": None},
                "ratio_threshold": 0.08,  # per-area override
                "message": "New mail",
            },
            {
                "name": "Teams",
                "region": {"left": 1500, "top": 800, "width": 400, "height": 200},
            },
        ],
        "capture": {"poll_interval_seconds": 1.0, "downscale_factor": 2, "grayscale": True},
        "detection": {
            "intensity_threshold": 25,
            "ratio_threshold": 0.02,
            "settle_ticks": 3,
            "cooldown_seconds": 30,
        },
        "alert": {
            "channel": "telegram",
            "message": "Change detected",
            "attach_screenshot": True,
            "include_timestamp": True,
        },
        "runtime": {"blank_frame_policy": "skip", "log_level": "INFO", "log_file": "x.log"},
    }


TELEGRAM_ENV = {
    "CHANGEDETECTOR_TELEGRAM_BOT_TOKEN": "123:abc",
    "CHANGEDETECTOR_TELEGRAM_CHAT_ID": "999",
}


class TestWatchers:
    def test_builds_all_watchers(self):
        cfg, _ = build_config(base_data(), TELEGRAM_ENV)
        assert isinstance(cfg, AppConfig)
        assert [w.name for w in cfg.watchers] == ["Inbox", "Teams"]
        assert all(isinstance(w, Watcher) for w in cfg.watchers)
        assert cfg.watchers[0].region == Region(10, 20, 640, 200)

    def test_per_watcher_override_and_fallback(self):
        cfg, _ = build_config(base_data(), TELEGRAM_ENV)
        inbox, teams = cfg.watchers
        # Inbox overrides ratio_threshold but inherits intensity_threshold
        assert inbox.detection.ratio_threshold == 0.08
        assert inbox.detection.intensity_threshold == 25
        # Teams overrides nothing -> all global defaults
        assert teams.detection.ratio_threshold == 0.02
        assert teams.detection.settle_ticks == 3

    def test_message_override_and_default(self):
        cfg, _ = build_config(base_data(), TELEGRAM_ENV)
        assert cfg.watchers[0].message == "New mail"
        assert cfg.watchers[1].message == "Change detected"  # falls back to alert.message

    def test_region_monitor_preserved(self):
        data = base_data()
        data["watchers"][0]["region"]["monitor"] = 2
        cfg, _ = build_config(data, TELEGRAM_ENV)
        assert cfg.watchers[0].monitor == 2


class TestReadPollInterval:
    def test_reads_value(self, tmp_path):
        from changedetector.config import read_poll_interval
        p = tmp_path / "c.yaml"
        p.write_text("capture:\n  poll_interval_seconds: 7\n", encoding="utf-8")
        assert read_poll_interval(str(p)) == 7.0

    def test_default_when_missing(self, tmp_path):
        from changedetector.config import read_poll_interval
        p = tmp_path / "c.yaml"
        p.write_text("watchers: []\n", encoding="utf-8")
        assert read_poll_interval(str(p), default=5.0) == 5.0

    def test_default_when_file_absent(self, tmp_path):
        from changedetector.config import read_poll_interval
        assert read_poll_interval(str(tmp_path / "nope.yaml"), default=5.0) == 5.0


class TestLegacySingleRegion:
    def test_single_region_becomes_one_watcher(self):
        data = {
            "region": {"left": 0, "top": 0, "width": 100, "height": 100},
            "alert": {"channel": "console", "message": "hi"},
        }
        cfg, _ = build_config(data, {})
        assert len(cfg.watchers) == 1
        w = cfg.watchers[0]
        assert w.name == "default"
        assert w.region == Region(0, 0, 100, 100)
        assert w.message == "hi"
        assert w.detection.ratio_threshold == 0.02  # global default

    def test_minimal_config_uses_defaults(self):
        cfg, _ = build_config({"region": {"left": 0, "top": 0, "width": 10, "height": 10}}, {})
        assert cfg.alert.channel == "console"
        assert cfg.capture.poll_interval_seconds > 0


class TestSecretValidation:
    def test_telegram_missing_token_raises_named_error(self):
        with pytest.raises(ConfigError) as exc:
            build_config(base_data(), {"CHANGEDETECTOR_TELEGRAM_CHAT_ID": "999"})
        assert "CHANGEDETECTOR_TELEGRAM_BOT_TOKEN" in str(exc.value)

    def test_console_channel_needs_no_secrets(self):
        data = base_data()
        data["alert"]["channel"] = "console"
        cfg, secrets = build_config(data, {})
        assert secrets.telegram_bot_token is None


class TestValidation:
    def test_missing_watchers_and_region_raises(self):
        with pytest.raises(ConfigError):
            build_config({"alert": {"channel": "console"}}, {})

    def test_empty_watchers_list_raises(self):
        data = base_data()
        data["watchers"] = []
        with pytest.raises(ConfigError):
            build_config(data, TELEGRAM_ENV)

    def test_duplicate_names_raise(self):
        data = base_data()
        data["watchers"][1]["name"] = "Inbox"
        with pytest.raises(ConfigError):
            build_config(data, TELEGRAM_ENV)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d["watchers"][0].update(name=""),
            lambda d: d["watchers"][0].pop("name"),
            lambda d: d["watchers"][0]["region"].update(width=0),
            lambda d: d["watchers"][0].update(ratio_threshold=1.5),
            lambda d: d["watchers"][1].update(settle_ticks=0),
            lambda d: d["detection"].update(intensity_threshold=300),
            lambda d: d["alert"].update(channel="carrier-pigeon"),
            lambda d: d["runtime"].update(blank_frame_policy="nonsense"),
            lambda d: d["capture"].update(poll_interval_seconds=0),
        ],
    )
    def test_invalid_values_raise(self, mutate):
        data = base_data()
        mutate(data)
        with pytest.raises(ConfigError):
            build_config(data, TELEGRAM_ENV)
