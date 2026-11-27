#!/usr/bin/env python3
"""results.py — the game store, the ranking and "play all games".

  python results.py play                 # play every missing/outdated game on all five boards
  python results.py play --force         # replay everything
  python results.py table                # print the ranking (test boards) to the terminal
  python results.py table --boards all   # ... over all five boards
  python results.py import private/battle_with_nerd/replays   # adopt already-played replays

Store: results/games.json (one record per Pac-Man / ghost / board — the LATEST game counts)
and results/replays/<pacman>__<ghost>__<board>.json. Every record keeps a hash of both agent
files, so "play" only re-plays a game when an agent changed or the game is missing.

Who plays whom ("play all"), on every board:
  * every player's Pac-Man against every player's ghost, its OWN ghost included
  * every player's Pac-Man against random_ghost and baseline_ghost
  * baseline_pacman against every player's ghost
Players are the files in agents/ (students, plus agent_nerd.py tagged "instructor").

Ranking (same rule as the league, instructor/league.py):
  pac_avg   = mean Pac-Man score against every OTHER player's ghost and the random ghost
  ghost_avg = mean ghost score against every OTHER player's Pac-Man
  league    = (pac_avg + ghost_avg) / 2; ties broken by pac_avg, then name
Games against your own ghost are played and shown (matrix diagonal) but never counted.
The instructor's agent plays everyone and its games count for the students, but it is not ranked.
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(HERE, "agents")
BOARDS = os.path.join(HERE, "boards")
STORE = os.path.join(HERE, "results")
REPLAYS = os.path.join(STORE, "replays")
GAMES = os.path.join(STORE, "games.json")

HOUSE = {"baseline_pacman": "pacman", "baseline_ghost": "ghost", "random_ghost": "ghost"}
INSTRUCTOR = {"nerd"}
LEAGUE_TIME_LIMIT = 0.1
GAME_TIMEOUT = 240                      # seconds before a game counts as "hung"

_lock = threading.RLock()


# ------------------------------------------------------------------------------ catalogue

def owner_of(path_or_name):
    name = os.path.splitext(os.path.basename(path_or_name))[0]
    return name[len("agent_"):] if name.startswith("agent_") else name


def kind_of(owner):
    if owner in HOUSE:
        return "house"
    if owner in INSTRUCTOR:
        return "instructor"
    return "student"


def players():
    """owner -> path, for every agent in agents/ (students + instructor)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(AGENTS, "agent_*.py"))):
        o = owner_of(p)
        if o != "template":
            out[o] = p
    return out


def house():
    return {h: os.path.join(HERE, h + ".py") for h in HOUSE if os.path.exists(os.path.join(HERE, h + ".py"))}


def path_of(owner):
    return players().get(owner) or house().get(owner)


def boards():
    """name -> path: training boards (practice*), then the round-1 test boards (hidden*), then the
    round-2 test boards (new*)."""
    found = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(BOARDS, "*.txt"))}
    return dict(sorted(found.items(), key=lambda kv: (KIND_ORDER.index(board_kind(kv[0])), kv[0])))


KIND_ORDER = ["training", "test", "new"]
KIND_LABEL = {"training": "Training ", "test": "Test ", "new": "New test "}


def board_kind(name):
    return "test" if name.startswith("hidden") else "new" if name.startswith("new") else "training"


def board_label(name):
    digits = "".join(ch for ch in name if ch.isdigit())
    return KIND_LABEL[board_kind(name)] + (digits or name)


def student_of(owner):
    """erbol_old / erbol_new -> erbol (round 2: the suffix says which submission is playing)."""
    for suffix in ("_old", "_new"):
        if owner.endswith(suffix):
            return owner[: -len(suffix)]
    return owner


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:12]


# ---------------------------------------------------------------------------------- store

def load():
    if not os.path.exists(GAMES):
        return {}
    with open(GAMES, encoding="utf-8") as f:
        return json.load(f)


