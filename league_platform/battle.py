#!/usr/bin/env python3
"""battle.py — runs the full league offline (every student's Pac-Man vs every other student's
ghost, on the hidden boards, plus the random/baseline house checks) and writes the official
ranking to private/battle/. Nothing about the ranking is printed.

  python3 battle.py                  # students only (agents/ minus nerd), boards/hidden*.txt
  python3 battle.py --with-nerd      # extra reference run with nerd as a player -> private/battle_with_nerd/

Jev is never part of the battle. Uses ../instructor/league.py (same scoring and marks).
Outputs: league_table.{csv,md,html}, games.csv, replays/, report_cards/, checks/.
"""
import argparse
import contextlib
import glob
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEAGUE = os.path.normpath(os.path.join(HERE, "..", "instructor"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-nerd", action="store_true")
    ap.add_argument("--jobs", type=int, default=1, help="games in parallel; keep 1 — parallel games push agents past 100 ms and cause false forfeits")
    args = ap.parse_args(argv)
    out = os.path.join(HERE, "private", "battle_with_nerd" if args.with_nerd else "battle")
    stage = os.path.join(out, "_input")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(os.path.join(stage, "agents"))
    os.makedirs(os.path.join(stage, "boards"))
    for p in glob.glob(os.path.join(HERE, "agents", "agent_*.py")):
        if os.path.basename(p) == "agent_nerd.py" and not args.with_nerd:
            continue
        shutil.copy(p, os.path.join(stage, "agents"))
    for p in glob.glob(os.path.join(HERE, "boards", "hidden*.txt")):
        shutil.copy(p, os.path.join(stage, "boards"))

    sys.path.insert(0, LEAGUE)
    import league  # noqa: E402
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):          # league.py prints the table at the end: keep it private
        rc = league.main(["--agents", os.path.join(stage, "agents"), "--boards", os.path.join(stage, "boards"),
                          "--out", out, "--kit", HERE, "--jobs", str(args.jobs)])
    with open(os.path.join(out, "battle_log.txt"), "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print(f"battle finished (exit {rc}); results are in {out} — not printed here")
    return rc


if __name__ == "__main__":
    sys.exit(main())
