# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python application for controlling Waveshare e-ink displays via MQTT messages. The application subscribes to MQTT topics and displays images from URLs on the e-ink display.

## Development Commands

### Running the application
```bash
python main.py                     # Run with default config.toml
python main.py -c custom.toml      # Run with custom config file
python main.py --test-display      # Test display with sample image
python main.py --dry-run           # Run with mock display (for testing MQTT without hardware)
```

**Dry-run mode** is useful for:
- Testing MQTT integration on development machines without Waveshare hardware
- Debugging message handlers without affecting the physical display
- Development on non-ARM platforms (Mac, Windows, x86 Linux)

### Running as a systemd service (Raspberry Pi)
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

### Development dependencies
```bash
uv sync               # Install dependencies using uv package manager
uv pip install -e .   # Install package in development mode
```

### Code quality
```bash
uv run ruff check .          # Run linter
uv run ruff format .         # Format code
uv run ruff check --fix .    # Auto-fix linting issues
```

## Architecture

### Core Components

- **main.py**: Entry point, orchestrates initialization and signal handling
- **src/config.py**: Configuration management with TOML parsing and environment variable overrides
- **src/mqtt/client.py**: MQTT client that subscribes to topics and routes messages to handlers
- **src/handlers/**: Message handlers implementing the HandlerBase interface
  - `image_handler.py`: Fetches and displays images from URLs
- **src/display/**: Display abstractions and implementations
  - `base.py`: Abstract display interface
  - `waveshare.py`: Waveshare e-ink display driver integration
  - `mock.py`: Mock display for testing without hardware

### Message Flow

1. MQTT client receives JSON message on subscribed topic
2. Message is parsed for `action` and `data` fields
3. Appropriate handler is selected based on action type
4. Handler processes the data and interacts with display

### MQTT Message Format

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

## Configuration

Configuration is loaded from `config.toml` with environment variable overrides:
- `WAVESHARE_MQTT_*` for MQTT settings
- `WAVESHARE_DISPLAY_*` for display settings
- `WAVESHARE_LOGGING_LEVEL` for logging

## Display Models

Supported Waveshare models in `src/display/waveshare.py`:
- 7in3e (7.3inch e-Paper, default)
- 7in5 (7.5inch e-Paper)
- 7in5_V2 (7.5inch e-Paper V2)

## Dependencies

- **waveshare-epd**: Installed from Waveshare's GitHub repository
- **paho-mqtt** (v2.x): MQTT client library - uses v2 API with `CallbackAPIVersion.VERSION2`
- **Pillow**: Image processing
- **requests**: HTTP client for fetching images

## Important Notes

- The MQTT client uses **paho-mqtt v2.x API** which has different callback signatures than v1.x
- Authentication supports username-only or username+password (password is optional)