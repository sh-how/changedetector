# changedetector

A headless tool that watches one or more fixed areas of your screen and sends a
**Telegram** alert when something visually changes in them — a new email row, a
new chat message, a status light turning red. Inspired by
[changedetection.io](https://github.com/dgtlmoon/changedetection.io), but for
local *screen regions* instead of a web page.

It compares successive screenshots of each area (pixel diff), waits for the
change to **settle**, and then sends one alert (optionally with a screenshot of
that area). A cooldown prevents spam. Each area is independent and alerts are
labeled with the area's name.

## How it works

```
capture region (mss) → grayscale + downscale → pixel diff vs baseline
   → settle/cooldown state machine → Telegram alert (text + screenshot)
```

- **Pixel diff:** a pixel counts as "changed" only if its intensity moves by
  more than `intensity_threshold`; an *event* fires only if more than
  `ratio_threshold` of the area changed. This rejects noise (anti-aliasing,
  a blinking cursor) while catching real updates.
- **Settle + cooldown:** alerts fire once, after the change stops animating for
  `settle_ticks` polls, then stay quiet for `cooldown_seconds`.

## Install

Requires Python 3.10+ (3.11 recommended). On Windows the standard CPython build
includes `tkinter`, which the region picker needs.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
# for running the tests:
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Configure

1. **Secrets** — copy `.env.example` to `.env` and fill in your Telegram bot
   credentials (see *Telegram setup* below). `.env` is gitignored.

   ```
   CHANGEDETECTOR_TELEGRAM_BOT_TOKEN=123456789:AA...
   CHANGEDETECTOR_TELEGRAM_CHAT_ID=987654321
   ```

2. **Settings** — copy `config.example.yaml` to `config.yaml` and adjust. The
   main thing to set is the area(s) to watch (next step).

## Configure the areas to watch

Add one named area at a time by dragging a box over it:

```powershell
.venv\Scripts\python -m changedetector select --name "Inbox" --write
```

A translucent overlay covers all monitors. Drag the box (Esc cancels); with
`--write` the area is saved into `config.yaml` under `watchers:`. Run it again
with a different `--name` to add more areas; re-using a name updates that area.
Without `--write` the YAML block is printed for you to paste. (You can also add
areas from the system tray — see below.)

Each area can optionally override the global detection settings and the alert
message — see `config.example.yaml`.

Delete an area you no longer want:

```powershell
.venv\Scripts\python -m changedetector remove --name "Chat"
```

It refuses to remove the last remaining area (a config needs at least one), and
if a monitor is running it auto-restarts it so the change takes effect right
away. It's also a tray submenu — **Remove area ▸** (which asks for confirmation
first). Re-adding is just another `select --name`.

To check that your boxes line up with what you want to watch, highlight them on
screen:

```powershell
.venv\Scripts\python -m changedetector show-areas            # ~4s highlight
.venv\Scripts\python -m changedetector show-areas --seconds 8
```

This briefly draws a labeled red frame around each watched area (Esc or a click
closes it early). It's also a tray menu item — **Show watched areas**. The frame
is drawn just *outside* each region, and the monitor captures exactly the region
rectangle, so the highlight is never captured and never triggers an alert.

## Run

```powershell
.venv\Scripts\python -m changedetector run
```

Leave it running. When a watched area changes and settles, you get a Telegram
message labeled with the area name. Stop it with Ctrl-C, or from anywhere
(works on a headless monitor too):

```powershell
.venv\Scripts\python -m changedetector stop
```

## Pausing while you work

When you're actively using the inbox yourself, silence alerts without stopping
the monitor:

```powershell
.venv\Scripts\python -m changedetector pause     # suppress alerts
.venv\Scripts\python -m changedetector resume    # re-enable
.venv\Scripts\python -m changedetector status    # -> running / running (paused) / not running
```

These work against a running monitor (including a headless one) — `pause`
creates a small `config.pause` file next to your config that the monitor checks
each tick; `resume` deletes it. **On resume the baseline is reset**, so anything
that changed while you were working is absorbed and won't trigger a burst of
alerts — you only get alerted on genuinely new activity afterward. Pause is
global (it covers all areas).

