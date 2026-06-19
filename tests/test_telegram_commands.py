from unittest import mock

from changedetector.telegram_commands import (
    parse_commands,
    next_offset,
    apply_command,
    CommandPoller,
)


def upd(update_id, chat_id, text):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def resp(*updates):
    return {"ok": True, "result": list(updates)}


class TestParseCommands:
    def test_pause_and_resume_from_allowed_chat(self):
        data = resp(upd(1, 42, "/pause"), upd(2, 42, "/resume"))
        assert parse_commands(data, "42") == ["pause", "resume"]

    def test_bot_suffix_is_stripped(self):
        assert parse_commands(resp(upd(1, 42, "/pause@MyBot")), 42) == ["pause"]

    def test_chat_id_type_mismatch_still_matches(self):
        # JSON chat id is int, configured id is str -> compared as strings
        assert parse_commands(resp(upd(1, 42, "/pause")), "42") == ["pause"]

    def test_other_chat_is_ignored(self):
        assert parse_commands(resp(upd(1, 999, "/pause")), "42") == []

    def test_unknown_command_ignored(self):
        assert parse_commands(resp(upd(1, 42, "/delete-everything")), "42") == []

    def test_non_message_updates_ignored(self):
        data = {"ok": True, "result": [{"update_id": 1, "edited_message": {"text": "/pause"}}]}
        assert parse_commands(data, "42") == []

    def test_message_without_text_ignored(self):
        data = {"ok": True, "result": [{"update_id": 1, "message": {"chat": {"id": 42}}}]}
        assert parse_commands(data, "42") == []

    def test_mixed_keeps_only_authorized_known(self):
        data = resp(
            upd(1, 42, "/pause"),
            upd(2, 999, "/pause"),      # wrong chat
            upd(3, 42, "/nope"),        # unknown
            upd(4, 42, "/resume"),
        )
        assert parse_commands(data, "42") == ["pause", "resume"]

    def test_empty(self):
        assert parse_commands({"ok": True, "result": []}, "42") == []

    def test_help_and_areas_recognized(self):
        data = resp(upd(1, 42, "/help"), upd(2, 42, "/areas"))
        assert parse_commands(data, "42") == ["help", "areas"]


class TestNextOffset:
    def test_advances_past_max(self):
        assert next_offset(resp(upd(10, 42, "x"), upd(12, 42, "y")), 5) == 13

    def test_empty_keeps_current(self):
        assert next_offset({"ok": True, "result": []}, 7) == 7

    def test_empty_with_none_current(self):
        assert next_offset({"ok": True, "result": []}, None) is None


class TestApplyCommand:
    def test_pause_sets_file(self, tmp_path):
        from changedetector.control import is_paused
        p = tmp_path / "c.pause"
        reply = apply_command("pause", p)
        assert is_paused(p) is True
        assert "paus" in reply.lower()

    def test_resume_clears_file(self, tmp_path):
        from changedetector.control import is_paused, set_paused
        p = tmp_path / "c.pause"
        set_paused(p)
        reply = apply_command("resume", p)
        assert is_paused(p) is False
        assert "resum" in reply.lower()

    def test_unknown_returns_none(self, tmp_path):
        assert apply_command("explode", tmp_path / "c.pause") is None

    def test_help_lists_commands_no_side_effect(self, tmp_path):
        from changedetector.control import is_paused
        p = tmp_path / "c.pause"
        reply = apply_command("help", p)
        for token in ("/pause", "/resume", "/areas", "/help"):
            assert token in reply
        assert is_paused(p) is False  # read-only

    def test_areas_lists_watched_areas(self, tmp_path):
        reply = apply_command("areas", tmp_path / "c.pause", area_names=["Inbox", "Chat"])
        assert "Inbox" in reply and "Chat" in reply
        assert "2" in reply
        assert "Profile" not in reply  # no profile -> no profile line

    def test_areas_includes_profile_when_set(self, tmp_path):
        reply = apply_command("areas", tmp_path / "c.pause", area_names=["Inbox"], profile="work")
        assert "Profile: work" in reply
        assert "Inbox" in reply

    def test_areas_with_none_is_graceful(self, tmp_path):
        reply = apply_command("areas", tmp_path / "c.pause", area_names=None)
        assert "no areas" in reply.lower()


def fake_session(json_obj):
    s = mock.Mock()
    s.get.return_value = mock.Mock(json=lambda: json_obj)
    return s


class TestCommandPoller:
    def test_poll_once_applies_and_replies_and_advances_offset(self, tmp_path):
        from changedetector.control import is_paused
        p = tmp_path / "c.pause"
        notifier = mock.Mock()
        session = fake_session(resp(upd(7, 42, "/pause")))
        poller = CommandPoller("TOKEN", "42", p, notifier=notifier, session=session)
        poller.poll_once()
        assert is_paused(p) is True
        notifier.send.assert_called_once()
        assert poller._offset == 8  # advanced past update 7

    def test_poll_once_ignores_other_chat(self, tmp_path):
        from changedetector.control import is_paused
        p = tmp_path / "c.pause"
        notifier = mock.Mock()
        poller = CommandPoller("TOKEN", "42", p, notifier=notifier,
                               session=fake_session(resp(upd(7, 999, "/pause"))))
        poller.poll_once()
        assert is_paused(p) is False
        notifier.send.assert_not_called()

    def test_poll_once_areas_reports_watched_areas(self, tmp_path):
        notifier = mock.Mock()
        poller = CommandPoller("TOKEN", "42", tmp_path / "c.pause", notifier=notifier,
                               session=fake_session(resp(upd(7, 42, "/areas"))),
                               area_names=["Inbox", "Chat"], profile="work")
        poller.poll_once()
        sent = notifier.send.call_args[0][0]
        assert "Inbox" in sent and "Chat" in sent and "work" in sent

    def test_drain_backlog_sets_offset_without_acting(self, tmp_path):
        from changedetector.control import is_paused
        p = tmp_path / "c.pause"
        session = fake_session(resp(upd(3, 42, "/pause"), upd(4, 42, "/resume")))
        poller = CommandPoller("TOKEN", "42", p, session=session)
        poller.drain_backlog()
        assert is_paused(p) is False     # backlog commands NOT executed
        assert poller._offset == 5       # but offset moved past them
