"""Ask the hosted Laya decision API (Jev-compatible) for a post-flop action.

Every failure returns None so the caller falls back to its own decision. A circuit breaker
stops calling after repeated failures, and auth/quota errors disable the API for the process.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = "https://api.laya-ai.com/v1/systemone"
# Committed on purpose: the team chose to accept that this key is public. Revoke it after the event.
API_KEY = os.environ.get("LAYA_API_KEY", "sk_ctyxV4gDtov6JKSQOHmnnJ23g2rriQAq")
TIMEOUT_S = 1.0
MIN_PROBABILITY = 0.5
FAILURES_TO_OPEN = 3
COOLDOWN_S = 60

_state = {"failures": 0, "open_until": 0.0, "disabled": False}

QUESTIONS = {
    "action": {
        "type": "choice",
        "instructions": "What is the best poker action for us in this spot?",
        "criteria": {"fold": "Give up the hand", "call": "Match the current bet or check",
                     "raise": "Bet or raise for value or as a semi-bluff"},
    },
}


def _fail(reason):
    _state["failures"] += 1
    if _state["failures"] >= FAILURES_TO_OPEN:
        _state["open_until"] = time.monotonic() + COOLDOWN_S
        _state["failures"] = 0
    print(f"laya: {reason}", file=sys.stderr)
    return None


def ask(state_text):
    """Return "fold", "call" or "raise" when Laya is confident enough, else None."""
    if _state["disabled"] or not API_KEY or time.monotonic() < _state["open_until"]:
        return None
    body = json.dumps({"state": state_text, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": "Bearer " + API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "megistekik-poker/1.0",  # Cloudflare rejects the default urllib agent
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            answer = json.loads(r.read())["answers"]["action"]
    except urllib.error.HTTPError as e:
        if e.code in (401, 402, 403):
            _state["disabled"] = True  # bad key, quota gone or blocked: stop paying the latency
        return _fail(f"HTTP {e.code}")
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")
    _state["failures"] = 0
    choice = answer.get("choice")
    if choice not in ("fold", "call", "raise"):
        return None
    if answer.get("probabilities", {}).get(choice, 0) < MIN_PROBABILITY:
        return None
    return choice
