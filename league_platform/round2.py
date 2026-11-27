#!/usr/bin/env python3
"""round2.py — the second round: every student's old and new agent, the better one stays.

  python round2.py prepare <folder>   # <folder> holds the unpacked round-2 agent_*.py files (any depth)
  python results.py play --boards new # old and new agents all play on the new test boards
  python round2.py select             # per student keep the higher league score; the other -> agents/not_kept/
  python results.py play              # the kept agents' missing games on the old boards
  python build_site.py

prepare: agents/agent_<x>.py becomes agent_<x>_old.py (stored games are renamed with it), and every
round-2 file that differs from the old one and passes the checker is loaded as agent_<x>_new.py.
A round-2 file identical to the round-1 file is not a new agent. nerd keeps its name.

select: league score on the new test boards (results.ranking("new")): Pac-Man against every other
student's ghosts (old and new), nerd's ghost and the random ghost; ghost against their Pac-Men.
An agent never meets its own student's other version. Writes results/round2_selection.json.
"""
import glob
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import results  # noqa: E402
import submissions  # noqa: E402

NOT_KEPT = os.path.join(results.AGENTS, "not_kept")
SELECTION = os.path.join(results.STORE, "round2_selection.json")


def rename_stored(mapping):
    """Rename players in games.json and the replay files (same agent files, new names)."""
    games, out = results.load(), {}
    for g in games.values():
        p, h = mapping.get(g["pacman"], g["pacman"]), mapping.get(g["ghost"], g["ghost"])
        if (p, h) != (g["pacman"], g["ghost"]) and g.get("replay"):
            old = os.path.join(results.REPLAYS, g["replay"])
            new_name = results.replay_name(p, h, g["board"])
            if os.path.exists(old):
                with open(old, encoding="utf-8") as f:
                    rep = json.load(f)
                rep["meta"]["pacman"], rep["meta"]["ghost"] = p, h
                rep["result"]["pacman"], rep["result"]["ghost"] = p, h
                with open(os.path.join(results.REPLAYS, new_name), "w", encoding="utf-8") as f:
                    json.dump(rep, f)
                os.remove(old)
            g["replay"] = new_name
        g["pacman"], g["ghost"] = p, h
        out[results.gkey(p, h, g["board"])] = g
    results._save(out)


def prepare(folder):
    olds = {o: p for o, p in results.players().items()
            if results.kind_of(o) == "student" and results.student_of(o) == o}
    mapping = {o: o + "_old" for o in olds}
    for o, p in olds.items():
        os.replace(p, os.path.join(results.AGENTS, f"agent_{o}_old.py"))
    if mapping:
        rename_stored(mapping)
        print("renamed:", ", ".join(f"{a} -> {b}" for a, b in mapping.items()))
    files = [p for p in sorted(glob.glob(os.path.join(folder, "**", "*.py"), recursive=True))
             if os.path.basename(p).lower().startswith("agent_") and "__MACOSX" not in p]
    tmp = tempfile.mkdtemp(prefix="pacman_r2_")
    report = []
    try:
        boards_dir = submissions.training_boards_dir(tmp)
        for p in files:
            student = submissions.clean_owner(os.path.splitext(os.path.basename(p))[0][len("agent_"):])
            with open(p, encoding="utf-8", errors="replace") as f:
                src = f.read()
            old = os.path.join(results.AGENTS, f"agent_{student}_old.py")
            if os.path.exists(old) and open(old, encoding="utf-8", errors="replace").read() == src:
                print(f"{student}: round-2 file is identical to the round-1 file - no new agent")
                report.append({"owner": student, "identical": True})
                continue
            owner = student + "_new"
            e = submissions.verify({"owner": owner, "folder": os.path.basename(os.path.dirname(p)), "source": src,
                                    "notes": [], "rel": os.path.relpath(p, folder)}, tmp, boards_dir)
            if e["passed"]:
                shutil.copy(e.pop("path"), os.path.join(results.AGENTS, f"agent_{owner}.py"))
            else:
                e.pop("path")
            print(f"{owner}: {'loaded' if e['passed'] else 'REJECTED'}")
            for c in e["checks"]:
                if c["level"] != "ok":
                    print(f"    {c['level'].upper()}: {c['text']}")
            report.append(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(results.STORE, "round2_submissions.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


def select():
    t = results.ranking("new")
    if t["played"] < t["expected"]:
        print(f"only {t['played']}/{t['expected']} games played on the new boards - play them first")
        return 1
    by = {}
    for r in t["rows"]:
        if r["kind"] == "student":
            by.setdefault(results.student_of(r["owner"]), {})[r["owner"].rsplit("_", 1)[1]] = r
    out = []
    os.makedirs(NOT_KEPT, exist_ok=True)
    for student, v in sorted(by.items()):
        old, new = v.get("old"), v.get("new")
        keep = "new" if new and (not old or new["league"] > old["league"]) else "old"
        out.append({"student": student, "kept": keep,
                    **{f"{k}_{f}": (v[k][f] if v.get(k) else None) for k in ("old", "new") for f in ("pac_avg", "ghost_avg", "league")}})
        drop = "old" if keep == "new" else "new"
        if v.get(drop):
            shutil.move(os.path.join(results.AGENTS, f"agent_{student}_{drop}.py"), os.path.join(NOT_KEPT, f"agent_{student}_{drop}.py"))
        f = lambda r: "   -  " if not r else f"{r['league']:.3f} (P {r['pac_avg']:.3f} / G {r['ghost_avg']:.3f})"
        print(f"{student:<14} old {f(old):<28} new {f(new):<28} -> keep {keep}")
    with open(SELECTION, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "prepare":
        sys.exit(prepare(sys.argv[2]))
    if len(sys.argv) == 2 and sys.argv[1] == "select":
        sys.exit(select())
    print(__doc__)
    sys.exit(2)
