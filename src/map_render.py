"""
God view, rebuilt around ONE persistent file: maps/game.html.

Every turn, a small JSON snapshot of that turn's state (kingdom stats,
conference, secret meetings, island ownership) is saved to
maps/turn_data/turn_N.json. Then ALL snapshots found on disk -- from this
session and any previous one, since games can now resume across sessions --
get bundled into a single self-contained HTML file with a turn selector at
the top. No more juggling separate turn_1.html, turn_2.html, ... tabs.

The map image, hotspot layout, and unit/infrastructure icons are still
embedded directly (base64 for the image, inline SVG for icons) so the whole
thing keeps working with a plain double-click, no server needed.
"""

import base64
import json
from pathlib import Path

MAP_PATH = Path(__file__).parent.parent / "data" / "map.json"
MAP_IMAGE_PATH = Path(__file__).parent.parent / "data" / "world_map.png"
SNAPSHOT_DIR = Path(__file__).parent.parent / "maps" / "turn_data"

KINGDOM_COLORS = {
    "north": "#3b82f6",
    "east": "#ef4444",
    "south": "#22c55e",
    "west": "#eab308",
    "player_llm": "#a855f7",
    None: "#64748b",
}

CONTINENT_HOTSPOTS = {
    "north":      {"left": 0,  "top": 0,  "width": 22, "height": 45},
    "east":       {"left": 37, "top": 0,  "width": 28, "height": 24},
    "south":      {"left": 60, "top": 26, "width": 20, "height": 30},
    "west":       {"left": 79, "top": 0,  "width": 21, "height": 56},
    "south_pole": {"left": 35, "top": 68, "width": 28, "height": 32},
}

UNIT_LABELS = {
    "infantry": "Infantry", "artillery": "Artillery", "armored_vehicle": "Armored Vehicle",
    "main_battle_tank": "Main Battle Tank", "rocket_artillery": "Rocket Artillery",
    "fighter_jet": "Fighter Jet", "guided_missile": "Guided Missile", "destroyer": "Destroyer",
    "aircraft_carrier": "Aircraft Carrier", "aerial_fortress": "Aerial Fortress",
}


def _build_kingdom_data(game_state, world: dict) -> dict:
    province_names = {}
    for cont in world["continents"].values():
        for p in cont["provinces"]:
            province_names[p["id"]] = p["name"]
    for isle in world["unclaimed_islands"]:
        province_names[isle["id"]] = isle["name"]

    kingdom_data = {}
    for kid, k in game_state.kingdoms.items():
        cont = world["continents"][k.home_continent]
        home_province_ids = {p["id"] for p in cont["provinces"]}
        provinces = []
        for prov in cont["provinces"]:
            units_here = k.unit_positions.get(prov["id"], {})
            provinces.append({
                "name": prov["name"],
                "terrain": prov["terrain"].replace("_", " ").title(),
                "units": {u: c for u, c in units_here.items() if c > 0},
            })
        forces_abroad = []
        for prov_id, units_here in k.unit_positions.items():
            if prov_id in home_province_ids:
                continue
            live = {u: c for u, c in units_here.items() if c > 0}
            if live:
                forces_abroad.append({"name": province_names.get(prov_id, prov_id), "units": live})

        infrastructure = []
        if "combustion_engines" in k.unlocked_tech:
            infrastructure.append("motor_transport")
        if "transport_infrastructure" in k.unlocked_tech:
            infrastructure.append("rail_network")
        if "jet_propulsion" in k.unlocked_tech or "aircraft_carrier_program" in k.unlocked_tech:
            infrastructure.append("airport")
        if "petrochemical_refining" in k.unlocked_tech:
            infrastructure.append("refinery")

        kingdom_data[kid] = {
            "name": k.name,
            "continent": cont["display_name"],
            "color": KINGDOM_COLORS.get(kid, "#64748b"),
            "treasury": f"${k.treasury:,.0f}",
            "population": f"{k.population:,}",
            "tax_rate": f"{k.tax_rate:.0%}",
            "stability": f"{k.stability:.0f}/100",
            "total_resources": f"{sum(k.resources.values()):,}",
            "resources": k.resources,
            "unlocked_tech": sorted(k.unlocked_tech),
            "infrastructure": infrastructure,
            "researching": k.researching or "(none)",
            "custom_researching": (
                f"{k.custom_researching['name']} ({k.custom_researching['progress']:.1f}/{k.custom_researching['turns_needed']} turns)"
                if k.custom_researching else "(none)"
            ),
            "custom_projects": [
                f"{p['name']} -- power {p['power_rating']:,.0f} ({p['description']})"
                for p in k.custom_projects
            ] or ["(none yet)"],
            "alliances": k.alliances or ["(none)"],
            "at_war_with": k.at_war_with or ["(none)"],
            "provinces": provinces,
            "forces_abroad": forces_abroad,
        }
    return kingdom_data


