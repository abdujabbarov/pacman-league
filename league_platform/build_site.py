#!/usr/bin/env python3
"""build_site.py — turns results/ into the students' replay site (GitHub Pages, ../docs).

  python build_site.py            # writes ../docs/data/ ; ../docs/index.html is the viewer

Only game data goes out: boards, who played whom, results, and the moves of every game.
No agent code, no reports, nothing from private/. Per-move timings are dropped.

docs/data/catalog.json            boards, players, every game's result
docs/data/games/<board>/<pacman>__<ghost>.json   the moves:
    [tick, side (0 = Pac-Man, 1 = ghost), move, row, col, ate, sat_out, fault or 0]
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import results  # noqa: E402
from pacman_engine import Board  # noqa: E402

DOCS = os.path.normpath(os.path.join(HERE, "..", "docs"))


def clean_fault(f):
    if not f:
        return 0
    return re.sub(r":\s*[\d.]+\s*ms", "", str(f))       # "too slow: 119 ms" -> "too slow"


def main():
    data = os.path.join(DOCS, "data")
    shutil.rmtree(data, ignore_errors=True)
    os.makedirs(data)
    boards = results.boards()
    players = sorted(results.players())
    on_site = set(players) | set(results.HOUSE)
    out_boards = []
    for name, path in boards.items():
        b = Board.load(path)
        out_boards.append({"name": name, "label": results.board_label(name), "kind": results.board_kind(name),
                           "rows": b.rows, "cols": b.cols,
                           "walls": sorted(list(x) for x in b.walls if 0 <= x[0] < b.rows and 0 <= x[1] < b.cols),
                           "food": sorted(list(x) for x in b.food), "pacman": list(b.pacman_start), "ghost": list(b.ghost_start)})
    games = []
    for g in sorted(results.load().values(), key=lambda g: (g["board"], g["pacman"], g["ghost"])):
        if g["board"] not in boards or g["pacman"] not in on_site or g["ghost"] not in on_site or not g.get("replay"):
            continue
        src = os.path.join(results.REPLAYS, g["replay"])
        if not os.path.exists(src):
            continue
        with open(src, encoding="utf-8") as f:
            rep = json.load(f)
        turns = [[e["tick"], 0 if e["who"] == "pacman" else 1, e.get("move") or "", e["to"][0], e["to"][1],
                  1 if e.get("ate") else 0, 1 if e.get("skipped") else 0, clean_fault(e.get("fault"))] for e in rep["turns"]]
        rel = f"games/{g['board']}/{g['pacman']}__{g['ghost']}.json"
        os.makedirs(os.path.join(data, "games", g["board"]), exist_ok=True)
        with open(os.path.join(data, rel), "w", encoding="utf-8") as f:
            json.dump({"turns": turns, "max_ticks": rep["rules"]["max_ticks"]}, f, separators=(",", ":"))
        games.append({"pacman": g["pacman"], "ghost": g["ghost"], "board": g["board"], "outcome": g["outcome"],
                      "pacman_score": g["pacman_score"], "ghost_score": g["ghost_score"], "eaten": g["eaten"],
                      "total": g["total"], "ticks": g["ticks"], "faults": [g["faults_pacman"], g["faults_ghost"]], "file": rel})
    catalog = {"boards": out_boards,
               "players": [{"name": p, "kind": results.kind_of(p)} for p in players],
               "house": {h: s for h, s in results.HOUSE.items()},
               "games": games}
    with open(os.path.join(data, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, separators=(",", ":"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print(f"site data: {len(games)} games on {len(out_boards)} boards, {len(players)} players -> {data}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
