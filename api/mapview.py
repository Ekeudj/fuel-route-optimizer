import html
import math


def simplify(coords, max_pts=400):
    """Downsample a long coordinate list (keeps first and last point)."""
    n = len(coords)
    if n <= max_pts:
        return coords
    step = n / max_pts
    out = [coords[int(i * step)] for i in range(max_pts)]
    out.append(coords[-1])
    return out


CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f8;color:#1f2937}
.wrap{max-width:960px;margin:0 auto;padding:20px}
h1{font-size:22px;margin:0 0 14px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.card{background:#fff;border-radius:10px;padding:12px 16px;flex:1;min-width:150px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card b{display:block;font-size:22px;margin-top:4px}
.card span{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em}
svg{width:100%;height:auto;background:#e8eef5;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;margin-top:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
th,td{padding:10px 12px;text-align:left;font-size:14px;border-bottom:1px solid #eef0f3}
th{background:#1f2937;color:#fff;font-weight:600}
.note{font-size:12px;color:#6b7280;margin-top:12px}
"""


def render_map_html(result):
    W, H, PAD = 900, 520, 40
    coords = simplify(result["map_of_the_route"]["coordinates"])
    stops = result["optimal_fuel_stops_along_route"]
    start, end = result["start"], result["end"]

    lons = [c[0] for c in coords] + [s["location"]["lon"] for s in stops]
    lats = [c[1] for c in coords] + [s["location"]["lat"] for s in stops]
    min_lon, max_lon, min_lat, max_lat = min(lons), max(lons), min(lats), max(lats)

    k = math.cos(math.radians((min_lat + max_lat) / 2))  # fix east-west stretching
    xspan = max((max_lon - min_lon) * k, 1e-6)
    yspan = max(max_lat - min_lat, 1e-6)
    scale = min((W - 2 * PAD) / xspan, (H - 2 * PAD) / yspan)
    ox = (W - xspan * scale) / 2
    oy = (H - yspan * scale) / 2

    def proj(lon, lat):
        return ox + (lon - min_lon) * k * scale, oy + (max_lat - lat) * scale

    path = " ".join(
        ("M" if i == 0 else "L") + "%.1f,%.1f" % proj(c[0], c[1])
        for i, c in enumerate(coords)
    )

    svg = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">',
           f'<path d="{path}" fill="none" stroke="#2563eb" stroke-width="4" '
           f'stroke-linecap="round" stroke-linejoin="round"/>']

    for i, s in enumerate(stops, 1):
        x, y = proj(s["location"]["lon"], s["location"]["lat"])
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="#f59e0b" stroke="#fff" stroke-width="2"/>')
        svg.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="12" '
                   f'font-weight="700" fill="#fff">{i}</text>')

    for p, color, label in ((start, "#16a34a", "START"), (end, "#dc2626", "END")):
        x, y = proj(p["lon"], p["lat"])
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{color}" stroke="#fff" stroke-width="3"/>')
        svg.append(f'<text x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" font-size="13" '
                   f'font-weight="700" fill="{color}">{label}: {html.escape(p["query"])}</text>')
    svg.append("</svg>")

    rows = "".join(
        f"<tr><td>{i}</td><td>{html.escape(s['truckstop'])}</td>"
        f"<td>{html.escape(s['city'])}, {html.escape(s['state'])}</td>"
        f"<td>{s['mile_marker']}</td><td>${s['price_per_gallon']}</td>"
        f"<td>{s['gallons_purchased']}</td><td>${s['cost_usd']}</td></tr>"
        for i, s in enumerate(stops, 1)
    ) or '<tr><td colspan="7">No fuel stops needed (or none found near the route).</td></tr>'

    a = result["assumptions"]
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fuel Route</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{html.escape(start['query'])} &rarr; {html.escape(end['query'])}</h1>
<div class="cards">
  <div class="card"><span>Distance</span><b>{result['total_miles']:,} mi</b></div>
  <div class="card"><span>Fuel needed</span><b>{result['total_gallons']:,} gal</b></div>
  <div class="card"><span>Total fuel cost</span><b>${result['total_money_spent_on_fuel_usd']:,}</b></div>
  <div class="card"><span>Fuel stops</span><b>{len(stops)}</b></div>
</div>
{''.join(svg)}
<table><tr><th>#</th><th>Truckstop</th><th>Location</th><th>Mile</th><th>$/gal</th><th>Gallons</th><th>Cost</th></tr>{rows}</table>
<p class="note">{html.escape(a['note'])} Raw data: add <code>&amp;format=json</code> to the URL.</p>
</div></body></html>"""