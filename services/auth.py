import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import streamlit as st

def _tz() -> ZoneInfo:
    tzname = st.secrets.get("TIMEZONE", "UTC")
    try:
        return ZoneInfo(tzname)
    except Exception:
        return ZoneInfo("UTC")

def _this_monday_start(now: datetime) -> datetime:
    """Return Monday 00:00:00 of current week in local tz."""
    # now is tz-aware in local tz
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)

def next_rotation_time() -> datetime:
    tz = _tz()
    now = datetime.now(tz)
    this_monday = _this_monday_start(now)
    return this_monday + timedelta(days=7)

def weekly_password(for_time: datetime | None = None, length: int = 10) -> str:
    """
    Deterministic weekly password:
    HMAC_SHA256(seed, f"{year}-W{iso_week}") -> take digits/letters subset.
    Rotates at Monday 00:00 in TIMEZONE.
    """
    seed = st.secrets.get("WEEKLY_PASSWORD_SEED", "")
    if not seed:
        raise RuntimeError("Missing WEEKLY_PASSWORD_SEED in Streamlit secrets.")

    tz = _tz()
    now = for_time or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    # Use ISO year/week based on local time
    iso_year, iso_week, _ = now.isocalendar()
    msg = f"{iso_year}-W{iso_week}".encode("utf-8")

    digest = hmac.new(seed.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    # Make it user-friendly: letters+digits
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no confusing I/O/1/0
    # Map hex -> alphabet
    out = []
    for ch in digest:
        idx = int(ch, 16) % len(alphabet)
        out.append(alphabet[idx])
        if len(out) >= length:
            break
    return "".join(out)

def check_user_password(pw: str) -> bool:
    return pw.strip() == weekly_password()

def check_admin_password(pw: str) -> bool:
    admin = st.secrets.get("ADMIN_PASSWORD", "")
    if not admin:
        raise RuntimeError("Missing ADMIN_PASSWORD in Streamlit secrets.")
    return pw == admin
