"""Panel palettes: the exact pixel colours a panel's driver maps to its inks.

An image that is already the panel's size and uses only these colours is "panel-ready":
it can be sent to the panel as-is. The prepare_image.py CLI writes such images, and the
frame then skips cropping, resizing and dithering. Anything else gets a barebones
conversion (Floyd-Steinberg against these pure colours, as the vendor driver does).
"""

import numpy as np
from PIL import Image

RGB = tuple[int, int, int]

# Spectra 6 (7in3e): pure RGB value -> 4-bit code the panel controller expects.
# Same values and codes as the vendor driver's getbuffer() (code 4 is unused).
SPECTRA6: dict[RGB, int] = {
    (0, 0, 0): 0x0,  # black
    (255, 255, 255): 0x1,  # white
    (255, 255, 0): 0x2,  # yellow
    (255, 0, 0): 0x3,  # red
    (0, 0, 255): 0x5,  # blue
    (0, 255, 0): 0x6,  # green
}

# Display models whose buffers we build ourselves; others use the vendor getbuffer().
PANEL_PALETTES: dict[str, dict[RGB, int]] = {
    "7in3e": SPECTRA6,
}


def uses_only(image: Image.Image, palette: dict[RGB, int]) -> bool:
    """Check whether every pixel of the image is one of the palette's colours."""
    colors = image.convert("RGB").getcolors(maxcolors=len(palette))
    return colors is not None and all(rgb in palette for _, rgb in colors)


def to_codes(image: Image.Image, palette: dict[RGB, int]) -> np.ndarray:
    """Map an image to an (H, W) array of panel codes.

    Uses Floyd-Steinberg dithering against the palette. For an image that already uses
    only palette colours the dithering error is zero, so it maps pixel for pixel.
    """
    colors = list(palette)
    pal_image = Image.new("P", (1, 1))
    pal_image.putpalette([channel for rgb in colors for channel in rgb])
    indexed = image.convert("RGB").quantize(palette=pal_image, dither=Image.Dither.FLOYDSTEINBERG)

    # Unused palette slots may be padded with black, so map them to black's code.
    lut = np.full(256, palette[(0, 0, 0)], dtype=np.uint8)
    lut[: len(colors)] = [palette[rgb] for rgb in colors]
    return lut[np.asarray(indexed)]


def pack_4bit(codes: np.ndarray) -> bytearray:
    """Pack panel codes two pixels per byte (high nibble first), as 7in3e expects."""
    flat = codes.ravel()
    return bytearray(((flat[0::2] << 4) | flat[1::2]).tobytes())
