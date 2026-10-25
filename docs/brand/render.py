"""Render brand SVGs to HA brand PNGs via headless Edge/Chrome (transparent).

Usage: python docs/brand/render.py
Writes icon/icon@2x/logo/logo@2x (+ dark_ variants) to
custom_components/finance_dashboard/brand/. Needs Pillow.
"""
import os
import pathlib
import subprocess
import tempfile

from PIL import Image

here = pathlib.Path(__file__).resolve().parent
out = here.parent.parent / "custom_components/finance_dashboard/brand"
browser = next(
    p
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    if os.path.exists(p)
)


def shot(svg, w, h, dest):
    html = (
        '<html><body style="margin:0;background:transparent">'
        f'<img src="{(here / svg).as_uri()}" width="{w}" height="{h}" style="display:block">'
        "</body></html>"
    )
    with tempfile.TemporaryDirectory() as t:
        f = pathlib.Path(t) / "p.html"
        f.write_text(html)
        subprocess.run(
            [
                browser, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--default-background-color=00000000",
                f"--window-size={w},{h}", f"--screenshot={dest}",
                f.as_uri(), f"--user-data-dir={t}/u",
            ],
            check=True,
            capture_output=True,
        )


for pre in ("", "dark_"):
    for suf, px in (("", 256), ("@2x", 512)):
        shot(f"{pre}icon.svg", px, px, out / f"{pre}icon{suf}.png")
    # Logo: render large, trim to content, scale to short side 128 / 256.
    big = here / f"_{pre}big.png"
    shot(f"{pre}logo.svg", 2800, 1024, big)
    im = Image.open(big).convert("RGBA")
    im = im.crop(im.getbbox())
    big.unlink()
    for suf, h in (("", 128), ("@2x", 256)):
        im.resize((round(im.width * h / im.height), h), Image.LANCZOS).save(
            out / f"{pre}logo{suf}.png"
        )
