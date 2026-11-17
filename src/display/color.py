"""Colour conversion from photos to e-paper ink patterns.

E-paper inks are far duller than the pure RGB primaries the vendor drivers assume: a
Spectra 6 panel's "white" is a light grey, its "black" a dark purple-grey, and its yellow
ink is about nine times brighter than its red. Dithering against idealised primaries in
gamma-encoded RGB (what the vendor code does) therefore gets tone and colour badly wrong:
midtones come out too light, highlights clip, and skin turns into yellow/blue speckle.

This module converts an image to a per-pixel ink map using the *measured* appearance of
each ink:

1. Colour management: an embedded ICC profile (e.g. Display P3 phone photos) is converted
   to sRGB, transparency is flattened onto white, and values are decoded to linear light.
2. Ink-anchored colour mapping: the sRGB cube is mapped onto the inks by tetrahedral
   interpolation (sRGB red -> red ink, yellow -> yellow ink, white -> white ink, ...), the
   way a printer colour table works. Every result is a mixture of inks, so it can always
   be reproduced, and saturated colours use the full strength of the inks. Within each
   hue sextant the primary/secondary balance is re-mapped so mixed hues (orange, lime,
   sky blue, ...) keep the source's OKLab hue, which plain interpolation would skew toward
   the much brighter yellow ink.
3. Perceptual black point compensation: lightness is compressed from [0, 1] into the
   panel's [black, white] range in OKLab, so shadow detail survives instead of clipping,
   and greys map onto the panel's own black-white axis (no coloured cast in neutrals).
4. Error diffusion in linear light (where ink dots physically average), choosing the
   perceptually nearest ink in OKLab. The loop runs over anti-diagonal wavefronts so each
   step is vectorised with numpy, which keeps it fast enough for a Raspberry Pi Zero.
"""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Linear sRGB -> LMS -> OKLab (https://bottosson.github.io/posts/oklab/)
_RGB_TO_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_LMS_TO_OKLAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
_LUMINANCE = np.array([0.2126, 0.7152, 0.0722])


def _srgb_decode(v: np.ndarray) -> np.ndarray:
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _srgb_encode(v: np.ndarray) -> np.ndarray:
    v = np.clip(v, 0.0, 1.0)
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * v ** (1 / 2.4) - 0.055)


_SRGB_TO_LINEAR = _srgb_decode(np.arange(256) / 255.0).astype(np.float32)


def _to_oklab(rgb: np.ndarray) -> np.ndarray:
    return np.cbrt(rgb @ _RGB_TO_LMS.T) @ _LMS_TO_OKLAB.T


@dataclass(frozen=True)
class Ink:
    """One ink of an e-paper panel.

    Attributes:
        name: Ink name. Every palette needs "black" and "white"; colour palettes also
            need "red", "green", "blue" and "yellow".
        code: Value the panel controller expects for a pixel of this ink
        rgb: Measured appearance in sRGB. Only ratios to the white ink matter, so a
            photo of the panel works at any exposure as long as nothing is clipped.
    """

    name: str
    code: int
    rgb: tuple[int, int, int]


# Waveshare 7.3" Spectra 6 (E6), measured from a linear-developed raw photo of the panel
# (OpenDisplay epaper-dithering, spectra_7_3_6color_v2), scaled so the brightest channel
# of any ink is 255.
SPECTRA6_INKS = (
    Ink("black", 0x0, (0x30, 0x24, 0x3A)),
    Ink("white", 0x1, (0xF1, 0xF1, 0xF1)),
    Ink("yellow", 0x2, (0xFF, 0xE7, 0x00)),
    Ink("red", 0x3, (0x9E, 0x23, 0x1C)),
    Ink("blue", 0x5, (0x3E, 0x60, 0xB9)),
    Ink("green", 0x6, (0x4F, 0x73, 0x52)),
)

# Inks per display model (for previews of panel-ready images on the frame).
PANEL_INKS: dict[str, tuple[Ink, ...]] = {"7in3e": SPECTRA6_INKS}

