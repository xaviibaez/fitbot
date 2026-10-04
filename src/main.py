import argparse
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from client import AimHarderClient
from exceptions import (
    MESSAGE_ALREADY_BOOKED,
    MESSAGE_BOX_IS_CLOSED,
    AlreadyBooked,
    BookingFailed,
    BoxClosed,
    InvalidBookingGoals,
    NoBookingGoal,
)
from logger import logger

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
DAY_NUMBERS = ("0", "1", "2", "3", "4", "5", "6")  # old format, "0" is Monday


def get_booking_goal_time(day: datetime, booking_goals):
    """Get the booking goal that satisfies the given day of the week"""
    try:
        return (
            booking_goals[str(day.weekday())]["time"],
            booking_goals[str(day.weekday())]["name"],
        )
    except KeyError:  # did not find a matching booking goal
        raise NoBookingGoal(
            f"There is no booking-goal for {day.strftime('%A, %Y-%m-%d')}."
        )


def get_class_to_book(classes: list[dict], target_time: str, class_name: str):
    if not classes or len(classes) == 0:
        raise BoxClosed(MESSAGE_BOX_IS_CLOSED)

    matches = [
        _class
        for _class in classes
        if target_time in _class["timeid"] and class_name in _class["className"]
    ]
    if not matches:
        raise NoBookingGoal(
            f"No class with the text `{class_name}` in its name at time `{target_time}`"
        )
    _class = matches[0]
    if _class["bookState"] == 1:
        raise AlreadyBooked(MESSAGE_ALREADY_BOOKED)
    return _class


def main(
    email,
    password,
    booking_goals,
    box_name,
    box_id,
    days_in_advance=None,
    family_id=None,
    proxy=None,
    timezone="UTC",
):
    today = datetime.now(tz=ZoneInfo(timezone))
    if days_in_advance is not None and _is_old_format(booking_goals):
        return _old_main(
            email,
            password,
            booking_goals,
            box_name,
            box_id,
            today + timedelta(days=days_in_advance),
            family_id,
            proxy,
        )
    _validate(booking_goals)
    client = AimHarderClient(
        email=email, password=password, box_id=box_id, box_name=box_name, proxy=proxy
    )
    for target_day, goals in _goal_days(booking_goals, today):
        classes = client.get_classes(target_day, family_id)
        for goal in goals:
            _book_goal(
                client, classes, target_day, goal["time"], goal["name"], family_id
            )


def _is_old_format(booking_goals):
    """Numeric days ("0" is Monday) with a single class each"""
    return isinstance(booking_goals, dict) and all(
        day in DAY_NUMBERS and isinstance(goal, dict)
        for day, goal in booking_goals.items()
    )


def _old_main(
    email, password, booking_goals, box_name, box_id, target_day, family_id, proxy
):
    """Behaviour before supporting the new format: book a single day"""
    try:
        target_time, target_name = get_booking_goal_time(target_day, booking_goals)
    except NoBookingGoal as e:
        logger.info(str(e))
        return
    client = AimHarderClient(
        email=email, password=password, box_id=box_id, box_name=box_name, proxy=proxy
    )
    classes = client.get_classes(target_day, family_id)
    try:
        _class = get_class_to_book(classes, target_time, target_name)
    except AlreadyBooked as e:
        logger.info(str(e))
        return
    try:
        client.book_class(target_day, _class["id"], family_id)
    except BookingFailed as e:
        logger.error(str(e))
        return
    logger.info("Class booked successfully")


def _validate(booking_goals):
    """Fail before booking anything if booking-goals is wrong"""
    if not isinstance(booking_goals, dict):
        raise InvalidBookingGoals("booking-goals must be a JSON object")
    for day, goals in booking_goals.items():
        if day not in WEEKDAYS + DAY_NUMBERS:
            raise InvalidBookingGoals(
                f"Unknown day `{day}`, use one of {', '.join(WEEKDAYS)} (or 0 to 6)"
            )
        if not isinstance(goals, dict | list):
            raise InvalidBookingGoals(f"`{day}` must be a list of classes")
        for goal in [goals] if isinstance(goals, dict) else goals:
            if not (
                isinstance(goal, dict)
                and isinstance(goal.get("time"), str)
                and re.fullmatch(r"\d{4}", goal["time"])
                and isinstance(goal.get("name"), str)
                and goal["name"].strip()
            ):
                raise InvalidBookingGoals(
                    f"Invalid class {goal!r} on `{day}`: "
                    'it needs a "time" as HHMM and a non empty "name"'
                )


def _goal_days(booking_goals, today):
    """(date, goals) of each configured weekday within the current week (Monday to
    Sunday)"""
    for day, goals in booking_goals.items():
        # numeric days ("0" is Monday) and a single class are accepted too
        weekday = int(day) if day.isdigit() else WEEKDAYS.index(day)
        goals = [goals] if isinstance(goals, dict) else goals
        yield today + timedelta(days=weekday - today.weekday()), goals


def _book_goal(client, classes, day, target_time, target_name, family_id):
    """Book one class, logging instead of raising so the rest keep going"""
    label = f"{target_name} at {target_time} on {day.strftime('%A, %Y-%m-%d')}"
    try:
        _class = get_class_to_book(classes, target_time, target_name)
        client.book_class(day, _class["id"], family_id)
        logger.info(f"{label}: class booked successfully")
    except (AlreadyBooked, NoBookingGoal, BoxClosed, BookingFailed) as e:
        logger.error(f"{label}: {e}")


if __name__ == "__main__":
    """
    python src/main.py
     --email your.email@mail.com
     --password 1234
     --box-name lahuellacrossfit
     --box-id 3984
     --booking-goals '{"monday":[{"time": "1815", "name": "Provenza"}]}'
     --family-id 123456
     --proxy socks5://89.58.45.94:34472
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, type=str)
    parser.add_argument("--password", required=True, type=str)
    parser.add_argument("--booking-goals", required=True, type=json.loads)
    parser.add_argument("--box-name", required=True, type=str)
    parser.add_argument("--box-id", required=True, type=int)
    parser.add_argument("--days-in-advance", required=False, type=int, default=None)
    parser.add_argument("--proxy", required=False, type=str, default=None)
    parser.add_argument("--timezone", required=False, type=str, default="UTC")
    parser.add_argument(
        "--family-id",
        required=False,
        type=int,
        default=None,
        help="ID of the family member (optional)",
    )
    args = parser.parse_args()
    input = {key: value for key, value in args.__dict__.items() if value != ""}
    main(**input)
