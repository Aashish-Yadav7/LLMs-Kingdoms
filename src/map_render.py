"""
Renders the god view as your ACTUAL map image with clickable region hotspots.
Click a continent -> a side panel opens with that kingdom's full exact stats
(you're the spectator/god, so you always see exact numbers for everyone,
regardless of what the kingdoms show each other). A bottom panel is always
visible with Public Conference and Secret Meetings, so you never have to
click anything to see the diplomacy.

No emoji anywhere -- some Windows font builds don't have glyphs for newer
emoji (that's why you saw boxes like a military helmet icon rendering as a
tofu square). Everything here is plain text + CSS-colored badges instead,
which renders identically on every platform.
"""

import base64
import json
from pathlib import Path

MAP_PATH = Path(__file__).parent.parent / "data" / "map.json"
MAP_IMAGE_PATH = Path(__file__).parent.parent / "data" / "world_map.png"

KINGDOM_COLORS = {
    "north": "#3b82f6",
    "east": "#ef4444",
    "south": "#22c55e",
    "west": "#eab308",
    "player_llm": "#a855f7",
    None: "#64748b",
}

# Percentage-based bounding boxes over data/world_map.png (1457x720), matched
# to where each continent actually sits in the image. Tweak these if a box
# doesn't line up with the landmass on your screen -- they're eyeballed
# percentages, not pixel-perfect.
CONTINENT_HOTSPOTS = {
    "north":      {"left": 0,  "top": 0,  "width": 22, "height": 45},
    "east":       {"left": 37, "top": 0,  "width": 28, "height": 24},
    "south":      {"left": 60, "top": 26, "width": 20, "height": 30},
    "west":       {"left": 79, "top": 0,  "width": 21, "height": 56},
    "south_pole": {"left": 35, "top": 68, "width": 28, "height": 32},
}

UNIT_LABELS = {
    "infantry": "INF", "artillery": "ART", "armored_vehicle": "ARM",
    "main_battle_tank": "MBT", "rocket_artillery": "RKT", "fighter_jet": "JET",
    "guided_missile": "GMS", "destroyer": "DES",
}


