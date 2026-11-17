#!/usr/bin/env python3
"""Prepare an image for the frame: crop, resize to the panel and convert to its inks.

Runs on a desktop (not the Pi). The output is a panel-ready PNG: exactly the panel size,
using only the colours the panel driver understands, so the frame shows it as-is.

Examples:
    uv run python prepare_image.py painting.jpg out/painting.png
    uv run python prepare_image.py painting.jpg out/ --crop 120,340,2400,1440
    uv run python prepare_image.py painting.jpg out/ --crop 0%,10%,100%,60% --preview p.png
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

from src.display.color import DEFAULT_DITHER, DITHER_METHODS, SPECTRA6_INKS, PanelPalette
from src.display.palette import SPECTRA6

Box = tuple[int, int, int, int]  # x, y, width, height


def parse_crop(value: str, image_size: tuple[int, int]) -> Box:
    """Parse "X,Y,W,H" in pixels, or with a % suffix as a percentage of the image size."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError(f"--crop needs 4 values X,Y,W,H, got {value!r}")
    totals = (image_size[0], image_size[1], image_size[0], image_size[1])
    numbers = []
    for part, total in zip(parts, totals, strict=True):
        if part.endswith("%"):
            numbers.append(round(float(part[:-1]) / 100 * total))
        else:
            numbers.append(round(float(part)))
    x, y, w, h = numbers
    if w <= 0 or h <= 0:
        raise ValueError(f"--crop width and height must be positive, got {value!r}")
    return x, y, w, h


def fit_aspect(box: Box, image_size: tuple[int, int], aspect: float) -> tuple[Box, bool]:
    """Adjust a crop box to the target aspect ratio, staying inside the image.

    The shorter side grows around the box centre, so everything requested stays in frame.
    Only when the image is too small for that does the longer side shrink instead.

    Returns:
        The adjusted box, and whether part of the requested box had to be cut off.
    """
    img_w, img_h = image_size
    # Clamp the requested box to the image first
    x0, y0 = max(0, box[0]), max(0, box[1])
    x1, y1 = min(img_w, box[0] + box[2]), min(img_h, box[1] + box[3])
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Crop box {box} is outside the {img_w}x{img_h} image")
    clamped = (x1 - x0, y1 - y0) != (box[2], box[3])

    w, h = float(x1 - x0), float(y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cut = clamped
    if w / h < aspect:  # Too narrow: widen
        w = h * aspect
        if w > img_w:
            w, h, cut = img_w, img_w / aspect, True
    else:  # Too wide: heighten
        h = w / aspect
        if h > img_h:
            w, h, cut = img_h * aspect, img_h, True

    # Centre on the requested box, then shift back inside the image
    left = min(max(0.0, cx - w / 2), img_w - w)
    top = min(max(0.0, cy - h / 2), img_h - h)
    return (round(left), round(top), round(w), round(h)), cut


def output_path(source: Path, destination: str) -> Path:
    """Resolve the output file: a directory (existing, or ending in /) gets <stem>.png."""
    path = Path(destination)  # Path() drops a trailing slash, so check the raw string
    if path.is_dir() or destination.endswith(("/", "\\")):
        return path / f"{source.stem}.png"
    if path.suffix.lower() != ".png":
        raise ValueError(f"Output must be a .png file (lossless), got {destination}")
    return path


def main() -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Crop an image to the frame's aspect ratio, resize it to the panel and convert it "
            "to the Spectra 6 inks. Writes a panel-ready PNG that the frame displays as-is, "
            "and prints a JSON summary."
        )
    )
    parser.add_argument("source", type=Path, help="Source image")
    parser.add_argument(
        "destination", help="Output .png file, or a directory for <source stem>.png"
    )
    parser.add_argument(
        "--crop",
        help=(
            "Crop box X,Y,W,H in pixels of the upright source image (x,y = top-left corner). "
            "Each value may also be a percentage, e.g. 0%%,10%%,100%%,60%%. The box is grown "
            "to the panel's aspect ratio around its centre. Default: largest centred box."
        ),
    )
    parser.add_argument(
        "--size", default="800x480", help="Panel size WIDTHxHEIGHT (default: 800x480)"
    )
    parser.add_argument(
        "--dither",
        default=DEFAULT_DITHER,
        choices=DITHER_METHODS,
        help=f"Error diffusion kernel (default: {DEFAULT_DITHER})",
    )
    parser.add_argument(
        "--preview", type=Path, help="Also write a simulation of how the panel will look"
    )
    parser.add_argument(
        "--ink",
        action="append",
        default=[],
        metavar="NAME=#RRGGBB",
        help="Override a measured ink colour (black, white, yellow, red, blue, green)",
    )
    args = parser.parse_args()

    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
        overrides = dict(item.split("=", 1) for item in args.ink)
        palette = PanelPalette.from_overrides(SPECTRA6_INKS, overrides)
        destination = output_path(args.source, args.destination)

        image = ImageOps.exif_transpose(Image.open(args.source))
        source_size = image.size
        if args.crop:
            requested = parse_crop(args.crop, image.size)
        else:
            requested = (0, 0, image.width, image.height)
        box, cut = fit_aspect(requested, image.size, width / height)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if cut and args.crop:
        print(
            f"warning: crop {requested} cut to {box} to fit the image at the panel's aspect ratio",
            file=sys.stderr,
        )
    upscaled = box[2] < width or box[3] < height
    if upscaled:
        print(f"warning: crop {box[2]}x{box[3]} is upscaled to {width}x{height}", file=sys.stderr)

    x, y, w, h = box
    image = image.crop((x, y, x + w, y + h)).resize((width, height), Image.Resampling.LANCZOS)
    indices = palette.convert(image, dither=args.dither)

    # Write the panel's pure driver colours, so the frame recognises the image as ready
    code_to_rgb = {code: rgb for rgb, code in SPECTRA6.items()}
    out = Image.frombytes("P", (width, height), indices.astype("uint8").tobytes())
    out.putpalette([c for ink in palette.inks for c in code_to_rgb[ink.code]])
    destination.parent.mkdir(parents=True, exist_ok=True)
    out.save(destination, optimize=True)

    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        palette.render(indices).save(args.preview)

    summary = {
        "source": str(args.source),
        "source_size": list(source_size),
        "crop": list(box),
        "cut": cut,
        "upscaled": upscaled,
        "output": str(destination),
        "preview": str(args.preview) if args.preview else None,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
