import argparse
import json
from datetime import UTC, datetime, timedelta

from client import AimHarderClient
from exceptions import (
    MESSAGE_ALREADY_BOOKED,
    MESSAGE_BOX_IS_CLOSED,
    AlreadyBooked,
    BookingFailed,
    BoxClosed,
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
    family_id=None,
    proxy=None,
):
    client = AimHarderClient(
        email=email, password=password, box_id=box_id, box_name=box_name, proxy=proxy
    )
    for target_day, goals in _goal_days(booking_goals):
        classes = client.get_classes(target_day, family_id)
        for goal in goals:
            _book_goal(
                client, classes, target_day, goal["time"], goal["name"], family_id
            )


def _goal_days(booking_goals):
    """(date, goals) of each configured weekday within the current week (Monday to Sunday)"""
    today = datetime.now(tz=UTC)
    for weekday, goals in booking_goals.items():
        yield today + timedelta(days=WEEKDAYS.index(weekday) - today.weekday()), goals


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
    parser.add_argument("--proxy", required=False, type=str, default=None)
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
