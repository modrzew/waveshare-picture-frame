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
        """Resize an image to fit the display.

        Args:
            image: Image to resize
            maintain_aspect: Whether to maintain aspect ratio

        Returns:
            Resized image
        """
        if maintain_aspect:
            image.thumbnail((self.width, self.height), Image.Resampling.LANCZOS)
            # Create a new image with display dimensions and paste the resized image
            new_image = Image.new("RGB", (self.width, self.height), (255, 255, 255))
            # Center the image
            x = (self.width - image.width) // 2
            y = (self.height - image.height) // 2
            new_image.paste(image, (x, y))
            return new_image
        else:
            return image.resize((self.width, self.height), Image.Resampling.LANCZOS)
