# changedetector

Watch an area of your screen and get a **Telegram** alert the moment something
changes there — a new email, a new chat message, a status light turning red.
It runs quietly in the background. (Windows; needs Python 3.10+.)

## Setup

**1. Install** (one time). Install Python from [python.org](https://www.python.org/downloads/), then:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
```

**2. Add your config files:**

```powershell
copy .env.example .env
copy config.example.yaml config.yaml
```

Open `.env` and paste in your Telegram bot token and chat id
(see [Getting your Telegram details](#getting-your-telegram-details) below).

**3. Pick what to watch** — a box appears; drag it over the area (e.g. your inbox):

```powershell
.venv\Scripts\python -m changedetector select --name "Inbox" --write
```

Run it again with a different name to watch more than one area.

**4. Test it:**

```powershell
.venv\Scripts\python -m changedetector test-alert
```

You should get a Telegram message with a screenshot of each watched area. If you
do, you're set.

## Run it

```powershell
.venv\Scripts\python -m changedetector run
```

Leave it running — you'll get a Telegram alert (with a screenshot) whenever a
watched area changes. Press `Ctrl-C` to stop.

## The easy way — the tray

Don't want to type commands? Double-click **`changedetector-tray.bat`**. A tray
icon appears whose colour shows the state (grey = stopped, green = running,
amber = paused). Right-click it to **Start, Pause/Resume, Stop, switch Profile,
show or add/remove areas, and Quit** — everything below, by clicking.

To have it start automatically when you log in, put a shortcut to
`changedetector-tray.bat` in your Windows Startup folder (press `Win+R`, type
`shell:startup`, drop the shortcut there).

## Everyday commands

```powershell
.venv\Scripts\python -m changedetector pause      # silence alerts while you work
.venv\Scripts\python -m changedetector resume     # turn them back on
.venv\Scripts\python -m changedetector stop       # stop the monitor
.venv\Scripts\python -m changedetector status     # running / paused / not running
.venv\Scripts\python -m changedetector show-areas # flash a box around each watched area
.venv\Scripts\python -m changedetector remove --name "Inbox"   # delete an area
```

All of these are in the tray menu too. Run `changedetector --help` for the full list.

## Profiles (optional)

A profile is a named set of areas — e.g. a `work` set and a `trading` set — that
you switch between. One is active at a time, and the areas you add/remove apply
to it.

```powershell
.venv\Scripts\python -m changedetector profile create trading   # new set, switches to it
.venv\Scripts\python -m changedetector profile switch work      # switch sets
.venv\Scripts\python -m changedetector profile list             # see them all
```

Or use the tray's **Profile ▸** menu.

## Getting your Telegram details

1. In Telegram, message **[@BotFather](https://t.me/BotFather)**, send `/newbot`,
   follow the prompts, and copy the **bot token**.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy
   the **chat id** (`result[].message.chat.id`).
4. Put both in `.env`.

Tip: set `channel: console` in `config.yaml` to try everything without Telegram —
alerts just print to the log instead.

## If something's off

- **Too many or too few alerts** — in `config.yaml`, raise `ratio_threshold` for
  fewer false alarms, or lower it to catch smaller changes.
- **Wrong spot is being watched** — run `select` again, then `test-alert` to see
  exactly what's captured.
- **No alerts while the PC is locked** — expected: a locked screen can't be read.
  Keep the machine unlocked (you can switch the monitor off).
