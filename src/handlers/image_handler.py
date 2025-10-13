"""Handler for displaying images from URLs."""

import base64
import io
import logging
from typing import TYPE_CHECKING, Any

import requests
from PIL import Image

from src.display.base import DisplayBase
from src.utils.image_processing import auto_crop_borders

from .base import HandlerBase

if TYPE_CHECKING:
    from src.config import ImageProcessingConfig, PreviewConfig
    from src.mqtt.client import MQTTClient

logger = logging.getLogger(__name__)


class ImageHandler(HandlerBase):
    """Handler for loading and displaying images from URLs."""

    display: DisplayBase  # Override to make display non-optional

    def __init__(
        self,
        display: DisplayBase,
        timeout: int = 30,
        mqtt_client: "MQTTClient | None" = None,
        preview_config: "PreviewConfig | None" = None,
        image_processing_config: "ImageProcessingConfig | None" = None,
    ):
        """Initialize the image handler.

        Args:
            display: Display instance to use for rendering
            timeout: Request timeout in seconds
            mqtt_client: Optional MQTT client for publishing previews
            preview_config: Optional preview configuration
            image_processing_config: Optional image processing configuration
        """
        super().__init__(display)
        assert self.display is not None, "ImageHandler requires a display instance"
        self.timeout = timeout
        self.mqtt_client = mqtt_client
        self.preview_config = preview_config
        self.image_processing_config = image_processing_config

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
        url = data.get("url")
        if not url:
            raise ValueError("Missing 'url' in message data")

        resize = data.get("resize", True)
        clear_first = data.get("clear_first", False)

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

            # Auto-crop borders if configured
            if self.image_processing_config and self.image_processing_config.auto_crop_borders:
                image = auto_crop_borders(image)

            # Resize if requested
            if resize:
                image = self.display.resize_image(image)

            # Display the image
            self.display.display_image(image)
            logger.info("Image displayed successfully")

            # Publish preview thumbnail if configured
            self._publish_preview(image)

        except requests.RequestException as e:
            logger.error(f"Failed to fetch image from {url}: {e}")
            raise
        except OSError as e:
            logger.error(f"Failed to process image: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error handling image: {e}")
            raise

    def _publish_preview(self, image: Image.Image) -> None:
        """Generate and publish a preview thumbnail to MQTT.

        Args:
            image: The image to create a thumbnail from
        """
        if not self.preview_config or not self.preview_config.enabled:
            return

        if not self.mqtt_client:
            logger.warning("Preview enabled but no MQTT client available")
            return

        try:
            # Calculate thumbnail size maintaining aspect ratio
            original_width, original_height = image.size
            thumbnail_width = self.preview_config.width
            thumbnail_height = int(original_height * (thumbnail_width / original_width))

            # Create thumbnail
            thumbnail = image.copy()
            thumbnail.thumbnail((thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)

            # Convert to JPEG bytes
            buffer = io.BytesIO()
            # Convert to RGB if necessary (e.g., RGBA images)
            if thumbnail.mode in ("RGBA", "LA", "P"):
                thumbnail = thumbnail.convert("RGB")
            thumbnail.save(
                buffer, format="JPEG", quality=self.preview_config.quality, optimize=True
            )
            jpeg_bytes = buffer.getvalue()

            # Base64 encode
            base64_image = base64.b64encode(jpeg_bytes)

            # Publish to MQTT
            self.mqtt_client.publish_binary(
                topic=self.preview_config.topic,
                payload=base64_image,
                qos=1,
                retain=True,
            )
            logger.info(
                f"Published preview thumbnail ({thumbnail.width}x{thumbnail.height}, "
                f"{len(base64_image)} bytes base64)"
            )

        except Exception as e:
            logger.error(f"Failed to publish preview thumbnail: {e}")
