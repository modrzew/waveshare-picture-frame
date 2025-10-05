# Waveshare E-Paper Display Drivers (Vendored)

This directory contains vendored Python drivers for Waveshare e-Paper displays.

## Source

- **Repository**: https://github.com/waveshareteam/e-Paper
- **Subdirectory**: `RaspberryPi_JetsonNano/python/lib/waveshare_epd`
- **Commit**: `b304c5151aa1edb31bc35e9eaf660f4dc7769590`
- **Date**: 2024-08-12

## Why Vendored?

The Waveshare e-Paper repository is very large (~500MB+) and contains code for multiple platforms (Arduino, STM32, Raspberry Pi, etc.). Cloning the entire repository fails on some systems due to filesystem issues with certain files.

By vendoring only the Python drivers we need (~2MB), we avoid:
- Large git clone times and bandwidth usage
- Filesystem errors during `pip install` from git
- Dependency on external repository availability

## License

The Waveshare e-Paper drivers are provided under the MIT License by Waveshare.

See: https://github.com/waveshareteam/e-Paper/blob/master/LICENSE

## Usage

Import drivers using the vendored path:

```python
from src.vendor.waveshare_epd import epd7in3e

epd = epd7in3e.EPD()
epd.init()
```

## Supported Models

This vendored copy includes drivers for all Waveshare e-Paper models. The models used in this project are:
- 7.3inch e-Paper (E) - `epd7in3e`
- 7.5inch e-Paper - `epd7in5`
- 7.5inch e-Paper V2 - `epd7in5_V2`

## Updating

To update to a newer version:

```bash
cd /tmp
git clone --depth 1 --filter=blob:none --sparse https://github.com/waveshareteam/e-Paper.git
cd e-Paper
git sparse-checkout set RaspberryPi_JetsonNano/python

# Get commit hash
git log -1 --format="%H"

# Copy files
cp -r RaspberryPi_JetsonNano/python/lib/waveshare_epd /path/to/waveshare-picture-frame/src/vendor/

# Clean up compiled files
find src/vendor/waveshare_epd -name "*.pyc" -delete
find src/vendor/waveshare_epd -name "__pycache__" -type d -exec rm -rf {} +

# Update this README with new commit hash
```
