from changedetector.tray import tray_state


def test_stopped_state():
    s = tray_state(running=False, paused=False)
    assert s["status"] == "Stopped"
    assert s["can_start"] is True
    assert s["can_stop"] is False
    assert s["can_pause"] is False
    assert s["can_resume"] is False


def test_running_state():
    s = tray_state(running=True, paused=False)
    assert s["status"] == "Running"
    assert s["can_start"] is False
    assert s["can_pause"] is True
    assert s["can_resume"] is False
    assert s["can_stop"] is True


def test_paused_state():
    s = tray_state(running=True, paused=True)
    assert s["status"] == "Paused"
    assert s["can_start"] is False
    assert s["can_pause"] is False
    assert s["can_resume"] is True
    assert s["can_stop"] is True


def test_paused_flag_ignored_when_not_running():
    s = tray_state(running=False, paused=True)
    assert s["status"] == "Stopped"
    assert s["can_start"] is True
    assert s["can_resume"] is False


def test_color_present_for_each_state():
    for running, paused in [(False, False), (True, False), (True, True)]:
        assert len(tray_state(running=running, paused=paused)["color"]) == 3
