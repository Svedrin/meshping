# Meshping Network Map: How It Works & Style Guide

This document describes how the `/network.svg` endpoint produces its output,
the layout algorithm, the visual design decisions, and the rules to follow
when modifying either the Python code or the Jinja template.

---

## What the Network Map Shows

The map visualises the union of all stored traceroutes.  Each unique hop
(identified by its IP address) becomes exactly one node, regardless of how
many target paths pass through it.  Each unique parent→child adjacency in any
traceroute becomes exactly one edge.

The result is a directed acyclic graph rooted at **SELF** (the local
meshping instance), fanning out toward the monitored targets at the leaves.
Because multiple targets often share upstream hops (e.g. the same default
gateway, the same ISP transit router), the graph is frequently a DAG rather
than a pure tree.

Node colour encodes the **reachability state** last recorded by the traceroute
engine:

| State       | Meaning                                                              |
|-------------|----------------------------------------------------------------------|
| `up`        | Hop replied in the most recent traceroute                            |
| `different` | Hop replied but with a different address than the last good trace    |
| `down`      | Hop was present in the last-known-good trace but is now silent       |
| `unknown`   | State has never been established (e.g. newly added target)           |
| `dummy`     | Placeholder for a gap in distance (see "Dummy Nodes" below)          |
| `self`      | The local node itself                                                |

---

## Data Pipeline

### 1. Building the graph (`api.py: network_diagram`)

Meshping iterates over `mp.all_targets()`.  For each target it walks
`target.traceroute`, a list of hop dicts produced by `db.py`:

```python
{
    "address":  "1.2.3.4",
    "name":     "gw.example.net",   # reverse-DNS, may equal address
    "distance": 3,                  # TTL hop number, 1-based
    "state":    "up",               # up / down / different
    "time":     1700000000.0,       # epoch, used for state freshness
    "whois":    {                   # result of IPWhois.lookup_rdap(), or {}
        "asn":     "AS1234",
        "network": {"name": "Example Transit"},
        ...
    },
    "target":   <Target object>,    # set only on the final hop
}
```

Two dicts accumulate as the loop runs:

* **`uniq_hops`** – `hop_id → hop dict`.  `hop_id` is the address with `.`
  and `:` replaced by `_` so it is safe to use as an SVG element id.
  `setdefault` ensures each physical hop appears exactly once; if the same
  hop is seen again with a fresher `time`, its `state` is updated.

* **`uniq_links`** – a `set` of `(parent_id, child_id)` tuples.

`prev_hop` starts as the string `"SELF"` each iteration and advances to
the current `hop_id`, so the first hop of each traceroute is automatically
connected to SELF.

#### Dummy nodes

