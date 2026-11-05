from datetime import datetime

import pytest

from backend.hours import VIENNA, reachable, summary

PV = [
    {"days": ["mon", "tue", "wed"], "from": "07:00", "to": "15:30"},
    {"days": ["thu"], "from": "07:00", "to": "18:00"},
    {"days": ["fri"], "from": "07:00", "to": "15:00"},
]
DAILY = [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "from": "08:00", "to": "20:00"}]
ALWAYS = [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "from": "00:00", "to": "24:00"}]


def at(day: int, hhmm: str) -> datetime:
    """2026-11-02 is a Monday."""
    hour, minute = map(int, hhmm.split(":"))
    return datetime(2026, 11, 2 + day, hour, minute, tzinfo=VIENNA)


def test_summary():
    assert summary(PV) == "Mo–Mi 7:00–15:30, Do 7:00–18:00, Fr 7:00–15:00"
    assert summary(DAILY) == "täglich 8:00–20:00"
    assert summary(ALWAYS) == "rund um die Uhr"
    assert summary([{"days": ["mon", "wed", "thu"], "from": "09:00", "to": "12:00"}]) == "Mo, Mi–Do 9:00–12:00"


@pytest.mark.parametrize(
    ("hours", "now", "expected"),
    [
        (PV, at(0, "10:00"), (True, "Jetzt erreichbar bis 15:30 Uhr")),
        (PV, at(0, "06:59"), (False, "Erreichbar heute ab 7:00 Uhr")),
        (PV, at(0, "15:30"), (False, "Erreichbar morgen ab 7:00 Uhr")),
        (PV, at(3, "17:59"), (True, "Jetzt erreichbar bis 18:00 Uhr")),
        (PV, at(4, "16:00"), (False, "Erreichbar Mo ab 7:00 Uhr")),
        (PV, at(5, "10:00"), (False, "Erreichbar Mo ab 7:00 Uhr")),
        (DAILY, at(6, "21:00"), (False, "Erreichbar morgen ab 8:00 Uhr")),
        (ALWAYS, at(6, "03:00"), (True, "Jetzt erreichbar, rund um die Uhr")),
    ],
)
def test_reachable(hours, now, expected):
    result = reachable(hours, now)
    assert (result["open"], result["text"]) == expected


def test_reachable_uses_vienna_time():
    # 09:30 UTC in November is 10:30 in Vienna.
    utc = datetime.fromisoformat("2026-11-06T14:30:00+00:00")  # Friday 15:30 in Vienna
    assert reachable(PV, utc)["open"] is False