MONO_INKS = (
    Ink("black", 0x0, (0x00, 0x00, 0x00)),
    Ink("white", 0x1, (0xFF, 0xFF, 0xFF)),
)

_COLOUR_INKS = ("red", "green", "blue", "yellow")

# Error diffusion kernels as (dx, dy, weight) taps; weights are normalised when used.
# fmt: off
DITHER_KERNELS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "floyd_steinberg": ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)),
    "atkinson": ((1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)),
    "burkes": ((1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2)),
    "sierra": (
        (1, 0, 5), (2, 0, 3),
        (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2),
        (-1, 2, 2), (0, 2, 3), (1, 2, 2),
    ),
    "stucki": (
        (1, 0, 8), (2, 0, 4),
        (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
        (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1),
    ),
    "jarvis_judice_ninke": (
        (1, 0, 7), (2, 0, 5),
        (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
        (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1),
    ),
}
# fmt: on
DITHER_METHODS = (*DITHER_KERNELS, "none")
# Lowest S-CIELAB halftone error on the Kodak set + synthetic chart (FS came second).
DEFAULT_DITHER = "burkes"


class PanelPalette:
    """Colour model of a panel's inks, precomputed for fast conversion."""

    _HUE_SAMPLES = 257

    def __init__(self, inks: Sequence[Ink]):
        names = [ink.name for ink in inks]
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate ink names in palette: {names}")
        if "black" not in names or "white" not in names:
            raise ValueError("Palette needs a 'black' and a 'white' ink")
        present = [name in names for name in _COLOUR_INKS]
        if any(present) and not all(present):
            raise ValueError(f"Colour palettes need all of {_COLOUR_INKS} besides black/white")

        self.inks = tuple(inks)
        self.codes = np.array([ink.code for ink in inks], dtype=np.uint8)

        lin = _srgb_decode(np.array([ink.rgb for ink in inks], dtype=np.float64) / 255.0)
        white = lin[names.index("white")]
        if np.any(white <= 0):
            raise ValueError("White ink must be brighter than zero in every channel")
        # Relative to the panel white: the viewer adapts to it, so it *is* white.
        self.linear = lin / white
        self._ink = {name: self.linear[i] for i, name in enumerate(names)}

        # The panel's achromatic axis: mixtures of black and white ink. Lightness along it
        # drives black point compensation; its tint defines "neutral" for the panel.
        black = self._ink["black"]
        mix = np.linspace(0.0, 1.0, 1025)
        axis = _to_oklab(black + mix[:, None] * (1.0 - black))
        if np.any(np.diff(axis[:, 0]) <= 0):
            raise ValueError("Black ink must be darker than white ink in every channel")
        self._axis_mix, self._axis_L, self._axis_a, self._axis_b = mix, *axis.T
        self.black_L = float(axis[0, 0])

        self.is_colour = all(present)
        if self.is_colour:
            self._build_colour_map()

    @classmethod
    def from_overrides(
        cls, defaults: Sequence[Ink], overrides: Mapping[str, str] | None = None
    ) -> "PanelPalette":
        """Build a palette from defaults, replacing ink colours given as '#rrggbb'."""
        overrides = dict(overrides or {})
        unknown = set(overrides) - {ink.name for ink in defaults}
        if unknown:
            raise ValueError(f"Unknown inks in palette override: {sorted(unknown)}")
        inks = [
            Ink(ink.name, ink.code, _parse_hex(overrides[ink.name]))
            if ink.name in overrides
            else ink
            for ink in defaults
        ]
        return cls(inks)

    # --- colour mapping -------------------------------------------------------------

    def _panel_hue(self, rgb: np.ndarray) -> np.ndarray:
        """OKLab hue of panel colours, measured from the panel's own grey axis."""
        lab = _to_oklab(rgb)
        a = lab[..., 1] - np.interp(lab[..., 0], self._axis_L, self._axis_a)
        b = lab[..., 2] - np.interp(lab[..., 0], self._axis_L, self._axis_b)
        return np.arctan2(b, a)

    def _mix_with_hue(self, a: np.ndarray, b: np.ndarray, hue: float) -> np.ndarray:
        """The mixture of inks a and b whose hue is closest to the given hue."""
        s = np.linspace(0.0, 1.0, 1001)[:, None]
        hues = np.unwrap(self._panel_hue((1 - s) * a + s * b))
        target = hue + 2 * np.pi * np.round((hues[0] - hue) / (2 * np.pi))
        best = s[np.argmin(np.abs(hues - target)), 0]
        return (1 - best) * a + best * b

    def _build_colour_map(self) -> None:
        """Precompute the ink-anchored mapping of the sRGB cube onto the inks.

        The cube is split into six tetrahedra around its grey diagonal, each spanned by
        black, white, one primary (indexed by the largest channel) and one secondary
        (indexed by the smallest channel). Corners map to inks; cyan and magenta, which
        have no ink, map to the green/blue and red/blue mixtures with the same hue.
        """
        ink = self._ink
        eye = np.eye(3)

        def source_hue(rgb: np.ndarray) -> np.ndarray:
            lab = _to_oklab(rgb)
            return np.arctan2(lab[..., 2], lab[..., 1])

        cyan = self._mix_with_hue(ink["green"], ink["blue"], float(source_hue(1 - eye[0])))
        magenta = self._mix_with_hue(ink["red"], ink["blue"], float(source_hue(1 - eye[1])))
        self._primaries = np.stack([ink["red"], ink["green"], ink["blue"]])
        self._secondaries = np.stack([cyan, magenta, ink["yellow"]])  # by smallest channel

        # Per sextant, re-map the position u between primary and secondary so the mixed
        # ink hue follows the source hue (aligned at the corners, linear in between).
        u = np.linspace(0.0, 1.0, self._HUE_SAMPLES)
        tables = np.zeros((3, 3, u.size))
        for hi in range(3):
            for lo in range(3):
                if hi == lo:
                    continue
                src = eye[hi] + u[:, None] * ((1 - eye[lo]) - eye[hi])
                src_hue = np.unwrap(source_hue(src))
                frac = (src_hue - src_hue[0]) / (src_hue[-1] - src_hue[0])
                prim, sec = self._primaries[hi], self._secondaries[lo]
                panel_hue = np.unwrap(self._panel_hue(prim + u[:, None] * (sec - prim)))
                if panel_hue[-1] < panel_hue[0]:
                    panel_hue = -panel_hue
                panel_hue = np.maximum.accumulate(panel_hue)
                wanted = panel_hue[0] + frac * (panel_hue[-1] - panel_hue[0])
                table = np.interp(wanted, panel_hue, u)
                table[0], table[-1] = 0.0, 1.0
                tables[hi, lo] = table
        self._hue_tables = tables.astype(np.float32).ravel()  # indexed by (hi, lo, sample)

    def _tone(self, v: np.ndarray) -> np.ndarray:
        """Black/white ink mix fraction reproducing a source grey's relative lightness."""
        lightness = self.black_L + (1.0 - self.black_L) * np.cbrt(np.clip(v, 0.0, 1.0))
        return np.interp(lightness, self._axis_L, self._axis_mix).astype(v.dtype)

    def map_colors(self, rgb: np.ndarray) -> np.ndarray:
        """Map linear sRGB colours (N, 3) to reproducible linear panel colours (N, 3)."""
        rgb = np.clip(rgb, 0.0, 1.0)
        black = self._ink["black"].astype(rgb.dtype)
        white = np.ones(3, dtype=rgb.dtype)

        if not self.is_colour:
            mix = self._tone(rgb @ _LUMINANCE.astype(rgb.dtype))[:, None]
            return black + mix * (white - black)

        hi_ch = np.argmax(rgb, axis=1)
        lo_ch = np.argmin(rgb, axis=1)
        lo_ch = np.where(hi_ch == lo_ch, (hi_ch + 1) % 3, lo_ch)  # greys: any sextant
        hi = np.take_along_axis(rgb, hi_ch[:, None], axis=1)[:, 0]
        lo = np.take_along_axis(rgb, lo_ch[:, None], axis=1)[:, 0]
        mid = rgb.sum(axis=1) - hi - lo

        # Hue position within the sextant, re-mapped to keep the source hue.
        spread = hi - lo
        u = np.where(spread > 1e-7, (mid - lo) / np.maximum(spread, 1e-7), 0.0)
        pos = u * (self._HUE_SAMPLES - 1)
        i = np.minimum(pos.astype(np.intp), self._HUE_SAMPLES - 2)
        frac = pos - i
        i += (hi_ch * 3 + lo_ch) * self._HUE_SAMPLES
        u = self._hue_tables[i] * (1 - frac) + self._hue_tables[i + 1] * frac
        mid = lo + u * spread

        # Black point compensation scales the colour toward black, keeping its hue and
        # saturation; for greys this is exactly the perceptual lightness mapping.
        scale = np.where(hi > 1e-7, self._tone(hi) / np.maximum(hi, 1e-7), 0.0)
        hi, mid, lo = hi * scale, mid * scale, lo * scale

        primaries = self._primaries.astype(rgb.dtype)
        secondaries = self._secondaries.astype(rgb.dtype)
        return (
            (1 - hi)[:, None] * black
            + (hi - mid)[:, None] * primaries[hi_ch]
            + (mid - lo)[:, None] * secondaries[lo_ch]
            + lo[:, None] * white
        )

    # --- conversion -----------------------------------------------------------------

    def convert(self, image: Image.Image, dither: str = DEFAULT_DITHER) -> np.ndarray:
        """Convert an image to an (H, W) array of ink indices (positions in ``inks``)."""
        if dither not in DITHER_METHODS:
            raise ValueError(f"Unknown dither method {dither!r}, expected one of {DITHER_METHODS}")
        started = time.monotonic()
        rgb = np.asarray(to_srgb(image))
        h, w, _ = rgb.shape
        target = self.map_colors(_SRGB_TO_LINEAR[rgb.reshape(-1, 3)]).reshape(h, w, 3)
        mapped = time.monotonic()
        if dither == "none":
            indices = self._nearest(target.reshape(-1, 3)).reshape(h, w)
        else:
            indices = self._diffuse(target, DITHER_KERNELS[dither])
        logger.debug(
            "Colour conversion %dx%d: mapping %.2fs, %s dithering %.2fs",
            w,
            h,
            mapped - started,
            dither,
            time.monotonic() - mapped,
        )
        return indices

    def render(self, indices: np.ndarray) -> Image.Image:
        """Simulate how the panel will look (relative to its white) from ink indices."""
        srgb = _srgb_encode(self.linear[indices])
        return Image.fromarray(np.round(srgb * 255).astype(np.uint8), "RGB")

    def _match_terms(self) -> tuple[np.ndarray, np.ndarray]:
        """Terms to find the nearest ink in OKLab from cube-root LMS with one matmul.

        With x = cbrt(LMS), |M (x - p)|^2 = x'M'Mx - 2 x'M'M p + p'M'M p; the first term
        is the same for every ink, so the rest decides which ink is nearest.
        """
        q = _LMS_TO_OKLAB.T @ _LMS_TO_OKLAB
        inks = np.cbrt(self.linear @ _RGB_TO_LMS.T)
        weights = (-2.0 * inks @ q).T.astype(np.float32)
        bias = np.einsum("ij,jk,ik->i", inks, q, inks).astype(np.float32)
        return weights, bias

    def _nearest(self, rgb: np.ndarray) -> np.ndarray:
        weights, bias = self._match_terms()
        lms = np.cbrt(np.maximum(rgb, 0.0) @ _RGB_TO_LMS.T.astype(np.float32))
        return np.argmin(lms @ weights + bias, axis=1).astype(np.uint8)

    def _diffuse(self, target: np.ndarray, kernel: tuple[tuple[int, int, int], ...]) -> np.ndarray:
        """Error diffusion in linear light, processed in anti-diagonal wavefronts.

        Pixel (x, y) only receives error from pixels with a smaller x + skew * y, so all
        pixels on one wavefront are independent and are processed in one vectorised step.
        """
        h, w, _ = target.shape
        total = sum(weight for _, _, weight in kernel)
        pad = max(abs(dx) for dx, _, _ in kernel)
        below = max(dy for _, dy, _ in kernel)
        skew = max([1] + [-dx // dy + 1 for dx, dy, _ in kernel if dy > 0])
        width = w + 2 * pad

        buf = np.zeros((h + below, width, 3), dtype=np.float32)
        buf[:h, pad : pad + w] = target
        flat = buf.reshape(-1, 3)

        # Taps grouped per row: within one wavefront, taps of the same row never collide.
        rows = []
        for dy in sorted({dy for _, dy, _ in kernel}):
            taps = [(dx, weight) for dx, tap_dy, weight in kernel if tap_dy == dy]
            offsets = np.array([[dy * width + dx for dx, _ in taps]])
            weights = np.array([weight / total for _, weight in taps], dtype=np.float32)
            rows.append((offsets, weights[None, :, None]))

        ys, xs = np.divmod(np.arange(h * w), w)
        front = xs + skew * ys
        order = np.argsort(front, kind="stable")
        positions = (ys * width + xs + pad)[order]
        bounds = np.searchsorted(front[order], np.arange(front.max() + 2))

        match_weights, match_bias = self._match_terms()
        to_lms = _RGB_TO_LMS.T.astype(np.float32)
        inks = self.linear.astype(np.float32)
        # Keep accumulated values within what the inks span so errors cannot run away.
        lo, hi = inks.min(axis=0), inks.max(axis=0)
        out = np.empty(h * w, dtype=np.uint8)

        for start, stop in zip(bounds[:-1], bounds[1:], strict=True):
            pos = positions[start:stop]
            value = np.clip(flat[pos], lo, hi)
            chosen = np.argmin(np.cbrt(value @ to_lms) @ match_weights + match_bias, axis=1)
            out[order[start:stop]] = chosen
            error = value - inks[chosen]
            for offsets, weights in rows:
                flat[pos[:, None] + offsets] += error[:, None, :] * weights
        return out.reshape(h, w)


def appearance(inks: Sequence[Ink]) -> dict[int, tuple[int, int, int]]:
    """How each ink looks relative to the panel white, as 8-bit sRGB, keyed by panel code.

    Same simulation as PanelPalette.render(), without building the full colour map.
    """
    lin = _srgb_decode(np.array([ink.rgb for ink in inks], dtype=np.float64) / 255.0)
    white = lin[[ink.name for ink in inks].index("white")]
    srgb = np.round(_srgb_encode(lin / white) * 255).astype(int)
    return {ink.code: (int(r), int(g), int(b)) for ink, (r, g, b) in zip(inks, srgb, strict=True)}


def to_srgb(image: Image.Image) -> Image.Image:
    """Return the image as 8-bit sRGB: ICC profile applied, transparency flattened on white."""
    from PIL import ImageCms  # Only needed on the desktop; keep it off the Pi's import path

    icc = image.info.get("icc_profile")
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        image = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image.alpha_composite(rgba)
        image = image.convert("RGB")
    elif image.mode not in ("RGB", "CMYK") or (image.mode == "CMYK" and not icc):
        image = image.convert("RGB")

    if icc:
        try:
            converted = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(BytesIO(icc)),
                ImageCms.createProfile("sRGB"),
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                outputMode="RGB",
            )
            if converted is not None:
                image = converted
        except (OSError, ImageCms.PyCMSError) as e:
            logger.warning(f"Ignoring unusable ICC profile: {e}")
    return image if image.mode == "RGB" else image.convert("RGB")


def _parse_hex(value: str) -> tuple[int, int, int]:
    text = value.strip().removeprefix("#")
    if len(text) != 6:
        raise ValueError(f"Expected a colour like '#a1b2c3', got {value!r}")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        raise ValueError(f"Expected a colour like '#a1b2c3', got {value!r}") from None