def render_map_html(game_state) -> str:
    world = json.loads(MAP_PATH.read_text())

    # Embed the map image directly as base64 -- this makes the HTML file
    # fully self-contained, so it renders correctly no matter which folder
    # you open/serve it from (double-click, or `python -m http.server` run
    # from any directory). No external file path to break.
    map_image_b64 = base64.b64encode(MAP_IMAGE_PATH.read_bytes()).decode("ascii")
    map_image_data_uri = f"data:image/png;base64,{map_image_b64}"

    # Build full exact data for every kingdom -- you're the spectator, you
    # always get the real numbers, not the noisy version kingdoms show each other.
    kingdom_data = {}
    for kid, k in game_state.kingdoms.items():
        cont = world["continents"][k.home_continent]
        provinces = []
        for prov in cont["provinces"]:
            units_here = k.unit_positions.get(prov["id"], {})
            provinces.append({
                "name": prov["name"],
                "terrain": prov["terrain"].replace("_", " ").title(),
                "units": {UNIT_LABELS.get(u, u): c for u, c in units_here.items() if c > 0},
            })
        kingdom_data[kid] = {
            "name": k.name,
            "continent": cont["display_name"],
            "color": KINGDOM_COLORS.get(kid, "#64748b"),
            "treasury": f"${k.treasury:,.0f}",
            "population": f"{k.population:,}",
            "tax_rate": f"{k.tax_rate:.0%}",
            "total_resources": f"{sum(k.resources.values()):,}",
            "resources": k.resources,
            "unlocked_tech": sorted(k.unlocked_tech),
            "researching": k.researching or "(none)",
            "alliances": k.alliances or ["(none)"],
            "at_war_with": k.at_war_with or ["(none)"],
            "provinces": provinces,
        }

    hotspot_divs = []
    label_divs = []
    for cont_id, box in CONTINENT_HOTSPOTS.items():
        owner_kid = world["continents"][cont_id]["owner"]
        color = KINGDOM_COLORS.get(owner_kid, "#64748b")
        name = game_state.kingdoms[owner_kid].name
        hotspot_divs.append(f"""
        <div class="hotspot" style="left:{box['left']}%; top:{box['top']}%; width:{box['width']}%; height:{box['height']}%; border-color:{color};"
             onclick="showKingdom('{owner_kid}')" title="{name}"></div>
        """)
        label_divs.append(f"""
        <div class="hotspot-label" style="left:{box['left']}%; top:{max(box['top']-3, 0)}%; color:{color};">{name}</div>
        """)

    island_chips = "".join(
        f"<span class='island-chip'>{isle['name']}</span>"
        for isle in world["unclaimed_islands"]
    )

    conference_html = "".join(
        f"<div class='msg'><b style=\"color:{KINGDOM_COLORS.get(m['from'], '#fff')}\">{m['name']}:</b> {m['message']}</div>"
        for m in game_state.conference_log
    ) or "<div class='empty'>No public messages this turn.</div>"

    secret_html = ""
    for pair_key, exchange in game_state.secret_meeting_log.items():
        ids = pair_key.split("|")
        names = [game_state.kingdoms[i].name for i in ids]
        secret_html += f"<div class='secret-block'><div class='secret-title'>[SECRET] {names[0]} <-> {names[1]} (hidden from other kingdoms)</div>"
        for m in exchange:
            speaker = game_state.kingdoms[m["from"]].name
            secret_html += f"<div class='msg'><b>{speaker}:</b> {m['message']}</div>"
        secret_html += "</div>"
    if not secret_html:
        secret_html = "<div class='empty'>No secret meetings this turn.</div>"

    legend_html = "".join(
        f"<span class='legend-item'><span class='swatch' style='background:{KINGDOM_COLORS[kid]}'></span>{k.name}</span>"
        for kid, k in game_state.kingdoms.items()
    )

    kingdom_json = json.dumps(kingdom_data)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Kingdoms AI -- Turn {game_state.turn}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ background:#0f172a; color:#e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; margin:0; padding:0; }}
  .topbar {{ padding:16px 24px; }}
  h1 {{ margin:0 0 8px 0; font-size:22px; }}
  .legend-item {{ margin-right:16px; font-size:13px; }}
  .swatch {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:6px; vertical-align:middle; }}

  .map-wrap {{ position:relative; width:100%; max-width:1457px; margin:0 auto; }}
  .map-wrap img {{ width:100%; display:block; }}
  .hotspot {{ position:absolute; border:2px dashed; border-radius:6px; cursor:pointer; background:rgba(255,255,255,0.02); transition: background 0.15s; }}
  .hotspot:hover {{ background:rgba(255,255,255,0.14); }}
  .hotspot-label {{ position:absolute; font-weight:700; font-size:13px; text-shadow: 0 1px 3px #000; pointer-events:none; }}

  .islands-bar {{ padding:12px 24px; font-size:13px; color:#94a3b8; }}
  .island-chip {{ display:inline-block; border:1px solid #475569; border-radius:5px; padding:3px 8px; margin:2px; }}

  #kingdom-panel {{
    position:fixed; top:0; right:-420px; width:400px; height:100%; background:#1e293b;
    box-shadow:-4px 0 20px rgba(0,0,0,0.5); padding:20px; overflow-y:auto; transition:right 0.25s;
    z-index:50; border-left:3px solid #475569;
  }}
  #kingdom-panel.open {{ right:0; }}
  #kingdom-panel h2 {{ margin-top:0; }}
  .close-btn {{ float:right; cursor:pointer; font-size:20px; color:#94a3b8; }}
  .stat-row {{ display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #334155; font-size:13px; }}
  .stat-label {{ color:#94a3b8; }}
  .province-card {{ background:#0f172a; border:1px solid #334155; border-radius:6px; padding:8px; margin-top:8px; }}
  .province-card .pname {{ font-weight:600; font-size:13px; }}
  .province-card .pterrain {{ color:#94a3b8; font-size:11px; }}
  .unit-badge {{ display:inline-block; background:#334155; border-radius:4px; padding:2px 6px; font-size:11px; margin:3px 3px 0 0; }}
  .empty {{ color:#64748b; font-style:italic; font-size:13px; }}
  .resource-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:4px; font-size:12px; margin-top:6px; }}

  .bottom-panel {{
    background:#1e293b; border-top:2px solid #334155; padding:16px 24px;
    max-height:280px; overflow-y:auto; margin-top:20px;
  }}
  .bottom-panel h3 {{ margin:0 0 8px 0; font-size:15px; }}
  .msg {{ padding:5px 0; border-bottom:1px solid #334155; font-size:13px; }}
  .secret-block {{ background:#312e1e; border:1px solid #a16207; border-radius:6px; padding:8px; margin-bottom:8px; }}
  .secret-title {{ font-weight:600; color:#facc15; margin-bottom:4px; font-size:12px; }}
</style>
</head>
<body>
  <div class="topbar">
    <h1>Kingdoms AI -- Turn {game_state.turn} (God View)</h1>
    <div>{legend_html}</div>
  </div>

  <div class="map-wrap">
    <img src="{map_image_data_uri}" alt="world map">
    {''.join(hotspot_divs)}
    {''.join(label_divs)}
  </div>

  <div class="islands-bar">
    <b>Unclaimed / Contested Islands:</b> {island_chips}
  </div>

  <div id="kingdom-panel">
    <span class="close-btn" onclick="closePanel()">&times;</span>
    <div id="panel-content"></div>
  </div>

  <div class="bottom-panel">
    <h3>Public Conference</h3>
    {conference_html}
    <h3 style="margin-top:16px;">Secret Meetings (only you see all of these)</h3>
    {secret_html}
  </div>

  <script>
    const KINGDOM_DATA = {kingdom_json};

    function showKingdom(kid) {{
      const d = KINGDOM_DATA[kid];
      let provincesHtml = d.provinces.map(p => {{
        let unitsHtml = Object.keys(p.units).length
          ? Object.entries(p.units).map(([u,c]) => `<span class="unit-badge">${{u}} x${{c}}</span>`).join('')
          : '<span class="empty">no units stationed</span>';
        return `<div class="province-card">
                  <div class="pname">${{p.name}}</div>
                  <div class="pterrain">${{p.terrain}}</div>
                  <div>${{unitsHtml}}</div>
                </div>`;
      }}).join('');

      let resourcesHtml = Object.entries(d.resources).map(([r,q]) =>
        `<div>${{r.replace(/_/g,' ')}}: <b>${{q.toLocaleString()}}</b></div>`
      ).join('');

      document.getElementById('panel-content').innerHTML = `
        <h2 style="color:${{d.color}}">${{d.name}}</h2>
        <div style="color:#94a3b8; margin-bottom:12px;">${{d.continent}}</div>
        <div class="stat-row"><span class="stat-label">Treasury</span><span>${{d.treasury}}</span></div>
        <div class="stat-row"><span class="stat-label">Population</span><span>${{d.population}}</span></div>
        <div class="stat-row"><span class="stat-label">Tax rate</span><span>${{d.tax_rate}}</span></div>
        <div class="stat-row"><span class="stat-label">Total resources</span><span>${{d.total_resources}}</span></div>
        <div class="stat-row"><span class="stat-label">Researching</span><span>${{d.researching}}</span></div>
        <div class="stat-row"><span class="stat-label">Tech unlocked</span><span>${{d.unlocked_tech.length}}</span></div>
        <div class="stat-row"><span class="stat-label">At war with</span><span>${{d.at_war_with.join(', ')}}</span></div>
        <h3 style="margin-top:16px; margin-bottom:4px;">Resources</h3>
        <div class="resource-grid">${{resourcesHtml}}</div>
        <h3 style="margin-top:16px; margin-bottom:4px;">Provinces & Deployed Units</h3>
        ${{provincesHtml}}
      `;
      document.getElementById('kingdom-panel').classList.add('open');
    }}

    function closePanel() {{
      document.getElementById('kingdom-panel').classList.remove('open');
    }}
  </script>
</body>
</html>"""