"""Persistent opponent profiles: Upstash Redis when configured in .env, else a local JSON file.

Reads happen once at startup; writes go out on a background thread so a bet request never waits on the network.
"""
import json
import os
import sys
import threading
import time
import traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = "megistekik:profiles"
SAVE_INTERVAL = 10  # seconds between writes, to stay well inside the free tier's request quota


def load_env(path=os.path.join(HERE, ".env")):
    """Minimal .env reader: KEY=VALUE lines, # comments; real environment variables win."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except FileNotFoundError:
        pass


load_env()
URL = os.environ.get("UPSTASH_REDIS_REST_URL")
TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
FILE = os.environ.get("PROFILE_FILE", os.path.join(HERE, "profiles.json"))
ENABLED = os.environ.get("PROFILE_STORE", "on") != "off"

_last_save = [0.0]


def _redis(*command):
    req = urllib.request.Request(URL, data=json.dumps(command).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=2) as resp:
        return json.load(resp)["result"]


def load():
    if not ENABLED:
        return {}
    try:
        if URL and TOKEN:
            raw = _redis("GET", KEY)
        else:
            with open(FILE) as f:
                raw = f.read()
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return {}


def _write(blob):
    try:
        if URL and TOKEN:
            _redis("SET", KEY, blob)
        else:
            tmp = FILE + ".tmp"
            with open(tmp, "w") as f:
                f.write(blob)
            os.replace(tmp, FILE)
    except Exception:
        traceback.print_exc(file=sys.stderr)


def save_soon(profiles, force=False):
    """Snapshot now (on the caller's thread, so the dict can't change mid-dump), write in the background."""
    if not ENABLED or (not force and time.time() - _last_save[0] < SAVE_INTERVAL):
        return
    _last_save[0] = time.time()
    threading.Thread(target=_write, args=(json.dumps(profiles),), daemon=True).start()
