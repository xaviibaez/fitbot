import datetime
from contextlib import nullcontext as does_not_raise
from http import HTTPStatus
from unittest.mock import Mock, patch

import pytest
from freezegun import freeze_time

from constants import LOGIN_ENDPOINT, book_endpoint
from exceptions import AlreadyBooked, BoxClosed, InvalidBookingGoals, NoBookingGoal
from main import get_booking_goal_time, get_class_to_book, main

GOAL = {"time": "1700", "name": "Open Box"}


class TestGetBookingGoalTime:
    @pytest.mark.parametrize(
        "day, booking_goals, expected_time, expectation",
        (
            (
                datetime.datetime(2022, 2, 28, tzinfo=datetime.UTC),
                {"0": {"time": "1700", "name": "foo"}},
                ("1700", "foo"),
                does_not_raise(),
            ),
            (
                datetime.datetime(2022, 2, 28, tzinfo=datetime.UTC),
                {},
                None,
                pytest.raises(NoBookingGoal),
            ),
        ),
    )
    def test_get_booking_goal_time(
        self, day, booking_goals, expected_time, expectation
    ):
        with expectation:
            assert get_booking_goal_time(day, booking_goals) == expected_time


class TestGetClassToBook:
    @pytest.mark.parametrize(
        "classes, target_time, class_name, expectation",
        (
            (
                [
                    {
                        "id": 123,
                        "timeid": "1700_60",
                        "className": "foo",
                        "bookState": None,
                    }
                ],
                "1700",
                "foo",
                does_not_raise(),
            ),
            (
                [
                    {
                        "id": 123,
                        "timeid": "1700_60",
                        "className": "foo",
                        "bookState": None,
                    },
                    {
                        "id": 123,
                        "timeid": "1700_60",
                        "className": "foo",
                        "bookState": None,
                    },
                ],
                "1700",
                "foo",
                does_not_raise(),
            ),
            (
                [
                    {
                        "id": 123,
                        "timeid": "1100_60",
                        "className": "foo",
                        "bookState": None,
                    }
                ],
                "1700",
                "foo",
                pytest.raises(NoBookingGoal),
            ),
            (
                [],
                "1700",
                "foo",
                pytest.raises(BoxClosed),
            ),
            (
                [
                    {
                        "id": 123,
                        "timeid": "1700_60",
                        "className": "foo",
                        "bookState": 1,
                    }
                ],
                "1700",
                "foo",
                pytest.raises(AlreadyBooked),
            ),
        ),
    )
    def test_get_class_to_book(self, classes, target_time, class_name, expectation):
        with expectation:
            assert get_class_to_book(classes, target_time, class_name) == {
                "id": 123,
                "timeid": "1700_60",
                "className": "foo",
                "bookState": None,
            }


