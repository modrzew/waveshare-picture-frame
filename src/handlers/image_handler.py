"""Handler for displaying images from URLs."""

import io
import logging
from typing import Any

import requests

from src.display.renderer import ImageRenderer
from src.state import AppState
from src.utils.image_processing import open_image

from .base import HandlerBase

logger = logging.getLogger(__name__)

# Some image hosts (e.g. Wikimedia, Art Institute of Chicago) reject the default
# python-requests User-Agent with a 403.
USER_AGENT = "waveshare-picture-frame/1.0"


class ImageHandler(HandlerBase):
    """Handler for loading and displaying images from URLs."""

    def __init__(
        self,
        renderer: ImageRenderer,
        app_state: AppState | None = None,
        timeout: int = 30,
    ):
        """Initialize the image handler.

        Args:
            renderer: Renderer that shows images on the display
            app_state: Optional shared state to record whether an image was shown
            timeout: Request timeout in seconds
        """
        super().__init__(renderer.display)
        self.renderer = renderer
        self.app_state = app_state
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
                - clear_first: Whether to clear display first (default: False)
        """
        try:
            url = data.get("url")
            if not url:
                raise ValueError("Missing 'url' in message data")

            logger.info(f"Fetching image from: {url}")
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()

            display = self.renderer.display
            image = open_image(io.BytesIO(response.content), (display.width, display.height))
            logger.info(f"Image loaded successfully: {image.size} {image.mode}")

            self.renderer.render(
                image,
                resize=data.get("resize", True),
                clear_first=data.get("clear_first", False),
            )
            if self.app_state:
                self.app_state.mark_image_displayed()

        except Exception as e:
            logger.error(f"Failed to display image from MQTT message: {e}")
            if self.app_state:
                self.app_state.mark_image_failed()
            raise