Double-clickable shortcuts are included: `pause.bat` and `resume.bat` — or use
the system tray below.

## System tray — control without typing

Prefer not to remember commands? Launch the tray controller:

```powershell
.venv\Scripts\python -m changedetector tray
```

or just double-click **`changedetector-tray.bat`**. A tray icon appears whose
color shows the state (grey = stopped, green = running, amber = paused).
Right-click it for **Start / Pause / Resume / Stop / Show watched areas /
Configure area… / Remove area ▸ / Status / Quit (stops monitoring)**.

The tray controls the monitor through the same control files the CLI uses, so
the two are interchangeable: the tray can start, pause, or stop a monitor no
matter how it was launched. **Quit** stops the monitor and then closes the tray.
To keep a headless monitor running without the tray, leave it running (started
via `run` / `run-hidden.bat`) and just don't open the tray, or use the CLI.

## Other commands

```powershell
.venv\Scripts\python -m changedetector test-alert    # one labeled test alert per area (validates token + screenshots)
.venv\Scripts\python -m changedetector show-config   # print the resolved config (no secrets)
```

Run `changedetector --help` (or `<command> --help`) for the full command list.

Tip: set `channel: console` in `config.yaml` for a dry run with no Telegram —
alerts are written to the log instead.

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, follow the
   prompts, and copy the **bot token**.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and read
   `result[].message.chat.id` — that's your **chat id**.
4. Put both in `.env`, then run `changedetector test-alert`.

## Tuning detection

In `config.yaml` under `detection`:

| Setting | Effect |
|---|---|
| `intensity_threshold` (0–255) | Higher = ignore more per-pixel noise. |
| `ratio_threshold` (0–1) | Higher = a larger area must change to count. Raise it if you get false alarms; lower it to catch small changes. |
| `settle_ticks` | How many still polls before alerting. Higher = wait longer for things to stop moving. |
| `cooldown_seconds` | Minimum gap between alerts. |

`capture.poll_interval_seconds` controls how often the screen is sampled.

## Running headless / on startup

Screen capture needs an **interactive, unlocked** desktop session, so run it as
*your* user (not a Windows service / SYSTEM, which sees a black screen).

- **No console window:** double-click `run-hidden.bat` (monitor) or
  `changedetector-tray.bat` (tray) — both launch via `pythonw.exe`. Monitor
  output goes to the log file (`runtime.log_file`).
- **Stop a headless monitor:** `changedetector stop`, or the tray's **Stop**.
- **Start at logon (Task Scheduler)** — point it at the tray (recommended, so
  you can start/stop later by hand) or the bare monitor:

  ```powershell
  schtasks /create /tn "changedetector" /sc onlogon /rl limited ^
    /tr "\"D:\Projects\Personal\changedetector\.venv\Scripts\pythonw.exe\" -m changedetector tray --config \"D:\Projects\Personal\changedetector\config.yaml\""
  ```

  In Task Scheduler, ensure **"Run only when user is logged on"** is selected.

## Multi-monitor & DPI

The app makes itself per-monitor **DPI-aware** at startup so the region picker
(tkinter) and the capture (mss) share one **physical-pixel** coordinate space.
Regions are stored in absolute virtual-screen coordinates, which may be negative
for a monitor placed left of / above the primary. You can instead set
`region.monitor` (1-based) to give `left`/`top` relative to a specific monitor.

## Troubleshooting

- **Alerts when I lock/unlock the PC** — shouldn't happen: locked sessions
  capture as black frames and are skipped (`runtime.blank_frame_policy: skip`).
  If your lock screen isn't fully black, lower the watched region off it.
- **Wrong area captured** — re-run `select`; this is usually a DPI-scaling
  mismatch that the DPI-awareness step fixes. Verify with `test-alert`, which
  attaches a screenshot of exactly what's being captured.
- **Too many / too few alerts** — tune `ratio_threshold` and `settle_ticks`.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

The pure logic (diff metric + settle/cooldown state machine, multi-area config
validation, geometry, Telegram payloads, control files, the run loop via
dependency injection, launcher commands, tray state, and area-highlight
resolution) is covered by unit tests; screen capture, the selector overlay, the
area-highlight overlay, and the tray GUI are verified manually.
