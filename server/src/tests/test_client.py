import datetime
from contextlib import nullcontext as does_not_raise
from http import HTTPStatus
from unittest.mock import patch

import pytest
from requests import Session
from requests.exceptions import HTTPError

from client import AimHarderClient
from constants import cancel_endpoint
from exceptions import (
    MESSAGE_BOOKING_FAILED_NO_CREDIT,
    MESSAGE_BOOKING_FAILED_UNKNOWN,
    MESSAGE_CANCEL_FAILED,
    MESSAGE_TOO_SOON_TO_BOOK,
    BookingFailed,
    CancelFailed,
    IncorrectCredentials,
    TooManyWrongAttempts,
)

LOGIN_OK = {
    "info": {
        "version": "1.0",
        "copyright": "Copyright © 2026 Aimharder Global. All rights reserved.",
    }
}


def login_error(message):
    return {"error": {"code": 401, "message": message}, "info": LOGIN_OK["info"]}


class TestAimHarderClient:
    @pytest.mark.parametrize(
        "status_code, response, expectation",
        (
            (HTTPStatus.OK, LOGIN_OK, does_not_raise()),
            (
                HTTPStatus.UNAUTHORIZED,
                login_error(TooManyWrongAttempts.key_phrase),
                pytest.raises(TooManyWrongAttempts),
            ),
            (
                HTTPStatus.UNAUTHORIZED,
                login_error(IncorrectCredentials.key_phrase),
                pytest.raises(IncorrectCredentials),
            ),
            (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                login_error("LOGIN_ERROR_SOMETHING_ELSE"),
                pytest.raises(HTTPError),
            ),
        ),
    )
    def test_init(self, status_code, response, expectation):
        with expectation, patch("requests.Session.post") as m_post:
            m_post.return_value.status_code = status_code
            m_post.return_value.json.return_value = response
            m_post.return_value.raise_for_status.side_effect = HTTPError
            AimHarderClient(email="foo", password="bar", box_id=1, box_name="foo")

    def test__login(self):
        with patch("requests.Session.post") as m_post:
            m_post.return_value.status_code = HTTPStatus.OK
            m_post.return_value.json.return_value = LOGIN_OK
            assert isinstance(
                AimHarderClient._login(email="foo", password="bar"), Session
            )

    def test__login_request_body(self):
        with patch("requests.Session.post") as m_post:
            m_post.return_value.status_code = HTTPStatus.OK
            m_post.return_value.json.return_value = LOGIN_OK
            AimHarderClient._login(email="foo", password="bar")

        assert m_post.call_args.kwargs["data"] == (
            '{"username":"foo","password":"bar","iniframe":0}'
        )

    @pytest.mark.parametrize(
        "response, expected_classes",
        (
            (
                {},
                None,
            ),
            (
                {"bookings": []},
                [],
            ),
            (
                {"bookings": [{"id": 123, "timeid": "1100_60", "className": "foo"}]},
                [{"id": 123, "timeid": "1100_60", "className": "foo"}],
            ),
        ),
    )
    def test_get_classes(self, response, expected_classes):
        # mock login
        with patch("requests.Session.post") as m_post:
            m_post.return_value.status_code = HTTPStatus.OK
            client = AimHarderClient(
                email="foo", password="bar", box_id=1, box_name="foo"
            )

        with patch("requests.Session.get") as m_get:
            m_get.return_value.json.return_value = response
            assert (
                client.get_classes(datetime.datetime(2022, 3, 2, tzinfo=datetime.UTC))
                == expected_classes
            )

    @pytest.mark.parametrize(
        "response, status_code, expectation",
        (
            (
                None,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                pytest.raises(BookingFailed, match=MESSAGE_BOOKING_FAILED_UNKNOWN),
            ),
            (
                {},
                HTTPStatus.OK,
                does_not_raise(),
            ),
            (
                {"errorMssg": "foo"},
                HTTPStatus.OK,
                pytest.raises(BookingFailed, match=MESSAGE_BOOKING_FAILED_UNKNOWN),
            ),
            (
                {"errorMssgLang": "foo"},
                HTTPStatus.OK,
                pytest.raises(BookingFailed, match=MESSAGE_BOOKING_FAILED_UNKNOWN),
            ),
            (
                {"bookState": -2},
                HTTPStatus.OK,
                pytest.raises(BookingFailed, match=MESSAGE_BOOKING_FAILED_NO_CREDIT),
            ),
            (
                {"bookState": -12},
                HTTPStatus.OK,
                pytest.raises(BookingFailed, match=MESSAGE_TOO_SOON_TO_BOOK),
            ),
        ),
    )
    def test_book_class(self, response, status_code, expectation):
        # mock login
        with patch("requests.Session.post") as m_post:
            m_post.return_value.status_code = HTTPStatus.OK
            client = AimHarderClient(
                email="foo", password="bar", box_id=1, box_name="foo"
            )

        with patch("requests.Session.post") as m_post:
            m_post.return_value.json.return_value = response
            m_post.return_value.status_code = status_code
            with expectation:
                client.book_class(
                    datetime.datetime(2022, 3, 2, tzinfo=datetime.UTC), "123"
                )

    @pytest.mark.parametrize(
        "response, status_code, expectation",
        (
            ({"cancelState": 1}, HTTPStatus.OK, does_not_raise()),
            (
                {"cancelState": 0},
                HTTPStatus.OK,
                pytest.raises(CancelFailed, match=MESSAGE_CANCEL_FAILED),
            ),
            (
                {},
                HTTPStatus.INTERNAL_SERVER_ERROR,
                pytest.raises(CancelFailed, match=MESSAGE_CANCEL_FAILED),
            ),
        ),
    )
    def test_cancel_booking(self, response, status_code, expectation):
        # mock login
        with patch("requests.Session.post") as m_post:
            m_post.return_value.status_code = HTTPStatus.OK
            client = AimHarderClient(
                email="foo", password="bar", box_id=1, box_name="foo"
            )

        with patch("requests.Session.post") as m_post:
            m_post.return_value.json.return_value = response
            m_post.return_value.status_code = status_code
            with expectation:
                client.cancel_booking("987")
        m_post.assert_called_once_with(
            cancel_endpoint("foo"), data={"id": "987", "late": 0, "familyId": None}
        )
