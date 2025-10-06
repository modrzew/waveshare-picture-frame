"""Base class for display implementations."""

from abc import ABC, abstractmethod

from PIL import Image


class DisplayBase(ABC):
    """Abstract base class for display implementations."""

    def __init__(self, width: int, height: int):
        """Initialize the display base.

        Args:
            width: Display width in pixels
            height: Display height in pixels
        """
        self.width = width
        self.height = height
        self.is_initialized = False

    @abstractmethod
    def init(self) -> None:
        """Initialize the display hardware."""
        pass

    @abstractmethod
    def display_image(self, image: Image.Image) -> None:
        """Display an image on the device.

        Args:
            image: PIL Image object to display
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear the display."""
        pass

    @abstractmethod
    def sleep(self) -> None:
        """Put the display into low power mode."""
        pass

    def resize_image(self, image: Image.Image, maintain_aspect: bool = True) -> Image.Image:
        """Resize an image to cover the display.

        Args:
            image: Image to resize
            maintain_aspect: Whether to maintain aspect ratio (covers screen, crops if needed)

        Returns:
            Resized image that covers the entire display
        """
        if maintain_aspect:
            # Calculate scale factors to cover the display (not fit inside it)
            scale_width = self.width / image.width
            scale_height = self.height / image.height

            # Use the larger scale factor so the image covers the entire display
            scale = max(scale_width, scale_height)

            # Resize image to cover display
            new_width = int(image.width * scale)
            new_height = int(image.height * scale)
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Crop to display size (center the image)
            left = (new_width - self.width) // 2
            top = (new_height - self.height) // 2
            right = left + self.width
            bottom = top + self.height

            return resized.crop((left, top, right, bottom))
        else:
            return image.resize((self.width, self.height), Image.Resampling.LANCZOS)
