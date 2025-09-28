import json
import os
import asyncio
import discord
from datetime import datetime, timedelta
from collections import deque
import random  # NEW: for tiny jitter on sleeps

# =========================
# Constants & configuration
# =========================
ATTEMPT_FILE = "attempts.json"
MAX_ATTEMPTS_PER_DAY = 4

FAILURE_LOG_WINDOW = timedelta(minutes=5)
FAILURE_THRESHOLD = 5  # Trigger warning if 5+ failures in 5 mins

# Global rate-limit / Cloudflare cool-down
DEFAULT_BLOCK_MINUTES = 15  # how long to refuse operations after 429/1015
_GLOBAL_BLOCK_UNTIL = None  # datetime|None

# Ensure attempts file exists
if not os.path.exists(ATTEMPT_FILE):
    with open(ATTEMPT_FILE, "w") as f:
        json.dump({}, f)

# ============
# Role helpers
# ============
def get_role_names(member):
    return [role.name.lower() for role in member.roles]

def is_user_verified(member, verified_role_name):
    return any(role.name.lower() == verified_role_name.lower() for role in member.roles)

# ======================
# Quiz attempt tracking
# ======================
def can_attempt_quiz(user_id):
    with open(ATTEMPT_FILE, "r") as f:
        data = json.load(f)

    user_id = str(user_id)
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    if user_id not in data:
        return True

    attempts = data[user_id].get(today, 0)
    return attempts < MAX_ATTEMPTS_PER_DAY

def record_attempt(user_id):
    with open(ATTEMPT_FILE, "r") as f:
        data = json.load(f)

    user_id = str(user_id)
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    if user_id not in data:
        data[user_id] = {}
    if today not in data[user_id]:
        data[user_id][today] = 0

    data[user_id][today] += 1

    with open(ATTEMPT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_remaining_attempts(user_id):
    with open(ATTEMPT_FILE, "r") as f:
        data = json.load(f)

    user_id = str(user_id)
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    if user_id not in data or today not in data[user_id]:
        return MAX_ATTEMPTS_PER_DAY

    return MAX_ATTEMPTS_PER_DAY - data[user_id][today]

# ==================================
# Failure log tracker for safe_send()
# ==================================
FAILURE_LOG = deque(maxlen=100)  # stores timestamps of failed sends

def increment_failure_count():
    FAILURE_LOG.append(datetime.utcnow())

def get_recent_failure_count(window_seconds=300):  # default: 5 minutes
    now = datetime.utcnow()
    return sum((now - ts).total_seconds() < window_seconds for ts in FAILURE_LOG)

# Back-compat alias (used elsewhere)
get_failure_count = get_recent_failure_count

# ==================================
# Global cool-down helpers (NEW)
# ==================================
def set_global_block(minutes: int = DEFAULT_BLOCK_MINUTES):
    """Block all higher-risk actions for N minutes (e.g., after 429/1015)."""
    global _GLOBAL_BLOCK_UNTIL
    _GLOBAL_BLOCK_UNTIL = datetime.utcnow() + timedelta(minutes=minutes)
    print(f"[GLOBAL-BLOCK] Entering cool-down for ~{minutes} minutes (until {_GLOBAL_BLOCK_UNTIL} UTC).")

def is_globally_blocked() -> bool:
    """Return True if we’re in a global cool-down window."""
    if _GLOBAL_BLOCK_UNTIL is None:
        return False
    return datetime.utcnow() < _GLOBAL_BLOCK_UNTIL

def get_block_remaining_seconds() -> int:
    """How many seconds remain in the global block; 0 if not blocked."""
    if not is_globally_blocked():
        return 0
    return max(0, int((_GLOBAL_BLOCK_UNTIL - datetime.utcnow()).total_seconds()))

# ==================================================
# General-purpose safe_send() with retry + backoff
# ==================================================
async def safe_send(destination, content, retries=3, delay=1.5):
    """
    Send a message safely with retry/backoff.
    - On 429 or Cloudflare 1015 HTML, sets a global cool-down and logs.
    - Respects the global cool-down: if active, short-circuit and return False.
    """
    # Respect global block (don’t hammer API while cooling down)
    if is_globally_blocked():
        rem = get_block_remaining_seconds()
        print(f"[SAFE_SEND] Skipping send; global cool-down active ({rem}s remaining).")
        return False

    backoff_schedule = [3600, 7200, 21600]  # Long delays only for 429s (1hr, 2hr, 6hr)

    for attempt in range(retries):
        try:
            await destination.send(content)
            return True

        except discord.Forbidden:
            # DMs closed or no permission — do not retry endlessly
            print(f"[ERROR] Forbidden: Cannot message {destination}")
            return False

        except discord.HTTPException as e:
            # Build a string to detect Cloudflare HTML “Error 1015” cases
            err_text = getattr(e, "text", "") or str(e)
            is_429 = (getattr(e, "status", None) == 429)
            looks_like_1015 = ("Error 1015" in err_text) or ("used Cloudflare to restrict access" in err_text)

            if is_429 or looks_like_1015:
                # Log once, flip global block, then back off hard on this call too.
                print(f"[RATE LIMIT] Detected {'429' if is_429 else 'Cloudflare 1015'} on attempt {attempt + 1}.")
                # Enter global cool-down so main flow can refuse new work.
                set_global_block(DEFAULT_BLOCK_MINUTES)
                wait_time = backoff_schedule[min(attempt, len(backoff_schedule) - 1)]
            else:
                # Generic network/API error — exponential backoff
                wait_time = delay * (2 ** attempt)

            jitter = random.uniform(0, 0.5)
            print(f"[RETRY] Waiting {wait_time + jitter:.2f}s before retry...")
            await asyncio.sleep(wait_time + jitter)

        except Exception as e:
            # Unknown error — log and try again with exponential backoff
            wait_time = delay * (2 ** attempt)
            print(f"[ERROR] Unexpected send error: {e}. Retrying in {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)

    # All attempts failed — record failure and possibly warn
    timestamp = datetime.utcnow()
    FAILURE_LOG.append(timestamp)
    # Trim to window
    FAILURE_LOG[:] = [t for t in FAILURE_LOG if timestamp - t <= FAILURE_LOG_WINDOW]

    if len(FAILURE_LOG) >= FAILURE_THRESHOLD:
        print(f"[RATE WARNING] {len(FAILURE_LOG)} failed sends in last 5 minutes.")

    print(f"[ERROR] Failed to send message after {retries} attempts")
    return False