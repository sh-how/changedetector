"""Listen for Telegram commands (/pause, /resume) via long-polling getUpdates.

Inbound counterpart to the outbound notifier. Runs as a sidecar thread while the
monitor is active. Only acts on messages from the configured chat id, and maps
commands onto the existing pause file (so the monitor's normal pause check and
rebaseline-on-resume do the rest). No server or open port — long-polling only.
"""

from __future__ import annotations

import logging
import threading

from .control import clear_paused, set_paused

log = logging.getLogger("changedetector.telegram_commands")

API_BASE = "https://api.telegram.org"

COMMANDS = {"/pause": "pause", "/resume": "resume"}

_REPLIES = {
    "pause": "Paused - alerts off.",
    "resume": "Resumed - monitoring active.",
}


def parse_commands(updates_json: dict, allowed_chat_id) -> list:
    """Recognized commands from messages sent by ``allowed_chat_id`` (order kept).

    Ignores other chats, non-message updates, textless messages, and unknown
    commands. A trailing ``@botname`` on the command is stripped.
    """
    commands = []
    for update in updates_json.get("result", []):
        message = update.get("message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat") or {}
        if str(chat.get("id")) != str(allowed_chat_id):
            continue
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        token = text.strip().split()[0].split("@", 1)[0].lower()
        command = COMMANDS.get(token)
        if command:
            commands.append(command)
    return commands


def next_offset(updates_json: dict, current):
    """The getUpdates offset to request next: max processed update_id + 1."""
    ids = [u["update_id"] for u in updates_json.get("result", []) if "update_id" in u]
    return max(ids) + 1 if ids else current


def apply_command(command: str, pause_path) -> str:
    """Perform a command's side effect; return the reply text (or None if unknown)."""
    if command == "pause":
        set_paused(pause_path)
    elif command == "resume":
        clear_paused(pause_path)
    return _REPLIES.get(command)


class CommandPoller:
    """Polls Telegram for commands and applies them. Inject ``session`` in tests."""

    def __init__(self, token, chat_id, pause_path, notifier=None, session=None, poll_timeout=20):
        self._token = token
        self._chat_id = chat_id
        self._pause_path = pause_path
        self._notifier = notifier
        self._poll_timeout = poll_timeout
        self._offset = None
        self._stop = threading.Event()
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    def _get_updates(self, offset, timeout) -> dict:
        params = {"timeout": timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        resp = self._session.get(
            f"{API_BASE}/bot{self._token}/getUpdates",
            params=params,
            timeout=timeout + 10,
        )
        return resp.json()

    def drain_backlog(self) -> None:
        """Skip any messages already queued before startup (don't act on them)."""
        data = self._get_updates(None, timeout=0)
        if data.get("ok"):
            self._offset = next_offset(data, self._offset)

    def poll_once(self) -> bool:
        """One getUpdates cycle. Returns False if the API response wasn't ok
        (e.g. bad token) so the caller can back off instead of tight-looping."""
        data = self._get_updates(self._offset, timeout=self._poll_timeout)
        if not data.get("ok"):
            return False
        for command in parse_commands(data, self._chat_id):
            reply = apply_command(command, self._pause_path)
            log.info("telegram command: /%s", command)
            if self._notifier and reply:
                try:
                    self._notifier.send(reply)
                except Exception:  # noqa: BLE001 - a failed reply must not stop polling
                    log.exception("failed to send command reply")
        self._offset = next_offset(data, self._offset)
        return True

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            self.drain_backlog()
        except Exception:  # noqa: BLE001 - keep going even if the first call fails
            log.exception("telegram getUpdates backlog drain failed")
        while not self._stop.is_set():
            try:
                if not self.poll_once():  # not-ok response (e.g. bad token): back off
                    self._stop.wait(5)
            except Exception:  # noqa: BLE001 - transient network errors shouldn't kill the loop
                log.exception("telegram getUpdates poll failed; retrying")
                self._stop.wait(5)
