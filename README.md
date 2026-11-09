# QuoteCard Forge

A self-hosted engine that turns text — reviews, testimonials, quotes — into
branded social-media cards (1080×1350 PNG) in bulk. FOSS only, $0 to run.

## Identity rules (strict — no exceptions)

Every generated card and page uses exactly three colors:

| Role       | Color     | Used for                                   |
|------------|-----------|--------------------------------------------|
| Background | `#000000` | Card and page background                   |
| Primary    | `#FF2400` | Labels, headlines, rules, attribution, CTAs |
| Body       | `#FFFFFF` | Quote/body text, fine print                |

The renderer enforces this mechanically: text is drawn through a
thresholded mask, so the exported PNGs contain **only** those three exact
RGB values — no anti-aliasing blends, no fourth color.

## Layout

```
quotecard-forge/
├── index.html            # static storefront (GitHub Pages-ready)
├── docker-compose.yml    # container run path (mirrors the local run)
├── requirements.txt
├── renderer/
│   ├── render.py         # the rendering engine
│   └── requirements.txt
├── configs/              # one JSON per niche
│   ├── restaurants-bars.json
│   ├── barbers.json
│   └── realtors.json
├── samples/              # rendered sample cards (all marked SAMPLE CARD)
└── data/jobs.db          # SQLite job log (created on first run)
```

## Run it locally

Requires Python 3.10+ and Pillow (plus a sans font — DejaVu Sans is used
when present):

```bash
pip install -r requirements.txt
cd renderer
python3 render.py --config ../configs/barbers.json --output ../samples
python3 render.py --config ../configs/restaurants-bars.json --output ../samples
python3 render.py --config ../configs/realtors.json --output ../samples
```

Render a custom entries file instead of the config's built-in entries
(CSV with `text,author,source` columns, or JSON with an `entries` list):

```bash
python3 render.py --config ../configs/barbers.json \
                  --entries my_reviews.csv --output ./out
```

Every run is logged to `data/jobs.db` (table `jobs`): UTC timestamp, niche,
cards rendered, failures, output directory. A failed entry never stops the
batch — it is counted and printed to stderr.

## Run with Docker

```bash
docker compose run --rm renderer \
  --config /app/configs/barbers.json --output /app/samples --db /app/data/jobs.db
```

## Niche config format

```json
{
  "niche": "barbers",
  "display_name": "Barbers",
  "description": "Review and testimonial cards for barbershops.",
  "card_label": "CLIENT REVIEW",
  "brand_line": "QUOTECARD FORGE",
  "entries": [
    { "text": "Quote or review text.", "author": "Name", "source": "Role or context", "sample": true }
  ]
}
```

- `text` — required; wrapped and auto-shrunk until it fits the card.
- `author` / `source` — rendered as the red attribution line.
- `sample: true` — adds a "SAMPLE CARD" marker to the footer. The entries
  shipped in `configs/` are illustrative sample copy, not real reviews.

Output files are named `<niche>-01.png`, `<niche>-02.png`, …

## Pricing

- **Custom pack: $29** — 50 cards rendered from the customer's own text.
- **Niche bundles: $19** — pre-built template packs (Restaurants & Bars,
  Barbers, Realtors).

Checkout is via Gumroad — **not live yet**; the storefront links in
`index.html` are placeholders (`href="#"`).

## Verified sample run (Phase 1 build)

10 cards rendered (4 Restaurants & Bars incl. a deliberate long-text
overflow test, 3 Barbers, 3 Realtors), 0 failures. Each PNG checked
programmatically: 1080×1350, palette exactly {#000000, #FF2400, #FFFFFF}.
