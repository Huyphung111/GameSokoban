"""Versioned, atomic progress saves. Restore states by replaying legal moves."""

import json
from pathlib import Path

try:
    from src.ai.solutions import valid_path
except ImportError:
    from solutions import valid_path


class Progress:
    def __init__(self, path):
        self.path = Path(path)
        self.error = ""
        self.data = {"version": 1, "current": "", "levels": {}, "sound": True}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(raw, dict) or raw.get("version") != 1
                    or not isinstance(raw.get("levels"), dict)
                    or not all(isinstance(v, dict) for v in raw["levels"].values())):
                raise ValueError("Invalid save format")
            self.data.update(raw)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.error = "Save could not be read; starting fresh."

    def entry(self, game):
        return self.data["levels"].setdefault(game.level_id, {})

    def restore(self, game):
        entry = self.entry(game)
        path = entry.get("actions", [])
        if not valid_path(game, game.initial_state, path):
            self.error = "Saved moves are invalid; level restarted."
            return False
        for move in path:
            game.move_player(*move)
        return bool(entry.get("assisted", False))

    def capture(self, game, assisted=False):
        entry = self.entry(game)
        entry["actions"] = game.actions
        entry["assisted"] = assisted
        self.data["current"] = game.current_level_path.name
        if game.game_won:
            entry["completed"] = True
            key = "best_assisted" if assisted else "best"
            score = [game.pushes, game.moves]
            old = entry.get(key)
            if (not isinstance(old, list) or len(old) != 2
                    or not all(type(n) is int and n >= 0 for n in old) or score < old):
                entry[key] = score

    def remember_solution(self, game, path):
        if valid_path(game, game.state, path, require_win=True):
            full_path = game.actions + list(path)
            if valid_path(game, game.initial_state, full_path, require_win=True):
                self.entry(game)["solution"] = full_path

    def cached_solution(self, game):
        path = self.entry(game).get("solution")
        if not valid_path(game, game.initial_state, path, require_win=True):
            return None
        return [tuple(move) for move in path]

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            self.error = ""
            return True
        except OSError:
            self.error = "Progress could not be saved."
            return False
