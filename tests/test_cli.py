from pathlib import Path

import yaml

from changedetector.cli import _upsert_watcher
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
