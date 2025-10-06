"""Pisugar client for RTC alarm and power management."""

import logging
import socket
from datetime import datetime

logger = logging.getLogger(__name__)


class PisugarClient:
    """Client for communicating with Pisugar power manager via Unix socket or TCP."""

    def __init__(
        self,
        socket_path: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8423,
    ):
        """Initialize Pisugar client.

        Args:
            socket_path: Path to Pisugar Unix domain socket (if None, uses TCP)
            host: TCP host (default: 127.0.0.1, only used if socket_path is None)
            port: TCP port (default: 8423, only used if socket_path is None)
        """
        self.socket_path = socket_path
        self.host = host
        self.port = port
        self.use_tcp = socket_path is None

    def _send_command(self, command: str) -> str:
        """Send command to Pisugar and return response.

        Args:
            command: Command to send

        Returns:
            Response string from Pisugar

        Raises:
            ConnectionError: If connection to Pisugar fails
            TimeoutError: If command times out
        """
        try:
            # Create socket (Unix domain or TCP)
            if self.use_tcp:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)  # 5 second timeout
                sock.connect((self.host, self.port))
                logger.debug(
                    f"Sending command to Pisugar via TCP {self.host}:{self.port}: {command}"
                )
            else:
                if self.socket_path is None:
                    raise ValueError("socket_path must be provided when use_tcp is False")
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(5.0)  # 5 second timeout
                sock.connect(self.socket_path)
                logger.debug(
                    f"Sending command to Pisugar via Unix socket {self.socket_path}: {command}"
                )

            # Send command (must end with newline)
            sock.sendall(f"{command}\n".encode())

            # Receive response (read all available data)
            sock.settimeout(1.0)  # 1 second timeout for reading
            response_parts = []
            while True:
                try:
                    chunk = sock.recv(1024).decode("utf-8")
                    if not chunk:
                        break
                    response_parts.append(chunk)
                except TimeoutError:
                    # No more data available
                    break

            response = "".join(response_parts).strip()
            logger.debug(f"Pisugar response: {response}")

            sock.close()
            return response

        except FileNotFoundError as e:
            raise ConnectionError(
                f"Pisugar socket not found at {self.socket_path}. Is pisugar-server running?"
            ) from e
        except ConnectionRefusedError as e:
            if self.use_tcp:
                raise ConnectionError(
                    f"Connection refused to Pisugar at {self.host}:{self.port}. "
                    "Is pisugar-server running?"
                ) from e
            raise ConnectionError(
                "Connection refused to Pisugar socket. Is pisugar-server running?"
            ) from e
        except TimeoutError as e:
            raise TimeoutError(f"Timeout waiting for Pisugar response to: {command}") from e
        except Exception as e:
            raise ConnectionError(f"Failed to communicate with Pisugar: {e}") from e

    def set_rtc_alarm(self, wake_time: datetime, repeat: int = 127) -> None:
        """Set RTC alarm for wake-up.

        Args:
            wake_time: Time to wake up
            repeat: Repeat pattern (127 = all days, default)

        Raises:
            ConnectionError: If connection to Pisugar fails
        """
        # Format time in ISO8601 format (YYYY-MM-DDTHH:MM:SS)
        iso_time = wake_time.strftime("%Y-%m-%dT%H:%M:%S")
        command = f"rtc_alarm_set {iso_time} {repeat}"

        logger.info(f"Setting RTC alarm for {iso_time}")
        response = self._send_command(command)

        # Check if command succeeded
        if "rtc_alarm_set" not in response.lower():
            logger.warning(f"Unexpected response from set_rtc_alarm: {response}")

    def disable_rtc_alarm(self) -> None:
        """Disable RTC alarm.

        Raises:
            ConnectionError: If connection to Pisugar fails
        """
        logger.info("Disabling RTC alarm")
        self._send_command("rtc_alarm_disable")

    def get_battery_level(self) -> float | None:
        """Get current battery level percentage.

        Returns:
            Battery level (0-100) or None if failed

        Raises:
            ConnectionError: If connection to Pisugar fails
        """
        try:
            response = self._send_command("get battery")
            # Response format: "single\nbattery: 98.37336" (multi-line)
            # Look for line containing "battery:"
            for line in response.split("\n"):
                if "battery:" in line.lower():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        battery_str = parts[1].strip().rstrip("%")
                        return float(battery_str)
            logger.warning(f"Unexpected battery response: {response}")
            return None
        except Exception as e:
            logger.error(f"Failed to get battery level: {e}")
            return None

    def get_rtc_alarm_time(self) -> str | None:
        """Get currently configured RTC alarm time.

        Returns:
            ISO8601 time string or None if not set

        Raises:
            ConnectionError: If connection to Pisugar fails
        """
        try:
            response = self._send_command("get rtc_alarm_time")
            # Response may be multi-line, look for line with "rtc_alarm_time:"
            for line in response.split("\n"):
                if "rtc_alarm_time:" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) >= 2:
                        return parts[1].strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get RTC alarm time: {e}")
            return None

    def is_rtc_alarm_enabled(self) -> bool:
        """Check if RTC alarm is enabled.

        Returns:
            True if enabled, False otherwise

        Raises:
            ConnectionError: If connection to Pisugar fails
        """
        try:
            response = self._send_command("get rtc_alarm_enabled")
            # Response may be multi-line, check if "true" appears in response
            return "true" in response.lower()
        except Exception as e:
            logger.error(f"Failed to check RTC alarm status: {e}")
            return False
