"""
A real 2D grid representation of the world, laid out to mirror the uploaded
map image's proportions. Each cell is one tile with a terrain type and,
if on land, a continent id + province id. This is the foundation for future
adjacency/movement/combat logic (e.g. "can Kingdom A's army reach province X
this turn" becomes a pathfinding question over this grid instead of an
abstract "kingdom vs kingdom" fight).

Grid is GRID_WIDTH x GRID_HEIGHT cells. Continent placement below is
approximated from the map image's layout (top-left / top-center / top-right /
far-right-edge continents, mid-ocean islands, south polar landmass).
"""

import json
import random
from pathlib import Path

from src.map import build_world_resources

GRID_WIDTH = 60
GRID_HEIGHT = 30

# Approximate bounding boxes (col_start, col_end, row_start, row_end) based on
# the map image, in a 60x30 grid. Tune these if you want tighter/looser fit
# once we overlay the actual image.
CONTINENT_BOUNDS = {
    "north":     (0, 13, 0, 13),    # top-left
    "east":      (22, 39, 0, 9),    # top-center
    "south":     (35, 46, 8, 17),   # top-right main body
    "west":      (49, 60, 0, 15),   # far-right edge peninsula
    "south_pole": (20, 40, 22, 30), # bottom polar continent
}

ISLAND_POSITIONS = {
    "isle_1": (16, 5), "isle_2": (17, 15), "isle_3": (44, 14),
    "isle_4": (46, 19), "isle_5": (24, 19), "isle_6": (55, 24), "isle_7": (56, 25),
}


def build_grid(rng_seed: int = 42) -> list:
    """
    Returns a GRID_HEIGHT x GRID_WIDTH nested list of cell dicts:
    {"terrain": str, "continent": str|None, "province": str|None}
    Ocean by default; land cells filled in per continent bounding box, with
    terrain sampled from that continent's province list so terrain diversity
    (desert/grassland/forest/hills/mountain/tundra/icecap/coastal) shows up
    spatially, not just as a flat per-continent tag.
    """
    random.seed(rng_seed)
    world = json.loads((Path(__file__).parent.parent / "data" / "map.json").read_text())

    grid = [[{"terrain": "ocean", "continent": None, "province": None} for _ in range(GRID_WIDTH)]
            for _ in range(GRID_HEIGHT)]

    for cont_id, (c0, c1, r0, r1) in CONTINENT_BOUNDS.items():
        provinces = world["continents"][cont_id]["provinces"]
        for r in range(r0, min(r1, GRID_HEIGHT)):
            for c in range(c0, min(c1, GRID_WIDTH)):
                # ~70% of the bounding box is land, rest stays ocean/coastline gaps
                if random.random() < 0.7:
                    prov = random.choice(provinces)
                    grid[r][c] = {
                        "terrain": prov["terrain"],
                        "continent": cont_id,
                        "province": prov["id"],
                    }

    for isle_id, (c, r) in ISLAND_POSITIONS.items():
        if 0 <= r < GRID_HEIGHT and 0 <= c < GRID_WIDTH:
            grid[r][c] = {"terrain": "island", "continent": None, "province": isle_id}

    return grid


def render_ascii(grid: list) -> str:
    """Quick-and-dirty ASCII view for debugging/sanity-checking the layout."""
    symbols = {
        "ocean": "~", "desert": "d", "grassland": "g", "forest": "f",
        "evergreen_forest": "F", "hills": "h", "mountain": "^", "tundra": "t",
        "coastal": "c", "icecap": "I", "volcanic_tundra": "v", "island": "o",
    }
    lines = []
    for row in grid:
        lines.append("".join(symbols.get(cell["terrain"], "?") for cell in row))
    return "\n".join(lines)


def save_grid(path: str = "data/grid.json", rng_seed: int = 42):
    grid = build_grid(rng_seed)
    Path(path).write_text(json.dumps(grid), encoding="utf-8")
    return grid


if __name__ == "__main__":
    g = build_grid()
    print(render_ascii(g))
