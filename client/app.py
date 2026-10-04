"""Local web page to log in to aimharder, pick classes of the current week and
book them by running the fitbot docker image (built from ../server).

    server/.venv/Scripts/python client/app.py

It reuses the aimharder client from ../server/src, so run it with the server's
virtualenv (it needs `requests`). Listens on 127.0.0.1 only.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import webbrowser
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import gcal

HERE = Path(__file__).parent
SERVER = HERE.parent / "server"
sys.path.insert(0, str(SERVER / "src"))
from main import WEEKDAYS

from client import AimHarderClient

IMAGE = "xaviibaez/fitbot"
TIMEZONE = "Europe/Madrid"
PORT = 8000
# ponytail: seen on edelweissfitness on Sunday 4/10: Thursday (+4) booked, Friday (+5)
# "Too soon to book". Calendar days or 96 hours, both fit; change it if the box does
BOOKING_WINDOW_DAYS = 4
DAY_LABELS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
# ponytail: Docker Desktop per-user install, used when docker is not in PATH
DOCKER_FALLBACK = Path(os.environ.get("LOCALAPPDATA", "")) / (
    "Programs/DockerDesktop/resources/bin/docker.exe"
)

# ponytail: one user on localhost, so a single in-memory session is enough
session = {}


def week_days(today: date) -> list[date]:
    """Monday to Sunday of the week `today` belongs to, as the bot books it"""
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def build_booking_goals(selected):
    """[{date, timeid, name}] -> booking-goals in the new format"""
    goals = {}
    for _class in selected:
        weekday = WEEKDAYS[date.fromisoformat(_class["date"]).weekday()]
        goals.setdefault(weekday, []).append(
            {"time": _class["timeid"][:4], "name": _class["name"]}
        )
    return goals


def weeks_ahead_of(selected, today: date) -> int:
    """How many weeks after the current one the selected classes are"""
    weeks = {
        (week_days(date.fromisoformat(_class["date"]))[0] - week_days(today)[0]).days
        // 7
        for _class in selected
    }
    if len(weeks) > 1:
        raise ValueError("Selecciona clases de una sola semana")
    return weeks.pop() if weeks else 0


def opens_on(day: date) -> date:
    """First day the classes of `day` can be booked"""
    return day - timedelta(days=BOOKING_WINDOW_DAYS)


def booking_results(selected, log):
    """What the bot said about each selected class, from its log lines like
    `<name> at <HHMM> on <Weekday>, <YYYY-MM-DD>: <message>`"""
    results = []
    for _class in selected:
        start = f"{_class['name']} at {_class['timeid'][:4]} on "
        end = f", {_class['date']}: "
        message = next(
            (
                line.split(end, 1)[1]
                for line in log
                if f" - {start}" in line and end in line
            ),
            "El bot no dijo nada de esta clase",
        )
        ok = message.endswith("booked successfully") or "already booked" in message
        results.append({**_class, "ok": ok, "message": message})
    return results


def docker_command(docker, box_name, box_id, booking_goals, weeks_ahead=0):
    """email and password go by name only: docker reads them from the environment,
    so they never show up in the process list"""
    return [
        docker, "run", "--rm",
        "-e", "email",
        "-e", "password",
        "-e", f"booking-goals={json.dumps(booking_goals)}",
        "-e", f"box-name={box_name}",
        "-e", f"box-id={box_id}",
        "-e", f"timezone={TIMEZONE}",
        "-e", f"weeks-ahead={weeks_ahead}",
        IMAGE,
    ]  # fmt: skip


def read_env():
    """Form defaults from server/.env and server/.env.secrets, if they exist"""
    env = {}
    for file in (SERVER / ".env", SERVER / ".env.secrets"):
        if file.exists():
            for line in file.read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def today():
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def login(email, password, box_name):
    """Log in to aimharder; the box id comes from server/.env"""
    box_id = read_env().get("box-id")
    if not box_id:
        raise ValueError("Falta box-id en server/.env")
    client = AimHarderClient(
        email=email, password=password, box_id=int(box_id), box_name=box_name
    )
    session.update(
        client=client,
        email=email,
        password=password,
        box_name=box_name,
        box_id=box_id,
    )
    return {"ok": True}


def week(weeks_ahead=0):
    """Classes of the week that is `weeks_ahead` weeks after the current one"""
    if not session:
        raise PermissionError("Haz login primero")
    now = today()
    days = []
    location = ""
    for day in week_days(now + timedelta(weeks=int(weeks_ahead))):
        classes = session["client"].get_classes(day) or []
        location = location or next((c.get("boxDir", "") for c in classes), "")
        days.append(
            {
                "date": day.isoformat(),
                "label": f"{DAY_LABELS[day.weekday()]} {day:%d/%m}",
                "past": day < now,
                "opens": opens_on(day).isoformat() if opens_on(day) > now else None,
                "classes": [
                    {
                        "timeid": _class["timeid"],
                        "time": _class["time"],
                        "name": _class["className"],
                        "places": _class.get("limit", ""),
                        "booked": _class.get("bookState") == 1,
                        "booking_id": _class.get("idres"),
                        "enabled": bool(_class.get("enabled")),
                    }
                    for _class in classes
                ],
            }
        )
    return {
        "week": days,
        "weeks_ahead": int(weeks_ahead),
        "google": sync_google(days, location),
    }


def sync_google(days, location):
    """Mirror the booked classes of the week in Google Calendar, if connected"""
    if not gcal.is_connected():
        return {"connected": False, "configured": gcal.is_configured()}
    try:
        return {"connected": True, **gcal.sync_week(days, location)}
    except Exception as e:  # noqa: BLE001 - the week still loads, error on the page
        return {"connected": True, "error": str(e) or type(e).__name__}


def run_bot(selected):
    """Book the selected classes running the fitbot container; returns its log"""
    weeks_ahead = weeks_ahead_of(selected, today())
    docker = shutil.which("docker") or str(DOCKER_FALLBACK)
    goals = build_booking_goals(selected)
    result = subprocess.run(
        docker_command(
            docker, session["box_name"], session["box_id"], goals, weeks_ahead
        ),
        env=dict(os.environ, email=session["email"], password=session["password"]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,  # failures show up per class in the results
    )
    output = (result.stdout + result.stderr).splitlines()
    # fitbot log lines and errors only, not the uv/make noise
    return [line for line in output if " - " in line or "Error" in line]


def cancel_classes(selected):
    """Cancel booked classes straight away (the bot only books)"""
    results = []
    for _class in selected:
        try:
            session["client"].cancel_booking(_class["booking_id"])
            results.append({**_class, "ok": True, "message": "Cancelada"})
        except Exception as e:  # noqa: BLE001 - shown on the page, keep going
            results.append({**_class, "ok": False, "message": str(e)})
    return results


def apply(book=(), cancel=()):
    """Cancel and book the selected classes, then return the fresh week"""
    if not session:
        raise PermissionError("Haz login primero")
    if not book and not cancel:
        raise ValueError("Selecciona al menos una clase")
    weeks_ahead = weeks_ahead_of([*book, *cancel], today())
    log = run_bot(book) if book else []
    results = [
        *({**r, "action": "cancel"} for r in cancel_classes(cancel)),
        *({**r, "action": "book"} for r in booking_results(book, log)),
    ]
    # fresh from aimharder, so booked and cancelled classes show up
    return {"results": results, "log": log, **week(weeks_ahead)}


PAGES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/reservas": ("reservas.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


# ponytail: one user on localhost, a single pending Google sign-in at a time
oauth_state = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/google/connect":
            if not gcal.is_configured():
                return self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Falta client/google-credentials.json (mira el README)"},
                )
            oauth_state["state"] = secrets.token_urlsafe()
            self.redirect(gcal.auth_url(oauth_state["state"]))
        elif url.path == "/oauth2callback":
            query = parse_qs(url.query)
            if query.get("state", [""])[0] != oauth_state.pop("state", None):
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Bad state"})
            if "code" in query:  # missing when the user cancels on Google
                gcal.finish_auth(query["code"][0])
            self.redirect("/reservas")
        elif self.path in PAGES:
            file, content_type = PAGES[self.path]
            self.send(HTTPStatus.OK, (HERE / file).read_bytes(), content_type)
        elif self.path == "/api/defaults":
            env = read_env()
            self.send_json(
                HTTPStatus.OK, {key: env.get(key, "") for key in ("email", "box-name")}
            )
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self):
        routes = {"/api/login": login, "/api/week": week, "/api/apply": apply}
        if self.path not in routes:
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        try:
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_json(HTTPStatus.OK, routes[self.path](**data))
        except PermissionError as e:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - shown on the page
            self.send_json(
                HTTPStatus.BAD_REQUEST, {"error": str(e) or type(e).__name__}
            )

    def redirect(self, location):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    def send_json(self, status, data):
        self.send(status, json.dumps(data).encode(), "application/json")

    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"FitBot en http://127.0.0.1:{PORT} (Ctrl+C para salir)")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    server.serve_forever()
