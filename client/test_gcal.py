import json
import time
from unittest.mock import MagicMock, patch

import gcal
import pytest

WOD = {
    "date": "2026-10-08",
    "timeid": "1700_60",
    "time": "17:00 - 18:00",
    "name": "WOD",
}
OPEN = {
    "date": "2026-10-09",
    "timeid": "0800_60",
    "time": "8:00 - 9:00",
    "name": "Open",
}


def event(event_id, _class):
    return {
        "id": event_id,
        "extendedProperties": {"private": {"fitbotKey": gcal.event_key(_class)}},
    }


def response(status=200, data=None):
    mock = MagicMock(status_code=status)
    mock.json.return_value = data or {}
    if status >= 400:
        mock.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return mock


def test_event_for_builds_a_madrid_event_marked_as_fitbot():
    assert gcal.event_for(WOD, "Edelweiss") == {
        "summary": "WOD",
        "location": "Edelweiss",
        "description": "Reservado con FitBot",
        "start": {"dateTime": "2026-10-08T17:00:00", "timeZone": "Europe/Madrid"},
        "end": {"dateTime": "2026-10-08T18:00:00", "timeZone": "Europe/Madrid"},
        "extendedProperties": {
            "private": {"fitbot": "1", "fitbotKey": "2026-10-08 1700_60 WOD"}
        },
    }


def test_event_for_pads_hours_without_leading_zero():
    _event = gcal.event_for(OPEN)
    assert _event["start"]["dateTime"] == "2026-10-09T08:00:00"
    assert _event["end"]["dateTime"] == "2026-10-09T09:00:00"
    assert _event["location"] == ""


def test_plan_sync_creates_missing_events():
    assert gcal.plan_sync([WOD, OPEN], [event("a", WOD)]) == ([OPEN], [])


def test_plan_sync_deletes_cancelled_classes():
    assert gcal.plan_sync([WOD], [event("a", WOD), event("b", OPEN)]) == ([], ["b"])


def test_plan_sync_deletes_duplicates():
    assert gcal.plan_sync([WOD], [event("a", WOD), event("b", WOD)]) == ([], ["b"])


def test_plan_sync_nothing_to_do():
    assert gcal.plan_sync([WOD], [event("a", WOD)]) == ([], [])
    assert gcal.plan_sync([], []) == ([], [])


def week_with(*classes):
    days = [{"date": f"2026-10-{day:02d}", "classes": []} for day in range(5, 12)]
    for _class in classes:
        day = next(d for d in days if d["date"] == _class["date"])
        day["classes"].append({**_class, "booked": True})
    days[0]["classes"].append({**WOD, "date": "2026-10-05", "booked": False})
    return days


@patch.object(gcal, "_access_token", return_value="tok")
@patch.object(gcal.requests, "delete")
@patch.object(gcal.requests, "post")
@patch.object(gcal.requests, "get")
def test_sync_week_creates_and_deletes_events(get, post, delete, _token):
    get.side_effect = [
        response(data={"items": [event("a", WOD)], "nextPageToken": "p2"}),
        response(data={"items": [event("b", WOD), event("c", {**WOD, "name": "X"})]}),
    ]
    post.return_value = response()
    delete.side_effect = [response(204), response(410)]

    assert gcal.sync_week(week_with(WOD, OPEN), "Box") == {"created": 1, "deleted": 2}

    first, second = get.call_args_list
    assert first.kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert first.kwargs["params"]["timeMin"] == "2026-10-05T00:00:00+02:00"
    assert first.kwargs["params"]["timeMax"] == "2026-10-12T00:00:00+02:00"
    assert first.kwargs["params"]["privateExtendedProperty"] == "fitbot=1"
    assert second.kwargs["params"]["pageToken"] == "p2"
    assert post.call_args.kwargs["json"] == gcal.event_for(OPEN, "Box")
    assert [c.args[0].rsplit("/", 1)[1] for c in delete.call_args_list] == ["b", "c"]


@patch.object(gcal, "_access_token", return_value="tok")
@patch.object(gcal.requests, "get")
def test_sync_week_uses_winter_offset_after_the_dst_change(get, _token):
    get.return_value = response(data={})
    week = [{"date": "2026-10-19", "classes": []}]
    assert gcal.sync_week(week) == {"created": 0, "deleted": 0}
    assert get.call_args.kwargs["params"]["timeMax"] == "2026-10-26T00:00:00+01:00"


@patch.object(gcal, "_access_token", return_value="tok")
@patch.object(gcal.requests, "delete", return_value=response(500))
@patch.object(gcal.requests, "get")
def test_sync_week_raises_on_other_http_errors(get, _delete, _token):
    get.return_value = response(data={"items": [event("a", WOD)]})
    with pytest.raises(Exception, match="HTTP 500"):
        gcal.sync_week(week_with())


@pytest.fixture
def files(tmp_path, monkeypatch):
    credentials = {
        "installed": {
            "client_id": "id",
            "client_secret": "secret",
            "auth_uri": "https://auth",
            "token_uri": "https://token",
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(credentials))
    monkeypatch.setattr(gcal, "CREDENTIALS", tmp_path / "credentials.json")
    monkeypatch.setattr(gcal, "TOKEN", tmp_path / "token.json")
    return tmp_path / "token.json"


def test_access_token_is_reused_while_valid(files):
    files.write_text(
        json.dumps(
            {
                "access_token": "old",
                "refresh_token": "r",
                "expires_at": time.time() + 600,
            }
        )
    )
    with patch.object(gcal.requests, "post") as post:
        assert gcal._access_token() == "old"
    post.assert_not_called()


def test_access_token_is_refreshed_near_expiry(files):
    files.write_text(
        json.dumps(
            {
                "access_token": "old",
                "refresh_token": "r",
                "expires_at": time.time() + 30,
            }
        )
    )
    with patch.object(gcal.requests, "post") as post:
        post.return_value = response(data={"access_token": "new", "expires_in": 3600})
        assert gcal._access_token() == "new"
    assert post.call_args.args[0] == "https://token"
    assert post.call_args.kwargs["data"] == {
        "client_id": "id",
        "client_secret": "secret",
        "refresh_token": "r",
        "grant_type": "refresh_token",
    }
    token = json.loads(files.read_text())
    assert token["refresh_token"] == "r"  # Google does not send it again
    assert token["expires_at"] > time.time() + 3500


def test_auth_flow(files):
    assert gcal.is_configured()
    assert not gcal.is_connected()
    url = gcal.auth_url("xyz")
    assert url.startswith("https://auth?client_id=id&")
    assert "access_type=offline" in url and "prompt=consent" in url
    assert "state=xyz" in url
    with patch.object(gcal.requests, "post") as post:
        post.return_value = response(
            data={"access_token": "a", "refresh_token": "r", "expires_in": 3600}
        )
        gcal.finish_auth("code")
    assert post.call_args.kwargs["data"]["grant_type"] == "authorization_code"
    assert post.call_args.kwargs["data"]["redirect_uri"] == gcal.REDIRECT_URI
    assert gcal.is_connected()