def _save(games):
    os.makedirs(STORE, exist_ok=True)
    tmp = GAMES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=0, sort_keys=True)
    os.replace(tmp, GAMES)


def gkey(pac, ghost, board):
    return f"{pac}|{ghost}|{board}"


def replay_name(pac, ghost, board):
    return f"{pac}__{ghost}__{board}.json"


def record(replay, pac, ghost, board, pac_hash, ghost_hash, source):
    """Store one finished game (replay = Game.replay() dict). The latest game for a pairing wins."""
    r = replay["result"]
    replay["meta"]["pacman"], replay["meta"]["ghost"] = pac, ghost
    replay["result"]["pacman"], replay["result"]["ghost"] = pac, ghost
    os.makedirs(REPLAYS, exist_ok=True)
    rfile = replay_name(pac, ghost, board)
    with open(os.path.join(REPLAYS, rfile), "w", encoding="utf-8") as f:
        json.dump(replay, f)
    rec = {"pacman": pac, "ghost": ghost, "board": board, "outcome": r["outcome"],
           "pacman_score": r["pacman_score"], "ghost_score": r["ghost_score"], "eaten": r["eaten"],
           "total": r["total"], "ticks": r["ticks"], "faults_pacman": r["faults"]["pacman"],
           "faults_ghost": r["faults"]["ghost"], "pac_hash": pac_hash, "ghost_hash": ghost_hash,
           "source": source, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "replay": rfile}
    with _lock:
        games = load()
        games[gkey(pac, ghost, board)] = rec
        _save(games)
    return rec


def schedule():
    """Every game "play all" should have: (pacman, ghost, board)."""
    ps, hs, bs = sorted(players()), house(), boards()
    out = []
    for b in bs:
        for p in ps:
            for g in ps:
                out.append((p, g, b))
            for g in ("random_ghost", "baseline_ghost"):
                if g in hs:
                    out.append((p, g, b))
        if "baseline_pacman" in hs:
            for g in ps:
                out.append(("baseline_pacman", g, b))
    return out


def is_current(rec, pac, ghost):
    pp, gp = path_of(pac), path_of(ghost)
    return bool(rec and pp and gp and rec.get("pac_hash") == file_hash(pp) and rec.get("ghost_hash") == file_hash(gp))


def missing(force=False, scope="all"):
    games = load()
    bs = set(scope_boards(scope))
    return [(p, g, b) for p, g, b in schedule()
            if b in bs and (force or not is_current(games.get(gkey(p, g, b)), p, g))]


def play_one(pac, ghost, board):
    """Plays one game in a fresh process (like the league) and stores it."""
    pp, gp, bp = path_of(pac), path_of(ghost), boards()[board]
    ph, gh = file_hash(pp), file_hash(gp)
    os.makedirs(REPLAYS, exist_ok=True)
    tmp = os.path.join(REPLAYS, f".tmp_{os.getpid()}_{threading.get_ident()}.json")
    cmd = [sys.executable, os.path.join(HERE, "play.py"), "--pacman", pp, "--ghost", gp, "--board", bp,
           "--json", "--record", tmp, "--time-limit", str(LEAGUE_TIME_LIMIT)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=GAME_TIMEOUT, cwd=HERE)
        ok = p.returncode == 0 and os.path.exists(tmp)
    except subprocess.TimeoutExpired:
        ok = False
    if not ok:
        rec = {"pacman": pac, "ghost": ghost, "board": board, "outcome": "crash", "pacman_score": 0.0,
               "ghost_score": 0.0, "eaten": 0, "total": 0, "ticks": 0, "faults_pacman": 0, "faults_ghost": 0,
               "pac_hash": ph, "ghost_hash": gh, "source": "play-all", "when": time.strftime("%Y-%m-%d %H:%M:%S"),
               "replay": None}
        with _lock:
            games = load()
            games[gkey(pac, ghost, board)] = rec
            _save(games)
        return rec
    with open(tmp, encoding="utf-8") as f:
        replay = json.load(f)
    os.remove(tmp)
    return record(replay, pac, ghost, board, ph, gh, "play-all")


