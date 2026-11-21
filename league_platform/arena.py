#!/usr/bin/env python3
"""arena.py — League-day arena (instructor platform).

  python arena.py                  # students + nerd + house agents, all five boards

Tabs
  Play     pick a Pac-Man (left), a ghost (right), a board, a view (all / Pac-Man / ghost), Start.
           Any agent can play against its own ghost. "you" plays from the keyboard.
  Ranking  league table and the Pac-Man x ghost table of games, for the test boards, the
           training boards, all boards, or one board. "Play all games" plays every missing game.

"Load submissions" (top right) finds every agent in ../Submission, runs the checker on it, and
copies the ones that pass into agents/ (see submissions.py).

Every finished agent-vs-agent game (own ghost included) is stored in results/ — the latest game
for a Pac-Man / ghost / board counts. build_site.py turns results/ into the GitHub Pages site.
"""
import argparse
import json
import os
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pacman_engine import Board, Game, load_agent  # noqa: E402
import results  # noqa: E402
import submissions  # noqa: E402

HOUSE = results.HOUSE


def label_of(name):
    return name[len("agent_"):] if name.startswith("agent_") else name


class Job:
    """One background job at a time (load submissions / play all games)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"kind": None, "running": False, "done": 0, "total": 0, "log": [], "report": None, "error": None}
        self.stop_flag = False

    def busy(self):
        return self.state["running"]

    def start(self, kind, fn):
        with self.lock:
            if self.state["running"]:
                return False
            self.state = {"kind": kind, "running": True, "done": 0, "total": 0, "log": [], "report": None, "error": None}
            self.stop_flag = False
        threading.Thread(target=self._run, args=(fn,), daemon=True).start()
        return True

    def _run(self, fn):
        try:
            self.state["report"] = fn(self)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.state["error"] = f"{type(e).__name__}: {e}"
        finally:
            self.state["running"] = False

    def progress(self, i, n, line=None):
        self.state["done"], self.state["total"] = i, n
        if line:
            self.state["log"] = (self.state["log"] + [line])[-400:]


def load_submissions_job(job):
    def progress(i, n, e):
        job.progress(i, n, None if e is None else
                     f"{'loaded' if e['loaded'] else 'REJECTED'}  {e['owner']}" + ("" if e["passed"] else "  — " + "; ".join(e["reasons"])))
    return submissions.load_all(progress=progress)


def play_all_job(job, force=False):
    def progress(i, n, rec):
        job.progress(i, n, None if rec is None else
                     f"{rec['pacman']} vs {rec['ghost']} on {rec['board']}: {rec['outcome']} {rec['pacman_score']:.2f}")
    return {"played": results.play_all(force, progress, stop=lambda: job.stop_flag)}


class Arena:
    def __init__(self, time_limit=0.1):
        self.time_limit = time_limit
        self.games, self.names, self.recorded = {}, {}, set()
        self.lock = threading.Lock()
        self.next_id = 1
        self.job = Job()

    # -- catalogue
    def agents(self):
        """name -> {path, label, side, kind}"""
        out = {}
        for owner, p in results.players().items():
            name = "agent_" + owner
            out[name] = {"path": p, "label": owner, "side": "both", "kind": results.kind_of(owner)}
        for h, p in results.house().items():
            out[h] = {"path": p, "label": h, "side": HOUSE[h], "kind": "house"}
        return out

    def boards(self):
        return results.boards()

    # -- games
    def new_game(self, pac_name, ghost_name, board_name):
        agents, boards = self.agents(), self.boards()
        if board_name not in boards:
            raise ValueError(f"unknown board {board_name}")
        for n in (pac_name, ghost_name):
            if n != "human" and n not in agents:
                raise ValueError(f"unknown agent {n}")
        board = Board.load(boards[board_name])
        pac = None if pac_name == "human" else load_agent(agents[pac_name]["path"])
        gho = None if ghost_name == "human" else load_agent(agents[ghost_name]["path"])
        labels = {"pacman": "you" if pac_name == "human" else label_of(pac_name),
                  "ghost": "you" if ghost_name == "human" else label_of(ghost_name)}
        human = pac is None or gho is None
        # with a human playing there is no tick limit: the game ends by capture or when the food is gone
        game = Game(board, pac, gho, time_limit=self.time_limit, labels=labels, meta={"arena": True},
                    max_ticks=10 ** 9 if human else None)
        hashes = (None if pac is None else results.file_hash(agents[pac_name]["path"]),
                  None if gho is None else results.file_hash(agents[ghost_name]["path"]))
        with self.lock:
            gid = str(self.next_id)
            self.next_id += 1
            self.games[gid] = game
            self.names[gid] = (pac_name, ghost_name, hashes)
        return gid, game

    def finished(self, gid, game):
        """Store finished agent-vs-agent games played at the league time limit (own ghost included)."""
        if not game.done or gid in self.recorded:
            return
        self.recorded.add(gid)
        pac, gho, (ph, gh) = self.names.get(gid, ("human", "human", (None, None)))
        if "human" in (pac, gho) or self.time_limit != results.LEAGUE_TIME_LIMIT:
            return
        try:
            results.record(game.replay(), label_of(pac), label_of(gho), game.board.name, ph, gh, "arena")
        except Exception:  # noqa: BLE001 - never disturb the game on screen
            traceback.print_exc()

    def payload(self, game, event=None):
        return {"view": game.view(), "event": event, "done": game.done,
                "needs": game.turn_side if game.needs_human_move() else None,
                "result": game.result() if game.done else None,
                "result_line": game.result_line() if game.done else None}


def board_json(board):
    return {"name": board.name, "label": results.board_label(board.name), "rows": board.rows, "cols": board.cols,
            "walls": sorted(list(x) for x in board.walls if 0 <= x[0] < board.rows and 0 <= x[1] < board.cols),
            "food": sorted(list(x) for x in board.food),
            "pacman": list(board.pacman_start), "ghost": list(board.ghost_start)}


def make_handler(arena: Arena):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path in ("/", "/arena.html", "/index.html"):
                    with open(os.path.join(HERE, "arena.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html")
                if u.path == "/api/list":
                    ag = arena.agents()
                    order = {"student": 0, "instructor": 1, "house": 2}
                    return self._send(200, {"agents": [{"name": n, "label": v["label"], "side": v["side"], "kind": v["kind"]}
                                                       for n, v in sorted(ag.items(), key=lambda kv: (order[kv[1]["kind"]], kv[1]["label"]))],
                                            "boards": [{"name": b, "label": results.board_label(b), "kind": results.board_kind(b)}
                                                       for b in arena.boards()]})
                if u.path == "/api/board":
                    name = q.get("name", [""])[0]
                    boards = arena.boards()
                    if name not in boards:
                        return self._send(404, {"error": "no such board"})
                    return self._send(200, board_json(Board.load(boards[name])))
                if u.path == "/api/ranking":
                    return self._send(200, results.ranking(q.get("scope", ["test"])[0]))
                if u.path == "/api/job":
                    return self._send(200, arena.job.state)
                return self._send(404, {"error": "not found"})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                if u.path == "/api/load_submissions":
                    ok = arena.job.start("load", load_submissions_job)
                    return self._send(200, {"started": ok, "job": arena.job.state})
                if u.path == "/api/play_all":
                    force = bool(body.get("force"))
                    ok = arena.job.start("play", lambda job: play_all_job(job, force))
                    return self._send(200, {"started": ok, "job": arena.job.state})
                if u.path == "/api/stop_job":
                    arena.job.stop_flag = True
                    return self._send(200, arena.job.state)
                if u.path == "/api/new":
                    if arena.job.busy():
                        return self._send(200, {"error": "Wait until the background job (loading or playing all games) has finished: "
                                                         "running both at once slows the agents down."})
                    gid, game = arena.new_game(body.get("pacman", "human"), body.get("ghost", "human"), body.get("board"))
                    out = arena.payload(game)
                    out.update({"id": gid, "board": board_json(game.board), "labels": game.labels,
                                "rules": game.replay()["rules"]})
                    return self._send(200, out)
                if u.path == "/api/turn":
                    game = arena.games.get(str(body.get("id")))
                    if game is None:
                        return self._send(404, {"error": "no such game"})
                    with arena.lock:
                        if game.done:
                            return self._send(200, arena.payload(game))
                        move = body.get("move")
                        if game.needs_human_move():
                            if move is None:
                                return self._send(200, arena.payload(game))
                            side = game.turn_side
                            legal = game.core.legal_moves(getattr(game.core, side))
                            if side == "ghost" and move == "STOP":
                                # a human ghost holding no key stands still (agents must move; humans may rest)
                                event = {"tick": game.core.tick, "who": "ghost", "from": list(game.core.ghost),
                                         "move": "STAY", "ms": 0.0, "fault": None, "skipped": False, "ate": False}
                                game.core.apply(None)
                                event["to"] = list(game.core.ghost)
                                event["outcome"] = game.core.outcome
                                game.turns.append(event)
                                arena.finished(str(body.get("id")), game)
                                return self._send(200, arena.payload(game, event))
                            if not (move in legal or (move == "STOP" and side == "pacman")):
                                out = arena.payload(game)
                                out["error"] = "illegal move"
                                return self._send(200, out)
                            event = game.turn(move)
                        else:
                            event = game.turn()
                    arena.finished(str(body.get("id")), game)
                    return self._send(200, arena.payload(game, event))
                return self._send(404, {"error": "not found"})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return self._send(500, {"error": str(e)})
    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--time-limit", type=float, default=0.1,
                    help="seconds per move (league: 0.1; games at any other limit are not stored)")
    args = ap.parse_args(argv)
    arena = Arena(time_limit=args.time_limit)
    port = args.port
    for _ in range(20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(arena))
            break
        except OSError:
            port += 1
    else:
        print("no free port"); return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"Pac-Man League arena at {url}  (Ctrl+C to stop)")
    print("agents:", ", ".join(v["label"] for v in arena.agents().values()) or "none found")
    print("boards:", ", ".join(results.board_label(b) for b in arena.boards()) or "none found")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
