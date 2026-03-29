"""
license_client.py  —  4K Downloader License Client
Validates license keys against the TikDL bot's /verify endpoint.

Flow:
  1. Load saved key + machine ID from QSettings
  2. Try online validation against BOT_SERVER_URL/verify
  3. Fall back to offline HMAC validation if the server is unreachable
  4. Cache the last known good result so short outages don't block the user
"""

import hmac
import hashlib
import datetime
import uuid
import platform
import json
import urllib.request
import urllib.error
import urllib.parse
import logging
import os

from PySide6.QtCore import QSettings

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
# Set TIKDL_BOT_URL env var, or edit the fallback string below.
BOT_SERVER_URL = os.environ.get(
    "TIKDL_BOT_URL",
    "https://tikdl-bot-production.up.railway.app"   # ← replace with your Railway URL
).rstrip("/")

# Must match SECRET_KEY in your tikdl-bot config.py exactly.
SECRET_KEY = os.environ.get(
    "TIKDL_SECRET_KEY",
    "TikDL@Secret#2025!ChangeThisNow!"
).encode("utf-8")

KEY_PREFIX  = "TIKDL"
CHARS       = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CACHE_TTL_H = 24    # re-verify online every 24 hours
GRACE_TTL_H = 72    # offline grace period after last successful online check

APP_NAME = "NexusDownloader"
ORG_NAME = "NexusLabs"


# ── Machine ID ─────────────────────────────────────────────────────────────────

def get_machine_id() -> str:
    """Return a stable 16-char hex machine identifier stored in QSettings."""
    s = QSettings(ORG_NAME, APP_NAME)
    mid = s.value("license/machine_id", "")
    if mid and len(mid) == 16:
        return mid.upper()

    salt = s.value("license/machine_salt", "")
    if not salt:
        salt = uuid.uuid4().hex
        s.setValue("license/machine_salt", salt)

    raw = platform.node() + platform.machine() + platform.processor()
    mid = hashlib.sha256((raw + salt).encode()).hexdigest()[:16].upper()
    s.setValue("license/machine_id", mid)
    return mid


# ── HMAC helpers (mirror of license.py in the bot) ────────────────────────────

def _hmac_check_expected(payload: str) -> str:
    sig = hmac.new(SECRET_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return "".join(CHARS[int(sig[i*2:i*2+2], 16) % len(CHARS)] for i in range(5))


def _offline_validate(key: str, machine_id: str) -> dict:
    """Validate key structure + HMAC without hitting the server."""
    parts = key.strip().upper().split("-")
    if len(parts) != 7 or parts[0] != KEY_PREFIX:
        return {"ok": False, "status": "invalid", "reason": "Malformed key format."}
    payload = "-".join(parts[:6])
    if parts[6] != _hmac_check_expected(payload):
        return {"ok": False, "status": "invalid", "reason": "Key signature mismatch."}
    return {"ok": True, "status": "offline_valid", "days_left": -1,
            "expires": "unknown", "machine_id": machine_id}


# ── Online validation ──────────────────────────────────────────────────────────

def _online_validate(key: str, machine_id: str, timeout: int = 6) -> dict | None:
    """GET /verify?key=...&mid=... — returns parsed JSON or None if unreachable."""
    params = urllib.parse.urlencode({"key": key, "mid": machine_id})
    url = f"{BOT_SERVER_URL}/verify?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NexusDownloader/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning(f"[license] Online check failed: {e}")
        return None


# ── QSettings helpers ──────────────────────────────────────────────────────────

def _s() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def load_saved_license() -> dict:
    s = _s()
    return {
        "key":         s.value("license/key", ""),
        "cached_ok":   s.value("license/cached_ok",   False, type=bool),
        "cached_exp":  s.value("license/cached_exp",  ""),
        "cached_days": s.value("license/cached_days", 0,     type=int),
        "last_online": s.value("license/last_online", ""),
    }


def save_license_key(key: str):
    s = _s()
    s.setValue("license/key", key.strip().upper())
    s.setValue("license/cached_ok", False)   # invalidate cache
    s.setValue("license/last_online", "")


def _cache_result(result: dict):
    s = _s()
    s.setValue("license/cached_ok",   result.get("ok", False))
    s.setValue("license/cached_exp",  result.get("expires", ""))
    s.setValue("license/cached_days", result.get("days_left", 0))
    s.setValue("license/last_online", datetime.datetime.utcnow().isoformat())


def _invalidate_cache():
    """Wipe all cached license state — forces a fresh check on next launch."""
    s = _s()
    s.setValue("license/cached_ok",   False)
    s.setValue("license/cached_exp",  "")
    s.setValue("license/cached_days", 0)
    s.setValue("license/last_online", "")
    log.info("[license] Cache invalidated (revoked/expired result from server).")


def _cache_age_hours(last_online_iso: str) -> float:
    if not last_online_iso:
        return float("inf")
    try:
        last = datetime.datetime.fromisoformat(last_online_iso)
        return (datetime.datetime.utcnow() - last).total_seconds() / 3600
    except Exception:
        return float("inf")


# ── Public API ─────────────────────────────────────────────────────────────────

def validate_license(force_online: bool = False) -> dict:
    """
    Full license check. Returns:
      { ok, status, reason, days_left, expires, machine_id, key }
    """
    saved      = load_saved_license()
    key        = saved["key"]
    machine_id = get_machine_id()
    base       = {"key": key, "machine_id": machine_id}

    if not key:
        return {**base, "ok": False, "status": "no_key",
                "reason": "No license key entered.", "days_left": 0, "expires": ""}

    # Use fresh cache if not forced
    age = _cache_age_hours(saved["last_online"])
    if not force_online and age < CACHE_TTL_H and saved["cached_ok"]:
        return {**base, "ok": True, "status": "active",
                "reason": f"License valid — {saved['cached_days']} days remaining.",
                "days_left": saved["cached_days"], "expires": saved["cached_exp"]}

    # Try online
    online = _online_validate(key, machine_id)
    if online is not None:
        result = {**base,
                  "ok":        online.get("ok", False),
                  "status":    online.get("status", "error"),
                  "reason":    online.get("reason", ""),
                  "days_left": online.get("days_left", 0),
                  "expires":   online.get("expires", "")}
        if result["ok"]:
            # Valid — update cache
            _cache_result(result)
        else:
            # Revoked / expired / invalid — wipe cache immediately so the
            # app cannot bypass the check on next launch via stale cache.
            _invalidate_cache()
        # Always return the server's authoritative answer — never fall through
        return result

    # Server genuinely unreachable (network error / timeout) — offline fallback
    log.info("[license] Server unreachable — offline HMAC validation.")
    offline = _offline_validate(key, machine_id)

    # Grace period: only trust cache if key structure is valid AND we had a
    # recent successful online check AND cache still says ok.
    # A revoked key that hit the server would have already wiped the cache above,
    # so reaching here with cached_ok=True means the server was merely offline.
    if saved["cached_ok"] and age < GRACE_TTL_H and offline["ok"]:
        return {**base, "ok": True, "status": "offline_grace",
                "reason": f"Server unreachable — offline mode ({int(age)}h since last check).",
                "days_left": saved["cached_days"], "expires": saved["cached_exp"]}

    # Cache expired or invalid key structure — deny
    if offline["ok"]:
        offline["reason"] = "Server unreachable — key structure valid but expiry unconfirmed."
    return {**base, **offline}


def is_licensed() -> bool:
    return bool(validate_license().get("ok"))
