# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python 3.13 application for controlling Waveshare e-ink displays via MQTT messages. The application subscribes to MQTT topics and displays images from URLs on the e-ink display. Designed to run on Raspberry Pi but can be developed/tested on any platform using dry-run mode.

## Development Commands

### Setup

**Standard installation (Mac/Linux/Windows with Python 3.13):**
```bash
uv sync               # Install dependencies (paho-mqtt, pillow, requests)
```

**Raspberry Pi installation:**
```bash
uv sync --extra rpi     # Installs RPi.GPIO and spidev
```

**Jetson Nano installation:**
```bash
uv sync --extra jetson  # Installs Jetson.GPIO
```

**Horizon Robotics installation:**
Hobot.GPIO is not available on PyPI, install manually:
```bash
uv sync
pip install Hobot.GPIO spidev  # Install from Horizon's repository
```

**Raspberry Pi Zero W (using system packages for Pillow):**
If you need to use system-installed Pillow/numpy on Pi Zero W:
```bash
sudo apt-get update
sudo apt-get install -y python3-pil python3-numpy python3-rpi.gpio python3-spidev
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
uv pip install paho-mqtt requests
```

### Running the application
```bash
python main.py                     # Run with default config.toml
python main.py -c custom.toml      # Run with custom config file
python main.py --test-display      # Test display with sample image and exit
python main.py --dry-run           # Run with mock display (for testing MQTT without hardware)
python main.py --battery-mode      # Run in battery-powered mode (Pisugar RTC)
```

**Dry-run mode** (`--dry-run`):
- Uses `MockDisplay` instead of `WaveshareDisplay` to avoid hardware initialization
- Logs all display operations without requiring Waveshare hardware or Raspberry Pi
- Essential for development on Mac/Windows/x86 Linux
- Perfect for testing MQTT integration and message handlers

**Battery mode** (`--battery-mode` or `pisugar.enabled = true` in config):
- Designed for Pisugar 3 battery-powered operation on Raspberry Pi Zero W
- Wake-check-display-sleep cycle:
  1. Connects to MQTT with QoS 2 + clean_session=false (queues messages while offline)
  2. Publishes battery status to configured MQTT topic (JSON: `{"battery_level": 98.37, "timestamp": "2025-10-06T10:38:00"}`)
  3. Waits for messages (configurable timeout, default 30s)
  4. Processes any queued/new messages
  5. Sets Pisugar RTC alarm for next wake-up (configurable interval, default 15 mins)
  6. Shuts down the system
- Pisugar communication: Uses TCP (127.0.0.1:8423) by default to avoid Unix socket permission issues. Can use Unix socket by setting `use_tcp = false` in config.
- Pisugar RTC alarm: Only stores time-of-day (HH:MM:SS), not full date. Alarm triggers at the specified time according to the repeat pattern (default: 127 = all days). Timezone must match RTC timezone (auto-detected from `get rtc_time`).
- Battery status publishing: Publishes to `battery_topic` (default: `home/displays/waveshare/battery`) on each wake-up for monitoring
- Requires passwordless sudo for shutdown: `pi ALL=(ALL) NOPASSWD: /sbin/shutdown`
- Battery life: weeks/months instead of hours with always-on mode
- **Switching to continuous mode**: Send MQTT command `{"action": "enter_continuous_mode"}` to prevent shutdown and switch to always-on mode. Useful for SSH access and maintenance. Device stays connected to MQTT until manually rebooted.
- See `waveshare-frame.service` for deployment instructions

**Signal handling:**
- First Ctrl+C: Graceful shutdown (disconnects MQTT, clears display, sleeps hardware)
- Second Ctrl+C: Force exit immediately

### Code quality
```bash
uv run ruff check .          # Run linter
uv run ruff format .         # Format code
uv run ruff check --fix .    # Auto-fix linting issues
```

### Deployment (Raspberry Pi)
```bash
# 1. Edit waveshare-frame.service and update paths/user as needed
# 2. Copy to systemd directory
sudo cp waveshare-frame.service /etc/systemd/system/
# 3. Enable and start the service
sudo systemctl enable waveshare-frame.service
sudo systemctl start waveshare-frame.service
# 4. Check status
sudo systemctl status waveshare-frame.service
# 5. View logs
journalctl -u waveshare-frame -f
```

## Architecture

### High-Level Design

**Plugin-based handler architecture:**
- MQTT client receives messages and routes them to registered handlers
- Handlers are registered dynamically in `main.py` via `register_handler()`
- Each handler implements `HandlerBase` interface with `can_handle()` and `handle()` methods
- Handlers receive a display instance in their constructor for rendering operations
- New message types can be added by creating new handlers without modifying MQTT client

**Configuration system:**
- Primary config loaded from TOML file (`config.toml`)
- Environment variables override TOML values (format: `WAVESHARE_<SECTION>_<KEY>`)
- Supports both file-based and systemd environment-based configuration
- Config classes use dataclasses for type safety

**Display abstraction:**
- `DisplayBase` abstract class defines the display interface
- `WaveshareDisplay` implements real hardware via waveshare-epd library
- `MockDisplay` implements logging-only version for development/testing
- All display operations (init, display_image, clear, sleep) are abstracted
- Image resizing/fitting logic is shared in the base class

### Key Files

