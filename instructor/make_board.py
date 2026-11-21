#!/usr/bin/env python3
"""make_board.py — INSTRUCTOR ONLY. Mint a Pac-Man League board from a seed.

  python make_board.py --seed 303 --out boards_hidden/hidden3.txt        # 15 x 21, the league size
  python make_board.py --seed 303 --show                                  # print it, do not save

Rows and columns must be odd (the maze mirrors left-right around the middle column).
The maze is a seeded perfect maze with loops added and dead ends removed, so it plays like
an arcade maze: corridors, loops, few traps. Pac-Man starts in the top-left corner, the
ghost in the bottom-right corner; every other floor cell has food.
"""
import argparse
import collections
import random
import sys


def generate(rows, cols, seed, loops=0.30, max_dead_ends=2):
    if rows % 2 == 0 or cols % 2 == 0:
        raise SystemExit("rows and cols must be odd")
    rng = random.Random(seed)
    mid = cols // 2
    # the left half including the middle column: node lattice at odd coordinates
    half_cols = mid + 1                                   # columns 0..mid
    wall = [[True] * cols for _ in range(rows)]
    nodes = [(r, c) for r in range(1, rows - 1, 2) for c in range(1, half_cols, 2)]
    node_set = set(nodes)

    def carve(r, c):
        wall[r][c] = False

    # perfect maze on the half lattice (recursive backtracker)
    start = nodes[0]
    carve(*start)
    stack = [start]
    seen = {start}
    while stack:
        r, c = stack[-1]
        options = [(r + dr, c + dc, r + dr // 2, c + dc // 2) for dr, dc in ((-2, 0), (2, 0), (0, 2), (0, -2))
                   if (r + dr, c + dc) in node_set and (r + dr, c + dc) not in seen]
        if not options:
            stack.pop(); continue
        nr, nc, wr, wc = rng.choice(options)
        carve(wr, wc); carve(nr, nc)
        seen.add((nr, nc)); stack.append((nr, nc))

    # add loops: open a fraction of the walls that separate two adjacent nodes
    between = [(r, c) for (r, c) in
               [(r, c + 1) for (r, c) in nodes if (r, c + 2) in node_set] +
               [(r + 1, c) for (r, c) in nodes if (r + 2, c) in node_set]
               if wall[r][c]]
    rng.shuffle(between)
    for (r, c) in between[: int(len(between) * loops)]:
        carve(r, c)

    # remove dead ends (open one more neighbour of each dead-end node)
    def neighbours_open(r, c):
        return [(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, 1), (0, -1)) if not wall[r + dr][c + dc]]

    for _ in range(200):
        dead = [(r, c) for (r, c) in nodes if len(neighbours_open(r, c)) == 1]
        if len(dead) <= max_dead_ends:
            break
        r, c = rng.choice(dead)
        closed = [(r + dr // 2, c + dc // 2) for dr, dc in ((-2, 0), (2, 0), (0, 2), (0, -2))
                  if (r + dr, c + dc) in node_set and wall[r + dr // 2][c + dc // 2]]
        if closed:
            carve(*rng.choice(closed))

    # mirror left -> right around the middle column
    for r in range(rows):
        for c in range(mid):
            wall[r][cols - 1 - c] = wall[r][c]
    # crossings between the halves: open the axis at some node rows (at least three)
    axis_rows = [r for r in range(1, rows - 1, 2) if not wall[r][mid - 1]]
    rng.shuffle(axis_rows)
    for r in axis_rows[: max(3, int(len(axis_rows) * 0.35))]:
        wall[r][mid] = False
    # starts: Pac-Man top-left corner, ghost bottom-right corner (both lattice nodes: floor)
    pr, pc = 1, 1
    gr, gc = rows - 2, cols - 2
    grid = [["#" if wall[r][c] else "." for c in range(cols)] for r in range(rows)]
    grid[pr][pc] = "P"; grid[gr][gc] = "G"
    return ["".join(row) for row in grid]


def stats(lines):
    rows, cols = len(lines), len(lines[0])
    walls = {(r, c) for r in range(rows) for c in range(cols) if lines[r][c] == "#"}
    floor = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in walls]
    p = next((r, c) for r in range(rows) for c in range(cols) if lines[r][c] == "P")
    seen = {p}; q = collections.deque([p])
    while q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, 1), (0, -1)):
            n = (r + dr, c + dc)
            if n not in walls and n not in seen and 0 <= n[0] < rows and 0 <= n[1] < cols:
                seen.add(n); q.append(n)
    dead = sum(1 for (r, c) in floor if sum((r + dr, c + dc) in walls for dr, dc in ((-1, 0), (1, 0), (0, 1), (0, -1))) == 3)
    return {"rows": rows, "cols": cols, "floor": len(floor), "food": sum(l.count(".") for l in lines),
            "dead_ends": dead, "connected": len(seen) == len(floor)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=15)
    ap.add_argument("--cols", type=int, default=21)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--loops", type=float, default=0.30, help="fraction of extra walls to open (0.2 sparse .. 0.5 open)")
    ap.add_argument("--dead-ends", type=int, default=2, help="dead ends to leave")
    ap.add_argument("--out")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)
    lines = generate(args.rows, args.cols, args.seed, args.loops, args.dead_ends)
    st = stats(lines)
    if not st["connected"]:
        print("not connected — try another seed", file=sys.stderr); return 1
    if args.show or not args.out:
        print("\n".join(lines))
    print(st, file=sys.stderr)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("saved", args.out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
