# Waveshare Picture Frame

A Python application that displays images on Waveshare e-ink displays via MQTT messages.

## Features

- Receives MQTT messages and displays images from URLs on Waveshare e-ink displays
- Supports multiple Waveshare display models (7in3e, 7in5, 7in5_V2)
- Configurable via TOML file or environment variables
- Runs as a systemd service on Raspberry Pi
- Includes dry-run mode for development without hardware

## Installation

Requires Python 3.13 and uv package manager.

```bash
uv sync
```

## Usage

```bash
python main.py                 # Run with config.toml
python main.py --dry-run       # Run without hardware (testing)
```

### MQTT Message Format

Send JSON messages to the configured topic:

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

Edit `config.toml` to configure MQTT broker, display model, and other settings.

```toml
[mqtt]
host = "192.168.1.100"
port = 1883
username = "user"
password = "pass"
topics = ["home/displays/waveshare/command"]

[display]
model = "7in3e"
width = 800
height = 480
```

## Deployment

For Raspberry Pi deployment as a systemd service, see the included `waveshare-frame.service` file.

## Documentation

See `CLAUDE.md` for architecture details and development guidance.
