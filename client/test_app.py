import datetime
import json
from types import SimpleNamespace

import app
import pytest
from app import (
    booking_results,
    build_booking_goals,
    docker_command,
    opens_on,
    week_days,
    weeks_ahead_of,
)
from exceptions import CancelFailed


def test_week_days_is_the_current_week_from_monday():
    sunday = datetime.date(2026, 10, 4)
    days = week_days(sunday)
    assert days[0] == datetime.date(2026, 9, 28)
    assert days[-1] == sunday
    assert len(days) == 7


def test_build_booking_goals_groups_selected_classes_by_weekday():
    selected = [
        {"date": "2026-10-05", "timeid": "1700_60", "name": "Open Box A.M"},
        {"date": "2026-10-08", "timeid": "1800_60", "name": "WOD"},
        {"date": "2026-10-05", "timeid": "1800_60", "name": "WOD"},
    ]
    assert build_booking_goals(selected) == {
        "monday": [
            {"time": "1700", "name": "Open Box A.M"},
            {"time": "1800", "name": "WOD"},
        ],
        "thursday": [{"time": "1800", "name": "WOD"}],
    }


def test_docker_command_keeps_credentials_out_of_the_arguments():
    goals = {"monday": [{"time": "1700", "name": "Open Box A.M"}]}
    command = docker_command("docker", "edelweissfitness", "8318", goals, 1)
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[-1] == "xaviibaez/fitbot"
    # email and password are passed by name and read from the environment
    assert command[3:7] == ["-e", "email", "-e", "password"]
    assert f"booking-goals={json.dumps(goals)}" in command
    assert "box-name=edelweissfitness" in command
    assert "box-id=8318" in command
    assert "timezone=Europe/Madrid" in command
    assert "weeks-ahead=1" in command


def test_weeks_ahead_of_selected_classes():
    sunday = datetime.date(2026, 10, 4)
    this_week = {"date": "2026-10-04", "timeid": "1700_60", "name": "WOD"}
    next_week = {"date": "2026-10-05", "timeid": "1700_60", "name": "WOD"}
    assert weeks_ahead_of([this_week], sunday) == 0
    assert weeks_ahead_of([next_week, next_week], sunday) == 1
    with pytest.raises(ValueError):
        weeks_ahead_of([this_week, next_week], sunday)  # one run books one week


def test_booking_results_matches_each_class_with_its_log_line():
    selected = [
        {"date": "2026-10-08", "timeid": "1700_60", "name": "Open Box P.M"},
        {"date": "2026-10-09", "timeid": "1600_60", "name": "Open Box P.M"},
        {"date": "2026-10-08", "timeid": "1800_60", "name": "WOD"},
        {"date": "2026-10-06", "timeid": "1700_60", "name": "WOD"},
    ]
    log = [
        "10:52:16 AM UTC - INFO - Open Box P.M at 1700 on Thursday, 2026-10-08: "
        + "class booked successfully",
        "10:52:17 AM UTC - ERROR - Open Box P.M at 1600 on Friday, 2026-10-09: "
        + "Too soon to book the class",
        "10:52:17 AM UTC - ERROR - WOD at 1800 on Thursday, 2026-10-08: "
        + "Class already booked. Nothing to do",
    ]
    assert [(r["ok"], r["message"]) for r in booking_results(selected, log)] == [
        (True, "class booked successfully"),
        (False, "Too soon to book the class"),
        (True, "Class already booked. Nothing to do"),
        (False, "El bot no dijo nada de esta clase"),
    ]


def test_opens_on_is_four_days_before_the_class():
    # Sunday 4: Thursday 8 (+4) could be booked, Friday 9 (+5) was too soon
    sunday = datetime.date(2026, 10, 4)
    assert opens_on(datetime.date(2026, 10, 8)) <= sunday
    assert opens_on(datetime.date(2026, 10, 9)) > sunday


def test_cancel_reports_each_class_and_keeps_going(monkeypatch):
    cancelled = []

    def cancel_booking(booking_id):
        if booking_id == "2":
            raise CancelFailed("Could not cancel the booking")
        cancelled.append(booking_id)

    monkeypatch.setitem(
        app.session, "client", SimpleNamespace(cancel_booking=cancel_booking)
    )
    selected = [
        {"date": "2026-10-08", "timeid": "1700_60", "name": "WOD", "booking_id": "1"},
        {"date": "2026-10-09", "timeid": "1800_60", "name": "WOD", "booking_id": "2"},
    ]
    assert [(r["ok"], r["message"]) for r in app.cancel_classes(selected)] == [
        (True, "Cancelada"),
        (False, "Could not cancel the booking"),
    ]
    assert cancelled == ["1"]
