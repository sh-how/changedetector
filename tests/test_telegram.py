from unittest import mock

import pytest

from changedetector.config import Secrets
from changedetector.notifier import build_notifier, NotifierError
from changedetector.notifier.telegram import TelegramNotifier
from changedetector.notifier.console import ConsoleNotifier


def ok_session():
    session = mock.Mock()
    session.post.return_value = mock.Mock(status_code=200, ok=True, text="ok")
    return session


class TestTelegramSend:
    def test_text_only_uses_sendmessage(self):
        session = ok_session()
        n = TelegramNotifier("TOKEN", "CHAT", session=session)
        n.send("hello")
        session.post.assert_called_once()
        args, kwargs = session.post.call_args
        assert args[0].endswith("/sendMessage")
        assert "TOKEN" in args[0]
        assert kwargs["data"]["chat_id"] == "CHAT"
        assert kwargs["data"]["text"] == "hello"
        assert not kwargs.get("files")

    def test_with_image_uses_sendphoto(self):
        session = ok_session()
        n = TelegramNotifier("TOKEN", "CHAT", session=session)
        n.send("caption here", image_bytes=b"PNGDATA")
        args, kwargs = session.post.call_args
        assert args[0].endswith("/sendPhoto")
        assert kwargs["data"]["chat_id"] == "CHAT"
        assert kwargs["data"]["caption"] == "caption here"
        assert "photo" in kwargs["files"]
        # the raw bytes are carried in the multipart payload
        assert b"PNGDATA" in kwargs["files"]["photo"]

    def test_non_2xx_raises(self):
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=400, ok=False, text="bad request")
        n = TelegramNotifier("TOKEN", "CHAT", session=session)
        with pytest.raises(NotifierError):
            n.send("boom")


class TestBuildNotifier:
    def test_console_channel(self):
        n = build_notifier("console", Secrets())
        assert isinstance(n, ConsoleNotifier)

    def test_telegram_channel(self):
        n = build_notifier("telegram", Secrets("tok", "chat"))
        assert isinstance(n, TelegramNotifier)

    def test_console_send_does_not_raise(self):
        # console notifier is the safe dry-run path; must never throw
        build_notifier("console", Secrets()).send("msg", image_bytes=b"x")
