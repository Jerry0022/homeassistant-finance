"""Render brand SVGs to HA brand PNGs with resvg (transparent, no browser).

Usage: pip install resvg-py pillow && python docs/brand/render.py
Writes icon/icon@2x/logo/logo@2x (+ dark_ variants) to
custom_components/finance_dashboard/brand/.
"""
import io
import pathlib

import resvg_py
from PIL import Image

here = pathlib.Path(__file__).resolve().parent
out = here.parent.parent / "custom_components/finance_dashboard/brand"


def render(svg, width=None, height=None):
    kw = {"svg_string": (here / svg).read_text(encoding="utf-8")}
    if width:
        kw["width"] = width
    if height:
        kw["height"] = height
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(**kw)))).convert("RGBA")


for pre in ("", "dark_"):
    for suf, px in (("", 256), ("@2x", 512)):
        render(f"{pre}icon.svg", px, px).save(out / f"{pre}icon{suf}.png")
    # Logo: render large, trim to content, scale to short side 128 / 256.
    big = render(f"{pre}logo.svg", height=1024)
    big = big.crop(big.getbbox())
    for suf, h in (("", 128), ("@2x", 256)):
        big.resize((round(big.width * h / big.height), h), Image.LANCZOS).save(
            out / f"{pre}logo{suf}.png"
        )