def save_turn_snapshot(game_state, out_dir: Path = SNAPSHOT_DIR) -> Path:
    """Call once per turn, right after resolution. Writes a small JSON file
    capturing everything the viewer needs for THIS turn only."""
    world = json.loads(MAP_PATH.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "turn": game_state.turn,
        "kingdoms": _build_kingdom_data(game_state, world),
        "conference": list(game_state.conference_log),
        "secret_meetings": dict(game_state.secret_meeting_log),
        "islands": {
            isle_id: data.get("controlled_by")
            for isle_id, data in game_state.unclaimed_islands.items()
        },
    }
    path = out_dir / f"turn_{game_state.turn}.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


def load_all_snapshots(snapshot_dir: Path = SNAPSHOT_DIR) -> dict:
    """Loads every turn_N.json found (including earlier sessions, since
    games can resume across runs), keyed by turn number."""
    if not snapshot_dir.exists():
        return {}
    snapshots = {}
    for path in snapshot_dir.glob("turn_*.json"):
        try:
            turn_num = int(path.stem.split("_")[-1])
        except ValueError:
            continue
        snapshots[turn_num] = json.loads(path.read_text(encoding="utf-8"))
    return dict(sorted(snapshots.items()))


def render_game_html(all_snapshots: dict) -> str:
    if not all_snapshots:
        return "<html><body>No turns played yet.</body></html>"

    world = json.loads(MAP_PATH.read_text())
    map_image_b64 = base64.b64encode(MAP_IMAGE_PATH.read_bytes()).decode("ascii")
    map_image_data_uri = f"data:image/png;base64,{map_image_b64}"

    latest_turn = max(all_snapshots.keys())
    latest = all_snapshots[latest_turn]

    legend_html = "".join(
        f"<span class='legend-item'><span class='swatch' style='background:{k['color']}'></span>{k['name']}</span>"
        for k in latest["kingdoms"].values()
    )

    hotspot_divs, label_divs = [], []
    for cont_id, box in CONTINENT_HOTSPOTS.items():
        owner_kid = world["continents"][cont_id]["owner"]
        owner = latest["kingdoms"].get(owner_kid, {})
        color = owner.get("color", "#64748b")
        name = owner.get("name", owner_kid)
        hotspot_divs.append(
            f'<div class="hotspot" style="left:{box["left"]}%; top:{box["top"]}%; '
            f'width:{box["width"]}%; height:{box["height"]}%; border-color:{color};" '
            f'onclick="showKingdom(\'{owner_kid}\')" title="{name}"></div>'
        )
        label_divs.append(
            f'<div class="hotspot-label" style="left:{box["left"]}%; top:{max(box["top"]-3, 0)}%; color:{color};">{name}</div>'
        )

    island_names = {isle["id"]: isle["name"] for isle in world["unclaimed_islands"]}

    turn_selector_html = "".join(
        f'<button class="turn-btn" data-turn="{t}" onclick="showTurn({t})">Turn {t}</button>'
        for t in sorted(all_snapshots.keys())
    )

    all_turns_json = json.dumps({str(t): snap for t, snap in all_snapshots.items()})
    island_names_json = json.dumps(island_names)
    kingdom_colors_json = json.dumps(KINGDOM_COLORS)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Kingdoms AI -- Full Game (Turns 1-{latest_turn})</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ background:#0f172a; color:#e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; margin:0; padding:0; }}
  .topbar {{ padding:16px 24px; }}
  h1 {{ margin:0 0 8px 0; font-size:22px; }}
  .legend-item {{ margin-right:16px; font-size:13px; }}
  .swatch {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:6px; vertical-align:middle; }}

  .turn-selector {{ padding:10px 24px; background:#1e293b; display:flex; flex-wrap:wrap; gap:6px; position:sticky; top:0; z-index:60; }}
  .turn-btn {{ background:#334155; color:#e2e8f0; border:none; border-radius:5px; padding:6px 12px; font-size:12px; cursor:pointer; }}
  .turn-btn:hover {{ background:#475569; }}
  .turn-btn.active {{ background:#3b82f6; font-weight:600; }}

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
    z-index:70; border-left:3px solid #475569;
  }}
  #kingdom-panel.open {{ right:0; }}
  #kingdom-panel h2 {{ margin-top:0; }}
  .close-btn {{ float:right; cursor:pointer; font-size:20px; color:#94a3b8; }}
  .stat-row {{ display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #334155; font-size:13px; }}
  .stat-label {{ color:#94a3b8; }}
  .province-card {{ background:#0f172a; border:1px solid #334155; border-radius:6px; padding:8px; margin-top:8px; }}
  .province-card .pname {{ font-weight:600; font-size:13px; }}
  .province-card .pterrain {{ color:#94a3b8; font-size:11px; }}
  .unit-badge {{ display:inline-flex; align-items:center; gap:4px; background:#334155; border-radius:4px; padding:3px 7px 3px 4px; font-size:11px; margin:3px 3px 0 0; }}
  .unit-icon {{ width:18px; height:18px; flex-shrink:0; }}
  .unit-icon.ground {{ animation: march 0.9s steps(2) infinite; }}
  .unit-icon.air {{ animation: fly 2.2s ease-in-out infinite; }}
  .unit-icon.naval {{ animation: bob 2.6s ease-in-out infinite; }}
  @keyframes march {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-1.5px); }} }}
  @keyframes fly {{ 0%,100% {{ transform: translateX(0) translateY(0); }} 50% {{ transform: translateX(2px) translateY(-2px); }} }}
  @keyframes bob {{ 0%,100% {{ transform: translateY(0) rotate(0deg); }} 50% {{ transform: translateY(-1.5px) rotate(-1deg); }} }}
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
    <h1 id="page-title">Kingdoms AI -- Turn {latest_turn} (God View)</h1>
    <div>{legend_html}</div>
  </div>

  <div class="turn-selector" id="turn-selector">{turn_selector_html}</div>

  <div class="map-wrap">
    <img src="{map_image_data_uri}" alt="world map">
    {''.join(hotspot_divs)}
    {''.join(label_divs)}
  </div>

  <div class="islands-bar" id="islands-bar"></div>

  <div id="kingdom-panel">
    <span class="close-btn" onclick="closePanel()">&times;</span>
    <div id="panel-content"></div>
  </div>

  <div class="bottom-panel">
    <h3>Public Conference</h3>
    <div id="conference-content"></div>
    <h3 style="margin-top:16px;">Secret Meetings (only you see all of these)</h3>
    <div id="secret-content"></div>
  </div>

  <script>
    const ALL_TURNS = {all_turns_json};
    const ISLAND_NAMES = {island_names_json};
    const KINGDOM_COLORS = {kingdom_colors_json};
    let currentTurn = "{latest_turn}";
    let openKingdomId = null;

    const UNIT_ICONS = {{
      infantry: {{ cls: "ground", label: "Infantry", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="2.4"/>
        <path d="M12 8c-2.2 0-4 1.8-4 4v3h2v7h4v-7h2v-3c0-2.2-1.8-4-4-4z"/></svg>` }},
      artillery: {{ cls: "ground", label: "Artillery", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="15" width="18" height="4" rx="1"/>
        <rect x="9" y="6" width="10" height="4" rx="1" transform="rotate(-20 9 6)"/>
        <circle cx="7" cy="19" r="2.5"/><circle cx="17" cy="19" r="2.5"/></svg>` }},
      armored_vehicle: {{ cls: "ground", label: "Armored Vehicle", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="9" width="18" height="8" rx="2"/>
        <rect x="8" y="5" width="6" height="5" rx="1"/>
        <circle cx="7" cy="18" r="2"/><circle cx="12" cy="18" r="2"/><circle cx="17" cy="18" r="2"/></svg>` }},
      main_battle_tank: {{ cls: "ground", label: "Main Battle Tank", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="2" y="14" width="20" height="4" rx="2"/>
        <rect x="6" y="8" width="10" height="6" rx="1"/><rect x="13" y="6" width="9" height="2" rx="1"/>
        <circle cx="6" cy="18" r="1.6"/><circle cx="12" cy="18" r="1.6"/><circle cx="18" cy="18" r="1.6"/></svg>` }},
      rocket_artillery: {{ cls: "ground", label: "Rocket Artillery", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="13" width="14" height="5" rx="1"/>
        <rect x="6" y="5" width="2.5" height="8" rx="1" transform="rotate(-15 7 9)"/>
        <rect x="10" y="5" width="2.5" height="8" rx="1" transform="rotate(-15 11 9)"/>
        <circle cx="6" cy="19" r="2"/><circle cx="15" cy="19" r="2"/></svg>` }},
      fighter_jet: {{ cls: "air", label: "Fighter Jet", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2 6 8 3-8 1v4l4 3-4-1-2 4-2-4-4 1 4-3v-4l-8-1 8-3z"/></svg>` }},
      guided_missile: {{ cls: "air", label: "Guided Missile", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c2 3 3 6 3 10v6l-3 3-3-3v-6c0-4 1-7 3-10z"/>
        <path d="M9 14l-4 2 4 1z"/><path d="M15 14l4 2-4 1z"/></svg>` }},
      destroyer: {{ cls: "naval", label: "Destroyer", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 16l2 3h16l2-3-3-2H5z"/>
        <rect x="9" y="7" width="6" height="6" rx="1"/><rect x="11" y="4" width="1.5" height="4"/></svg>` }},
      aircraft_carrier: {{ cls: "naval", label: "Aircraft Carrier", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 16l2 3h18l2-3-3-2H4z"/>
        <rect x="3" y="12.5" width="18" height="1.5"/>
        <rect x="15" y="6" width="5" height="4" rx="1"/><rect x="17" y="3" width="1.5" height="3.5"/></svg>` }},
      aerial_fortress: {{ cls: "air", label: "Aerial Fortress", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="2" y="9" width="20" height="6" rx="2"/>
        <circle cx="5" cy="7" r="1.6"/><circle cx="10" cy="6" r="1.6"/>
        <circle cx="14" cy="6" r="1.6"/><circle cx="19" cy="7" r="1.6"/></svg>` }},
    }};

    const INFRA_ICONS = {{
      motor_transport: {{ cls: "ground", label: "Motor Transport Network", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="11" width="18" height="5" rx="2"/>
        <rect x="6" y="7" width="8" height="5" rx="1"/>
        <circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg>` }},
      rail_network: {{ cls: "ground", label: "Rail Logistics Network", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="5" width="16" height="10" rx="2"/>
        <rect x="6" y="8" width="5" height="4"/><rect x="13" y="8" width="5" height="4"/>
        <circle cx="7" cy="18" r="1.5"/><circle cx="11" cy="18" r="1.5"/>
        <circle cx="15" cy="18" r="1.5"/><circle cx="19" cy="18" r="1.5"/></svg>` }},
      airport: {{ cls: "air", label: "Air Transit Hub", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 14l9-2V4l2-1 2 1v8l9 2v2l-9-1.5V19l3 2v1l-5-1-5 1v-1l3-2v-4.5L2 16z"/></svg>` }},
      refinery: {{ cls: "ground", label: "Petrochemical Refinery", svg: `
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="14" width="18" height="6" rx="1"/>
        <rect x="6" y="9" width="2.5" height="5"/><rect x="11" y="6" width="2.5" height="8"/>
        <rect x="16" y="10" width="2.5" height="4"/><circle cx="7.25" cy="8" r="1.3"/></svg>` }},
    }};

    function renderInfraRow(key) {{
      const meta = INFRA_ICONS[key];
      if (!meta) return '';
      return `<span class="unit-badge">
                <span class="unit-icon ${{meta.cls}}">${{meta.svg}}</span>
                ${{meta.label}}
              </span>`;
    }}

    function renderUnitBadge(u, c, color) {{
      const meta = UNIT_ICONS[u] || {{ cls: "ground", label: u, svg: '' }};
      return `<span class="unit-badge">
                <span class="unit-icon ${{meta.cls}}" style="color:${{color}}">${{meta.svg}}</span>
                ${{meta.label}} x${{c}}
              </span>`;
    }}

    function showKingdom(kid) {{
      openKingdomId = kid;
      const turnData = ALL_TURNS[currentTurn];
      const d = turnData.kingdoms[kid];
      if (!d) return;

      let provincesHtml = d.provinces.map(p => {{
        let unitsHtml = Object.keys(p.units).length
          ? Object.entries(p.units).map(([u,c]) => renderUnitBadge(u, c, d.color)).join('')
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
        <div style="color:#94a3b8; margin-bottom:12px;">${{d.continent}} -- Turn ${{currentTurn}}</div>
        <div class="stat-row"><span class="stat-label">Treasury</span><span>${{d.treasury}}</span></div>
        <div class="stat-row"><span class="stat-label">Population</span><span>${{d.population}}</span></div>
        <div class="stat-row"><span class="stat-label">Tax rate</span><span>${{d.tax_rate}}</span></div>
        <div class="stat-row"><span class="stat-label">Stability</span><span>${{d.stability}}</span></div>
        <div class="stat-row"><span class="stat-label">Total resources</span><span>${{d.total_resources}}</span></div>
        <div class="stat-row"><span class="stat-label">Researching</span><span>${{d.researching}}</span></div>
        <div class="stat-row"><span class="stat-label">Custom project in progress</span><span>${{d.custom_researching}}</span></div>
        <div class="stat-row"><span class="stat-label">Tech unlocked</span><span>${{d.unlocked_tech.length}}</span></div>
        <div class="stat-row"><span class="stat-label">At war with</span><span>${{d.at_war_with.join(', ')}}</span></div>
        <h3 style="margin-top:16px; margin-bottom:4px;">Infrastructure</h3>
        <div>${{d.infrastructure.length ? d.infrastructure.map(renderInfraRow).join('') : '<span class="empty">no infrastructure tech unlocked yet</span>'}}</div>
        <h3 style="margin-top:16px; margin-bottom:4px;">Completed Custom Inventions</h3>
        <div style="font-size:12px;">${{d.custom_projects.map(p => `<div style="padding:4px 0;border-bottom:1px solid #334155;">${{p}}</div>`).join('')}}</div>
        <h3 style="margin-top:16px; margin-bottom:4px;">Resources</h3>
        <div class="resource-grid">${{resourcesHtml}}</div>
        <h3 style="margin-top:16px; margin-bottom:4px;">Provinces & Deployed Units</h3>
        ${{provincesHtml}}
        ${{d.forces_abroad.length ? `
          <h3 style="margin-top:16px; margin-bottom:4px; color:#f87171;">Forces Abroad (invading / staged / claimed)</h3>
          ${{d.forces_abroad.map(f => `
            <div class="province-card" style="border-color:#f87171;">
              <div class="pname">${{f.name}}</div>
              <div>${{Object.entries(f.units).map(([u,c]) => renderUnitBadge(u, c, d.color)).join('')}}</div>
            </div>
          `).join('')}}
        ` : ''}}
      `;
      document.getElementById('kingdom-panel').classList.add('open');
    }}

    function closePanel() {{
      document.getElementById('kingdom-panel').classList.remove('open');
      openKingdomId = null;
    }}

    function renderBottomPanels() {{
      const turnData = ALL_TURNS[currentTurn];

      const conf = turnData.conference || [];
      document.getElementById('conference-content').innerHTML = conf.length
        ? conf.map(m => `<div class="msg"><b style="color:${{KINGDOM_COLORS[m.from] || '#fff'}}">${{m.name}}:</b> ${{m.message}}</div>`).join('')
        : '<div class="empty">No public messages this turn.</div>';

      const secrets = turnData.secret_meetings || {{}};
      const secretKeys = Object.keys(secrets);
      document.getElementById('secret-content').innerHTML = secretKeys.length
        ? secretKeys.map(pairKey => {{
            const ids = pairKey.split('|');
            const names = ids.map(i => (turnData.kingdoms[i] || {{}}).name || i);
            const exchange = secrets[pairKey];
            const msgsHtml = exchange.map(m => {{
              const speakerName = (turnData.kingdoms[m.from] || {{}}).name || m.from;
              return `<div class="msg"><b>${{speakerName}}:</b> ${{m.message}}</div>`;
            }}).join('');
            return `<div class="secret-block">
                      <div class="secret-title">[SECRET] ${{names[0]}} &lt;-&gt; ${{names[1]}} (hidden from other kingdoms)</div>
                      ${{msgsHtml}}
                    </div>`;
          }}).join('')
        : '<div class="empty">No secret meetings this turn.</div>';

      const islands = turnData.islands || {{}};
      document.getElementById('islands-bar').innerHTML = '<b>Unclaimed / Contested Islands:</b> ' +
        Object.entries(ISLAND_NAMES).map(([id, name]) => {{
          const controller = islands[id];
          const color = controller ? (KINGDOM_COLORS[controller] || '#475569') : '#475569';
          const label = controller && turnData.kingdoms[controller] ? `${{name}} (${{turnData.kingdoms[controller].name}})` : name;
          return `<span class="island-chip" style="border-color:${{color}}">${{label}}</span>`;
        }}).join('');
    }}

    function showTurn(t) {{
      currentTurn = String(t);
      document.getElementById('page-title').textContent = `Kingdoms AI -- Turn ${{currentTurn}} (God View)`;
      document.querySelectorAll('.turn-btn').forEach(btn => {{
        btn.classList.toggle('active', btn.dataset.turn === currentTurn);
      }});
      renderBottomPanels();
      if (openKingdomId) showKingdom(openKingdomId);
    }}

    showTurn(currentTurn);
  </script>
</body>
</html>"""
