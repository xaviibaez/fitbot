# FitBot

Python script to automate your session bookings in [aimharder.com](http://aimharder.com) platform

## Usage

Having docker installed, build the image from this repo and run it:

```bash
docker build -t fitbot .
docker run -e email=your.email@mail.com -e password=1234 -e booking-goals='{"monday":[{"time":"1815","name":"Provenza"}]}' -e box-name=lahuellacrossfit -e box-id=3984 fitbot
```

> **Note:** the published `pablobuenaposada/fitbot` image still uses the old `booking-goals` format (one class per day, without lists), so build your own image to use the format described here.

Explanation about the fields:

`email`: self-explanatory

`password`: self-explanatory

`booking-goals`: expects a json where as keys you would use the day of the week in lowercase English (`monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday`) and the value should be a list of classes to book that day, each one with the time (HHMM) of the class and the name of the class or part of it. The value is always a list, even for a single class. The name is case sensitive: `Open Box` matches `Open Box A.M` but `open box` does not.
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

## Using env files

You can use env files for configuration and credentials instead of passing them directly on the command line:

### Setup

1. **Copy the example files:**
   ```bash
   cp .env.example .env
   cp .env.secrets.example .env.secrets
   ```

2. **Edit `.env`** with your gym configuration (box-name, box-id, booking-goals)

3. **Edit `.env.secrets`** with your credentials (email, password)

4. **Run:**
   ```bash
   docker build -t fitbot .
   docker run --env-file .env --env-file .env.secrets fitbot
   ```

> **Security Note:** `.env.secrets` is gitignored to prevent accidentally committing credentials. Never commit this file.

## 🚨 Proxy note 🚨
It appears that AimHarder has started blocking connections by returning a 403 error based on the IP address location. If you are running this script from outside Spain, you may encounter these errors, which is why the proxy argument has been added.

The United States seems to be heavily blocked (possibly only Azure IPs), so running this script from GitHub Actions will likely fail without a proxy. While this is not confirmed, it seems AimHarder doesn't like the use of automated scripts, especially when run for free via GitHub Actions 😀. If you choose this approach, ensure you use a proxy that is not blocked by AimHarder.

**Note:** Use free proxies at your own risk, as your credentials will be transmitted through them. Additionally avoid sharing the proxy you are using in here since AimHarder may block it.

## I'm a cheapo, can I run this without using my own infrastructure for free?
Yes, you can! By using GitHub Actions, you can run this script without needing your own infrastructure. It can also be configured to run automatically on a schedule. For details about potential connection blocks and proxy usage, refer to the previous section.

You can find an example of the GitHub Actions workflow in the [`.github/workflows/scheduled.yml`](.github/workflows/scheduled.yml) file.

Clone this repo, get a proxy (https://www.freeproxy.world/), add your secrets, edit the file to your needs and it should be ready to go.

Enjoy!
