"""Keep the primary Google Calendar in sync with the classes booked in aimharder.

Uses the OAuth client in google-credentials.json (Desktop app, from Google Cloud
Console) and saves the user's tokens in google-token.json, both next to this file.
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).parent
CREDENTIALS = HERE / "google-credentials.json"
TOKEN = HERE / "google-token.json"
REDIRECT_URI = "http://127.0.0.1:8000/oauth2callback"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TIMEZONE = "Europe/Madrid"
TIMEOUT = 30


def is_configured() -> bool:
    return CREDENTIALS.exists()


def is_connected() -> bool:
    return TOKEN.exists() and bool(_read(TOKEN).get("refresh_token"))


def _read(file: Path) -> dict:
    return json.loads(file.read_text(encoding="utf-8"))


def _client() -> dict:
    """client_id, client_secret, auth_uri and token_uri of the OAuth client"""
    data = _read(CREDENTIALS)
    return data.get("installed") or data["web"]


def _save_token(response: dict, refresh_token: str = "") -> None:
    TOKEN.write_text(
        json.dumps(
            {
                "access_token": response["access_token"],
                "refresh_token": response.get("refresh_token", refresh_token),
                "expires_at": time.time() + response.get("expires_in", 3600),
            }
        ),
        encoding="utf-8",
    )


def _token_request(form: dict) -> dict:
    client = _client()
    response = requests.post(
        client["token_uri"],
        data={
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            **form,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def auth_url(state: str) -> str:
    """Google consent page; it redirects back to REDIRECT_URI with a code"""
    params = {
        "client_id": _client()["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # always returns a refresh_token
        "state": state,
    }
    return f"{_client()['auth_uri']}?{urlencode(params)}"


def finish_auth(code: str) -> None:
    """Exchange the code from the redirect for tokens and save them"""
    form = {
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    _save_token(_token_request(form))


def _access_token() -> str:
    """A valid access token, refreshed when it expires in less than a minute"""
    token = _read(TOKEN)
    if token["expires_at"] - 60 > time.time():
        return token["access_token"]
    form = {"refresh_token": token["refresh_token"], "grant_type": "refresh_token"}
    _save_token(_token_request(form), token["refresh_token"])
    return _read(TOKEN)["access_token"]


def event_key(_class: dict) -> str:
    return f"{_class['date']} {_class['timeid']} {_class['name']}"


def event_for(_class: dict, location: str = "") -> dict:
    """Google Calendar event of a class with time like "8:00 - 9:00" """

    def at(hour):
        hours, minutes = hour.strip().split(":")
        return {
            "dateTime": f"{_class['date']}T{int(hours):02d}:{minutes}:00",
            "timeZone": TIMEZONE,
        }

    start, end = _class["time"].split(" - ")
    return {
        "summary": _class["name"],
        "location": location,
        "description": "Reservado con FitBot",
        "start": at(start),
        "end": at(end),
        "extendedProperties": {
            "private": {"fitbot": "1", "fitbotKey": event_key(_class)}
        },
    }


def plan_sync(booked: list[dict], events: list[dict]) -> tuple[list[dict], list[str]]:
    """(classes to create, event ids to delete) so there is one event per class"""
    booked_keys = {event_key(_class) for _class in booked}
    seen = set()
    delete = []
    for event in events:
        key = event["extendedProperties"]["private"].get("fitbotKey")
        if key not in booked_keys or key in seen:
            delete.append(event["id"])
        seen.add(key)
    create = [_class for _class in booked if event_key(_class) not in seen]
    return create, delete


def _list_events(headers: dict, start: datetime, end: datetime) -> list[dict]:
    params = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": "true",
        "privateExtendedProperty": "fitbot=1",
        "maxResults": 250,
    }
    events = []
    while True:
        response = requests.get(EVENTS, headers=headers, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        page = response.json()
        events += page.get("items", [])
        if not page.get("nextPageToken"):
            return events
        params["pageToken"] = page["nextPageToken"]


def sync_week(week: list[dict], location: str = "") -> dict:
    """Create the events of the booked classes of a Monday..Sunday week and delete
    the fitbot events of that week that are no longer booked"""
    headers = {"Authorization": f"Bearer {_access_token()}"}
    monday = datetime.combine(
        date.fromisoformat(week[0]["date"]), datetime.min.time(), ZoneInfo(TIMEZONE)
    )
    # ponytail: timedelta on an aware datetime keeps 00:00 wall time across DST
    events = _list_events(headers, monday, monday + timedelta(days=7))
    booked = [
        {**_class, "date": day["date"]}
        for day in week
        for _class in day["classes"]
        if _class.get("booked")
    ]
    create, delete = plan_sync(booked, events)
    for _class in create:
        response = requests.post(
            EVENTS, headers=headers, json=event_for(_class, location), timeout=TIMEOUT
        )
        response.raise_for_status()
    for event_id in delete:
        response = requests.delete(
            f"{EVENTS}/{event_id}", headers=headers, timeout=TIMEOUT
        )
        if response.status_code not in (404, 410):  # already deleted
            response.raise_for_status()
    return {"created": len(create), "deleted": len(delete)}
