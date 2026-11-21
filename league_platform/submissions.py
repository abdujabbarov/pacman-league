#!/usr/bin/env python3
"""submissions.py — find every agent in ../Submission, verify it against the assignment rules,
and load the ones that pass into agents/.

  python submissions.py              # verify all and load the passing ones
  python submissions.py --dry-run    # verify only

Where agents come from (one folder per student, or files directly in Submission/):
  * agent_<surname>.py — the name is lower-cased (agent_Erbol.py -> agent_erbol.py, noted)
  * a Colab notebook with no agent file: the "%%writefile {AGENT_FILE}" cell, named from SURNAME
  agent_template.py is ignored.

Verification = check_submission.py (the checker the students had) on the three training boards,
each agent in its own process, one at a time.
  Must pass (else NOT loaded): syntax · allowed imports only · no private attributes · no
    file/exec tricks · the five functions · OPPONENT_MODEL · both movers call astar ·
    lookahead on every tick the ghost is in sight.
  Reported only (loaded anyway): A* tests below 10/10, moves slower than 100 ms and faults
    (timing depends on the machine), and the "beats the house" lines.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SUBMISSION = os.path.normpath(os.path.join(HERE, "..", "Submission"))
AGENTS = os.path.join(HERE, "agents")
REPORT = os.path.join(HERE, "results", "submissions.json")
SOFT = ("A* tests", "slowest move", "faults:")       # reported, not blocking


def clean_owner(raw):
    o = re.sub(r"[^a-z0-9_]", "", raw.strip().lower().replace(" ", "_").replace("-", "_"))
    return o or "unknown"


def from_notebook(path):
    """(owner, source) from a Colab notebook, or None."""
    try:
        with open(path, encoding="utf-8") as f:
            nb = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    surname, body = None, None
    for c in nb.get("cells", []):
        if c.get("cell_type") != "code":
            continue
        src = "".join(c.get("source", []))
        m = re.search(r"""^\s*SURNAME\s*=\s*["']([^"']+)["']""", src, re.M)
        if m and surname is None:
            surname = m.group(1)
        if src.lstrip().startswith("%%writefile") and "def astar" in src:
            body = src.lstrip().split("\n", 1)[1] if "\n" in src.lstrip() else ""
    if body is None:
        return None
    if surname is None:
        surname = os.path.basename(os.path.dirname(path))
    return clean_owner(surname), body


def discover(folder=SUBMISSION):
    """List of {owner, source_path, source, notes} for every submission found."""
    found = []
    dirs = [folder] + sorted(d for d in glob.glob(os.path.join(folder, "*")) if os.path.isdir(d))
    for d in dirs:
        files = [p for p in sorted(glob.glob(os.path.join(d, "*.py")))
                 if os.path.basename(p).lower().startswith("agent_") and os.path.basename(p).lower() != "agent_template.py"]
        for p in files:
            base = os.path.basename(p)
            owner = clean_owner(os.path.splitext(base)[0][len("agent_"):])
            notes = []
            if base != f"agent_{owner}.py":
                notes.append(f"file renamed {base} -> agent_{owner}.py (names must be lowercase, no spaces)")
            with open(p, encoding="utf-8", errors="replace") as f:
                found.append({"owner": owner, "folder": os.path.basename(d), "source_path": p, "source": f.read(), "notes": notes,
                              "rel": os.path.relpath(p, folder)})
        if not files and d != folder:
            for nbp in sorted(glob.glob(os.path.join(d, "*.ipynb"))):
                got = from_notebook(nbp)
                if got:
                    owner, src = got
                    found.append({"owner": owner, "folder": os.path.basename(d), "source_path": nbp, "source": src,
                                  "rel": os.path.relpath(nbp, folder),
                                  "notes": [f"no agent file: taken from the agent cell of {os.path.basename(nbp)}"]})
                    break
    seen = {}
    for s in found:                         # two files with the same owner: keep the first, say so
        if s["owner"] in seen:
            seen[s["owner"]]["notes"].append(f"also found {s['rel']} — ignored")
        else:
            seen[s["owner"]] = s
    return list(seen.values())


def training_boards_dir(tmp):
    d = os.path.join(tmp, "boards")
    os.makedirs(d, exist_ok=True)
    for p in glob.glob(os.path.join(HERE, "boards", "practice*.txt")):
        shutil.copy(p, d)
    return d


def verify(sub, tmp, boards_dir):
    """Runs the checker on one submission. Returns the report entry."""
    path = os.path.join(tmp, f"agent_{sub['owner']}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(sub["source"])
    out_json = os.path.join(tmp, f"check_{sub['owner']}.json")
    cmd = [sys.executable, os.path.join(HERE, "check_submission.py"), path, "--boards", boards_dir, "--json", out_json, "--quiet"]
    checks, error = [], None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=HERE)
        if os.path.exists(out_json):
            with open(out_json, encoding="utf-8") as f:
                checks = json.load(f).get("checks", [])
        else:                                # the checker stops early on a broken file and prints why
            for line in (p.stdout or "").splitlines():
                if line.startswith("[OK ]") or line.startswith("[FAIL]") or line.startswith("[WARN]"):
                    checks.append({"ok": line.startswith("[OK"), "warn": line.startswith("[WARN"), "text": line[6:].strip()})
            if not checks:
                error = (p.stderr or p.stdout or "checker produced no output").strip()[-300:]
    except subprocess.TimeoutExpired:
        error = "checker did not finish in 15 minutes"
    lines, blocking = [], []
    for c in checks:
        if c.get("text", "").startswith("file name"):
            continue                          # the file is renamed on load; noted above instead
        soft = c.get("warn") or c.get("text", "").startswith(SOFT)
        level = "ok" if c["ok"] else ("warn" if soft else "fail")
        lines.append({"level": level, "text": c["text"]})
        if level == "fail":
            blocking.append(c["text"])
    if error:
        blocking.append(error)
        lines.append({"level": "fail", "text": error})
    if not checks and not error:
        blocking.append("no checks ran")
    return {"owner": sub["owner"], "folder": sub["folder"], "source": sub["rel"],
            "notes": sub["notes"], "checks": lines, "passed": not blocking, "reasons": blocking, "path": path}


def load_all(dry_run=False, progress=None):
    subs = discover()
    tmp = tempfile.mkdtemp(prefix="pacman_subs_")
    report = []
    try:
        boards_dir = training_boards_dir(tmp)
        if progress:
            progress(0, len(subs), None)
        for i, s in enumerate(subs):
            entry = verify(s, tmp, boards_dir)
            dest = os.path.join(AGENTS, f"agent_{s['owner']}.py")
            entry["loaded"] = False
            if entry["passed"] and not dry_run:
                changed = not os.path.exists(dest) or open(dest, encoding="utf-8").read() != s["source"]
                os.makedirs(AGENTS, exist_ok=True)
                shutil.copy(entry["path"], dest)
                entry["loaded"] = True
                entry["changed"] = changed
            elif not entry["passed"] and os.path.exists(dest):
                entry["notes"].append(f"an older agents/agent_{s['owner']}.py is still in place — remove it by hand if needed")
            entry.pop("path")
            report.append(entry)
            if progress:
                progress(i + 1, len(subs), entry)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="verify only, do not copy into agents/")
    args = ap.parse_args(argv)

    def progress(i, n, e):
        if e is None:
            print(f"{n} submissions found in {SUBMISSION}")
            return
        tag = "LOADED " if e["loaded"] else ("PASSED " if e["passed"] else "REJECTED")
        print(f"[{i}/{n}] {tag} {e['owner']:<16} ({e['source']})")
        for n_ in e["notes"]:
            print("           note:", n_)
        for c in e["checks"]:
            if c["level"] != "ok":
                print(f"           {c['level'].upper()}: {c['text']}")
    load_all(args.dry_run, progress)
    return 0


if __name__ == "__main__":
    sys.exit(main())
