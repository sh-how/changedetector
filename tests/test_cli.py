from pathlib import Path

import yaml

from changedetector.cli import _upsert_watcher, _remove_watcher
from changedetector.geometry import Region


def read(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def test_creates_watchers_list_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    _upsert_watcher(str(cfg), "Inbox", Region(1, 2, 3, 4))
    data = read(cfg)
    assert data["watchers"][0]["name"] == "Inbox"
    assert data["watchers"][0]["region"]["left"] == 1
    assert data["watchers"][0]["region"]["monitor"] is None


def test_appends_distinct_names(tmp_path):
    cfg = tmp_path / "config.yaml"
    _upsert_watcher(str(cfg), "Inbox", Region(1, 2, 3, 4))
    _upsert_watcher(str(cfg), "Teams", Region(5, 6, 7, 8))
    assert [w["name"] for w in read(cfg)["watchers"]] == ["Inbox", "Teams"]


def test_same_name_updates_region_and_preserves_overrides(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {"watchers": [
                {"name": "Inbox",
                 "region": {"left": 0, "top": 0, "width": 1, "height": 1, "monitor": None},
                 "ratio_threshold": 0.09}
            ]}
        ),
        encoding="utf-8",
    )
    _upsert_watcher(str(cfg), "Inbox", Region(10, 20, 30, 40))
    watchers = read(cfg)["watchers"]
    assert len(watchers) == 1
    assert watchers[0]["region"]["left"] == 10
    assert watchers[0]["ratio_threshold"] == 0.09  # override preserved


def _two_area_config(path):
    path.write_text(
        yaml.safe_dump({"watchers": [
            {"name": "Inbox", "region": {"left": 0, "top": 0, "width": 1, "height": 1, "monitor": None}},
            {"name": "Chat", "region": {"left": 9, "top": 9, "width": 9, "height": 9, "monitor": None},
             "ratio_threshold": 0.07},
        ], "alert": {"channel": "console"}}),
        encoding="utf-8",
    )


def test_remove_existing_area(tmp_path):
    cfg = tmp_path / "config.yaml"
    _two_area_config(cfg)
    assert _remove_watcher(str(cfg), "Chat") == "removed"
    data = read(cfg)
    assert [w["name"] for w in data["watchers"]] == ["Inbox"]
    assert data["alert"]["channel"] == "console"  # other sections preserved


def test_remove_unknown_name_leaves_config_unchanged(tmp_path):
    cfg = tmp_path / "config.yaml"
    _two_area_config(cfg)
    before = cfg.read_text(encoding="utf-8")
    assert _remove_watcher(str(cfg), "Nope") == "not_found"
    assert cfg.read_text(encoding="utf-8") == before


def test_remove_last_area_is_refused(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"watchers": [
            {"name": "Inbox", "region": {"left": 0, "top": 0, "width": 1, "height": 1, "monitor": None}},
        ]}),
        encoding="utf-8",
    )
    before = cfg.read_text(encoding="utf-8")
    assert _remove_watcher(str(cfg), "Inbox") == "last"
    assert cfg.read_text(encoding="utf-8") == before  # unchanged


def test_remove_default_from_legacy_single_region_is_refused(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"region": {"left": 0, "top": 0, "width": 1, "height": 1, "monitor": None}}),
        encoding="utf-8",
    )
    assert _remove_watcher(str(cfg), "default") == "last"


def test_remove_from_missing_file(tmp_path):
    assert _remove_watcher(str(tmp_path / "nope.yaml"), "X") == "not_found"


def _profiles_cfg(tmp_path, active="work"):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({
            "active_profile": active,
            "profiles": {
                "work": {"watchers": [
                    {"name": "Inbox", "region": {"left": 0, "top": 0, "width": 1, "height": 1, "monitor": None}},
                ]},
                "trading": {"watchers": [
                    {"name": "Chart", "region": {"left": 5, "top": 0, "width": 1, "height": 1, "monitor": None}},
                ]},
            },
            "alert": {"channel": "console"},
        }, sort_keys=False),
        encoding="utf-8",
    )
    return cfg


class TestProfileTargeting:
    def test_upsert_goes_to_active_profile(self, tmp_path):
        cfg = _profiles_cfg(tmp_path, active="trading")
        _upsert_watcher(str(cfg), "News", Region(9, 9, 9, 9))
        data = read(cfg)
        assert [w["name"] for w in data["profiles"]["trading"]["watchers"]] == ["Chart", "News"]
        assert [w["name"] for w in data["profiles"]["work"]["watchers"]] == ["Inbox"]  # untouched

    def test_upsert_updates_existing_in_active_profile(self, tmp_path):
        cfg = _profiles_cfg(tmp_path, active="work")
        _upsert_watcher(str(cfg), "Inbox", Region(10, 20, 30, 40))
        data = read(cfg)
        assert data["profiles"]["work"]["watchers"][0]["region"]["left"] == 10

    def test_remove_from_active_profile_only(self, tmp_path):
        cfg = _profiles_cfg(tmp_path, active="trading")
        # "Inbox" exists only in the inactive profile -> not found from trading
        assert _remove_watcher(str(cfg), "Inbox") == "not_found"
        # "Chart" is the active profile's last area -> refused
        assert _remove_watcher(str(cfg), "Chart") == "last"

    def test_remove_works_within_active_profile(self, tmp_path):
        cfg = _profiles_cfg(tmp_path, active="trading")
        _upsert_watcher(str(cfg), "News", Region(9, 9, 9, 9))
        assert _remove_watcher(str(cfg), "Chart") == "removed"
        data = read(cfg)
        assert [w["name"] for w in data["profiles"]["trading"]["watchers"]] == ["News"]
        assert [w["name"] for w in data["profiles"]["work"]["watchers"]] == ["Inbox"]


def test_migrates_legacy_single_region(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {"region": {"left": 0, "top": 0, "width": 1, "height": 1, "monitor": None},
             "alert": {"channel": "console"}}
        ),
        encoding="utf-8",
    )
    _upsert_watcher(str(cfg), "Inbox", Region(9, 9, 9, 9))
    data = read(cfg)
    assert "region" not in data  # legacy key removed
    names = [w["name"] for w in data["watchers"]]
    assert "default" in names and "Inbox" in names
    assert data["alert"]["channel"] == "console"  # untouched sections preserved
