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


def test_show_areas_command():
    from changedetector.launcher import showareas_command
    cmd = showareas_command("c.yaml", python="PYW")
    assert cmd[0] == "PYW"
    assert "show-areas" in cmd
    assert cmd[-2:] == ["--config", "c.yaml"]


def test_profile_switch_command():
    from changedetector.launcher import profile_switch_command
    cmd = profile_switch_command("c.yaml", "trading", python="PYW")
    assert cmd[0] == "PYW"
    assert "profile" in cmd and "switch" in cmd and "trading" in cmd
    assert cmd[-2:] == ["--config", "c.yaml"]


def test_profile_create_command_has_no_name():
    from changedetector.launcher import profile_create_command
    cmd = profile_create_command("c.yaml", python="PYW")
    assert "profile" in cmd and "create" in cmd
    assert cmd[-2:] == ["--config", "c.yaml"]
    # no name -> the spawned command GUI-prompts for one
    assert cmd.index("create") == len(cmd) - 3


def test_remove_command_includes_name_and_confirm():
    from changedetector.launcher import remove_command
    cmd = remove_command("c.yaml", "Chat", python="PYW")
    assert cmd[0] == "PYW"
    assert "remove" in cmd
    assert "--name" in cmd and "Chat" in cmd
    assert "--confirm" in cmd  # tray-spawned removals always confirm
    assert cmd[-2:] == ["--config", "c.yaml"]
