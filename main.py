#!/usr/bin/env python3
"""Main entry point for the Waveshare picture frame application."""

import argparse
import logging
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from src.config import Config
from src.display.waveshare import WaveshareDisplay
from src.handlers.image_handler import ImageHandler
from src.handlers.system_handler import SystemHandler
from src.mqtt.client import MQTTClient
from src.pisugar.client import PisugarClient
from src.state import AppState

logger = logging.getLogger(__name__)


class WavesharePictureFrame:
    """Main application class."""

    def __init__(self, config: Config, dry_run: bool = False, battery_mode: bool = False):
        """Initialize the application.

        Args:
            config: Application configuration
            dry_run: If True, use mock display instead of real hardware
            battery_mode: If True, run in battery-powered mode
        """
        self.config = config
        self.dry_run = dry_run
        self.battery_mode = battery_mode
        self.display = None
        self.mqtt_client = None
        self.handlers = []
        self._shutting_down = False
        self.app_state = AppState()

        # Setup logging first
        self.setup_logging()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        if self._shutting_down:
            logger.warning("Forced shutdown!")
            sys.exit(1)

        logger.info(f"Received signal {signum}, shutting down...")
        self._shutting_down = True
        self.shutdown()
        sys.exit(0)

    def setup_logging(self):
        """Configure logging based on config."""
        logging.basicConfig(
            level=getattr(logging, self.config.logging.level),
            format=self.config.logging.format,
        )
        logger.info("Logging configured")

    def setup_display(self):
        """Initialize the display."""
        logger.info("Setting up display")

        if self.dry_run:
            from src.display.mock import MockDisplay

            self.display = MockDisplay(
                model=self.config.display.model,
                width=self.config.display.width,
                height=self.config.display.height,
            )
        else:
            self.display = WaveshareDisplay(
                model=self.config.display.model,
                width=self.config.display.width,
                height=self.config.display.height,
            )

        self.display.init()
        logger.info("Display setup complete")

    def setup_handlers(self):
        """Initialize message handlers."""
        logger.info("Setting up handlers")

        assert self.display is not None, "Display must be initialized before setting up handlers"

        # Add system handler (for mode control)
        system_handler = SystemHandler(self.app_state)
        self.handlers.append(system_handler)

        # Add image handler
        image_handler = ImageHandler(self.display)
        self.handlers.append(image_handler)

        logger.info(f"Initialized {len(self.handlers)} handler(s)")

    def setup_mqtt(self):
        """Initialize MQTT client and register handlers."""
        logger.info("Setting up MQTT client")

        self.mqtt_client = MQTTClient(
            broker_host=self.config.mqtt.host,
            broker_port=self.config.mqtt.port,
            client_id=self.config.mqtt.client_id,
            username=self.config.mqtt.username,
            password=self.config.mqtt.password,
            shutdown_timeout=self.config.mqtt.shutdown_timeout,
        )

        # Register handlers
        for handler in self.handlers:
            self.mqtt_client.register_handler(handler)

        # Add topics
        for topic in self.config.mqtt.topics:
            self.mqtt_client.add_topic(topic)

        # Connect to broker
        self.mqtt_client.connect()
        logger.info("MQTT setup complete")

    def run(self):
        """Run the application."""
        if self.battery_mode or self.config.pisugar.enabled:
            self.run_battery_mode()
        else:
            self.run_normal_mode()

    def run_normal_mode(self):
        """Run in normal always-on mode."""
        try:
            logger.info("Starting Waveshare Picture Frame (normal mode)")

            # Setup components
            self.setup_display()
            self.setup_handlers()
            self.setup_mqtt()

            assert self.mqtt_client is not None, "MQTT client must be initialized"

            # Run MQTT client (blocking)
            self.mqtt_client.run_forever()

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            self.shutdown()

    def run_battery_mode(self):
        """Run in battery-powered mode with Pisugar RTC wake-up."""
        try:
            logger.info("Starting Waveshare Picture Frame (battery mode)")

            # Setup components
            self.setup_display()
            self.setup_handlers()
            self.setup_mqtt()

            assert self.mqtt_client is not None, "MQTT client must be initialized"

            # Publish battery status to MQTT
            try:
                # Create Pisugar client to read battery level
                if self.config.pisugar.use_tcp:
                    pisugar = PisugarClient(
                        host=self.config.pisugar.tcp_host,
                        port=self.config.pisugar.tcp_port,
                    )
                else:
                    pisugar = PisugarClient(socket_path=self.config.pisugar.socket_path)

                battery_level = pisugar.get_battery_level()
                if battery_level is not None:
                    # Publish battery status
                    battery_payload = {
                        "battery_level": battery_level,
                        "timestamp": datetime.now().isoformat(),
                    }
                    self.mqtt_client.publish(
                        topic=self.config.pisugar.battery_topic,
                        payload=battery_payload,
                        qos=1,
                    )
                    logger.info(f"Published battery level: {battery_level:.1f}%")
                else:
                    logger.warning("Could not read battery level from Pisugar")
            except Exception as e:
                logger.error(f"Failed to publish battery status: {e}")

            # Check for messages with timeout
            timeout = self.config.pisugar.message_wait_timeout
            messages_processed = self.mqtt_client.run_once(timeout=timeout)

            logger.info(f"Battery mode: processed {messages_processed} message(s)")

            # Check if continuous mode was enabled via MQTT command
            if self.app_state.is_continuous_mode():
                logger.info(
                    "Continuous mode enabled - switching to always-on mode. "
                    "Device will not shutdown automatically."
                )
                # Reconnect MQTT and run forever
                self.mqtt_client.connect()
                self.mqtt_client.run_forever()
                return  # Skip RTC alarm and shutdown

            # Setup Pisugar RTC alarm for next wake-up
            if self.config.pisugar.shutdown_after_display:
                try:
                    # Create Pisugar client (TCP or Unix socket based on config)
                    if self.config.pisugar.use_tcp:
                        pisugar = PisugarClient(
                            host=self.config.pisugar.tcp_host,
                            port=self.config.pisugar.tcp_port,
                        )
                    else:
                        pisugar = PisugarClient(socket_path=self.config.pisugar.socket_path)

                    # Get battery level for logging
                    battery_level = pisugar.get_battery_level()
                    if battery_level is not None:
                        logger.info(f"Battery level: {battery_level:.1f}%")

                    # Calculate next wake time
                    wake_interval = timedelta(minutes=self.config.pisugar.wake_interval_minutes)
                    next_wake = datetime.now() + wake_interval
                    logger.info(
                        f"Setting RTC alarm for {next_wake.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"({self.config.pisugar.wake_interval_minutes} minutes from now)"
                    )

                    # Set RTC alarm
                    pisugar.set_rtc_alarm(next_wake)

                    # Verify alarm was set
                    if pisugar.is_rtc_alarm_enabled():
                        alarm_time = pisugar.get_rtc_alarm_time()
                        logger.info(f"RTC alarm confirmed: {alarm_time}")
                    else:
                        logger.warning("RTC alarm may not have been set correctly")

                except Exception as e:
                    logger.error(f"Failed to set RTC alarm: {e}", exc_info=True)
                    logger.warning("Continuing without RTC alarm")

                # Shutdown the system
                logger.info("Initiating system shutdown")
                try:
                    # Use subprocess to run shutdown command
                    # Note: Requires passwordless sudo for shutdown command
                    subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to shutdown system: {e}")
                    logger.error(
                        "Make sure the user has passwordless sudo for shutdown. "
                        "Add to /etc/sudoers.d/waveshare-frame:\n"
                        "waveshare ALL=(ALL) NOPASSWD: /sbin/shutdown"
                    )
                except FileNotFoundError:
                    logger.error("shutdown command not found")

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Battery mode error: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """Gracefully shutdown the application."""
        logger.info("Shutting down application")

        # Disconnect MQTT
        if self.mqtt_client:
            try:
                self.mqtt_client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting MQTT: {e}")

        # Sleep display
        if self.display and self.display.is_initialized:
            try:
                self.display.sleep()
            except Exception as e:
                logger.error(f"Error shutting down display: {e}")

        logger.info("Shutdown complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Waveshare e-ink picture frame with MQTT support")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="config.toml",
        help="Path to configuration file (default: config.toml)",
    )
    parser.add_argument(
        "--test-display",
        action="store_true",
        help="Test the display with a sample image and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mock display instead of real hardware (for testing MQTT without hardware)",
    )
    parser.add_argument(
        "--battery-mode",
        action="store_true",
        help="Run in battery mode: check for messages, display, set RTC alarm, and shutdown",
    )

    args = parser.parse_args()

    # Check if config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Configuration file not found: {config_path}")
        print("Please create a config.toml file or specify a different path with -c")
        sys.exit(1)

    # Load configuration
    try:
        config = Config.from_file(str(config_path))
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Test mode
    if args.test_display:
        logging.basicConfig(level=logging.DEBUG)
        logger.info("Running display test")

        try:
            display = WaveshareDisplay(
                model=config.display.model,
                width=config.display.width,
                height=config.display.height,
            )
            display.init()

            # Create test image
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (display.width, display.height), (255, 255, 255))
            draw = ImageDraw.Draw(image)

            # Draw test pattern
            draw.rectangle((10, 10, display.width - 10, display.height - 10), outline=(0, 0, 0))
            draw.text(
                (display.width // 2 - 50, display.height // 2 - 10),
                "Test Image",
                fill=(0, 0, 0),
            )

            display.display_image(image)
            logger.info("Test image displayed. Press Ctrl+C to exit")

            input()  # Wait for user input
            display.clear()
            display.sleep()

        except Exception as e:
            logger.error(f"Display test failed: {e}")
            sys.exit(1)

        logger.info("Display test complete")
        sys.exit(0)

    # Run application
    app = WavesharePictureFrame(config, dry_run=args.dry_run, battery_mode=args.battery_mode)
    app.run()


if __name__ == "__main__":
    main()