def play_all(force=False, progress=None, stop=None, scope="all", parallel=1):
    """Plays the missing games, one at a time by default (on a laptop parallel games pushed agents
    past 100 ms). parallel=N plays N games at once, one board at a time; check the faults afterwards."""
    todo = missing(force, scope)
    if progress:
        progress(0, len(todo), None)
    if parallel <= 1:
        for i, (p, g, b) in enumerate(todo):
            if stop and stop():
                break
            rec = play_one(p, g, b)
            if progress:
                progress(i + 1, len(todo), rec)
        return len(todo)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    done = 0
    for board in dict.fromkeys(b for _, _, b in todo):
        if stop and stop():
            break
        with ThreadPoolExecutor(parallel) as pool:
            for fut in as_completed([pool.submit(play_one, p, g, b) for p, g, b in todo if b == board]):
                done += 1
                if progress:
                    progress(done, len(todo), fut.result())
    return len(todo)


def import_replays(folder, source="import"):
    """Adopt replays played elsewhere (e.g. private/battle_with_nerd/replays). They are stored with
    the hashes of the CURRENT agent files, so only import games played with these same files."""
    n = 0
    for p in sorted(glob.glob(os.path.join(folder, "*__*__*.json"))):
        pac, ghost, board = os.path.splitext(os.path.basename(p))[0].split("__")
        pp, gp = path_of(pac), path_of(ghost)
        if not pp or not gp or board not in boards():
            continue
        with open(p, encoding="utf-8") as f:
            replay = json.load(f)
        record(replay, pac, ghost, board, file_hash(pp), file_hash(gp), source)
        n += 1
    return n


# -------------------------------------------------------------------------------- ranking

def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def scope_boards(scope):
    bs = list(boards())
    if scope in (None, "", "test"):
        return [b for b in bs if board_kind(b) == "test"]
    if scope in ("training", "new"):
        return [b for b in bs if board_kind(b) == scope]
    if scope == "all":
        return bs
    return [b for b in bs if b == scope]


