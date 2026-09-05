# Sokoban

Desktop Sokoban with undo/redo, saved progress, six levels, and optional AI assistance.
The original 14-box level is the final challenge. All levels are available immediately.

## Run

Python 3.10+ is recommended (tested with Python 3.13.2).

```powershell
python -m pip install -r requirements.txt
python main.py
```

Assets and levels are resolved relative to the project, so the script can also be
launched by absolute path from another working directory. No web server is needed.

## Project Structure

```text
Sokoban/
├── main.py              # Main application entry point
├── benchmark.py         # Solver performance benchmark CLI
├── requirements.txt     # Python dependencies
│
├── src/                 # Application source package
│   ├── config.py        # Centralized settings and resource paths
│   ├── core/            # Game logic and state (independent of Pygame)
│   │   ├── game.py      # Core Sokoban rules, board state, deadlock checks
│   │   └── progress.py  # Progress persistence, scores, and replay history
│   ├── ai/              # Search algorithms and solution validators
│   │   ├── ai_solver.py # A* push search and Hill Climbing algorithms
│   │   └── solutions.py # Move sequence validation against Sokoban rules
│   └── ui/              # Pygame presentation layer
│       ├── renderer.py  # Board graphics, responsive UI, fonts, modals
│       └── audio.py     # Sound effects synthesizer and playback
│
├── assets/              # Pixel-art game sprites (.png)
├── data/                # Player save files (progress.json)
├── levels/              # 11 hand-crafted levels (.txt)
└── tests/               # Automated unit tests
```

## Controls

| Key | Action |
| --- | --- |
| Arrow keys | Move or push |
| Z / Y | Undo / redo |
| R | Restart the current level |
| Tab | Open or close level selection |
| N | Next level |
| H | Apply one A* hint move |
| A | Solve from the current state and play the result |
| J | Run the educational Hill Climbing variant |
| L | Replay a verified saved solution from the start |
| Space / Escape | Cancel search and stop playback |
| M | Toggle sound |
| F11 | Toggle fullscreen |
| Enter | Next level from the completion menu (level selection after the final level) |

Mouse controls are also available. Scroll the level list with the mouse wheel or
up/down arrows. The speed slider changes playback speed. Moving, undoing, restarting,
or changing levels cancels any pending AI result. Undo is available after winning.
Filling every goal opens a completion menu with the move/push totals, next level,
restart and level selection. Escape or the close button dismisses the menu without
restarting. Completing the final level offers level selection instead of a nonexistent
next level. The menu also appears when an AI playback completes a level.

## Progress

`data/progress.json` stores the last level, each level's legal move history, completion,
verified cached solutions, best scores, and sound preference. Writes use an atomic
temporary-file replacement. Invalid saves are reported and ignored. Level content
hashes prevent applying saves or solutions to changed maps.

Scores are ordered by pushes, then moves. Assisted and solo records are separate.

Every completed level earns at least one star. Meeting the configured move limits
earns two or three stars, and the highest rating is saved across solo and assisted
runs. Per-level limits are defined in `STAR_MOVE_TARGETS` in `src/config.py`; custom
levels without configured limits still earn one star when completed.

Choosing a level from the level list or navigating with Previous/Next always starts
that board from its initial state; saved completion, stars, and best scores are kept.
Once assistance has been used, a run remains assisted even after undo; restart clears
that flag. Undo history is rebuilt on reload; undone redo branches are session-only.

## AI

A* searches push states and uses shortest walking routes between pushes. It minimizes
pushes, not total walking steps. It uses reverse-push distance lower bounds, best-known
costs, parent links, static dead squares and filled 2x2 deadlock detection. Other kinds
of deadlocks can still escape detection. A background worker keeps the UI responsive;
cancellation is cooperative. Limits default to 15 seconds and 50,000 discovered states.

Hill Climbing is a greedy push-search demonstration with deterministic random tie
breaking and no repeated exact states. It is not a complete or optimal solver. Partial
paths are reported as incomplete and never automatically played as solutions.

The large map may reach the limits without a solution; this does not mean it is
unsolvable. Limits can be adjusted in `config.py`. More advanced box-goal assignment
and dynamic deadlock analysis are future improvements.

The old `solve_a_star` / Hill Climbing list return values have been replaced with
`SolveResult(status, path, explored, elapsed, pushes)`. `game_map` and `player_pos`
are derived read-only views; changes go through the rules API.

## Verification

```powershell
python -m unittest discover -s tests -v
python benchmark.py --seconds 2 --seed 0 --output test-artifacts/benchmark.json
```

Tests include rules, undo/redo, validation, push-optimality against an independent
0-1 BFS, save restoration, solution validation, worker cancellation, current-state
playback and headless Pygame screenshots at three window sizes. Tests use temporary
saves and do not touch player progress. Screenshots go to `test-artifacts/`.

## Adding Levels

Add an enclosed `.txt` map under `levels/`. Symbols: `#` wall, space floor, `@` player,
`$` box, `.` goal, `+` player on goal, `*` box on goal. Exactly one player and an equal,
nonzero number of boxes and goals are required. All boxes and goals must be in the
same enclosed floor region as the player. Outside padding is non-playable void.

The existing PNG assets are loaded once and resized with nearest-neighbor sampling
to preserve their pixels. Text is rendered at its final font size, and Windows DPI
awareness avoids OS bitmap stretching. Movement animation
and sound cues are optional presentation details; rules and solver do not depend on
Pygame. No additional solver or audio packages are required.
# Sokoban
# GameSokoban