If a traceroute skips a distance value (e.g. jumps from distance 1 to
distance 3 because an intermediate router doesn't reply to probes), a
**dummy** hop is synthesised for each missing distance.  Dummy hops have
`address = None` and `name = None`; they are displayed as `?` nodes and
carry no state colour.  The dummy's `id` is a random 8-digit integer,
chosen fresh each render — dummy nodes are ephemeral.

---

### 2. Layout (`api.py: network_diagram`, layout section)

The layout is entirely hierarchical: every real hop already carries a
`distance` value (its TTL hop number), so the vertical axis is free.

**Key constants** (all in pixels):

| Constant      | Default | Purpose                                     |
|---------------|---------|---------------------------------------------|
| `NODE_W`      | 260     | Fixed node width                            |
| `H_GAP`       | 70      | Horizontal gap between sibling nodes        |
| `V_GAP`       | 60      | Vertical gap between levels                 |
| `PAD_X`       | 80      | Canvas left/right margin                    |
| `PAD_Y`       | 86      | Canvas top margin (accounts for title bar)  |
| `INNER_PAD`   | 14      | Text padding inside each node card          |
| `TITLE_FONT`  | 14      | Font size for the node's primary label      |
| `BODY_FONT`   | 11      | Font size for secondary lines               |
| `BODY_LINE_H` | 17      | Line height for body text                   |
| `BODY_GAP`    | 5       | Extra vertical gap between title and body   |

#### Level grouping

Nodes are grouped by distance:

```
level 0 → ["SELF"]
level 1 → [all hops with distance == 1]
level 2 → [all hops with distance == 2]
...
```

The canvas height is the sum of each level's tallest node plus `V_GAP`
separators plus top and bottom padding.

The canvas width is `max(1000, max_nodes_per_level × (NODE_W + H_GAP) − H_GAP + 2 × PAD_X)`.

#### Node height

Each node's height is computed from its content:

```
h = INNER_PAD × 2 + TITLE_FONT + BODY_GAP + body_lines × BODY_LINE_H
```

where `body_lines` is:

* 0 for dummy nodes (renders as a fixed 48 px square)
* 1 for SELF (`This node` label)
* 1 for a plain hop (address only)
* 2 if the hop also has whois data
* 3 if the hop also links to a histogram

All nodes in the same level are vertically centred on that level's midpoint
(the tallest node in the level determines the midpoint).

#### Sibling ordering

Within each level, siblings are sorted by the **average X coordinate of their
parents** already computed in the level above.  This is a single top-down
pass and keeps related branches visually clustered — hops that share a parent
stay close to each other — without the complexity of a full Reingold-Tilford
layout.

#### Edge geometry

Each edge is a **cubic Bézier curve** connecting the bottom-centre of the
parent node to the top-centre of the child node:

```
P0 = (parent.cx, parent.cy + parent.h / 2)     # departure
P3 = (child.cx,  child.cy  − child.h  / 2)     # arrival
P1 = (P0.x, P0.y + (P3.y − P0.y) × 0.5)       # control 1
P2 = (P3.x, P3.y − (P3.y − P0.y) × 0.5)       # control 2
```

The control points pull straight down/up from the endpoints, producing a
gentle S-curve.  Edges connect to the exact centre of the card's top/bottom
edge regardless of where the sibling sits horizontally.

---

### 3. Rendering (`src/templates/network.svg`)

All layout work is done in Python before the template is called.  The
template receives:

| Variable   | Type              | Contents                                    |
|------------|-------------------|---------------------------------------------|
| `canvas_w` | `int`             | Total SVG width in pixels                   |
| `canvas_h` | `int`             | Total SVG height in pixels                  |
| `hostname` | `str`             | Local machine hostname (used in SELF node)  |
| `now`      | `str`             | Render timestamp, `YYYY-MM-DD HH:MM:SS`     |
| `nodes`    | `list[dict]`      | One dict per node (see below)               |
| `edges`    | `list[dict]`      | One dict per edge (see below)               |

Each **node dict**:

```python
{
    "cx":     float,   # centre X
    "cy":     float,   # centre Y
    "w":      260,     # always NODE_W
    "h":      float,   # computed height
    "state":  str,     # "up" / "down" / "different" / "dummy" / "self" / "unknown"
    "stroke": str,     # hex colour matching state (see palette below)
    "lines":  [        # pre-computed text lines, top to bottom
        {
            "text":   str,
            "href":   str | None,   # None → plain text; str → wrapped in <a>
            "x":      float,        # absolute SVG x (baseline anchor)
            "y":      float,        # absolute SVG y (baseline)
            "size":   int,          # font-size in px
            "weight": str,          # "600" for title, "normal" for body
            "fill":   str,          # hex colour
            "anchor": str,          # "start" or "middle"
        },
        ...
    ],
}
```

Each **edge dict**:

```python
{
    "x1": float, "y1": float,    # start point (bottom-centre of parent)
    "cx1": float, "cy1": float,  # Bézier control point 1
    "cx2": float, "cy2": float,  # Bézier control point 2
    "x2": float, "y2": float,    # end point (top-centre of child)
}
```

The template is **purely presentational**: it iterates the pre-computed lists
and writes SVG markup.  No arithmetic, no conditionals on hop data.

#### Jinja delimiters

The project configures non-standard Jinja2 delimiters so they don't clash with
Vue.js in the HTML templates:

```python
variable_start_string = '{['
variable_end_string   = ']}'
```

Control blocks (`{% for %}`, `{% if %}`, `{% set %}`) use the standard
`{% %}` delimiters unchanged.  Floating-point coordinates are formatted with
`{[ '%.2f' % value ]}`.

---

## Visual Design

### Palette

| State       | Stroke / glow / accent   |
|-------------|--------------------------|
| `self`      | `#60a5fa` (blue-400)     |
| `up`        | `#22c55e` (green-500)    |
| `different` | `#f59e0b` (amber-500)    |
| `down`      | `#ef4444` (red-500)      |
| `dummy`     | `#475569` (slate-600)    |
| `unknown`   | `#475569` (slate-600)    |

Background layers:

| Element           | Value                              |
|-------------------|------------------------------------|
| Base gradient     | `#182644` → `#090d1a` (diagonal)   |
| Dot-grid overlay  | `#1e3a5f` at 30% opacity, 28 px    |
| Title bar         | `#060c1a` at 88% opacity           |
| Title bar border  | `#1d4ed8` at 50% opacity           |
| Node card fill    | `#07101f`                          |
| Edge stroke       | `#2d4a6b` at 65% opacity           |
| Legend fill       | `#07101f`                          |
| Legend border     | `#1e3a5f`                          |

Text colours:

| Role              | Value                |
|-------------------|----------------------|
| Primary (title)   | `#f1f5f9` (slate-100)|
| Address / body    | `#94a3b8` (slate-400)|
| ASN / secondary   | `#64748b` (slate-500)|
| Histogram link    | Matches state stroke  |
| Subtitle / footer | `#334155` (slate-700)|

### Node anatomy

```
╔══[accent stripe — state colour, 3 px, inset 12 px each side]══╗  ← y0
║                                                               ║
║  Hostname or target name                   ← title, 14 px bold, #f1f5f9
║  1.2.3.4                                   ← address, 11 px, #94a3b8, linked to ipinfo.io
║  AS1234: Example Transit                   ← whois, 11 px, #64748b, linked to bgp.tools
║  View Histogram →                          ← 11 px, state colour, linked to /histogram/…
║                                               (only on final-hop target nodes)
╚═══════════════════════════════════════════╝
```

The outer rectangle has:
* `fill="#07101f"` — near-black dark navy
* `stroke` — state colour at 85% opacity, 1.5 px
* `rx="10"` — rounded corners

The glow is an SVG `<filter>` applied to the whole `<g>` containing the card.
It blurs the node's alpha channel, floods it with the state colour at ~45%
opacity, and composites the result behind the original:

```xml
<feGaussianBlur in="SourceAlpha" stdDeviation="5" result="b"/>
<feFlood flood-color="…" flood-opacity="0.45" result="c"/>
<feComposite in="c" in2="b" operator="in" result="g"/>
<feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>
```

SELF uses `stdDeviation="7"` and `flood-opacity="0.55"` for a stronger glow.

### Links in nodes

Text lines that have an `href` are wrapped in:

```xml
<a xlink:href="…" href="…" target="_blank">
  <text … text-decoration="underline">…</text>
</a>
```

Both `href` and `xlink:href` are emitted so the SVG works when:
* opened in a browser directly (uses `href`)
* embedded in an older SVG viewer that only understands `xlink:href`

All content is HTML-escaped via Jinja's `| e` filter to handle hostnames or
network names that contain `&`, `<`, or `>`.

The `→` in "View Histogram →" is the Unicode arrow U+2192, written as
`→` in source so it survives XML round-trips.

### Legend

A small panel in the bottom-left lists the four user-visible states (Up,
Degraded, Down, Unknown) with a small square swatch for each.  The swatch
is a filled rect at 18% opacity with a state-coloured stroke — matching
the visual language of the node cards.  The panel itself uses the same
`#07101f` fill and `#1e3a5f` border as a node card, with a drop-shadow
filter for depth.

The dummy and unknown states are deliberately merged into "Unknown" in the
legend because the distinction (placeholder gap vs. never-seen hop) is not
meaningful to a reader glancing at the map.

---

## Portability: Save As

The SVG is designed to be self-contained:

* No external resources — all fonts are specified as system-font stacks
  (`ui-sans-serif, system-ui, …`), so they render in any browser or
  SVG viewer without network access.
* All hyperlinks (`ipinfo.io`, `bgp.tools`, histogram) use absolute URLs
  (generated with `url_for(…, _external=True)`) so they remain valid
  regardless of where the saved file is opened.
* All layout and styling is inline — no separate CSS file, no `<use>` references
  to external symbol sheets, no `<image>` tags.

Opening a saved copy six months later will render identically to the live
endpoint, minus any data that has since changed.

---

## Extending the Template

When adding new content to the SVG:

1. **Add data in Python, not in the template.**  The template is dumb
   markup; all decisions (what text to show, what colour, what URL) live
   in `network_diagram()` in `api.py`.  The template receives flat,
   pre-computed values.

2. **Respect the layering order** (background → edges → nodes → panels →
   footer).  SVG has no z-index; later elements paint over earlier ones.
   Edges must be drawn before nodes so they disappear behind the cards.

3. **Use `| e` on all user-supplied strings** in the template.  Hostnames,
   network names, and addresses can contain characters that break XML.

4. **Match the palette.**  New states or indicators should pick a colour
   from the existing Tailwind-CSS-aligned palette (use `slate-*`, `green-500`,
   `amber-500`, `red-500`, `blue-400`) and define a corresponding
   `<filter id="glow-<state>">` in `<defs>`.

5. **Keep `PAD_Y ≥ 58 + breathing room`.**  The title bar is 58 px tall.
   Nodes must not overlap it.  The current default of 86 px leaves 28 px
   of clear space below the bar.
