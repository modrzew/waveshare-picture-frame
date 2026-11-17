"""Tell a scheduled RTC wake-up apart from a manual power-on.

PiSugar doesn't report why it powered the Pi on (PiSugar 3 has no alarm flag), so this infers
it from timing. Right before battery mode shuts down, it records when the RTC alarm should
wake the Pi. On the next boot, a boot time close to that means the alarm woke it; anything
else means the button was pressed (or power plugged in) while the frame slept.

The record is removed when read, so a reboot or service restart never counts as a manual
wake-up.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from src.pisugar.client import PisugarClient

logger = logging.getLogger(__name__)

STATE_FILE = (
    Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    / "waveshare-frame"
    / "scheduled_wake.json"
)

# How far the boot time may be from the scheduled wake-up and still count as the alarm.
# The kernel starts a few seconds after the PiSugar powers the Pi on.
EARLY_TOLERANCE = timedelta(minutes=1)
LATE_TOLERANCE = timedelta(minutes=3)


class WakeReason(StrEnum):
    """Why the Pi was powered on."""

    ALARM = "alarm"  # Scheduled RTC wake-up
    MANUAL = "manual"  # Button pressed (or power plugged in) while sleeping
    UNKNOWN = "unknown"  # Not woken from a battery-mode sleep, or timing unavailable


def record_scheduled_wake(wake_time: datetime, path: Path = STATE_FILE) -> None:
    """Record when the RTC alarm should wake the Pi. Call right before shutting down.

    Args:
        wake_time: Scheduled wake-up time (naive local time, as passed to the RTC alarm)
        path: State file location
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"wake_time": wake_time.astimezone().isoformat()}))
    logger.debug(f"Recorded scheduled wake-up in {path}")


def clear_scheduled_wake(path: Path = STATE_FILE) -> None:
    """Remove the recorded wake-up (e.g. when the shutdown didn't happen)."""
    path.unlink(missing_ok=True)


def detect_wake_reason(pisugar: PisugarClient, path: Path = STATE_FILE) -> WakeReason:
    """Work out whether the RTC alarm or a manual power-on booted the Pi.

    Compares the boot time (RTC time minus uptime, so it doesn't depend on the system clock
    being synced yet) with the wake-up recorded before the last shutdown.

    Args:
        pisugar: Pisugar client used to read the RTC time
        path: State file location

    Returns:
        The wake reason; UNKNOWN when there's nothing to compare against
    """
    try:
        data = json.loads(path.read_text())
        scheduled = datetime.fromisoformat(data["wake_time"])
    except FileNotFoundError:
        logger.info("No scheduled wake-up recorded: not woken from a battery-mode sleep")
        return WakeReason.UNKNOWN
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.warning(f"Unreadable scheduled wake-up record {path}: {e}")
        clear_scheduled_wake(path)
        return WakeReason.UNKNOWN
    clear_scheduled_wake(path)

    uptime = _read_uptime()
    rtc_now = pisugar.get_rtc_time()
    if uptime is None or rtc_now is None:
        logger.warning("Can't determine the wake reason: RTC time or uptime unavailable")
        return WakeReason.UNKNOWN

    boot_time = rtc_now - timedelta(seconds=uptime)
    offset = boot_time - scheduled
    reason = WakeReason.ALARM if -EARLY_TOLERANCE <= offset <= LATE_TOLERANCE else WakeReason.MANUAL
    logger.info(
        f"Wake reason: {reason} (booted at {boot_time.isoformat(timespec='seconds')}, "
        f"wake-up was scheduled for {scheduled.isoformat(timespec='seconds')})"
    )
    return reason


def _read_uptime() -> float | None:
    """Seconds since the kernel started, or None if unavailable (non-Linux)."""
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
