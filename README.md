# Waveshare Picture Frame

A Python application that displays images on Waveshare e-ink displays via MQTT messages.

## Features

- Receives MQTT messages and displays images from URLs on Waveshare e-ink displays
- Supports multiple Waveshare display models (7in3e, 7in5, 7in5_V2)
- Configurable via TOML file
- Runs as a systemd service on Raspberry Pi
- Includes dry-run mode for development without hardware
- Publishes preview thumbnails to Home Assistant via MQTT
- Standalone: shows a random image from a local folder when no MQTT image arrives
- Desktop CLI (`prepare_image.py`) to crop and colour-convert images so the Pi shows them as-is

## Installation

### Standard Installation (Mac/Linux/Windows)

Requires Python 3.13 and uv package manager.

```bash
uv sync
```

### Hardware Platform Installation

Install with platform-specific GPIO libraries:

```bash
# Raspberry Pi
uv sync --extra rpi

# Jetson Nano
uv sync --extra jetson

# Horizon Robotics (Hobot.GPIO not on PyPI, install manually)
uv sync
pip install Hobot.GPIO spidev
```

### Raspberry Pi Zero W (System Packages)

If you need system-installed Pillow on Pi Zero W:

```bash
sudo apt-get update
sudo apt-get install -y python3-pil python3-numpy python3-rpi.gpio python3-spidev
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
uv pip install paho-mqtt requests
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

Use `"random": true` instead of `url` to show a random image from the local image folder
(same as the startup fallback, handy for testing without restarting):

```json
{"action": "display_image", "data": {"random": true}}
```

## Local Image Folder

On startup (every mode; in battery mode that is every wake-up) the frame waits
`pisugar.message_wait_timeout` seconds (default 5) for an MQTT message. If no image arrives
(or fetching it fails), it shows a random image from `local_images.path`, searched
recursively. Hidden files and folders are skipped. If MQTT is unreachable, the frame still
shows a local image; battery mode then sets the RTC alarm and shuts down, normal mode exits.
In normal mode, MQTT images keep replacing it as they arrive.

```toml
[local_images]
path = "/home/pi/frame-images"
```

Sync the folder from your computer with rsync, e.g.:

```bash
rsync -av --delete prepared/ pi@frame.local:/home/pi/frame-images/
```

Images that are already **panel-ready** (exactly the panel size, using only the panel's pure
driver colours) are displayed without any processing. Everything else gets a barebones
conversion on the Pi: border auto-crop, centre crop/resize and Floyd-Steinberg dithering.

## Manual Wake-Up (Battery Mode)

In battery mode, pressing the PiSugar button while the frame sleeps wakes it as usual, but it
then stays on (continuous mode) instead of shutting down again, so you can SSH in. Reboot it
or restart the service to return to the normal sleep cycle. Disable with
`pisugar.stay_on_after_manual_wake = false`.

PiSugar doesn't tell the Pi why it powered on, so the frame infers it: a boot within a few
minutes of the scheduled RTC alarm counts as the alarm, anything else as a button press.

## Preparing Images (`prepare_image.py`)

Run on your computer (not the Pi) to turn any image into a panel-ready PNG:

```bash
uv run python prepare_image.py SOURCE DESTINATION [--crop X,Y,W,H] [--preview PREVIEW.png]

# Crop box in source pixels (x,y = top-left), or as percentages of the image size
uv run python prepare_image.py painting.jpg prepared/ --crop 120,340,2400,1440
uv run python prepare_image.py painting.jpg prepared/painting.png --crop 0%,10%,100%,60%
```

- `--crop` is grown to the panel's 5:3 aspect ratio around its centre, so nothing in the box
  is lost; only if the image is too small is the box cut down (reported as `"cut": true`).
  Without `--crop`, the largest centred 5:3 box is used. Coordinates refer to the upright
  image (EXIF orientation applied).
- Colour conversion uses measured Spectra 6 ink colours, perceptual gamut mapping and Burkes
  error diffusion (`--dither` to change). Override a measured ink with
  `--ink green=#4f7352` if you measure your own panel.
- The output PNG stores the driver's pure colours, so it looks garish on screen. Use
  `--preview` to write a simulation of how the panel will actually look.
- Prints a one-line JSON summary (source size, final crop box, `cut`, `upscaled`, paths).

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
