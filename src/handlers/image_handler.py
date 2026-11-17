"""Handler for displaying images from URLs or the local image folder."""

import io
import logging
from typing import Any

import requests

from src.display.renderer import ImageRenderer
from src.local_images import LocalImageFolder
from src.state import AppState
from src.utils.image_processing import open_image

from .base import HandlerBase

logger = logging.getLogger(__name__)

# Some image hosts (e.g. Wikimedia, Art Institute of Chicago) reject the default
# python-requests User-Agent with a 403.
USER_AGENT = "waveshare-picture-frame/1.0"

# How many local images to try before giving up (skips unreadable files)
MAX_LOCAL_IMAGE_ATTEMPTS = 5


class ImageHandler(HandlerBase):
    """Handler for displaying an image from a URL or a random one from the local folder.

    ``show_random_image()`` is also the startup fallback when no MQTT image arrives, so
    ``display_image`` with ``random: true`` behaves exactly like it.
    """

    def __init__(
        self,
        renderer: ImageRenderer,
        app_state: AppState | None = None,
        local_folder: str | None = None,
        timeout: int = 30,
    ):
        """Initialize the image handler.

        Args:
            renderer: Renderer that shows images on the display
            app_state: Optional shared state to record whether an image was shown
            local_folder: Local image folder (searched recursively); None if not configured
            timeout: Request timeout in seconds
        """
        super().__init__(renderer.display)
        self.renderer = renderer
        self.app_state = app_state
        self.local_folder = local_folder
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
            data: Message data containing either of:
                - url: Image URL to load
                - random: true to show a random image from the local folder
                and optionally:
                - resize: Whether to resize the image (default: True)
                - clear_first: Whether to clear display first (default: False)
        """
        try:
            random_image = data.get("random", False) is True
            url = data.get("url")
            if random_image and url:
                raise ValueError("Use either 'url' or 'random: true', not both")
            if not random_image and not url:
                raise ValueError("Missing 'url' (or 'random: true') in message data")
            resize = data.get("resize", True)
            clear_first = data.get("clear_first", False)
        except Exception as e:
            logger.error(f"Invalid display_image message: {e}")
            self._mark_failed()
            raise

        if random_image:
            self.show_random_image(resize=resize, clear_first=clear_first)
        else:
            self._display_url(str(url), resize=resize, clear_first=clear_first)

    def _display_url(self, url: str, resize: bool, clear_first: bool) -> None:
        """Fetch an image from a URL and show it."""
        try:
            logger.info(f"Fetching image from: {url}")
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()

            display = self.renderer.display
            image = open_image(io.BytesIO(response.content), (display.width, display.height))
            logger.info(f"Image loaded successfully: {image.size} {image.mode}")

            self.renderer.render(image, resize=resize, clear_first=clear_first)
            self._mark_displayed()

        except Exception as e:
            logger.error(f"Failed to display image from MQTT message: {e}")
            self._mark_failed()
            raise

    def show_random_image(self, resize: bool = True, clear_first: bool = False) -> None:
        """Show a random image from the local folder, if one is configured.

        Args:
            resize: Whether to crop/resize images that don't match the panel size
            clear_first: Whether to clear the display before showing the image
        """
        if not self.local_folder:
            logger.info("No local image folder configured - keeping the current image")
            return

        try:
            candidates = LocalImageFolder(self.local_folder).random_images()
        except OSError as e:
            logger.error(f"Cannot read local image folder: {e}")
            self._mark_failed()
            return

        if not candidates:
            logger.error(f"No images found in local image folder {self.local_folder}")
            self._mark_failed()
            return

        display = self.renderer.display
        for path in candidates[:MAX_LOCAL_IMAGE_ATTEMPTS]:
            try:
                image = open_image(str(path), (display.width, display.height))
            except Exception as e:
                logger.warning(f"Skipping unreadable image {path}: {e}")
                continue

            logger.info(f"Showing local image: {path}")
            try:
                self.renderer.render(image, resize=resize, clear_first=clear_first)
                self._mark_displayed()
            except Exception as e:
                logger.error(f"Failed to display local image {path}: {e}")
                self._mark_failed()
            return

        logger.error(f"Could not load any of {MAX_LOCAL_IMAGE_ATTEMPTS} local images")
        self._mark_failed()

    def _mark_displayed(self) -> None:
        if self.app_state:
            self.app_state.mark_image_displayed()

    def _mark_failed(self) -> None:
        if self.app_state:
            self.app_state.mark_image_failed()
