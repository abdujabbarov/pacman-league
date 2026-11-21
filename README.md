# Pac-Man League — AI: Principles and Techniques, Assignment 1

Replay site: **https://abdujabbarov.github.io/pacman-league/** — every game on the three training boards and
the two test boards.

```
AI_MDS_Assignment1_PacMan_League.pdf   the assignment
league_platform/   engine, checker, house agents, arena (Play + Ranking), submission loader, results, site builder
docs/              the replay site (GitHub Pages): boards, results and moves only
instructor/        league.py (the original league runner), board generator, the two test boards
```

## Kept on the instructor's computer only (see .gitignore)

Students' code and reports (`Submission/`, `league_platform/agents/`), earlier runs with report cards and marks
(`league_platform/private/`), the checker report (`league_platform/results/submissions.json`), the ranking files
with marks, and the reference solution. The repository and the site hold game data only — no student code.

## When a new or changed agent arrives

```
# put it in Submission/<Name>/, then:
cd league_platform
python arena.py               # "Load submissions", then Ranking -> "Play all games" (only new/changed games are played)
python build_site.py          # refresh docs/data
cd .. && git add -A && git commit -m "update replays" && git push      # the site updates in a minute or two
```

Command-line equivalents: `python submissions.py`, `python results.py play`. Details in `league_platform/README.md`.

## The replay site

Pick a Pac-Man (left), a ghost (right) and a board, choose the view (All / Pac-Man / Ghost) and the speed, and
step or scrub through the game. The Table tab shows every Pac-Man (rows) against every ghost (columns); click a
cell to watch that game. Links keep the selection (`#p=<pacman>&g=<ghost>&b=<board>`).
