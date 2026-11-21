# Pac-Man League — instructor folder (do not distribute)

```
Assignment/
  league_platform/          engine, checker, house agents, arena, ranking, site builder (the kit was folded into it)
  Submission/               put every submitted agent_<surname>.py here (nothing else)
  instructor/
    boards_hidden/hidden1.txt, hidden2.txt   the two league boards (15x21, like the practice boards; different mazes)
    make_board.py           mints a new board from a seed:  python3 make_board.py --seed 303 --out boards_hidden/hidden3.txt
    reference_agent.py      a complete plain solution (minimax; flip OPPONENT_MODEL for expectimax)
    league.py               runs the league, writes table, replays, report cards
    league_out/             created by league.py
```

## Running the league (morning of 21 Nov — the deadline is 20 Nov 23:59)

1. Download every `agent_<surname>.py` from OCS into `Assignment/Submission/`.
2. In a terminal in this `instructor` folder:
   ```
   python3 league.py
   ```
   Defaults: agents from `../Submission`, boards from `boards_hidden`, output to `league_out`.
   ~30 games per 3 students on 2 boards (seconds); a 20-student cohort is ~900 games, a few minutes.
3. Outputs in `league_out/`: `league_table.{csv,md,html}`, `games.csv`, `replays/` (+ `index.json`),
   `report_cards/<owner>.md` (checker output on the hidden boards, house checks, every game, rank,
   suggested league marks, blanks for code and report marks), `checks/<owner>.json`.
4. For the league session and afterwards, use `../league_platform` (see its README): `python arena.py`
   (Play + Ranking tabs, "Load submissions"), and `python build_site.py` for the students' replay site.

## Marks (15)

- League 5 = house 2 (1 if the Pac-Man's average against the baseline ghost and the random ghost on
  the league boards is above 0.5; 1 if the ghost's average against the baseline Pac-Man is above 0.5)
  + rank 3 (1st = 3, last = 1, linear). `league.py` computes both; `--house-marks/--rank-marks` change the split.
- Code 5 = A* tests 1 · lookahead 2 · evaluate 1 · movers 1 — only for code explained in the Q&A.
- Report and reflections 5.

A file that fails the static checks is replaced by the house agents so the league always runs,
flagged in the table, and gets 0 league marks.

## Testing the kit

Copy `reference_agent.py` to `Submission/agent_reference.py` and it appears in the arena and the league
like a student. `python3 ../league_platform/check_submission.py ../Submission/agent_reference.py` should
pass every check. The reference plays a plain depth-2 minimax with maze distances and a dead-end map; the
second reference (expectimax) is the same file with the model flipped. Against the house ghosts it scores
0.8–1.0 as Pac-Man on these boards and catches the baseline Pac-Man within ~100 ticks — a solid-but-plain
yardstick, not the ceiling.
