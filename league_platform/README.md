# Pac-Man League platform (instructor)

```
league_platform/
  arena.py, arena.html   the arena: Play tab + Ranking tab + "Load submissions" button
  submissions.py         finds every agent in ../Submission, checks it, loads the passing ones into agents/
  results.py             the game store (results/), the ranking, and "play all games"
  build_site.py          results/ -> ../docs/data/ (the students' replay site on GitHub Pages)
  agents/                agent_<surname>.py (loaded submissions) + agent_nerd.py (yours, "instructor")
  boards/                practice1-3 (training boards) + hidden1-2 (test boards = the league)
  results/               games.json (latest game per Pac-Man/ghost/board) + replays/ + submissions.json
  battle.py              the original offline league via ../instructor/league.py -> private/battle/
  private/               earlier runs (battle, battle_run1, battle_with_nerd, live games) — never published
  ranking_public.md, ranking_moodle.html   the published league ranking (= battle_with_nerd)
```

## Arena

```
python arena.py
```

- **Play** — pick a Pac-Man (left), a ghost (right), a board, a view (**All**, **Pac-Man**, **Ghost**: what that
  side sees), the speed, then **Start**. Any agent can play against its own ghost. "you" plays from the keyboard.
- **Ranking** — the league table and the Pac-Man × ghost table (rows: Pac-Men, columns: ghosts) for the test
  boards, the training boards, all boards, or one board. Click a cell to play that game.
  **Play all games** plays every game that is missing or whose agent file changed (one at a time).
- **Load submissions** — finds every agent in `../Submission` (`agent_*.py`, lower-cased; or the agent cell of a
  Colab notebook), runs `check_submission.py` on the training boards, and copies the passing ones into `agents/`.
  Blocking: syntax, allowed imports, private attributes, file/exec tricks, the five functions, OPPONENT_MODEL,
  both movers call astar, lookahead on every tick the ghost is in sight. Reported only: A* tests, speed and faults
  (timing depends on the machine), beating the house.

Every finished agent-vs-agent game (own ghost included) is stored in `results/`; the latest game for a
Pac-Man / ghost / board counts. Games with a human player are not stored.

## Ranking rule (as in the league)

- Pac-Man avg: against every other player's ghost and the random ghost.
- Ghost avg: against every other player's Pac-Man.
- League score: the mean of the two; ties by Pac-Man avg. Games against your own ghost are shown, not counted.
- nerd plays everyone and counts as an opponent but is not ranked. On the test boards this reproduces
  `ranking_public.md` exactly (results/ was seeded from `private/battle_with_nerd/replays`).

## Command line

```
python submissions.py [--dry-run]       # same as the button
python results.py play [--force]        # same as "Play all games"
python results.py table [--boards test|training|all|hidden1]
python build_site.py                    # refresh ../docs/data for the site, then commit and push
```

## Notes

- Keep games one at a time. Running games in parallel on a laptop pushed agents past 100 ms and caused false
  "too slow" forfeits; the arena refuses to start a game while a background job runs.
- Agents that search until their time budget runs out make results depend on timing: two identical runs differed
  in 16 of 126 games.
- Didenko submitted only the Colab notebook; Erbol's file is `agent_Erbol.py`. Both are handled by the loader.
