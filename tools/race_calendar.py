#!/usr/bin/env python3
"""Put this season's F1 calendar into a theme, for the launcher's race-weekend mode.

    race_calendar.py <theme folder>              fetch the current season and write race_calendar into
                                                 <theme folder>/config.json, keeping every other key
    race_calendar.py <theme folder> --season 2027

Then push the theme as usual: tools/theme.sh <theme folder>. The launcher never goes online; this script is
the only thing that does, once, on your computer. The data comes from Jolpica (https://jolpi.ca), the free
community successor to the Ergast API: no key, no account. Run it again when F1 moves a session or a new
season starts. Races that are already over are left out. The theme folder has to exist (config.json in it is
created if it is not there yet).

Exit status: 0 the calendar is in the theme, 1 the season has no race left to show, 2 this run could not do
its job - the folder is not there, --season is not a year, or the fetch failed - and says why on stderr.
Nothing is written on 1 or 2: the theme stays as it was.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

API = "https://api.jolpi.ca/ergast/f1/{season}.json?limit=100"
# Jolpica serves the championship seasons: 1950 is the first one, so a year before it is a typo (or a
# date typed into --season) rather than a season whose calendar this could fetch.
FIRST_SEASON = 1950
# Jolpica's session keys, in weekend order, and the names the launcher shows.
SESSIONS = (
    ("FirstPractice", "FP1"),
    ("SecondPractice", "FP2"),
    ("ThirdPractice", "FP3"),
    ("SprintQualifying", "SPRINT QUALI"),
    ("SprintShootout", "SPRINT QUALI"),   # the 2023 name for the same session
    ("Sprint", "SPRINT"),
    ("Qualifying", "QUALIFYING"),
)


def instant(block):
    """"2026-10-23" + "17:30:00Z" as one UTC timestamp; None when the time is not published yet."""
    if not block.get("date") or not block.get("time"):
        return None
    return f"{block['date']}T{block['time']}" if block["time"].endswith("Z") else f"{block['date']}T{block['time']}Z"


def calendar(races, now):
    out = []
    for race in races:
        sessions = []
        for key, name in SESSIONS:
            if key in race and (start := instant(race[key])):
                sessions.append({"name": name, "start": start})
        start = instant(race)
        if not start:
            continue
        sessions.append({"name": "RACE", "start": start})
        # The launcher keeps a weekend on screen for four hours after the start; a day covers that.
        if datetime.datetime.fromisoformat(start.replace("Z", "+00:00")) < now - datetime.timedelta(days=1):
            continue
        out.append({
            "round": int(race["round"]),
            "name": race["raceName"],
            "place": race.get("Circuit", {}).get("Location", {}).get("locality", ""),
            "sessions": sessions,
        })
    return out


def season(value):
    """'current' or a championship year, the two forms Jolpica takes.

    Judged here rather than by the API: `--season 2027x` (a typo) and `--season 1990` reach Jolpica as a
    URL that 404s or as a season that never existed, and its answer was a traceback either way.
    """
    if value == "current" or (len(value) == 4 and value.isdigit() and int(value) >= FIRST_SEASON):
        return value
    raise argparse.ArgumentTypeError(
        f"a season is 'current' or a year from {FIRST_SEASON} on, not {value!r}")


def refuse(message):
    """Say what went wrong on stderr and give back 2: this run could not do its job."""
    print(message, file=sys.stderr)
    return 2


def main():
    parser = argparse.ArgumentParser(description="Put this season's F1 calendar into a theme.")
    parser.add_argument("theme", help="theme folder that already exists; its config.json is created if "
                                     "missing")
    parser.add_argument("--season", default="current", type=season,
                        help="season year, default the current one")
    args = parser.parse_args()

    # A folder that is not there is nearly always a typo in the theme's name, and the run used to make
    # that folder and put a calendar in it: the author then pushed, or debugged, a theme that is not the
    # one they meant. The config.json inside is still created for a folder that does exist.
    folder = Path(args.theme)
    if not folder.is_dir():
        return refuse(f"there is no theme folder at {args.theme}. Nothing was written: a theme is a "
                      f"folder of its own under themes/, so check the name you passed - this run will not "
                      f"create one for you.")
    config = folder / "config.json"
    theme = json.loads(config.read_text(encoding="utf-8-sig")) if config.is_file() else {}
    endpoint = API.format(season=args.season)
    request = urllib.request.Request(endpoint, headers={"User-Agent": "cleanyourtv"})
    # The one online step in this repository, on a laptop that may be offline, behind a proxy that
    # answers for it, or running on the day the API is down: each of those ended in a traceback that
    # named neither what was being fetched nor that the theme was left alone.
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as e:
        return refuse(f"Jolpica answered {e.code} {e.reason} for {endpoint}. Nothing was written: try "
                      f"again later, or pass --season with a year it serves.")
    except (urllib.error.URLError, TimeoutError) as e:
        return refuse(f"could not reach Jolpica at {endpoint} ({getattr(e, 'reason', e)}). Nothing was "
                      f"written: this is the one step that goes online, so check the connection - a "
                      f"proxy or a captive portal is the usual cause - and run it again.")
    except ValueError as e:
        return refuse(f"Jolpica answered something that is not JSON ({e}) for {endpoint}. Nothing was "
                      f"written: this is usually a proxy or a login page answering instead of the API, "
                      f"so run it again from a network that reaches it.")
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        table = payload["MRData"]["RaceTable"]
        races = calendar(table["Races"], now)
    except (KeyError, TypeError):
        return refuse(f"the answer for the {args.season} season has no MRData.RaceTable in it. Nothing "
                      f"was written: run it again, or pass --season with a year.")
    except ValueError as e:
        return refuse(f"a session time in the {args.season} calendar is not a timestamp this script "
                      f"understands ({e}). Nothing was written: the API has changed how it writes a "
                      f"session's time.")
    if not races:
        sys.stderr.write(f"no upcoming races in the {table['season']} calendar; try --season with next "
                         f"year\n")
        return 1
    theme["race_calendar"] = races
    config.write_text(json.dumps(theme, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    first = races[0]
    print(f"{len(races)} races from the {table['season']} season -> {config}")
    print(f"next: round {first['round']} {first['name']}, race {first['sessions'][-1]['start']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
