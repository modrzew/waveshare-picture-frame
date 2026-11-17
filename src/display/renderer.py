"""Show images on the display, doing only as much work as each image needs."""

import base64
import io
import logging
import threading
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from src.utils.image_processing import auto_crop_borders

from .base import DisplayBase
from .color import PANEL_INKS, appearance
from .palette import to_codes

if TYPE_CHECKING:
    from src.config import ImageProcessingConfig, PreviewConfig
    from src.mqtt.client import MQTTClient

logger = logging.getLogger(__name__)


class ImageRenderer:
    """Renders images from any source (MQTT URL, local folder) and publishes previews.

    Panel-ready images (exact panel size, panel colours only) are shown as-is. Anything
    else gets the barebones treatment: border auto-crop, centre cover-crop and resize, then
    the display's own dithering.
    """

    def __init__(
        self,
        display: DisplayBase,
        mqtt_client: "MQTTClient | None" = None,
        preview_config: "PreviewConfig | None" = None,
        image_processing_config: "ImageProcessingConfig | None" = None,
    ):
        """Initialize the renderer.

        Args:
            display: Display to render on
            mqtt_client: Optional MQTT client for publishing previews
            preview_config: Optional preview configuration
            image_processing_config: Optional image processing configuration
        """
        self.display = display
        self.mqtt_client = mqtt_client
        self.preview_config = preview_config
        self.image_processing_config = image_processing_config
        # MQTT handlers run on the MQTT thread; never drive the panel from two threads.
        self._lock = threading.Lock()

    def render(self, image: Image.Image, resize: bool = True, clear_first: bool = False) -> None:
        """Show an image on the display and publish its preview.

        Args:
            image: Image to show
            resize: Whether to crop/resize images that don't match the panel size
            clear_first: Whether to clear the display before showing the image
        """
        with self._lock:
            if clear_first:
                logger.debug("Clearing display before showing new image")
                self.display.clear()

            panel_ready = self.display.is_panel_ready(image)
            if panel_ready:
                logger.info("Image is panel-ready, displaying as-is")
            else:
                logger.info(f"Image is not panel-ready ({image.size} {image.mode}), converting")
                if self.image_processing_config and self.image_processing_config.auto_crop_borders:
                    image = auto_crop_borders(image)
                if resize:
                    image = self.display.resize_image(image)

            self.display.display_image(image)
            logger.info("Image displayed successfully")

        self._publish_preview(self._simulate(image) if panel_ready else image)

    def _simulate(self, image: Image.Image) -> Image.Image:
        """How a panel-ready image looks on the panel (its pure driver colours look garish)."""
        inks = PANEL_INKS.get(self.display.model)
        if inks is None or self.display.palette is None:
            return image
        lut = np.zeros((256, 3), dtype=np.uint8)
        for code, rgb in appearance(inks).items():
            lut[code] = rgb
        return Image.fromarray(lut[to_codes(image, self.display.palette)], "RGB")

    def _publish_preview(self, image: Image.Image) -> None:
        """Generate and publish a preview thumbnail to MQTT.

        Args:
            image: The image to create a thumbnail from
        """
        if not self.preview_config or not self.preview_config.enabled:
            return

        if not self.mqtt_client or not self.mqtt_client.connected.is_set():
            logger.info("Preview enabled but MQTT is not connected, skipping preview")
            return

        try:
            # Calculate thumbnail size maintaining aspect ratio
            original_width, original_height = image.size
            thumbnail_width = self.preview_config.width
            thumbnail_height = int(original_height * (thumbnail_width / original_width))

            # Create thumbnail (RGB first, so palette images are averaged, not sampled)
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail((thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)

            # Convert to JPEG bytes
            buffer = io.BytesIO()
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
