"""Display module for managing e-ink displays."""

from .base import DisplayBase
from .waveshare import WaveshareDisplay

__all__ = ["DisplayBase", "WaveshareDisplay"]
