import yaml
from pathlib import Path

from changedetector.profiles import (
    read_profiles,
    create_profile,
    switch_profile,
    delete_profile,
)


def write_yaml(path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def region(x=0):
    return {"left": x, "top": 0, "width": 10, "height": 10, "monitor": None}


def flat_config():
    return {
        "watchers": [{"name": "Inbox", "region": region()}],
        "alert": {"channel": "console"},
    }


def profiles_config(active="work"):
    return {
        "active_profile": active,
        "profiles": {
            "work": {"watchers": [{"name": "Inbox", "region": region()}]},
            "trading": {"watchers": [{"name": "Chart", "region": region(50)}]},
        },
        "alert": {"channel": "console"},
    }


class TestReadProfiles:
    def test_missing_file(self, tmp_path):
        assert read_profiles(tmp_path / "nope.yaml") == ([], None)

    def test_flat_config_is_implicit_default(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, flat_config())
        assert read_profiles(p) == (["default"], "default")

    def test_profiles_with_explicit_active(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config(active="trading"))
        names, active = read_profiles(p)
        assert names == ["work", "trading"]
        assert active == "trading"

    def test_missing_active_key_defaults_to_first(self, tmp_path):
        p = tmp_path / "c.yaml"
        data = profiles_config()
        del data["active_profile"]
        write_yaml(p, data)
        assert read_profiles(p)[1] == "work"

    def test_unknown_active_falls_back_to_first(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config(active="ghost"))
        assert read_profiles(p)[1] == "work"


class TestCreateProfile:
    def test_create_migrates_flat_and_switches(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, flat_config())
        assert create_profile(p, "trading") == "created"
        data = read_yaml(p)
        assert "watchers" not in data  # flat list migrated away
        assert data["active_profile"] == "trading"
        assert data["profiles"]["trading"]["watchers"] == []
        # existing areas preserved under "default"
        assert data["profiles"]["default"]["watchers"][0]["name"] == "Inbox"
        assert data["alert"]["channel"] == "console"  # other sections untouched

    def test_create_on_profiles_config(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config())
        assert create_profile(p, "home") == "created"
        data = read_yaml(p)
        assert data["active_profile"] == "home"
        assert data["profiles"]["home"]["watchers"] == []

    def test_create_existing_name_no_change(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config())
        before = p.read_text(encoding="utf-8")
        assert create_profile(p, "work") == "exists"
        assert p.read_text(encoding="utf-8") == before


class TestSwitchProfile:
    def test_switch(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config(active="work"))
        assert switch_profile(p, "trading") == "switched"
        assert read_yaml(p)["active_profile"] == "trading"

    def test_switch_to_active_is_noop(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config(active="work"))
        assert switch_profile(p, "work") == "already_active"

    def test_switch_unknown(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config())
        assert switch_profile(p, "ghost") == "not_found"

    def test_switch_on_flat_config(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, flat_config())
        assert switch_profile(p, "default") == "already_active"
        assert switch_profile(p, "other") == "not_found"


class TestDeleteProfile:
    def test_delete_inactive(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config(active="work"))
        assert delete_profile(p, "trading") == ("deleted", None)
        data = read_yaml(p)
        assert "trading" not in data["profiles"]
        assert data["active_profile"] == "work"

    def test_delete_active_auto_switches(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config(active="work"))
        status, new_active = delete_profile(p, "work")
        assert status == "deleted"
        assert new_active == "trading"
        assert read_yaml(p)["active_profile"] == "trading"

    def test_delete_last_refused(self, tmp_path):
        p = tmp_path / "c.yaml"
        data = profiles_config()
        del data["profiles"]["trading"]
        data["active_profile"] = "work"
        write_yaml(p, data)
        assert delete_profile(p, "work") == ("last", None)
        assert "work" in read_yaml(p)["profiles"]  # unchanged

    def test_delete_unknown(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, profiles_config())
        assert delete_profile(p, "ghost") == ("not_found", None)

    def test_delete_on_flat_config(self, tmp_path):
        p = tmp_path / "c.yaml"
        write_yaml(p, flat_config())
        assert delete_profile(p, "default") == ("last", None)
        assert delete_profile(p, "other") == ("not_found", None)
