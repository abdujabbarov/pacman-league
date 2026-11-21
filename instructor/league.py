#!/usr/bin/env python3
"""league.py — INSTRUCTOR ONLY. Runs the Pac-Man League and writes the marking material.

  python league.py                       # agents from ../Submission, boards from boards_hidden, output to league_out
  python league.py --agents ../Submission --boards boards_hidden --out league_out --jobs 4
  python league.py ... --no-check        # skip the per-student checker run (faster)

Games played
  * every student's Pac-Man against every other student's ghost, on every board
  * every student's Pac-Man against the random ghost, on every board      (counts in the league)
  * house checks: Pac-Man vs baseline ghost, ghost vs baseline Pac-Man   (the 2 league marks)
A file that fails the static checks (imports, functions, syntax) is replaced by the house
agents so the league always runs, and is flagged in the table.

Outputs in --out
  league_table.csv / .md / .html     ranks, averages, suggested league marks (2 + 3 scheme)
  games.csv                          one line per game
  replays/*.json + index.json        every game; open with  python arena.py --replays league_out/replays
  report_cards/<owner>.md            one page per student: checker output, results, rank, marks to fill
  checks/<owner>.json                raw checker output on the league boards
"""
import argparse
import concurrent.futures as cf
import csv
import glob
import html
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KIT = os.path.normpath(os.path.join(HERE, "..", "league_platform"))   # engine, play.py, checker, house agents


def owner_of(path):
    name = os.path.splitext(os.path.basename(path))[0]
    return name[len("agent_"):] if name.startswith("agent_") else name


def static_ok(kit, path):
    """Static checks only (syntax, imports, functions, model) through the kit's checker."""
    sys.path.insert(0, kit)
    import check_submission as cs  # noqa: E402
    from pacman_engine import load_agent  # noqa: E402
    rep = cs.Report()
    tree = cs.static_checks(path, rep)
    reasons = [c["text"] for c in rep.data["checks"] if not c["ok"]]
    if tree is None:
        return False, reasons
    try:
        mod = load_agent(path)
    except Exception as e:  # noqa: BLE001
        return False, reasons + [f"does not import: {type(e).__name__}: {e}"]
    missing = [f for f in cs.REQUIRED if not callable(getattr(mod, f, None))]
    if missing:
        reasons.append("missing functions: " + ", ".join(missing))
    if getattr(mod, "OPPONENT_MODEL", None) not in cs.MODELS:
        reasons.append("OPPONENT_MODEL not set to minimax/expectimax")
    return not reasons, reasons


def run_game(kit, pac_path, ghost_path, board_path, replay_path, labels, timeout=240):
    cmd = [sys.executable, os.path.join(kit, "play.py"), "--pacman", pac_path, "--ghost", ghost_path,
           "--board", board_path, "--json", "--record", replay_path]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=kit)
        if p.returncode != 0 or not p.stdout.strip():
            return {"outcome": "crash", "pacman_score": 0.0, "ghost_score": 0.0, "eaten": 0, "total": 0,
                    "ticks": 0, "faults": {"pacman": 0, "ghost": 0}, "error": (p.stderr or "")[-400:], "seconds": time.time() - t0}
        r = json.loads(p.stdout.strip().splitlines()[-1])
        r["seconds"] = round(time.time() - t0, 1)
        # fix labels (play.py labels by file name; we want owners)
        try:
            with open(replay_path, encoding="utf-8") as f:
                rep = json.load(f)
            rep["meta"]["pacman"], rep["meta"]["ghost"] = labels[0], labels[1]
            rep["result"]["pacman"], rep["result"]["ghost"] = labels[0], labels[1]
            with open(replay_path, "w", encoding="utf-8") as f:
                json.dump(rep, f)
        except Exception:  # noqa: BLE001
            pass
        return r
    except subprocess.TimeoutExpired:
        return {"outcome": "hung", "pacman_score": 0.0, "ghost_score": 0.0, "eaten": 0, "total": 0, "ticks": 0,
                "faults": {"pacman": 0, "ghost": 0}, "error": f"no result after {timeout}s", "seconds": timeout}


