"""Handler for displaying images from URLs."""

import io
import logging
from typing import Any

import requests
from PIL import Image

from src.display.base import DisplayBase

from .base import HandlerBase

logger = logging.getLogger(__name__)


class ImageHandler(HandlerBase):
    """Handler for loading and displaying images from URLs."""

    def __init__(self, display: DisplayBase, timeout: int = 30):
        """Initialize the image handler.

        Args:
            display: Display instance to use for rendering
            timeout: Request timeout in seconds
        """
        super().__init__(display)
        self.timeout = timeout

    @property
    def supported_actions(self) -> list[str]:
        """List of supported action types."""
        return ["display_image"]

    def can_handle(self, action: str) -> bool:
        """Check if this handler can process the given action.

        Args:
            action: Action type from the message

        Returns:
            True if this handler can process the action
        """
        return action in self.supported_actions

    def handle(self, data: dict[str, Any]) -> None:
        """Process the image display request.

        Args:
            data: Message data containing:
                - url: Image URL to load
                - resize: Whether to resize the image (default: True)
                - clear_first: Whether to clear display first (default: True)
        """
        url = data.get("url")
        if not url:
            raise ValueError("Missing 'url' in message data")

        resize = data.get("resize", True)
        clear_first = data.get("clear_first", True)

        try:
            # Clear display if requested
            if clear_first:
                logger.debug("Clearing display before showing new image")
                self.display.clear()

            # Fetch image from URL
            logger.info(f"Fetching image from: {url}")
            response = requests.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            # Load image
            image_data = io.BytesIO(response.content)
            image = Image.open(image_data)
            logger.info(f"Image loaded successfully: {image.size} {image.mode}")

            # Resize if requested
            if resize:
                image = self.display.resize_image(image)

            # Display the image
            self.display.display_image(image)
            logger.info("Image displayed successfully")

        except requests.RequestException as e:
            logger.error(f"Failed to fetch image from {url}: {e}")
            raise
        except OSError as e:
            logger.error(f"Failed to process image: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error handling image: {e}")
            raise