class TestMain:
    def mock_request_post(*args, **kwargs):
        if args[1] == LOGIN_ENDPOINT:
            return Mock(status_code=HTTPStatus.OK)
        elif args[1] == book_endpoint("foo"):
            return Mock(json=dict, status_code=HTTPStatus.OK)

    def booked(self, m_post):
        """(day, class id) of every booking request sent"""
        return [
            (call.kwargs["data"]["day"], call.kwargs["data"]["id"])
            for call in m_post.call_args_list
            if call.args[0] == book_endpoint("foo")
        ]

    @freeze_time("2022-03-04")  # Friday
    def test_main(self):
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            m_post.side_effect = self.mock_request_post
            m_get.return_value.json.return_value = {
                "bookings": [
                    {
                        "id": 123,
                        "timeid": "1700_60",
                        "className": "Provenza",
                        "bookState": None,
                    }
                ]
            }
            main(
                email="foo",
                password="bar",
                booking_goals={"monday": [{"time": "1700", "name": "Provenza"}]},
                box_name="foo",
                box_id=1,
            )
        assert self.booked(m_post) == [("20220228", 123)]  # this week's Monday

    @freeze_time("2022-02-28 09:00")
    def test_main_books_several_classes_per_day_for_the_whole_week(self):
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            m_post.side_effect = self.mock_request_post
            m_get.return_value.json.return_value = {
                "bookings": [
                    {
                        "id": 1,
                        "timeid": "1700_60",
                        "className": "Open Box A.M",
                        "bookState": None,
                    },
                    {
                        "id": 2,
                        "timeid": "1800_60",
                        "className": "WOD",
                        "bookState": None,
                    },
                ]
            }
            goals = [
                {"time": "1700", "name": "Open Box"},
                {"time": "1800", "name": "WOD"},
            ]
            main(
                email="foo",
                password="bar",
                booking_goals={
                    "monday": goals,
                    "tuesday": goals,
                    "thursday": goals,
                    "friday": goals,
                },
                box_name="foo",
                box_id=1,
            )
        assert sorted(self.booked(m_post)) == [
            ("20220228", 1),
            ("20220228", 2),
            ("20220301", 1),
            ("20220301", 2),
            ("20220303", 1),
            ("20220303", 2),
            ("20220304", 1),
            ("20220304", 2),
        ]
        assert m_get.call_count == 4  # only the configured days are fetched

    @freeze_time("2022-02-28 09:00")
    def test_main_skips_booked_or_missing_classes_and_keeps_going(self):
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            m_post.side_effect = self.mock_request_post
            m_get.return_value.json.return_value = {
                "bookings": [
                    {
                        "id": 1,
                        "timeid": "1700_60",
                        "className": "Open Box",
                        "bookState": 1,
                    },
                    {
                        "id": 2,
                        "timeid": "1800_60",
                        "className": "WOD",
                        "bookState": None,
                    },
                ]
            }
            main(
                email="foo",
                password="bar",
                booking_goals={
                    "monday": [
                        {"time": "1700", "name": "Open Box"},
                        {"time": "1900", "name": "Yoga"},
                        {"time": "1800", "name": "WOD"},
                    ],
                },
                box_name="foo",
                box_id=1,
            )
        assert self.booked(m_post) == [("20220228", 2)]

    @pytest.mark.parametrize(
        "days_in_advance, expected",
        (
            (3, [("20220303", 1)]),  # Thursday has a goal
            (1, []),  # Tuesday has no goal
        ),
    )
    @freeze_time("2022-02-28 09:00")  # Monday
    def test_main_keeps_old_format_working(self, days_in_advance, expected):
        """numeric days, one class per day and days_in_advance books a single day"""
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            m_post.side_effect = self.mock_request_post
            m_get.return_value.json.return_value = {
                "bookings": [
                    {
                        "id": 1,
                        "timeid": "1700_60",
                        "className": "Open Box A.M",
                        "bookState": None,
                    }
                ]
            }
            goal = {"time": "1700", "name": "Open Box"}
            main(
                email="foo",
                password="bar",
                booking_goals={"0": goal, "3": goal},
                box_name="foo",
                box_id=1,
                days_in_advance=days_in_advance,
            )
        assert self.booked(m_post) == expected

    @pytest.mark.parametrize(
        "booking_goals",
        (
            [{"time": "1700", "name": "Open Box"}],  # not an object
            {"Monday": [{"time": "1700", "name": "Open Box"}]},  # only lowercase
            {"lunes": [{"time": "1700", "name": "Open Box"}]},
            {"7": {"time": "1700", "name": "Open Box"}},  # out of range
            {"-1": {"time": "1700", "name": "Open Box"}},
            {"monday": None},
            {"monday": ["1700"]},
            {"monday": [{"time": "1700"}]},  # missing name
            {"monday": [{"time": "1700", "name": ""}]},  # would match any class
            {"monday": [{"time": 1700, "name": "Open Box"}]},  # not a string
            {"monday": [{"time": "17:00", "name": "Open Box"}]},  # not HHMM
            {"monday": [{"time": "60", "name": "Open Box"}]},
            # a valid day before the wrong one must not be booked either
            {
                "monday": [{"time": "1700", "name": "Open Box"}],
                "tuesday": [{"time": "1800"}],
            },
        ),
    )
    def test_main_rejects_invalid_booking_goals_before_logging_in(self, booking_goals):
        with (
            patch("requests.Session.post") as m_post,
            pytest.raises(InvalidBookingGoals),
        ):
            main(
                email="foo",
                password="bar",
                booking_goals=booking_goals,
                box_name="foo",
                box_id=1,
            )
        m_post.assert_not_called()

    @pytest.mark.parametrize(
        "timezone, expected",
        (
            ("UTC", [("20220228", 1)]),  # still Sunday: this week started Feb 28
            ("Europe/Madrid", [("20220307", 1)]),  # already Monday Mar 7
        ),
    )
    @freeze_time("2022-03-06 23:30")  # UTC
    def test_main_uses_the_given_timezone_for_today(self, timezone, expected):
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            m_post.side_effect = self.mock_request_post
            m_get.return_value.json.return_value = {
                "bookings": [
                    {
                        "id": 1,
                        "timeid": "1700_60",
                        "className": "Open Box",
                        "bookState": None,
                    }
                ]
            }
            main(
                email="foo",
                password="bar",
                booking_goals={"monday": [{"time": "1700", "name": "Open Box"}]},
                box_name="foo",
                box_id=1,
                timezone=timezone,
            )
        assert self.booked(m_post) == expected

    @freeze_time("2022-02-28 09:00")  # Monday
    def test_main_old_format_with_days_in_advance_follows_the_original_path(self):
        """original behaviour: no goal for the target day means no login at all"""
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            main(
                email="foo",
                password="bar",
                booking_goals={"0": {"time": "1700", "name": "Open Box"}},
                box_name="foo",
                box_id=1,
                days_in_advance=1,  # Tuesday
            )
        m_post.assert_not_called()
        m_get.assert_not_called()

    @pytest.mark.parametrize(
        "booking_goals, days_in_advance",
        (
            # new format: days_in_advance is ignored
            ({"monday": [GOAL], "thursday": [GOAL]}, 0),
            ({"0": [GOAL], "3": [GOAL]}, 0),
            ({"monday": GOAL, "thursday": GOAL}, 0),
            # old format without days_in_advance
            ({"0": GOAL, "3": GOAL}, None),
        ),
    )
    @freeze_time("2022-02-28 09:00")  # Monday
    def test_main_books_the_current_week_unless_old_format_with_days_in_advance(
        self, booking_goals, days_in_advance
    ):
        with (
            patch("requests.Session.post") as m_post,
            patch("requests.Session.get") as m_get,
        ):
            m_post.side_effect = self.mock_request_post
            m_get.return_value.json.return_value = {
                "bookings": [
                    {
                        "id": 1,
                        "timeid": "1700_60",
                        "className": "Open Box A.M",
                        "bookState": None,
                    }
                ]
            }
            main(
                email="foo",
                password="bar",
                booking_goals=booking_goals,
                box_name="foo",
                box_id=1,
                days_in_advance=days_in_advance,
            )
        assert sorted(self.booked(m_post)) == [("20220228", 1), ("20220303", 1)]
