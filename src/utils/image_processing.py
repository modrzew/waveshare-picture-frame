"""Image processing utilities for border detection and cropping."""

import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Border detection constants
UNIFORMITY_THRESHOLD = 25.0  # Max std deviation for uniform borders (higher = more permissive)
MIN_BORDER_SIZE = 5  # Minimum border size in pixels to warrant cropping


def auto_crop_borders(image: Image.Image) -> Image.Image:
    """Automatically detect and crop uniform/solid color borders from an image.

    This function scans from each edge (top, bottom, left, right) inward to detect
    rows/columns that are uniform (low variance/contrast). It detects borders of ANY
    solid color (white, beige, tan, gray, yellow, etc.) by looking for low pixel
    variance rather than specific color values.

    Args:
        image: PIL Image to process

    Returns:
        Cropped PIL Image if borders were detected, otherwise the original image.
    """
    # Convert image to RGB if needed (handles RGBA, L, etc.)
    if image.mode not in ("RGB", "L"):
        original_mode = image.mode
        image_rgb = image.convert("RGB")
        logger.debug(f"Converted image from {original_mode} to RGB for border detection")
    else:
        image_rgb = image

    # Convert to numpy array for efficient processing
    img_array = np.array(image_rgb)
    height, width = img_array.shape[:2]

    logger.debug(
        f"Analyzing image ({width}x{height}) for uniform borders "
        f"(uniformity_threshold={UNIFORMITY_THRESHOLD}, min_border_size={MIN_BORDER_SIZE})"
    )

    # Determine if a row/column is "uniform" (solid color) based on variance
    def is_border_line(line: np.ndarray) -> bool:
        """Check if a line (row or column) is uniform (low variance/contrast).

        This detects borders of ANY solid color by measuring pixel variance.
        Low variance = uniform/solid color = likely a border.

        Args:
            line: numpy array representing a row or column

        Returns:
            True if the line has low enough variance to be considered uniform
        """
        if len(line.shape) == 3:  # RGB image
            # Calculate standard deviation across all RGB channels
            # Flatten to (pixels * channels) and compute std
            std_dev = np.std(line)
        else:  # Grayscale
            std_dev = np.std(line)

        return bool(std_dev <= UNIFORMITY_THRESHOLD)

    # Find borders from each edge
    top_border = 0
    bottom_border = height
    left_border = 0
    right_border = width

    # Scan from top
    for i in range(height):
        if not is_border_line(img_array[i, :]):
            top_border = i
            break

    # Scan from bottom
    for i in range(height - 1, -1, -1):
        if not is_border_line(img_array[i, :]):
            bottom_border = i + 1
            break

    # Scan from left
    for i in range(width):
        if not is_border_line(img_array[:, i]):
            left_border = i
            break

    # Scan from right
    for i in range(width - 1, -1, -1):
        if not is_border_line(img_array[:, i]):
            right_border = i + 1
            break

    # Calculate detected border sizes
    border_sizes = {
        "top": top_border,
        "bottom": height - bottom_border,
        "left": left_border,
        "right": width - right_border,
    }

    # Check if any border meets minimum size threshold
    significant_borders = {k: v for k, v in border_sizes.items() if v >= MIN_BORDER_SIZE}

    if not significant_borders:
        logger.debug(f"No significant borders detected (all < {MIN_BORDER_SIZE}px): {border_sizes}")
        return image

    # Validate crop box
    if left_border >= right_border or top_border >= bottom_border:
        logger.warning(
            f"Invalid crop box detected: left={left_border}, right={right_border}, "
            f"top={top_border}, bottom={bottom_border}. Returning original image."
        )
        return image

    # Calculate crop dimensions
    new_width = right_border - left_border
    new_height = bottom_border - top_border
    cropped_percentage = (1 - (new_width * new_height) / (width * height)) * 100

    logger.info(
        f"Cropping borders: {significant_borders} | "
        f"Original: {width}x{height} → Cropped: {new_width}x{new_height} "
        f"({cropped_percentage:.1f}% removed)"
    )

    # Crop the original image (not the converted RGB version)
    cropped = image.crop((left_border, top_border, right_border, bottom_border))

    return cropped
