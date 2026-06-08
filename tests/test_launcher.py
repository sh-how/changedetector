from changedetector.launcher import monitor_command, select_command


def test_monitor_command():
    cmd = monitor_command("config.yaml", python="PYW")
    assert cmd[0] == "PYW"
    assert cmd[1:] == ["-m", "changedetector", "run", "--config", "config.yaml"]


def test_select_command_with_name():
    cmd = select_command("c.yaml", name="Inbox", python="PYW")
    assert cmd[0] == "PYW"
    assert "select" in cmd and "--write" in cmd
    assert "--name" in cmd and "Inbox" in cmd


def test_select_command_without_name_has_no_name_flag():
    cmd = select_command("c.yaml", python="PYW")
    assert "--name" not in cmd
    assert "select" in cmd and "--write" in cmd
