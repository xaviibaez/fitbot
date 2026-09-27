from contextlib import nullcontext as does_not_raise
from http import HTTPStatus
from unittest.mock import Mock, patch

import pytest
from freezegun import freeze_time

from constants import LOGIN_ENDPOINT, book_endpoint
from exceptions import AlreadyBooked, BoxClosed, NoBookingGoal
from main import get_class_to_book, main


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
