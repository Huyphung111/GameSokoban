"""Reproducible CLI comparison; never reads or changes player progress."""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

try:
    from src import config
    from src.ai.ai_solver import solve_a_star, solve_hill_climbing_full
    from src.ai.solutions import valid_path
    from src.core.game import Game
except ImportError:
    import config
    from ai_solver import solve_a_star, solve_hill_climbing_full
    from game import Game
    from progress import valid_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = []
    for path in config.level_files():
        for name, solver in (("A*", solve_a_star), ("Hill climbing", solve_hill_climbing_full)):
            game = Game(path)
            options = {"max_seconds": args.seconds}
            if name == "Hill climbing":
                options["seed"] = args.seed
            result = solver(game, **options)
            verified = result.status == "solved" and valid_path(game, game.state, result.path, True)
            row = {"level": path.name, "algorithm": name, "status": result.status,
                   "verified": verified, "seconds": round(result.elapsed, 4),
                   "states": result.explored, "moves": len(result.path),
                   "pushes": result.pushes, "seed": args.seed if name != "A*" else None}
            rows.append(row)
            print(json.dumps(row))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
