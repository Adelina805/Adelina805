#!/usr/bin/env python3
"""Build assets/flow-field.svg from the upstream flow-field template paths."""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG_OUT = ROOT / "assets" / "flow-field.svg"
ORIGINAL_URL = (
    "https://raw.githubusercontent.com/beydemirfurkan/awesome-github-profile/"
    "main/assets/generative/flow-field.svg"
)

TEXT = "adelina martinez"
FONT_SIZE = 52
TEXT_Y = 212
MASK_DILATE = 24  # ~24px clearance around glyph bounds

# Subtle traveling highlight (overlay only); base strokes stay solid.
OVERLAY_DASH = "96 704"
OVERLAY_OPACITY = "0.32"

GROUP_PATTERN = re.compile(
    r'(<g stroke="([^"]+)" stroke-width="([^"]+)" opacity="([^"]+)">)(.*?)(</g>)',
    re.DOTALL,
)

DURATIONS = [
    22.0,
    26.5,
    19.8,
    24.2,
    28.0,
    21.3,
    25.6,
    20.4,
    27.2,
    23.8,
    18.6,
    29.4,
    22.8,
    24.9,
    20.9,
    26.1,
    23.1,
    25.0,
    21.7,
    28.6,
    19.2,
    27.8,
    24.5,
]


def fetch_original() -> str:
    cached = Path("/tmp/original-flow-field.svg")
    if cached.is_file() and cached.stat().st_size > 50_000:
        return cached.read_text()
    with urllib.request.urlopen(ORIGINAL_URL, timeout=60) as resp:
        data = resp.read().decode("utf-8")
    cached.write_text(data)
    return data


def extract_streamlines(svg: str) -> str:
    start = svg.index('<g fill="none" stroke-linecap="round">')
    end = svg.index('<rect width="1200" height="420" fill="url(#ff-vig)"/>')
    return svg[start:end]


def animate_overlay(index: int, stroke: str, width: str) -> str:
    dur = DURATIONS[index % len(DURATIONS)]
    begin = f"{(index * 1.37) % dur:.2f}s"
    period = 800  # dash + gap sum for seamless loop
    return (
        f'<g fill="none" stroke-linecap="round" stroke="{stroke}" '
        f'stroke-width="{width}" stroke-dasharray="{OVERLAY_DASH}" '
        f'stroke-dashoffset="0" opacity="{OVERLAY_OPACITY}" data-flow-overlay="1">'
        f'<animate attributeName="stroke-dashoffset" from="0" to="{period}" '
        f'dur="{dur:.2f}s" begin="{begin}" repeatCount="indefinite" calcMode="linear" />'
    )


def add_flow_overlay(stream_block: str) -> str:
    idx = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal idx
        open_tag, stroke, width, opacity, paths, close_tag = match.groups()
        if "<path" not in paths:
            return match.group(0)
        overlay_open = animate_overlay(idx, stroke, width)
        chunk = (
            f'{open_tag}{paths}{overlay_open}{paths}</g>{close_tag}'
        )
        idx += 1
        return chunk

    inner = stream_block
    if inner.startswith('<g fill="none" stroke-linecap="round">'):
        inner = inner[len('<g fill="none" stroke-linecap="round">') :]
        inner = inner.rstrip()
        if inner.endswith("</g>"):
            inner = inner[:-4]
    rebuilt = '<g fill="none" stroke-linecap="round">'
    rebuilt += GROUP_PATTERN.sub(repl, inner)
    rebuilt += "</g>"
    return rebuilt


def build_svg(stream_block: str) -> str:
    stream_animated = add_flow_overlay(stream_block)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" width="1200" height="420" role="img" aria-label="adelina martinez — animated generative flow field wordmark">
<title>adelina martinez</title>
<desc>Original flow-field streamlines with centered wordmark and calm SVG motion.</desc>
<defs>
<filter id="ff-text-expand" x="-30%" y="-30%" width="160%" height="160%">
<feMorphology operator="dilate" radius="{MASK_DILATE}" in="SourceGraphic"/>
</filter>
<mask id="ff-stream-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="1200" height="420">
<rect width="1200" height="420" fill="white"/>
<text x="600" y="{TEXT_Y}" text-anchor="middle" dominant-baseline="middle"
font-family="system-ui, -apple-system, 'Segoe UI', sans-serif" font-size="{FONT_SIZE}" font-weight="600"
fill="black" filter="url(#ff-text-expand)">{TEXT}</text>
</mask>
<style><![CDATA[
@media (prefers-reduced-motion: reduce) {{
  #ff-streamlines [data-flow-overlay] {{ display: none; }}
}}
@media (prefers-color-scheme: light) {{
  #ff-wordmark text {{ fill: #1a2a3a; }}
}}
]]></style>
</defs>
<g id="ff-streamlines" mask="url(#ff-stream-mask)">
{stream_animated}
</g>
<g id="ff-wordmark">
<text x="600" y="{TEXT_Y}" text-anchor="middle" dominant-baseline="middle"
font-family="system-ui, -apple-system, 'Segoe UI', sans-serif" font-size="{FONT_SIZE}" font-weight="600"
fill="#f0f2f8">{TEXT}</text>
</g>
<rect x="0.5" y="0.5" width="1199" height="419" fill="none" stroke="#ffffff" stroke-width="1"/>
</svg>
'''


def main() -> None:
    original = fetch_original()
    stream = extract_streamlines(original)
    path_count = len(re.findall(r"<path ", stream))
    if path_count < 500:
        raise SystemExit(f"Expected ~520 paths, found {path_count}")
    svg = build_svg(stream)
    SVG_OUT.write_text(svg)
    print(f"Wrote {SVG_OUT} ({len(svg)} bytes, {path_count} paths)")


if __name__ == "__main__":
    main()
