"""Configuration management for the application."""

import logging
import os
import tomllib
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MQTTConfig:
    """MQTT broker configuration."""

    host: str
    port: int = 1883
    client_id: str | None = None
    username: str | None = None
    password: str | None = None
    topics: list[str] = field(default_factory=list)
    shutdown_timeout: float = 60.0  # Seconds to wait for handlers during shutdown


@dataclass
class DisplayConfig:
    """Display configuration."""

    model: str = "7in3e"
    width: int = 800
    height: int = 480


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class PisugarConfig:
    """Pisugar battery and RTC configuration."""

    enabled: bool = False
    wake_interval_minutes: int = 15
    socket_path: str = "/tmp/pisugar-server.sock"
    message_wait_timeout: int = 30  # Seconds to wait for MQTT messages
    shutdown_after_display: bool = True


@dataclass
class Config:
    """Application configuration."""

    mqtt: MQTTConfig
    display: DisplayConfig
    logging: LoggingConfig
    pisugar: PisugarConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create config from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Config instance
        """
        mqtt_data = data.get("mqtt", {})
        display_data = data.get("display", {})
        logging_data = data.get("logging", {})
        pisugar_data = data.get("pisugar", {})

        mqtt_config = MQTTConfig(
            host=mqtt_data.get("host", "localhost"),
            port=mqtt_data.get("port", 1883),
            client_id=mqtt_data.get("client_id"),
            username=mqtt_data.get("username"),
            password=mqtt_data.get("password"),
            topics=mqtt_data.get("topics", []),
            shutdown_timeout=mqtt_data.get("shutdown_timeout", 60.0),
        )

        display_config = DisplayConfig(
            model=display_data.get("model", "7in3e"),
            width=display_data.get("width", 800),
            height=display_data.get("height", 480),
        )

        logging_config = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            format=logging_data.get(
                "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ),
        )

        pisugar_config = PisugarConfig(
            enabled=pisugar_data.get("enabled", False),
            wake_interval_minutes=pisugar_data.get("wake_interval_minutes", 15),
            socket_path=pisugar_data.get("socket_path", "/tmp/pisugar-server.sock"),
            message_wait_timeout=pisugar_data.get("message_wait_timeout", 30),
            shutdown_after_display=pisugar_data.get("shutdown_after_display", True),
        )

        return cls(
            mqtt=mqtt_config,
            display=display_config,
            logging=logging_config,
            pisugar=pisugar_config,
        )

    @classmethod
    def from_file(cls, file_path: str) -> "Config":
        """Load configuration from TOML file.

        Args:
            file_path: Path to configuration file

        Returns:
            Config instance
        """
        logger.info(f"Loading configuration from {file_path}")

        try:
            with open(file_path, "rb") as f:
                data = tomllib.load(f)

            # Override with environment variables if present
            data = cls._override_with_env(data)

            config = cls.from_dict(data)
            logger.info("Configuration loaded successfully")
            return config

        except FileNotFoundError:
            logger.error(f"Configuration file not found: {file_path}")
            raise
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Invalid TOML in configuration file: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    @staticmethod
    def _override_with_env(data: dict[str, Any]) -> dict[str, Any]:
        """Override configuration with environment variables.

        Environment variable format: WAVESHARE_<SECTION>_<KEY>
        Example: WAVESHARE_MQTT_HOST, WAVESHARE_MQTT_PORT

        Args:
            data: Configuration dictionary

        Returns:
            Updated configuration dictionary
        """
        # MQTT overrides
        if "mqtt" not in data:
            data["mqtt"] = {}

        if host := os.getenv("WAVESHARE_MQTT_HOST"):
            data["mqtt"]["host"] = host
            logger.debug(f"Overriding MQTT host from environment: {host}")

        if port := os.getenv("WAVESHARE_MQTT_PORT"):
            data["mqtt"]["port"] = int(port)
            logger.debug(f"Overriding MQTT port from environment: {port}")

        if username := os.getenv("WAVESHARE_MQTT_USERNAME"):
            data["mqtt"]["username"] = username
            logger.debug("Overriding MQTT username from environment")

        if password := os.getenv("WAVESHARE_MQTT_PASSWORD"):
            data["mqtt"]["password"] = password
            logger.debug("Overriding MQTT password from environment")

        if client_id := os.getenv("WAVESHARE_MQTT_CLIENT_ID"):
            data["mqtt"]["client_id"] = client_id
            logger.debug(f"Overriding MQTT client_id from environment: {client_id}")

        if shutdown_timeout := os.getenv("WAVESHARE_MQTT_SHUTDOWN_TIMEOUT"):
            data["mqtt"]["shutdown_timeout"] = float(shutdown_timeout)
            logger.debug(f"Overriding MQTT shutdown_timeout from environment: {shutdown_timeout}")

        # Display overrides
        if "display" not in data:
            data["display"] = {}

        if model := os.getenv("WAVESHARE_DISPLAY_MODEL"):
            data["display"]["model"] = model
            logger.debug(f"Overriding display model from environment: {model}")

        if width := os.getenv("WAVESHARE_DISPLAY_WIDTH"):
            data["display"]["width"] = int(width)
            logger.debug(f"Overriding display width from environment: {width}")

        if height := os.getenv("WAVESHARE_DISPLAY_HEIGHT"):
            data["display"]["height"] = int(height)
            logger.debug(f"Overriding display height from environment: {height}")

        # Logging overrides
        if "logging" not in data:
            data["logging"] = {}

        if level := os.getenv("WAVESHARE_LOGGING_LEVEL"):
            data["logging"]["level"] = level
            logger.debug(f"Overriding logging level from environment: {level}")

        # Pisugar overrides
        if "pisugar" not in data:
            data["pisugar"] = {}

        if enabled := os.getenv("WAVESHARE_PISUGAR_ENABLED"):
            data["pisugar"]["enabled"] = enabled.lower() in ("true", "1", "yes")
            logger.debug(f"Overriding pisugar enabled from environment: {enabled}")

        if wake_interval := os.getenv("WAVESHARE_PISUGAR_WAKE_INTERVAL_MINUTES"):
            data["pisugar"]["wake_interval_minutes"] = int(wake_interval)
            logger.debug(f"Overriding pisugar wake interval from environment: {wake_interval}")

        if socket_path := os.getenv("WAVESHARE_PISUGAR_SOCKET_PATH"):
            data["pisugar"]["socket_path"] = socket_path
            logger.debug(f"Overriding pisugar socket path from environment: {socket_path}")

        if timeout := os.getenv("WAVESHARE_PISUGAR_MESSAGE_WAIT_TIMEOUT"):
            data["pisugar"]["message_wait_timeout"] = int(timeout)
            logger.debug(f"Overriding pisugar message wait timeout from environment: {timeout}")

        if shutdown := os.getenv("WAVESHARE_PISUGAR_SHUTDOWN_AFTER_DISPLAY"):
            data["pisugar"]["shutdown_after_display"] = shutdown.lower() in ("true", "1", "yes")
            logger.debug(f"Overriding pisugar shutdown after display from environment: {shutdown}")

        return data
