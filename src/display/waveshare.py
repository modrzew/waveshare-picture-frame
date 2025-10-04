"""Waveshare e-ink display implementation."""

import logging

from PIL import Image

from .base import DisplayBase

logger = logging.getLogger(__name__)


class WaveshareDisplay(DisplayBase):
    """Waveshare e-ink display implementation."""

    def __init__(self, model: str = "7in3e", width: int = 800, height: int = 480):
        """Initialize the Waveshare display.

        Args:
            model: Waveshare model (e.g., "7in3e" for 7.3inch e-Paper)
            width: Display width in pixels
            height: Display height in pixels
        """
        super().__init__(width, height)
        self.model = model
        self.epd = None

    def _get_epd_module(self):
        """Get the appropriate EPD module for the display model."""
        try:
            if self.model == "7in3e":
                from waveshare_epd import epd7in3e

                return epd7in3e.EPD()
            elif self.model == "7in5":
                from waveshare_epd import epd7in5

                return epd7in5.EPD()
            elif self.model == "7in5_V2":
                from waveshare_epd import epd7in5_V2

                return epd7in5_V2.EPD()
            else:
                raise ValueError(f"Unsupported Waveshare model: {self.model}")
        except ImportError as e:
            logger.error(f"Failed to import Waveshare EPD module: {e}")
            raise

    def init(self) -> None:
        """Initialize the display hardware."""
        try:
            logger.info(f"Initializing Waveshare {self.model} display")
            self.epd = self._get_epd_module()
            self.epd.init()
            self.epd.Clear()
            self.is_initialized = True
            logger.info("Display initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")
            raise

    def display_image(self, image: Image.Image) -> None:
        """Display an image on the e-ink display.

        Args:
            image: PIL Image object to display
        """
        if not self.is_initialized:
            raise RuntimeError("Display not initialized. Call init() first.")

        try:
            # Ensure image is in the correct mode
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Resize image if necessary
            if image.size != (self.width, self.height):
                logger.debug(f"Resizing image from {image.size} to ({self.width}, {self.height})")
                image = self.resize_image(image)

            # Display the image
            logger.info("Displaying image on e-ink display")
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Image displayed successfully")

        except Exception as e:
            logger.error(f"Failed to display image: {e}")
            raise

    def clear(self) -> None:
        """Clear the display."""
        if not self.is_initialized:
            raise RuntimeError("Display not initialized. Call init() first.")

        try:
            logger.info("Clearing display")
            self.epd.Clear()
            logger.info("Display cleared")
        except Exception as e:
            logger.error(f"Failed to clear display: {e}")
            raise

    def sleep(self) -> None:
        """Put the display into low power mode."""
        if not self.is_initialized:
            raise RuntimeError("Display not initialized. Call init() first.")

        try:
            logger.info("Putting display to sleep")
            self.epd.sleep()
            self.is_initialized = False
            logger.info("Display in sleep mode")
        except Exception as e:
            logger.error(f"Failed to put display to sleep: {e}")
            raise

    def __del__(self):
        """Clean up resources on deletion."""
        if self.is_initialized and self.epd:
            try:
                self.sleep()
            except Exception:
                pass
