"""Application state for runtime control."""

import logging
import threading

logger = logging.getLogger(__name__)


class AppState:
    """Shared application state for runtime control.

    This class is thread-safe and can be accessed by multiple handlers
    and the main application to coordinate runtime behavior changes.
    """

    def __init__(self):
        """Initialize application state."""
        self._continuous_mode = False
        self._image_displayed = False
        self._image_failed = False
        self._lock = threading.Lock()

    def enter_continuous_mode(self) -> None:
        """Switch from battery mode to continuous mode.

        In continuous mode, the application will not shut down after
        processing messages and will instead run indefinitely until
        manually stopped.
        """
        with self._lock:
            if not self._continuous_mode:
                logger.info("Entering continuous mode - shutdown canceled")
                self._continuous_mode = True

    def is_continuous_mode(self) -> bool:
        """Check if application is in continuous mode.

        Returns:
            True if in continuous mode, False otherwise
        """
        with self._lock:
            return self._continuous_mode

    def mark_image_displayed(self) -> None:
        """Record that an image was shown on the display."""
        with self._lock:
            self._image_displayed = True

    def mark_image_failed(self) -> None:
        """Record that an image could not be fetched, loaded or shown."""
        with self._lock:
            self._image_failed = True

    @property
    def image_displayed(self) -> bool:
        """Whether an image was shown on the display during this run."""
        with self._lock:
            return self._image_displayed

    @property
    def image_failed(self) -> bool:
        """Whether showing an image failed during this run."""
        with self._lock:
            return self._image_failed
