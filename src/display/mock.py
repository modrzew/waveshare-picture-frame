"""Mock display implementation for testing without hardware."""

import logging

from PIL import Image

from .base import DisplayBase

logger = logging.getLogger(__name__)


class MockDisplay(DisplayBase):
    """Mock display implementation that logs operations without real hardware."""

    def __init__(self, model: str = "mock", width: int = 800, height: int = 480):
        """Initialize the mock display.

        Args:
            model: Display model name (for logging purposes)
            width: Display width in pixels
            height: Display height in pixels
        """
        super().__init__(width, height)
        self.model = model
        logger.info(f"MockDisplay initialized (model={model}, {width}x{height})")

    def init(self) -> None:
        """Initialize the mock display."""
        logger.info(f"[DRY RUN] Initializing {self.model} display")
        self.is_initialized = True
        logger.info("[DRY RUN] Display initialized successfully")

    def display_image(self, image: Image.Image) -> None:
        """Log image display operation.

        Args:
            image: PIL Image object to display
        """
        if not self.is_initialized:
            raise RuntimeError("Display not initialized. Call init() first.")

        logger.info(
            f"[DRY RUN] Displaying image: mode={image.mode}, size={image.size}, "
            f"format={getattr(image, 'format', 'unknown')}"
        )

        # Optionally save the image for inspection
        if image.size != (self.width, self.height):
            logger.debug(
                f"[DRY RUN] Would resize image from {image.size} to ({self.width}, {self.height})"
            )

    def clear(self) -> None:
        """Log display clear operation."""
        if not self.is_initialized:
            raise RuntimeError("Display not initialized. Call init() first.")

        logger.info("[DRY RUN] Clearing display")

    def sleep(self) -> None:
        """Log display sleep operation."""
        if not self.is_initialized:
            raise RuntimeError("Display not initialized. Call init() first.")

        logger.info("[DRY RUN] Putting display to sleep")
        self.is_initialized = False