def run_checker(kit, path, boards_dir, out_json):
    cmd = [sys.executable, os.path.join(kit, "check_submission.py"), path, "--boards", boards_dir, "--json", out_json, "--quiet"]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=kit)
        with open(out_json, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", default=os.path.join(HERE, "..", "Submission"), help="folder with the submitted agent_<surname>.py files (default: ../Submission)")
    ap.add_argument("--boards", default=os.path.join(HERE, "boards_hidden"), help="folder with the league (hidden) boards")
    ap.add_argument("--out", default=os.path.join(HERE, "league_out"))
    ap.add_argument("--kit", default=DEFAULT_KIT, help="the starter kit folder (engine, play.py, house agents)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--house-marks", type=float, default=2.0, help="league marks for beating the house (default 2)")
    ap.add_argument("--rank-marks", type=float, default=3.0, help="league marks by rank, 1st=all, last=1 (default 3)")
    args = ap.parse_args(argv)

    kit = os.path.abspath(args.kit)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.join(out, "replays"), exist_ok=True)
    os.makedirs(os.path.join(out, "report_cards"), exist_ok=True)
    os.makedirs(os.path.join(out, "checks"), exist_ok=True)
    boards = sorted(glob.glob(os.path.join(os.path.abspath(args.boards), "*.txt")))
    files = sorted(glob.glob(os.path.join(os.path.abspath(args.agents), "agent_*.py")))
    if not boards or not files:
        print("need at least one board and one agent_*.py"); return 1
    house = {k: os.path.join(kit, k + ".py") for k in ("baseline_pacman", "baseline_ghost", "random_ghost")}

    # 1. validate
    players = {}
    for f in files:
        owner = owner_of(f)
        ok, reasons = static_ok(kit, f)
        players[owner] = {"file": f, "valid": ok, "reasons": reasons,
                          "pac_file": f if ok else house["baseline_pacman"],
                          "ghost_file": f if ok else house["baseline_ghost"]}
        print(f"{'valid  ' if ok else 'INVALID'} {owner}" + ("" if ok else "  — " + "; ".join(reasons)))
    owners = sorted(players)

    # 2. games
    jobs = []
    def add(pac_owner, ghost_owner, pac_file, ghost_file, kind):
        for b in boards:
            bname = os.path.splitext(os.path.basename(b))[0]
            rp = os.path.join(out, "replays", f"{pac_owner}__{ghost_owner}__{bname}.json")
            jobs.append({"pacman": pac_owner, "ghost": ghost_owner, "board": bname, "kind": kind,
                         "args": (kit, pac_file, ghost_file, b, rp, (pac_owner, ghost_owner)), "file": os.path.basename(rp)})
    for a in owners:
        for b in owners:
            if a != b:
                add(a, b, players[a]["pac_file"], players[b]["ghost_file"], "league")
        add(a, "random_ghost", players[a]["pac_file"], house["random_ghost"], "league")
        add(a, "baseline_ghost", players[a]["pac_file"], house["baseline_ghost"], "house")
        add("baseline_pacman", a, house["baseline_pacman"], players[a]["ghost_file"], "house")
    print(f"{len(jobs)} games on {len(boards)} boards, {args.jobs} in parallel …")
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_game, *j["args"]): j for j in jobs}
        done = 0
        for fut in cf.as_completed(futs):
            j = futs[fut]
            j["result"] = fut.result()
            done += 1
            if done % 20 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} games, {time.time() - t0:.0f}s")

    # 3. aggregate
    for o in owners:
        p = players[o]
        p["pac_games"] = [j for j in jobs if j["kind"] == "league" and j["pacman"] == o]
        p["ghost_games"] = [j for j in jobs if j["kind"] == "league" and j["ghost"] == o]
        p["house_pac"] = [j for j in jobs if j["kind"] == "house" and j["pacman"] == o]
        p["house_pac"] += [j for j in jobs if j["kind"] == "league" and j["pacman"] == o and j["ghost"] == "random_ghost"]
        p["house_ghost"] = [j for j in jobs if j["kind"] == "house" and j["ghost"] == o]
        p["pac_avg"] = mean(j["result"]["pacman_score"] for j in p["pac_games"]) if p["valid"] else 0.0
        p["ghost_avg"] = mean(j["result"]["ghost_score"] for j in p["ghost_games"]) if p["valid"] else 0.0
        p["league"] = (p["pac_avg"] + p["ghost_avg"]) / 2 if p["valid"] else 0.0
        p["beats_house_pac"] = p["valid"] and mean(j["result"]["pacman_score"] for j in p["house_pac"]) > 0.5
        p["beats_house_ghost"] = p["valid"] and mean(j["result"]["ghost_score"] for j in p["house_ghost"]) > 0.5
        p["hung"] = [j for j in p["pac_games"] + p["ghost_games"] if j["result"]["outcome"] in ("hung", "crash")]
    ranked = sorted(owners, key=lambda o: (-players[o]["league"], -players[o]["pac_avg"], o))
    valid_ranked = [o for o in ranked if players[o]["valid"]]
    n = len(valid_ranked)
    for i, o in enumerate(ranked):
        p = players[o]
        p["rank"] = i + 1
        if p["valid"]:
            r = valid_ranked.index(o)
            rank_marks = args.rank_marks if n == 1 else 1 + (args.rank_marks - 1) * (n - 1 - r) / (n - 1)
            house_marks = args.house_marks / 2 * (p["beats_house_pac"] + p["beats_house_ghost"])
        else:
            rank_marks = house_marks = 0.0
        p["rank_marks"], p["house_marks"] = round(rank_marks, 1), round(house_marks, 1)
        p["league_marks"] = round(rank_marks + house_marks, 1)

    # 4. checker per student on the league boards
    if not args.no_check:
        print("running the checker on the league boards for every student …")
        with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(run_checker, kit, players[o]["file"], os.path.abspath(args.boards),
                              os.path.join(out, "checks", o + ".json")): o for o in owners if players[o]["valid"]}
            for fut in cf.as_completed(futs):
                players[futs[fut]]["check"] = fut.result()

    # 5. write outputs
    with open(os.path.join(out, "games.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "pacman", "ghost", "board", "outcome", "pacman_score", "ghost_score", "eaten", "total", "ticks",
                    "faults_pacman", "faults_ghost", "seconds", "replay"])
        for j in jobs:
            r = j["result"]
            w.writerow([j["kind"], j["pacman"], j["ghost"], j["board"], r["outcome"], r["pacman_score"], r["ghost_score"],
                        r["eaten"], r["total"], r["ticks"], r["faults"]["pacman"], r["faults"]["ghost"], r.get("seconds", ""), j["file"]])
    with open(os.path.join(out, "replays", "index.json"), "w", encoding="utf-8") as f:
        json.dump([{"file": j["file"], "pacman": j["pacman"], "ghost": j["ghost"], "board": j["board"], "kind": j["kind"],
                    "outcome": j["result"]["outcome"], "pacman_score": j["result"]["pacman_score"],
                    "ghost_score": j["result"]["ghost_score"]} for j in jobs], f)

    cols = ["rank", "owner", "valid", "pac_avg", "ghost_avg", "league", "beats_house_pac", "beats_house_ghost",
            "house_marks", "rank_marks", "league_marks", "hung_games"]
    rows = []
    for o in ranked:
        p = players[o]
        rows.append([p["rank"], o, "yes" if p["valid"] else "NO: " + "; ".join(p["reasons"])[:80], f"{p['pac_avg']:.3f}",
                     f"{p['ghost_avg']:.3f}", f"{p['league']:.3f}", "yes" if p["beats_house_pac"] else "no",
                     "yes" if p["beats_house_ghost"] else "no", p["house_marks"], p["rank_marks"], p["league_marks"], len(p["hung"])])
    with open(os.path.join(out, "league_table.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    with open(os.path.join(out, "league_table.md"), "w", encoding="utf-8") as f:
        f.write(f"# Pac-Man League — table\n\n{len(owners)} players · {len(boards)} boards · {len(jobs)} games\n\n" + "\n".join(md) + "\n")
    with open(os.path.join(out, "league_table.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset=utf-8><title>Pac-Man League</title>"
                "<style>body{font:15px -apple-system,Segoe UI,Roboto,sans-serif;background:#0b0f17;color:#e6edf7;padding:24px}"
                "table{border-collapse:collapse}td,th{padding:6px 12px;border-bottom:1px solid #1f2a3d;text-align:left}"
                "th{color:#8a97ad;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.08em}"
                "tr:nth-child(1) td{color:#f5b942;font-weight:600}</style>"
                f"<h1>Pac-Man League</h1><p>{len(owners)} players · {len(boards)} boards · {len(jobs)} games</p><table><tr>"
                + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>"
                + "".join("<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in r) + "</tr>" for r in rows) + "</table>")

    # 6. report cards
    for o in owners:
        p = players[o]
        L = [f"# Assignment 1 — report card: {o}", ""]
        if not p["valid"]:
            L += ["**File replaced by the house agents in the league** — " + "; ".join(p["reasons"]), ""]
        chk = p.get("check") or {}
        L += ["## Checker (league boards)", ""]
        if chk.get("checks"):
            L += ["```"] + [("[OK ] " if c["ok"] else ("[WARN] " if c.get("warn") else "[FAIL] ")) + c["text"] for c in chk["checks"]] + ["```", ""]
            L += [f"- A* tests: {chk.get('astar_tests', ['?', '?'])[0]}/{chk.get('astar_tests', ['?', 10])[1]}",
                  f"- OPPONENT_MODEL: {chk.get('opponent_model')}",
                  f"- lookahead on ticks with the ghost in sight: {chk.get('counters', {}).get('lookahead_on_visible', '?')}/{chk.get('counters', {}).get('visible_ticks', '?')}",
                  f"- slowest move: {chk.get('worst_ms', 0):.0f} ms · faults: {chk.get('faults', '?')}", ""]
        elif not args.no_check:
            L += ["(checker produced no output)", ""]
        L += ["## House checks (league boards)", "", "| game | board | outcome | score |", "|---|---|---|---|"]
        for j in p["house_pac"]:
            L.append(f"| Pac-Man vs {j['ghost']} | {j['board']} | {j['result']['outcome']} | {j['result']['pacman_score']:.2f} |")
        for j in p["house_ghost"]:
            L.append(f"| ghost vs baseline_pacman | {j['board']} | {j['result']['outcome']} | {j['result']['ghost_score']:.2f} |")
        L += ["", f"Beats the house as Pac-Man: **{'yes' if p['beats_house_pac'] else 'no'}** · as ghost: **{'yes' if p['beats_house_ghost'] else 'no'}**", ""]
        L += ["## League games", "", "| as | opponent | board | outcome | my score |", "|---|---|---|---|---|"]
        for j in sorted(p["pac_games"], key=lambda j: (j["ghost"], j["board"])):
            L.append(f"| Pac-Man | {j['ghost']} | {j['board']} | {j['result']['outcome']} | {j['result']['pacman_score']:.2f} |")
        for j in sorted(p["ghost_games"], key=lambda j: (j["pacman"], j["board"])):
            L.append(f"| ghost | {j['pacman']} | {j['board']} | {j['result']['outcome']} | {j['result']['ghost_score']:.2f} |")
        L += ["", f"Pac-Man average **{p['pac_avg']:.3f}** · ghost average **{p['ghost_avg']:.3f}** · league score **{p['league']:.3f}** · rank **{p['rank']} / {len(owners)}**", ""]
        if p["hung"]:
            L += ["Games with no result (hung/crashed): " + ", ".join(f"{j['pacman']} vs {j['ghost']} on {j['board']}" for j in p["hung"]), ""]
        L += ["## Marks", "", "| component | marks | note |", "|---|---|---|",
              f"| League — house ({args.house_marks:g}) | {p['house_marks']} | Pac-Man {'✓' if p['beats_house_pac'] else '✗'} · ghost {'✓' if p['beats_house_ghost'] else '✗'} |",
              f"| League — rank ({args.rank_marks:g}) | {p['rank_marks']} | rank {p['rank']} of {len(owners)} |",
              "| Code (5) | ____ | A* 1 · lookahead 2 · evaluate 1 · movers 1 — only for code explained in the Q&A |",
              "| Report and reflections (5) | ____ | strategy · opponent model with evidence · ghost · results table · reflections · AI use |",
              f"| **Total (15)** | ____ | |", "", "Q&A question asked: ______________________", "", "Notes:", ""]
        with open(os.path.join(out, "report_cards", o + ".md"), "w", encoding="utf-8") as f:
            f.write("\n".join(L))

    print(f"\ndone in {time.time() - t0:.0f}s → {out}")
    print("\n".join(md))
    print(f"\nwatch any game:  cd {kit} && python3 arena.py --boards {os.path.abspath(args.boards)} --replays {os.path.join(out, 'replays')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
