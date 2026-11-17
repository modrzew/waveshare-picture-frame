"""Pick random images from a local folder (e.g. one synced with rsync)."""

import logging
import os
import random
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"})


class LocalImageFolder:
    """A folder of images, searched recursively."""

    def __init__(self, path: str):
        """Initialize the folder.

        Args:
            path: Folder to search for images (subfolders included)
        """
        self.path = Path(path).expanduser()

    def list_images(self) -> list[Path]:
        """List all image files in the folder and its subfolders.

        Hidden files and folders are skipped, which also skips macOS metadata such as
        .DS_Store and ._* AppleDouble files.

        Returns:
            Image file paths

        Raises:
            FileNotFoundError: If the folder doesn't exist
        """
        if not self.path.is_dir():
            raise FileNotFoundError(f"Image folder not found: {self.path}")

        images = []
        for root, dirs, files in os.walk(self.path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            images.extend(
                Path(root) / name
                for name in files
                if not name.startswith(".") and Path(name).suffix.lower() in IMAGE_EXTENSIONS
            )
        return images

    def random_images(self) -> list[Path]:
        """All images in random order, so callers can move on if one fails to load.

        Returns:
            Shuffled image file paths
        """
        images = self.list_images()
        random.shuffle(images)
        logger.info(f"Found {len(images)} image(s) in {self.path}")
        return images
