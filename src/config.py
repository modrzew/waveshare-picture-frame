"""Configuration management for the application."""

import logging
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
    use_tcp: bool = True  # Use TCP instead of Unix socket (avoids permission issues)
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 8423
    socket_path: str = "/tmp/pisugar-server.sock"  # Only used if use_tcp = false
    message_wait_timeout: int = 30  # Seconds to wait for MQTT messages
    shutdown_after_display: bool = True
    battery_topic: str = "home/displays/waveshare/battery"  # MQTT topic for battery status


@dataclass
class PreviewConfig:
    """Preview image configuration for Home Assistant."""

    enabled: bool = True
    topic: str = "home/displays/waveshare/preview"  # MQTT topic for preview image
    width: int = 320  # Thumbnail width in pixels
    quality: int = 80  # JPEG quality (1-100)


@dataclass
class Config:
    """Application configuration."""

    mqtt: MQTTConfig
    display: DisplayConfig
    logging: LoggingConfig
    pisugar: PisugarConfig
    preview: PreviewConfig

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
        preview_data = data.get("preview", {})

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
            use_tcp=pisugar_data.get("use_tcp", True),
            tcp_host=pisugar_data.get("tcp_host", "127.0.0.1"),
            tcp_port=pisugar_data.get("tcp_port", 8423),
            socket_path=pisugar_data.get("socket_path", "/tmp/pisugar-server.sock"),
            message_wait_timeout=pisugar_data.get("message_wait_timeout", 30),
            shutdown_after_display=pisugar_data.get("shutdown_after_display", True),
            battery_topic=pisugar_data.get("battery_topic", "home/displays/waveshare/battery"),
        )

        preview_config = PreviewConfig(
            enabled=preview_data.get("enabled", True),
            topic=preview_data.get("topic", "home/displays/waveshare/preview"),
            width=preview_data.get("width", 320),
            quality=preview_data.get("quality", 80),
        )

        return cls(
            mqtt=mqtt_config,
            display=display_config,
            logging=logging_config,
            pisugar=pisugar_config,
            preview=preview_config,
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
