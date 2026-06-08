"""Telegram Bot API notifier over plain HTTP (no SDK)."""

from __future__ import annotations

from typing import Optional

import requests

from . import NotifierError

API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 15


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, session: Optional[requests.Session] = None):
        self._token = token
        self._chat_id = chat_id
        self._session = session or requests.Session()

    def _url(self, method: str) -> str:
        return f"{API_BASE}/bot{self._token}/{method}"

    def send(self, text: str, image_bytes: Optional[bytes] = None) -> None:
        if image_bytes:
            url = self._url("sendPhoto")
            data = {"chat_id": self._chat_id, "caption": text}
            files = {"photo": ("region.png", image_bytes, "image/png")}
        else:
            url = self._url("sendMessage")
            data = {"chat_id": self._chat_id, "text": text}
            files = None

        resp = self._session.post(url, data=data, files=files, timeout=TIMEOUT_SECONDS)
        if not (200 <= resp.status_code < 300):
            raise NotifierError(
                f"Telegram API returned {resp.status_code}: {getattr(resp, 'text', '')}"
            )
