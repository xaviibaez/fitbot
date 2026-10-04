# FitBot

Python script to automate your session bookings in [aimharder.com](http://aimharder.com) platform

## Usage

Having docker installed you only need to do the following command:

```bash
docker run -e email=your.email@mail.com -e password=1234 -e booking-goals='{"monday":[{"time":"1815","name":"Provenza"}]}' -e box-name=lahuellacrossfit -e box-id=3984 xaviibaez/fitbot
```

> **Note:** use the `xaviibaez/fitbot` image. The original `pablobuenaposada/fitbot` image only understands the old format (numeric days, one class per day and `days-in-advance`), which this image still supports, see [Old format](#old-format).

Explanation about the fields:

`email`: self-explanatory

`password`: self-explanatory

`booking-goals`: expects a json where as keys you would use the day of the week in lowercase English (`monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday`) and the value should be a list of classes to book that day, each one with the time (HHMM) of the class and the name of the class or part of it. The value is always a list, even for a single class. The name is case sensitive: `Open Box` matches `Open Box A.M` but `open box` does not.
The json is checked before logging in: an unknown day (days are lowercase only, `Monday` is not valid), a time that is not HHMM or an empty name stops the script with an error and nothing is booked.
Unfortunately this structure needs to be crazy escaped, but here's an example:

Mondays at 18:15 class name should contain ARIBAU and at 19:15 class name should contain WOD
Wednesdays at 18:15 class name should contain ARIBAU
```python
{"monday": [{"time": "1815", "name": "ARIBAU"}, {"time": "1915", "name": "WOD"}], "wednesday": [{"time": "1815", "name": "ARIBAU"}]}
```
which should be sent in this form:
```sh
'{"monday":[{"time":"1815","name":"ARIBAU"},{"time":"1915","name":"WOD"}],"wednesday":[{"time":"1815","name":"ARIBAU"}]}'
```

`box-name`: this is the sub-domain you will find in the url when accessing the booking list from a browser, something like _https://**lahuellacrossfit**.aimharder.com/schedule_

`box-id`: it's always the same one for your gym, you can find it inspecting the request made while booking a class from the browser:

<img src="https://raw.github.com/pablobuenaposada/fitbot/master/inspect.png" data-canonical-src="https://raw.github.com/pablobuenaposada/fitbot/master/inspect.png" height="300" />

Each run books the classes of the current week (Monday to Sunday), so run it on Monday to book the whole week. Days of the week that have already passed will fail to book and are just logged.

Example: run it every Monday to book Open Box at 17:00 and WOD at 18:00 on Mondays, Tuesdays, Thursdays and Fridays in a single run:
```sh
booking-goals={"monday":[{"time":"1700","name":"Open Box"},{"time":"1800","name":"WOD"}],"tuesday":[{"time":"1700","name":"Open Box"},{"time":"1800","name":"WOD"}],"thursday":[{"time":"1700","name":"Open Box"},{"time":"1800","name":"WOD"}],"friday":[{"time":"1700","name":"Open Box"},{"time":"1800","name":"WOD"}]}
```

`family-id`: Optional. This is the id for the person who wants to book a class in case the account has more than one member. 
The value for this parameter can be found by inspecting the requests with the browser, as with the field `box-id`.

`proxy`: Optional. If you want to use a proxy, you can set it with the format `socks5://ip:port`.

`weeks-ahead`: Optional, `0` by default. Book the week that is this many weeks after the current one, for example `1` to book next week when running it on a Sunday. Ignored by the [old format](#old-format).

`timezone`: Optional, `UTC` by default. Timezone used to know which day is today, for example `Europe/Madrid`. Set it to your gym's timezone, otherwise a run close to midnight can take the previous or next day (and week) as today.

## Old format

The format of the original `pablobuenaposada/fitbot` image keeps working exactly as before when `booking-goals` uses the old format and `days-in-advance` is set:

- days as numbers from `0` (Monday) to `6` (Sunday)
- one class per day as an object instead of a list
- `days-in-advance`: only the day that is `days-in-advance` days from today is booked

```bash
docker run -e email=your.email@mail.com -e password=1234 -e booking-goals='{"0":{"time":"1815","name":"Provenza"}}' -e box-name=lahuellacrossfit -e box-id=3984 -e days-in-advance=3 xaviibaez/fitbot
```

In any other case (any day written as a name, any list of classes, or no `days-in-advance`) the new behaviour is used: the whole current week is booked and `days-in-advance` is ignored.

## Using env files

You can use env files for configuration and credentials instead of passing them directly on the command line:

### Setup

1. **Copy the example files:**
   ```bash
   cd server
   cp .env.example .env
   cp .env.secrets.example .env.secrets
   ```

2. **Edit `.env`** with your gym configuration (box-name, box-id, booking-goals)

3. **Edit `.env.secrets`** with your credentials (email, password)

4. **Run:**
   ```bash
   docker run --env-file .env --env-file .env.secrets xaviibaez/fitbot
   ```

> **Security Note:** `.env.secrets` is gitignored to prevent accidentally committing credentials. Never commit this file.

## Web client

The repo has two folders: `server` (the bot and its docker image) and `client` (a local web page to pick the classes).

The web page logs in to aimharder, shows the classes of the current week and books the ones you select by running the `xaviibaez/fitbot` container.

1. Build the image: `docker build -t xaviibaez/fitbot server`
2. Install the server dependencies once: `cd server && uv sync`
3. Run the page with the server's virtualenv: `server/.venv/Scripts/python client/app.py` (on Linux/macOS `server/.venv/bin/python client/app.py`)
4. It opens http://127.0.0.1:8000. The login form is prefilled from `server/.env` and `server/.env.secrets` if they exist. The box id is not asked: it is read from `box-id` in `server/.env`.
5. After logging in you get a weekly calendar: click the classes to book and press **Reservar**. Classes already booked in aimharder show in green, and the page reloads them when you come back to the tab, so bookings made or cancelled in the aimharder app show up.

Your password is only kept in memory while the page server runs, and it is passed to docker as an environment variable, never as a command argument.

### Cancel a booking

Click a booked (green) class to mark it to cancel (it turns red) and press **Aplicar**. Cancelling is done straight away from the page, without the container. Cancelling close to the class can cost you the credit, depending on your box rules.

## 🚨 Proxy note 🚨
It appears that AimHarder has started blocking connections by returning a 403 error based on the IP address location. If you are running this script from outside Spain, you may encounter these errors, which is why the proxy argument has been added.

The United States seems to be heavily blocked (possibly only Azure IPs), so running this script from GitHub Actions will likely fail without a proxy. While this is not confirmed, it seems AimHarder doesn't like the use of automated scripts, especially when run for free via GitHub Actions 😀. If you choose this approach, ensure you use a proxy that is not blocked by AimHarder.

**Note:** Use free proxies at your own risk, as your credentials will be transmitted through them. Additionally avoid sharing the proxy you are using in here since AimHarder may block it.

## I'm a cheapo, can I run this without using my own infrastructure for free?
Yes, you can! By using GitHub Actions, you can run this script without needing your own infrastructure. It can also be configured to run automatically on a schedule. For details about potential connection blocks and proxy usage, refer to the previous section.

You can find an example of the GitHub Actions workflow in the [`.github/workflows/scheduled.yml`](.github/workflows/scheduled.yml) file.

Clone this repo, get a proxy (https://www.freeproxy.world/), add your secrets, edit the file to your needs and it should be ready to go.

Enjoy!
