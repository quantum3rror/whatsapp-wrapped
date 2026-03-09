#!/usr/bin/env python3
"""
Generate app icon assets from the WhatsApp Wrapped SVG logo.
Uses Playwright (already a project dependency) — no system libraries needed.

Outputs (all in this icons/ folder):
  icon.icns  – macOS .app bundle icon  (macOS only, requires iconutil)
  icon.ico   – Windows .exe icon
  icon.png   – 1024×1024 master PNG

Requirements:
  pip install Pillow
  playwright install chromium   (if not already done)
"""

import re
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow not found.  Run: pip install Pillow")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright not found.  Run: pip install playwright && playwright install chromium")


ICONS_DIR   = Path(__file__).parent.resolve()
# Switch between icon variants:
#   icon.svg          – transparent background, green bubble (original)
#   icon-green-bg.svg – green background, white bubble (Option A)
SVG         = ICONS_DIR / "icon-green-bg.svg"
ICONSET     = ICONS_DIR / "icon.iconset"   # temp folder, deleted after use
MASTER_SIZE = 1024

# macOS iconset: pixel size → required filenames
ICONSET_MAP: dict[int, list[str]] = {
    16:   ["icon_16x16.png"],
    32:   ["icon_16x16@2x.png", "icon_32x32.png"],
    64:   ["icon_32x32@2x.png"],
    128:  ["icon_128x128.png"],
    256:  ["icon_128x128@2x.png", "icon_256x256.png"],
    512:  ["icon_256x256@2x.png", "icon_512x512.png"],
    1024: ["icon_512x512@2x.png"],
}

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)]


def render_master() -> Image.Image:
    """Render icon.svg at 1024×1024 via Playwright with transparent background."""
    svg_text = SVG.read_text()
    # Replace only the <svg> element's width/height, not attributes on child elements
    svg_text = re.sub(r'(<svg[^>]*)\bwidth="[^"]*"',  rf'\1width="{MASTER_SIZE}px"',  svg_text)
    svg_text = re.sub(r'(<svg[^>]*)\bheight="[^"]*"', rf'\1height="{MASTER_SIZE}px"', svg_text)

    html = f'<!DOCTYPE html><html><body style="margin:0;padding:0;">{svg_text}</body></html>'

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": MASTER_SIZE, "height": MASTER_SIZE})
        page.set_content(html)
        data = page.screenshot(omit_background=True)   # transparent PNG
        browser.close()

    return Image.open(BytesIO(data)).convert("RGBA")


def sized(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


def build_master_png(master: Image.Image):
    master.save(ICONS_DIR / "icon.png")
    print("  saved icon.png  (1024×1024)")


def build_icns(master: Image.Image):
    ICONSET.mkdir(exist_ok=True)
    for size, names in ICONSET_MAP.items():
        img = sized(master, size)
        for name in names:
            img.save(ICONSET / name)
        print(f"  rendered {size:>4}×{size:<4}  →  {', '.join(names)}")

    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICONS_DIR / "icon.icns")],
        capture_output=True,
        text=True,
    )
    shutil.rmtree(ICONSET)

    if result.returncode != 0:
        sys.exit(f"iconutil failed:\n{result.stderr}")
    print("  saved icon.icns")


def round_corners(img: Image.Image, radius_pct: float = 0.22) -> Image.Image:
    """Apply a rounded corner mask — matches Apple's ~22% corner radius."""
    radius = int(img.width * radius_pct)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (img.width - 1, img.height - 1)], radius=radius, fill=255
    )
    result = img.copy().convert("RGBA")
    result.putalpha(mask)
    return result


def build_ico(master: Image.Image):
    """Build icon.ico with all sizes stored as PNG-within-ICO.

    Pillow saves smaller sizes as BMP DIBs whose alpha channel Windows
    may not render correctly when the icon is embedded in an EXE by
    PyInstaller. Writing raw PNG blobs into the ICO container guarantees
    that the alpha channel (and therefore the rounded corners) survives.
    """
    import struct
    ordered = sorted(ICO_SIZES, reverse=True)   # 256 → 48 → 32 → 16
    png_blobs = []
    for size in ordered:
        img = master.resize(size, Image.LANCZOS)
        if size[0] >= 24:                        # only round at sizes where it looks good
            img = round_corners(img)
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_blobs.append((size, buf.getvalue()))

    n = len(png_blobs)
    dir_offset = 6 + 16 * n
    entries, data_parts = [], []
    offset = dir_offset
    for (w, h), data in png_blobs:
        bw = 0 if w >= 256 else w   # 0 encodes 256 in the ICO spec
        bh = 0 if h >= 256 else h
        entries.append(struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32, len(data), offset))
        data_parts.append(data)
        offset += len(data)

    with open(ICONS_DIR / "icon.ico", "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, n))   # ICONDIR header
        for e in entries:
            f.write(e)
        for d in data_parts:
            f.write(d)
    print(f"  saved icon.ico  ({', '.join(f'{w}x{h}' for w, h in ordered)})")


if __name__ == "__main__":
    if not SVG.exists():
        sys.exit(f"SVG not found: {SVG}")

    print("Rendering SVG via Playwright...")
    master = render_master()

    print("\nSaving master PNG...")
    build_master_png(master)

    print("\nBuilding macOS icon.icns...")
    if sys.platform == "darwin":
        build_icns(master)
    else:
        print("  Skipped — iconutil is macOS-only.")

    print("\nBuilding Windows icon.ico...")
    build_ico(master)

    print("\nDone. Files are in icons/")
