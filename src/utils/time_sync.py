"""Time synchronization utilities."""

import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def try_ntp_sync(timeout: int = 10, ntp_servers: list[str] | None = None) -> bool:
    """Try to sync time using NTP.

    Args:
        timeout: Timeout in seconds for NTP sync
        ntp_servers: List of NTP servers to try (not used with timedatectl)

    Returns:
        True if NTP sync succeeded, False otherwise
    """
    if ntp_servers is None:
        ntp_servers = ["pool.ntp.org"]

    logger.info(f"Attempting NTP sync (timeout: {timeout}s)")

    try:
        # Try using timedatectl (systemd-timesyncd)
        # First enable NTP
        result = subprocess.run(
            ["timedatectl", "set-ntp", "true"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.returncode != 0:
            logger.warning(f"Failed to enable NTP: {result.stderr}")
            return False

        # Give it a moment to sync
        import time

        time.sleep(2)

        # Check if time was synced
        result = subprocess.run(
            ["timedatectl", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

        # Look for "System clock synchronized: yes" in output
        if "System clock synchronized: yes" in result.stdout:
            logger.info(f"NTP sync successful: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return True

        logger.warning("NTP sync not confirmed by timedatectl")
        return False

    except subprocess.TimeoutExpired:
        logger.warning(f"NTP sync timed out after {timeout}s")
        return False
    except FileNotFoundError:
        logger.warning("timedatectl not found - NTP sync not available")
        return False
    except Exception as e:
        logger.warning(f"NTP sync failed: {e}")
        return False


def sync_from_pisugar_rtc(
    pisugar_client, min_valid_year: int = 2025
) -> tuple[bool, datetime | None]:
    """Sync system time from Pisugar RTC with sanity check.

    Args:
        pisugar_client: PisugarClient instance
        min_valid_year: Minimum valid year for RTC time (reject if before this)

    Returns:
        Tuple of (success, rtc_datetime)
    """
    try:
        # Get RTC time to check if it's sane
        rtc_response = pisugar_client._send_command("get rtc_time")
        logger.debug(f"RTC time response: {rtc_response}")

        # Parse RTC time from response
        # Format: "rtc_time: 2025-10-06T12:08:51.000+11:00"
        if "rtc_time:" not in rtc_response.lower():
            logger.error("Failed to get RTC time - unexpected response format")
            return False, None

        parts = rtc_response.split(":", 1)
        if len(parts) < 2:
            logger.error("Failed to parse RTC time")
            return False, None

        rtc_time_str = parts[1].strip()

        # Parse ISO8601 datetime
        try:
            # Remove microseconds and timezone for parsing
            # Format: 2025-10-06T12:08:51.000+11:00
            if "." in rtc_time_str:
                rtc_time_str = rtc_time_str.split(".")[0]
            if "+" in rtc_time_str or rtc_time_str.count("-") > 2:
                # Remove timezone
                for tz_sep in ["+", "-"]:
                    if tz_sep in rtc_time_str.split("T")[-1]:
                        rtc_time_str = rtc_time_str.rsplit(tz_sep, 1)[0]
                        break

            rtc_datetime = datetime.fromisoformat(rtc_time_str)
        except ValueError as e:
            logger.error(f"Failed to parse RTC time '{rtc_time_str}': {e}")
            return False, None

        # Sanity check: is the year reasonable?
        if rtc_datetime.year < min_valid_year:
            logger.warning(
                f"RTC time ({rtc_datetime.strftime('%Y-%m-%d %H:%M:%S')}) is before "
                f"{min_valid_year} - likely invalid (battery died?). Skipping RTC sync."
            )
            return False, rtc_datetime

        # RTC time looks valid, sync it to system
        logger.info(f"RTC time looks valid: {rtc_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        pisugar_client.sync_time_from_rtc()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Synced system time from Pisugar RTC: {current_time}")
        return True, rtc_datetime

    except Exception as e:
        logger.error(f"Failed to sync from Pisugar RTC: {e}")
        return False, None


def sync_system_time(pisugar_client, config) -> dict:
    """Sync system time using configured strategy.

    Tries NTP first (if enabled), then falls back to Pisugar RTC with sanity check.

    Args:
        pisugar_client: PisugarClient instance
        config: TimeSyncConfig instance

    Returns:
        Dictionary with sync results:
        {
            "success": bool,
            "method": "ntp" | "rtc" | "failed",
            "rtc_time": datetime | None,
            "rtc_valid": bool,
        }
    """
    result = {
        "success": False,
        "method": "failed",
        "rtc_time": None,
        "rtc_valid": True,
    }

    # Try NTP first if enabled
    if config.try_ntp_first:
        logger.info("Attempting NTP sync first")
        if try_ntp_sync(timeout=config.ntp_timeout, ntp_servers=config.ntp_servers):
            result["success"] = True
            result["method"] = "ntp"
            logger.info("Time sync successful via NTP")
            return result
        logger.info("NTP sync failed, falling back to Pisugar RTC")

    # Fall back to Pisugar RTC with sanity check
    logger.info("Attempting to sync from Pisugar RTC")
    rtc_success, rtc_datetime = sync_from_pisugar_rtc(pisugar_client, config.min_valid_year)

    result["rtc_time"] = rtc_datetime
    result["rtc_valid"] = rtc_datetime is None or rtc_datetime.year >= config.min_valid_year

    if rtc_success:
        result["success"] = True
        result["method"] = "rtc"
        logger.info("Time sync successful via Pisugar RTC")
    else:
        logger.warning(
            "Failed to sync time from both NTP and Pisugar RTC. System time may be incorrect!"
        )

    return result
