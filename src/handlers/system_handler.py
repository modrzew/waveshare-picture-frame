"""System control handler for runtime mode changes."""

import logging
from typing import Any

from src.handlers.base import HandlerBase
from src.state import AppState

logger = logging.getLogger(__name__)


class SystemHandler(HandlerBase):
    """Handler for system control commands.

    This handler processes system-level commands like mode switching,
    shutdown prevention, and other runtime control operations.
    """

    def __init__(self, app_state: AppState):
        """Initialize system handler.

        Args:
            app_state: Shared application state for runtime control
        """
        super().__init__()  # System handler doesn't need display
        self.app_state = app_state

    def can_handle(self, action: str) -> bool:
        """Check if this handler can process the action.

        Args:
            action: Action string from MQTT message

        Returns:
            True if this handler supports the action
        """
        return action in self.supported_actions

    def handle(self, data: dict[str, Any]) -> None:
        """Handle system control commands.

        Supported commands:
        - enter_continuous_mode: Switch from battery mode to continuous mode

        Args:
            data: Message data dictionary (not used for system commands)
        """
        # The action is already determined by can_handle(), but we need to
        # figure out which action was called. Since this handler only supports
        # one action currently, we can just call enter_continuous_mode directly.
        # If we add more actions, we'd need to pass the action to this method.
        self.app_state.enter_continuous_mode()
        logger.info("System command processed: entered continuous mode")

    @property
    def supported_actions(self) -> list[str]:
        """List of supported actions.

        Returns:
            List of action strings this handler supports
        """
        return ["enter_continuous_mode"]
