"""Opening hours: a readable summary and "jetzt erreichbar" / next window (Europe/Vienna)."""

from datetime import datetime
from zoneinfo import ZoneInfo

VIENNA = ZoneInfo("Europe/Vienna")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _clock(hhmm: str) -> str:
    hours, minutes = hhmm.split(":")
    return f"{int(hours)}:{minutes}"


def summary(windows: list[dict]) -> str:
    """e.g. "Mo–Mi 7:00–15:30, Do 7:00–18:00" or "täglich 8:00–20:00" or "rund um die Uhr"."""
    parts = []
    for window in windows:
        days = sorted(DAYS.index(d) for d in window["days"])
        span = f"{_clock(window['from'])}–{_clock(window['to'])}"
        if len(days) == 7:
            parts.append("rund um die Uhr" if span == "0:00–24:00" else f"täglich {span}")
            continue
        # Consecutive days become a range: Mo–Mi.
        runs: list[list[int]] = []
        for day in days:
            if runs and day == runs[-1][-1] + 1:
                runs[-1].append(day)
            else:
                runs.append([day])
        label = ", ".join(
            SHORT[r[0]] if len(r) == 1 else f"{SHORT[r[0]]}–{SHORT[r[-1]]}" for r in runs
        )
        parts.append(f"{label} {span}")
    return ", ".join(parts)


def reachable(windows: list[dict], now: datetime) -> dict:
    """Whether the channel is open now, and a short text for the card."""
    # shortcut: public holidays are not modelled; add a closed_on list per institution when sources state them.
    now = now.astimezone(VIENNA)
    minute = now.hour * 60 + now.minute
    today = now.weekday()
    for window in windows:
        if DAYS[today] in window["days"] and _minutes(window["from"]) <= minute < _minutes(window["to"]):
            if window["to"] == "24:00" and len(window["days"]) == 7:
                return {"open": True, "text": "Jetzt erreichbar, rund um die Uhr"}
            return {"open": True, "text": f"Jetzt erreichbar bis {_clock(window['to'])} Uhr"}
    for offset in range(8):
        day = (today + offset) % 7
        starts = sorted(
            _minutes(w["from"]) for w in windows
            if DAYS[day] in w["days"] and (offset or _minutes(w["from"]) > minute)
        )  # fmt: skip
        if starts:
            start = f"{starts[0] // 60}:{starts[0] % 60:02d}"
            when = "heute" if offset == 0 else "morgen" if offset == 1 else SHORT[day]
            return {"open": False, "text": f"Erreichbar {when} ab {start} Uhr"}
    return {"open": False, "text": ""}


def now() -> datetime:
    return datetime.now(VIENNA)