- **main.py**: Application orchestrator - initializes config, display, handlers, MQTT client; handles signals; supports battery mode
- **src/config.py**: TOML parsing + environment variable override logic; includes PisugarConfig
- **src/mqtt/client.py**: MQTT v2 client with handler registry and message routing; supports both always-on (`run_forever()`) and one-shot (`run_once()`) modes
- **src/handlers/base.py**: Abstract handler interface (can_handle, handle, supported_actions)
- **src/handlers/image_handler.py**: Fetches images from URLs and displays them
- **src/handlers/system_handler.py**: System control commands (mode switching, runtime control)
- **src/state.py**: Shared application state for runtime mode switching
- **src/display/base.py**: Abstract display interface with shared image resizing
- **src/display/waveshare.py**: Real hardware implementation using waveshare-epd library
- **src/display/mock.py**: Mock display for development without hardware
- **src/pisugar/client.py**: Pisugar power manager client for RTC alarm and battery status

### MQTT Message Protocol

Messages must be JSON with `action` and optional `data` fields:

```json
{
  "action": "display_image",
  "data": {
    "url": "https://example.com/image.jpg",
    "resize": true,
    "clear_first": true
  }
}
```

The MQTT client calls `handler.can_handle(action)` for each registered handler until one returns `True`, then calls `handler.handle(data)`.

**Supported Actions:**

1. **display_image** - Display an image from URL
   ```json
   {
     "action": "display_image",
     "data": {
       "url": "https://example.com/image.jpg",
       "resize": true,
       "clear_first": false
     }
   }
   ```

2. **enter_continuous_mode** - Switch from battery mode to continuous mode
   ```json
   {
     "action": "enter_continuous_mode"
   }
   ```
   When in battery mode, this prevents the scheduled shutdown and switches to always-on mode. Useful for maintenance, debugging, or SSH access. Device will stay connected to MQTT until manually rebooted.

### Configuration

**File-based (config.toml):**
```toml
[mqtt]
host = "192.168.1.101"
port = 1883
username = "user"      # Optional
password = "pass"      # Optional
topics = ["home/displays/waveshare/command"]

[display]
model = "7in3e"        # 7in3e, 7in5, 7in5_V2
width = 800
height = 480

[logging]
level = "INFO"         # DEBUG, INFO, WARNING, ERROR

[pisugar]
enabled = false                     # Enable battery mode
wake_interval_minutes = 15          # Minutes between wake-ups
use_tcp = true                      # Use TCP instead of Unix socket (avoids permission issues)
tcp_host = "127.0.0.1"              # Pisugar TCP host
tcp_port = 8423                     # Pisugar TCP port
socket_path = "/tmp/pisugar-server.sock"  # Unix socket (only if use_tcp = false)
message_wait_timeout = 30           # Seconds to wait for MQTT messages
shutdown_after_display = true       # Shutdown after processing
battery_topic = "home/displays/waveshare/battery"  # MQTT topic for battery status
```

**Environment overrides:**
- `WAVESHARE_MQTT_HOST`, `WAVESHARE_MQTT_PORT`, `WAVESHARE_MQTT_USERNAME`, `WAVESHARE_MQTT_PASSWORD`, `WAVESHARE_MQTT_CLIENT_ID`
- `WAVESHARE_DISPLAY_MODEL`, `WAVESHARE_DISPLAY_WIDTH`, `WAVESHARE_DISPLAY_HEIGHT`
- `WAVESHARE_LOGGING_LEVEL`
- `WAVESHARE_PISUGAR_ENABLED`, `WAVESHARE_PISUGAR_WAKE_INTERVAL_MINUTES`, `WAVESHARE_PISUGAR_USE_TCP`, `WAVESHARE_PISUGAR_TCP_HOST`, `WAVESHARE_PISUGAR_TCP_PORT`, `WAVESHARE_PISUGAR_SOCKET_PATH`, `WAVESHARE_PISUGAR_MESSAGE_WAIT_TIMEOUT`, `WAVESHARE_PISUGAR_SHUTDOWN_AFTER_DISPLAY`, `WAVESHARE_PISUGAR_BATTERY_TOPIC`

### Adding New Message Handlers

1. Create new handler class in `src/handlers/` extending `HandlerBase`
2. Implement `can_handle()`, `handle()`, and `supported_actions` property
3. Register handler in `main.py` in `setup_handlers()` method
4. Handler receives display instance and can call `display.display_image()`, `display.clear()`, etc.

Example:
```python
class MyHandler(HandlerBase):
    def can_handle(self, action: str) -> bool:
        return action in self.supported_actions

    def handle(self, data: dict[str, Any]) -> None:
        # Process data and interact with self.display
        pass

    @property
    def supported_actions(self) -> list[str]:
        return ["my_action"]
```

## Important Technical Notes

- **paho-mqtt v2.x API**: Uses `CallbackAPIVersion.VERSION2` with different callback signatures than v1.x (callbacks receive `reason_code` and `properties` parameters)
- **Python 3.13 required**: Uses modern type hints (`dict`, `list`, `X | None` instead of `Dict`, `List`, `Optional[X]`)
- **waveshare-epd vendored**: The waveshare_epd drivers are vendored in `src/vendor/waveshare_epd/` to avoid cloning the massive GitHub repo. Imports use `from src.vendor.waveshare_epd import ...`
- **Platform-specific GPIO**: Use optional dependencies via `--extra rpi` or `--extra jetson` to install platform-specific GPIO libraries (RPi.GPIO, Jetson.GPIO). Hobot.GPIO must be installed manually.
- **MQTT authentication**: Supports username-only or username+password (password is optional)
- **Ruff configuration**: Line length 100, targets Python 3.13, uses pycodestyle, pyflakes, isort, flake8-bugbear, comprehensions, and pyupgrade rules