#!/usr/bin/env python3
"""QuoteCard Forge — text-to-social-card renderer.

Reads a niche config (JSON) containing entries (quote text, author/source),
lays each entry out on a 1080x1350 card, and exports PNGs.

Identity (strict, no other colors are ever emitted):
  background  #000000
  primary     #FF2400  (headlines, labels, attribution, rule lines)
  body        #FFFFFF  (quote text, fine print)

Text is drawn through a thresholded mask so the output PNG contains ONLY
the three exact identity colors — no anti-aliasing blends.

Usage:
  python3 render.py --config ../configs/barbers.json --output ../samples
  python3 render.py --config ../configs/barbers.json \
                    --entries extra_entries.csv --output ../samples

Every run is logged to SQLite (default ../data/jobs.db): timestamp, niche,
card count, failure count, output directory.
"""

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- Identity ---------------------------------------------------------------
BLACK = (0, 0, 0)
RED = (255, 36, 0)        # #FF2400
WHITE = (255, 255, 255)

CARD_W, CARD_H = 1080, 1350
MARGIN = 90
CONTENT_W = CARD_W - 2 * MARGIN

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_CANDIDATES_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def load_font(size, bold=False):
    for path in FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REG:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    """Greedy word-wrap measured with the real font — never exceeds max_width."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            # A single word wider than the box: hard-split it.
            while draw.textlength(word, font=font) > max_width and len(word) > 1:
                cut = len(word)
                while draw.textlength(word[:cut], font=font) > max_width and cut > 1:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
    if current:
        lines.append(current)
    return lines


def fit_quote(draw, text, max_height):
    """Shrink the quote font until the wrapped block fits max_height."""
    for size in range(68, 27, -4):
        font = load_font(size, bold=True)
        lines = wrap_text(draw, text, font, CONTENT_W)
        line_h = int(size * 1.32)
        if len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = load_font(28, bold=True)
    lines = wrap_text(draw, text, font, CONTENT_W)
    return font, lines, int(28 * 1.32)


def stamp_text(base, xy, text, font, color, draw_probe, anchor_left=True):
    """Draw text via a thresholded mask so only the exact color is emitted."""
    mask = Image.new("L", base.size, 0)
    md = ImageDraw.Draw(mask)
    md.text(xy, text, font=font, fill=255)
    hard = mask.point(lambda a: 255 if a >= 128 else 0)
    base.paste(color, (0, 0), hard)


def render_card(entry, config, out_path):
    img = Image.new("RGB", (CARD_W, CARD_H), BLACK)
    draw = ImageDraw.Draw(img)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    label = config.get("card_label", "TESTIMONIAL")
    brand = config.get("brand_line", "QUOTECARD FORGE")

    # Top label (red) + thin red rule.
    label_font = load_font(34, bold=True)
    stamp_text(img, (MARGIN, 80), label, label_font, RED, probe)
    draw = ImageDraw.Draw(img)
    draw.rectangle([MARGIN, 150, CARD_W - MARGIN, 158], fill=RED)

    # Quote body (white), auto-fitted so it never overflows its box.
    quote = (entry.get("text") or "").strip()
    if not quote:
        raise ValueError("entry has empty text")
    q_font, lines, line_h = fit_quote(probe, quote, max_height=760)
    y = 240
    for line in lines:
        stamp_text(img, (MARGIN, y), line, q_font, WHITE, probe)
        y += line_h

    # Attribution (red).
    author = (entry.get("author") or "").strip()
    source = (entry.get("source") or "").strip()
    attr = author if author else ""
    if source:
        attr = f"{attr} — {source}" if attr else source
    if attr:
        a_font = load_font(36, bold=True)
        # wrap attribution if needed
        a_lines = wrap_text(probe, attr, a_font, CONTENT_W)
        ay = CARD_H - 300
        for line in a_lines[:2]:
            stamp_text(img, (MARGIN, ay), line, a_font, RED, probe)
            ay += 50

    # Bottom rule + brand / sample marker (white fine print).
    draw = ImageDraw.Draw(img)
    draw.rectangle([MARGIN, CARD_H - 170, CARD_W - MARGIN, CARD_H - 162], fill=RED)
    foot_font = load_font(28, bold=False)
    footer = brand + ("  ·  SAMPLE CARD" if entry.get("sample") else "")
    stamp_text(img, (MARGIN, CARD_H - 120), footer, foot_font, WHITE, probe)

    img.save(out_path, "PNG")
    return out_path


def load_entries(config, entries_path):
    if entries_path is None:
        return config.get("entries", [])
    p = Path(entries_path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("entries", data)
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8") as f:
            return [row for row in csv.DictReader(f)]
    raise ValueError(f"unsupported entries file: {p}")


def log_job(db_path, niche, count, failures, output_dir):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               ts TEXT NOT NULL,
               niche TEXT NOT NULL,
               cards INTEGER NOT NULL,
               failures INTEGER NOT NULL,
               output_dir TEXT NOT NULL
           )"""
    )
    conn.execute(
        "INSERT INTO jobs (ts, niche, cards, failures, output_dir) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), niche, count, failures, str(output_dir)),
    )
    conn.commit()
    conn.close()


def main():
    ap = argparse.ArgumentParser(description="QuoteCard Forge renderer")
    ap.add_argument("--config", required=True, help="niche config JSON")
    ap.add_argument("--entries", help="optional CSV/JSON entries file (overrides config entries)")
    ap.add_argument("--output", required=True, help="output directory for PNGs")
    ap.add_argument("--db", default=None, help="SQLite jobs db (default: ../data/jobs.db relative to this script)")
    args = ap.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    niche = config.get("niche", Path(args.config).stem)
    entries = load_entries(config, args.entries)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db) if args.db else Path(__file__).resolve().parent.parent / "data" / "jobs.db"

    made, failures = 0, 0
    for i, entry in enumerate(entries, start=1):
        out_path = out_dir / f"{niche}-{i:02d}.png"
        try:
            render_card(entry, config, out_path)
            made += 1
            print(f"OK  {out_path}")
        except Exception as exc:  # keep the batch going; count and log the failure
            failures += 1
            print(f"FAIL entry {i} ({niche}): {exc}", file=sys.stderr)

    log_job(db_path, niche, made, failures, out_dir)
    print(f"Done: niche={niche} cards={made} failures={failures} db={db_path}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