def ranking(scope="test"):
    """Ranking + Pac-Man x ghost matrix over the boards in scope."""
    bs = scope_boards(scope)
    ps = sorted(players())
    games = [g for g in load().values() if g["board"] in bs]
    by = {}
    for g in games:
        by.setdefault((g["pacman"], g["ghost"]), []).append(g)

    rows = []
    for o in ps:
        others = [x for x in ps if student_of(x) != student_of(o)]    # never its own old/new version
        pg = [g for x in others + ["random_ghost"] for g in by.get((o, x), [])]
        gg = [g for x in others for g in by.get((x, o), [])]
        pa, ga = _mean(g["pacman_score"] for g in pg), _mean(g["ghost_score"] for g in gg)
        league = (pa + ga) / 2 if pa is not None and ga is not None else None
        hp = _mean(g["pacman_score"] for x in ("baseline_ghost", "random_ghost") for g in by.get((o, x), []))
        hg = _mean(g["ghost_score"] for g in by.get(("baseline_pacman", o), []))
        rows.append({"owner": o, "kind": kind_of(o), "pac_avg": pa, "ghost_avg": ga, "league": league,
                     "pac_games": len(pg), "ghost_games": len(gg),
                     "pac_expected": len(bs) * len(others + ["random_ghost"]), "ghost_expected": len(bs) * len(others),
                     "house_pac": hp, "house_ghost": hg,
                     "faults": sum(g["faults_pacman"] for g in pg) + sum(g["faults_ghost"] for g in gg)})
    rows.sort(key=lambda r: (-(r["league"] if r["league"] is not None else -1),
                             -(r["pac_avg"] if r["pac_avg"] is not None else -1), r["owner"]))
    rank, n = 0, sum(1 for r in rows if r["kind"] == "student")
    for r in rows:
        r["house_marks"] = r["rank_marks"] = r["marks"] = None
        if r["kind"] == "student":
            rank += 1
            r["rank"] = rank
            if r["league"] is not None:      # league marks out of 5, as in instructor/league.py
                r["house_marks"] = float((r["house_pac"] or 0) > 0.5) + float((r["house_ghost"] or 0) > 0.5)
                r["rank_marks"] = 3.0 if n == 1 else 1 + 2 * (n - rank) / (n - 1)
                r["marks"] = r["house_marks"] + r["rank_marks"]
        else:
            r["rank"] = None

    pac_axis = ps + ["baseline_pacman"]
    ghost_axis = ps + ["baseline_ghost", "random_ghost"]
    cells = {}
    for p in pac_axis:
        for g in ghost_axis:
            lst = by.get((p, g), [])
            if not lst:
                continue
            cells[f"{p}|{g}"] = {"pacman_score": _mean(x["pacman_score"] for x in lst), "n": len(lst),
                                 "games": [{"board": x["board"], "outcome": x["outcome"], "pacman_score": x["pacman_score"],
                                            "eaten": x["eaten"], "total": x["total"], "ticks": x["ticks"]}
                                           for x in sorted(lst, key=lambda x: x["board"])]}
    have = {gkey(x["pacman"], x["ghost"], x["board"]) for x in games}
    due = [gkey(p, g, b) for p, g, b in schedule() if b in bs]
    played, expected = sum(1 for k in due if k in have), len(due)
    return {"scope": scope, "boards": bs, "rows": rows, "pacmen": pac_axis, "ghosts": ghost_axis, "cells": cells,
            "kinds": {o: kind_of(o) for o in set(pac_axis) | set(ghost_axis)}, "played": played, "expected": expected}


def fmt(x):
    return "  -  " if x is None else f"{x:.3f}"


def print_table(scope):
    t = ranking(scope)
    print(f"boards: {', '.join(t['boards'])} - {t['played']}/{t['expected']} games played")
    print(f"{'rank':>4}  {'player':<16} {'pac_avg':>7} {'ghost_avg':>9} {'league':>7}  games P/G")
    for r in t["rows"]:
        rk = str(r["rank"]) if r["rank"] else "-"
        print(f"{rk:>4}  {r['owner']:<16} {fmt(r['pac_avg']):>7} {fmt(r['ghost_avg']):>9} {fmt(r['league']):>7}  "
              f"{r['pac_games']}/{r['pac_expected']} - {r['ghost_games']}/{r['ghost_expected']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("play", help="play every missing or outdated game")
    sp.add_argument("--force", action="store_true", help="replay every game")
    sp.add_argument("--boards", default="all", help="all | test | training | new | <board name>")
    sp.add_argument("--parallel", type=int, default=1, help="games played at once, one board at a time (default 1)")
    st = sub.add_parser("table", help="print the ranking")
    st.add_argument("--boards", default="test", help="test | training | new | all | <board name>")
    si = sub.add_parser("import", help="adopt replays from a folder")
    si.add_argument("folder")
    args = ap.parse_args(argv)
    if args.cmd == "play":
        t0 = time.time()

        def progress(i, n, rec):
            if rec:
                print(f"[{i}/{n}] {rec['pacman']} vs {rec['ghost']} on {rec['board']}: {rec['outcome']} "
                      f"{rec['pacman_score']:.2f}  ({time.time() - t0:.0f}s)", flush=True)
            else:
                print(f"{n} games to play", flush=True)
        play_all(args.force, progress, scope=args.boards, parallel=args.parallel)
    elif args.cmd == "table":
        print_table(args.boards)
    elif args.cmd == "import":
        print(f"imported {import_replays(args.folder)} replays")
    return 0


if __name__ == "__main__":
    sys.exit(main())
