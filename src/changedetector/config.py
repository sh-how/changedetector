"""Load, validate, and assemble configuration; keep secrets out of the watched file.

``config.yaml`` holds non-secret settings. Telegram credentials come from the
environment (a ``.env`` file or real env vars) and are returned in a separate
``Secrets`` object so they never live in the loggable ``AppConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import yaml

from .geometry import Region

BOT_TOKEN_ENV = "CHANGEDETECTOR_TELEGRAM_BOT_TOKEN"
CHAT_ID_ENV = "CHANGEDETECTOR_TELEGRAM_CHAT_ID"

VALID_CHANNELS = {"telegram", "console"}
VALID_BLANK_POLICIES = {"skip", "process"}


class ConfigError(Exception):
    """Raised when the configuration is missing required fields or out of range."""


@dataclass
class CaptureConfig:
    poll_interval_seconds: float = 1.0
    downscale_factor: int = 2
    grayscale: bool = True


@dataclass
class DetectionConfig:
    intensity_threshold: int = 25
    ratio_threshold: float = 0.02
    settle_ticks: int = 3
    cooldown_seconds: float = 30.0


@dataclass
class AlertConfig:
    channel: str = "console"
    message: str = "Change detected in watched region"
    attach_screenshot: bool = True
    include_timestamp: bool = True


@dataclass
class RuntimeConfig:
    blank_frame_policy: str = "skip"
    log_level: str = "INFO"
    log_file: str = "changedetector.log"


@dataclass
class Watcher:
    name: str
    region: Region
    monitor: Optional[int]
    detection: DetectionConfig
    message: str


@dataclass
class AppConfig:
    watchers: list
    capture: CaptureConfig
    alert: AlertConfig
    runtime: RuntimeConfig


@dataclass
class Secrets:
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ConfigError(message)


def _build_region(data: dict) -> tuple[Region, Optional[int]]:
    region = data.get("region")
    _require(isinstance(region, dict), "config must define a 'region' mapping")
    for key in ("left", "top", "width", "height"):
        _require(key in region, f"region is missing '{key}'")
    width, height = region["width"], region["height"]
    _require(width > 0 and height > 0, "region width and height must be positive")
    monitor = region.get("monitor")
    _require(monitor is None or monitor >= 1, "region.monitor must be >= 1 or null")
    return (
        Region(region["left"], region["top"], width, height),
        monitor,
    )


def _build_capture(data: dict) -> CaptureConfig:
    raw = data.get("capture", {})
    cap = CaptureConfig(
        poll_interval_seconds=raw.get("poll_interval_seconds", CaptureConfig.poll_interval_seconds),
        downscale_factor=raw.get("downscale_factor", CaptureConfig.downscale_factor),
        grayscale=raw.get("grayscale", CaptureConfig.grayscale),
    )
    _require(cap.poll_interval_seconds > 0, "capture.poll_interval_seconds must be > 0")
    _require(cap.downscale_factor >= 1, "capture.downscale_factor must be >= 1")
    return cap


DETECTION_KEYS = ("intensity_threshold", "ratio_threshold", "settle_ticks", "cooldown_seconds")


def _detection_from_dict(raw: dict) -> DetectionConfig:
    det = DetectionConfig(
        intensity_threshold=raw.get("intensity_threshold", DetectionConfig.intensity_threshold),
        ratio_threshold=raw.get("ratio_threshold", DetectionConfig.ratio_threshold),
        settle_ticks=raw.get("settle_ticks", DetectionConfig.settle_ticks),
        cooldown_seconds=raw.get("cooldown_seconds", DetectionConfig.cooldown_seconds),
    )
    _require(0 <= det.ratio_threshold <= 1, "detection.ratio_threshold must be in [0, 1]")
    _require(0 <= det.intensity_threshold <= 255, "detection.intensity_threshold must be in [0, 255]")
    _require(det.settle_ticks >= 1, "detection.settle_ticks must be >= 1")
    _require(det.cooldown_seconds >= 0, "detection.cooldown_seconds must be >= 0")
    return det


def _build_watcher(wdata: dict, global_detection: dict, default_message: str) -> Watcher:
    _require(isinstance(wdata, dict), "each watcher must be a mapping")
    name = wdata.get("name")
    _require(isinstance(name, str) and name.strip() != "", "each watcher needs a non-empty 'name'")
    region, monitor = _build_region(wdata)
    # per-watcher detection = global defaults overridden by any keys on the watcher
    merged = dict(global_detection)
    for key in DETECTION_KEYS:
        if key in wdata:
            merged[key] = wdata[key]
    detection = _detection_from_dict(merged)
    message = wdata.get("message", default_message)
    return Watcher(name=name, region=region, monitor=monitor, detection=detection, message=message)


def _build_watchers(data: dict, default_message: str) -> list:
    global_detection = data.get("detection", {})
    raw_watchers = data.get("watchers")

    if raw_watchers is not None:
        _require(isinstance(raw_watchers, list) and len(raw_watchers) > 0,
                 "'watchers' must be a non-empty list")
        watchers = [_build_watcher(w, global_detection, default_message) for w in raw_watchers]
    elif "region" in data:
        # legacy single-region config -> one watcher named "default"
        watchers = [_build_watcher(
            {"name": "default", "region": data["region"]}, global_detection, default_message
        )]
    else:
        raise ConfigError("config must define either 'watchers' (a list) or a single 'region'")

    names = [w.name for w in watchers]
    _require(len(names) == len(set(names)), "watcher names must be unique")
    return watchers


def _build_alert(data: dict) -> AlertConfig:
    raw = data.get("alert", {})
    alert = AlertConfig(
        channel=raw.get("channel", AlertConfig.channel),
        message=raw.get("message", AlertConfig.message),
        attach_screenshot=raw.get("attach_screenshot", AlertConfig.attach_screenshot),
        include_timestamp=raw.get("include_timestamp", AlertConfig.include_timestamp),
    )
    _require(
        alert.channel in VALID_CHANNELS,
        f"alert.channel must be one of {sorted(VALID_CHANNELS)}",
    )
    return alert


def _build_runtime(data: dict) -> RuntimeConfig:
    raw = data.get("runtime", {})
    rt = RuntimeConfig(
        blank_frame_policy=raw.get("blank_frame_policy", RuntimeConfig.blank_frame_policy),
        log_level=raw.get("log_level", RuntimeConfig.log_level),
        log_file=raw.get("log_file", RuntimeConfig.log_file),
    )
    _require(
        rt.blank_frame_policy in VALID_BLANK_POLICIES,
        f"runtime.blank_frame_policy must be one of {sorted(VALID_BLANK_POLICIES)}",
    )
    return rt


def _build_secrets(channel: str, env: Mapping[str, str]) -> Secrets:
    token = env.get(BOT_TOKEN_ENV) or None
    chat_id = env.get(CHAT_ID_ENV) or None
    if channel == "telegram":
        _require(token is not None, f"telegram alerts require {BOT_TOKEN_ENV} in the environment")
        _require(chat_id is not None, f"telegram alerts require {CHAT_ID_ENV} in the environment")
    return Secrets(telegram_bot_token=token, telegram_chat_id=chat_id)


def _assemble_app_config(data: dict) -> AppConfig:
    """Validate and assemble the non-secret AppConfig from a parsed dict."""
    alert = _build_alert(data)
    return AppConfig(
        watchers=_build_watchers(data, default_message=alert.message),
        capture=_build_capture(data),
        alert=alert,
        runtime=_build_runtime(data),
    )


def build_config(data: dict, env: Mapping[str, str]) -> tuple[AppConfig, Secrets]:
    """Validate a parsed config dict and merge secrets from ``env`` (pure)."""
    cfg = _assemble_app_config(data)
    secrets = _build_secrets(cfg.alert.channel, env)
    return cfg, secrets


def read_poll_interval(config_path, default: float = 5.0) -> float:
    """Best-effort read of capture.poll_interval_seconds, no validation/secrets.

    Used by control commands (status/tray) to size the heartbeat staleness window
    without requiring a full, secret-validated config load.
    """
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        value = (data.get("capture") or {}).get("poll_interval_seconds", default)
        value = float(value)
        return value if value > 0 else default
    except Exception:  # noqa: BLE001 - any read/parse problem -> safe default
        return default


def _read_yaml(path) -> dict:
    path = Path(path)
    _require(path.is_file(), f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    _require(isinstance(data, dict), "config file must contain a YAML mapping")
    return data


def load_app_config(path) -> AppConfig:
    """Load and validate the AppConfig (watchers etc.) without requiring secrets.

    Used by commands that only need the watched areas (e.g. show-areas), so they
    never demand a valid Telegram ``.env``.
    """
    return _assemble_app_config(_read_yaml(path))


def load_config(path, env: Optional[Mapping[str, str]] = None) -> tuple[AppConfig, Secrets]:
    """Load config from a YAML file, loading ``.env`` and merging os.environ."""
    import os

    from dotenv import load_dotenv

    load_dotenv()  # no-op if .env is absent; real env vars still take precedence
    if env is None:
        env = os.environ

    return build_config(_read_yaml(path), env)
