#!/usr/bin/env python3
"""Regenerate flow-field streamlines for assets/flow-field.svg.

Uses obstacle-aware path integration (ellipse around wordmark) plus SVG mask
for display. Preserves upper streamlines (max y < UPPER_Y_KEEP) and rebuilds
the rest from the same vector field.
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "assets" / "flow-field.svg"

# Wordmark exclusion (matches mask + debug ellipse)
CX, CY = 600.0, 258.6
RX, RY = 266.0, 53.0

X_MIN, X_MAX = 8.0, 1190.0
Y_MIN, Y_MAX = 98.0, 372.0

UPPER_Y_KEEP = 246.0
FIELD_SEED = 80524

# Canvas bounds in path space (inside scaled group)


def ellipse_metric(x: float, y: float) -> float:
    dx = (x - CX) / RX
    dy = (y - CY) / RY
    return dx * dx + dy * dy


def in_forbidden(x: float, y: float, margin: float = 1.02) -> bool:
    return ellipse_metric(x, y) < margin


def flow_velocity(x: float, y: float) -> tuple[float, float]:
    """Smooth rotational field with soft deflection around the text ellipse."""
    a = (
        math.sin(x * 0.0051 + 0.35) * 1.35
        + math.sin(y * 0.0044 - 0.55) * 1.05
        + math.sin((x + y * 0.62) * 0.0026) * 0.95
        + math.sin(x * 0.0022 - y * 0.0019) * 0.55
    )
    vx, vy = math.cos(a), math.sin(a)

    m = ellipse_metric(x, y)
    if m < 1.45:
        dx = (x - CX) / (RX * RX)
        dy = (y - CY) / (RY * RY)
        # outward normal of ellipse gradient
        ox, oy = dx, dy
        olen = math.hypot(ox, oy) or 1e-6
        ox, oy = ox / olen, oy / olen
        tx, ty = -oy, ox
        tangent_sign = 1.0 if vx * tx + vy * ty >= 0 else -1.0
        strength = (1.45 - m) * 2.4
        vx += ox * strength + tx * tangent_sign * strength * 0.75
        vy += oy * strength + ty * tangent_sign * strength * 0.75

    # gentle vertical bias in lower half so currents fill beneath the name
    if y > 285:
        vy += 0.12 * min(1.0, (y - 285) / 70)
    if 520 < x < 680 and 295 < y < 360:
        vx += math.sin(x * 0.09 + y * 0.05) * 0.02

    vlen = math.hypot(vx, vy) or 1.0
    return vx / vlen, vy / vlen


def integrate_streamline(x0: float, y0: float, step: float = 2.6, steps: int = 130) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = [(x0, y0)]

    def march(sign: float) -> None:
        x, y = x0, y0
        for _ in range(steps):
            vx, vy = flow_velocity(x, y)
            x += vx * step * sign
            y += vy * step * sign
            if not (X_MIN <= x <= X_MAX and Y_MIN <= y <= Y_MAX):
                break
            if in_forbidden(x, y):
                break
            if sign > 0:
                pts.append((x, y))
            else:
                pts.insert(0, (x, y))

    march(1.0)
    march(-1.0)
    return pts


def path_length(pts: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def path_stats(pts: list[tuple[float, float]]) -> tuple[float, float, float]:
    ys = [p[1] for p in pts]
    xs = [p[0] for p in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys), max(ys)


def points_to_d(pts: list[tuple[float, float]]) -> str:
    x0, y0 = pts[0]
    parts = [f"M{x0:.1f} {y0:.1f}"]
    for x, y in pts[1:]:
        parts.append(f"L{x:.1f} {y:.1f}")
    return " ".join(parts)


def parse_paths_from_stream_section(section: str) -> list[str]:
    return re.findall(r'<path d="([^"]+)"', section)


def max_y_of_d(d: str) -> float:
    return max(float(b) for a, b in re.findall(r"[ML]([\d.]+)\s+([\d.]+)", d))


def extract_groups(section: str) -> list[dict]:
    pattern = re.compile(
        r'<g stroke-dasharray="([^"]+)" stroke-dashoffset="0" stroke="([^"]+)" '
        r'stroke-width="([^"]+)" opacity="([^"]+)">'
        r"(<animate[^/]+/>)"
        r"(.*?)</g>",
        re.DOTALL,
    )
    groups = []
    for m in pattern.finditer(section):
        groups.append(
            {
                "dash": m.group(1),
                "stroke": m.group(2),
                "width": m.group(3),
                "opacity": m.group(4),
                "animate": m.group(5),
                "paths": parse_paths_from_stream_section(m.group(6)),
            }
        )
    return groups


def build_stream_section(groups: list[dict]) -> str:
    chunks = [
        '<g fill="none" stroke-linecap="round" '
        'transform="translate(600.0,236.0) scale(1.38) translate(-600.0,-236.0)">'
    ]
    for g in groups:
        chunks.append(
            f'<g stroke-dasharray="{g["dash"]}" stroke-dashoffset="0" stroke="{g["stroke"]}" '
            f'stroke-width="{g["width"]}" opacity="{g["opacity"]}">{g["animate"]}'
        )
        for d in g["paths"]:
            chunks.append(f'<path d="{d}" />')
        chunks.append("</g>")
    chunks.append("</g></g>")  # transform group + #ff-streamlines
    return "".join(chunks)


def generate_candidates(rng: random.Random, target: int) -> list[str]:
    out: list[str] = []
    attempts = 0
    while len(out) < target and attempts < target * 80:
        attempts += 1
        # Bias seeds toward lower canvas; still sample mid for continuity
        roll = rng.random()
        if roll < 0.52:
            y0 = rng.uniform(292, Y_MAX - 4)
            x0 = rng.uniform(120, X_MAX - 120)
        elif roll < 0.78:
            y0 = rng.uniform(248, 318)
            x0 = rng.uniform(40, X_MAX - 40)
        else:
            y0 = rng.uniform(Y_MIN + 8, 250)
            x0 = rng.uniform(40, X_MAX - 40)

        if in_forbidden(x0, y0, margin=1.08):
            continue

        pts = integrate_streamline(x0, y0)
        if len(pts) < 11:
            continue
        if path_length(pts) < 72:
            continue
        if any(in_forbidden(x, y, margin=1.0) for x, y in pts):
            continue

        ax, ay, my = path_stats(pts)
        # Prefer lower integration; reject paths that live entirely above keep band
        if my < 268 and ay < 235:
            continue
        # Reject tiny lower-center stubs
        if len(pts) < 14 and ay > 300:
            continue

        out.append(points_to_d(pts))
    return out


def distribute_paths(groups: list[dict], kept: list[str], generated: list[str]) -> None:
    targets = [len(g["paths"]) for g in groups]
    total_target = sum(targets)
    pool = kept + generated
    rng = random.Random(FIELD_SEED + 99)
    rng.shuffle(pool)

    # Slightly boost lower-heavy paths in groups that originally had more paths
    lower_first = sorted(
        pool,
        key=lambda d: (-max_y_of_d(d), -len(d)),
    )
    pool = lower_first

    if len(pool) < total_target:
        raise RuntimeError(f"Not enough streamlines: have {len(pool)}, need {total_target}")

    idx = 0
    for g, count in zip(groups, targets):
        g["paths"] = pool[idx : idx + count]
        idx += count


def main() -> None:
    svg = SVG_PATH.read_text()
    start = svg.index('<g id="ff-streamlines"')
    stream_open = svg.index('mask="url(#ff-stream-mask)">', start) + len('mask="url(#ff-stream-mask)">')
    wordmark = svg.index('<g id="ff-wordmark">', start)
    stream_section = svg[stream_open:wordmark]

    groups = extract_groups(stream_section)
    if not groups:
        raise SystemExit("Could not parse streamline groups")

    all_paths = [p for g in groups for p in g["paths"]]
    kept = [p for p in all_paths if max_y_of_d(p) < UPPER_Y_KEEP]
    need = len(all_paths) - len(kept)

    rng = random.Random(FIELD_SEED)
    generated = generate_candidates(rng, need + 95)
    if len(generated) < need:
        raise SystemExit(f"Generation produced only {len(generated)} paths; need {need}")

    distribute_paths(groups, kept, generated)
    new_stream = build_stream_section(groups)

    new_svg = svg[:stream_open] + new_stream + svg[wordmark:]
    new_svg = new_svg.replace(
        'ellipse cx="600.0" cy="239.5" rx="392" ry="69"',
        f'ellipse cx="{CX}" cy="{CY}" rx="{RX:.0f}" ry="{RY:.0f}"',
    )
    new_svg = re.sub(
        r'(<ellipse id="ff-debug-exclusion" cx=")[^"]+(" cy=")[^"]+(" rx=")[^"]+(" ry=")[^"]+',
        rf'\g<1>{CX}\g<2>{CY}\g<3>{RX:.0f}\g<4>{RY:.0f}',
        new_svg,
        count=1,
    )
    SVG_PATH.write_text(new_svg)

    # Stats
    part = new_stream
    paths = parse_paths_from_stream_section(part)
    ys = []
    for d in paths:
        ys.extend(float(b) for a, b in re.findall(r"[ML]([\d.]+)\s+([\d.]+)", d))
    lower = sum(1 for d in paths if max_y_of_d(d) > 300)
    print(f"Wrote {SVG_PATH}")
    print(f"paths total={len(paths)} kept_upper={len(kept)} regenerated={len(paths)-len(kept)}")
    print(f"paths with max_y>300: {lower}")
    print(f"y range {min(ys):.1f}-{max(ys):.1f}")


if __name__ == "__main__":
    main()
