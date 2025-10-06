"""Base class for message handlers."""

from abc import ABC, abstractmethod
from typing import Any

from src.display.base import DisplayBase


class HandlerBase(ABC):
    """Abstract base class for message handlers."""

    def __init__(self, display: DisplayBase | None = None):
        """Initialize the handler.

        Args:
            display: Display instance to use for rendering (optional for system handlers)
        """
        self.display = display

    @abstractmethod
    def can_handle(self, action: str) -> bool:
        """Check if this handler can process the given action.

        Args:
            action: Action type from the message

        Returns:
            True if this handler can process the action
        """
        pass

    @abstractmethod
    def handle(self, data: dict[str, Any]) -> None:
        """Process the message data.

        Args:
            data: Message data to process
        """
        pass

    @property
    @abstractmethod
    def supported_actions(self) -> list[str]:
        """List of supported action types.

        Returns:
            List of action strings this handler supports
        """
        pass
