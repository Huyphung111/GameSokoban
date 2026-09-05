"""Versioned progress, settings and solution cache with migration and backups."""

import json
import os
import shutil
from pathlib import Path

try:
    from src import config
    from src.ai.solutions import valid_path
except ImportError:
    import config
    from solutions import valid_path


class Progress:
    PROGRESS_VERSION = 2
    SETTINGS_VERSION = 1
    SOLUTIONS_VERSION = 1

    def __init__(self, path, settings_path=None, solutions_path=None,
                 backup_path=None, legacy_path=None):
        self.path = Path(path)
        self.settings_path = Path(settings_path or self.path.with_name(
            f"{self.path.stem}.settings.json"))
        self.solutions_path = Path(solutions_path or self.path.with_name(
            f"{self.path.stem}.solutions.json"))
        self.backup_path = Path(backup_path or self.path.with_name(
            f"{self.path.stem}.backup.json"))
        self.legacy_path = Path(legacy_path) if legacy_path else None
        self.error = ""
        self.data = {"version": self.PROGRESS_VERSION, "current": "", "levels": {}}
        self.settings = {"version": self.SETTINGS_VERSION, "sound": True}
        self.solutions = {"version": self.SOLUTIONS_VERSION, "levels": {}}

        source = self.path
        if (not source.exists() and not self.backup_path.exists()
                and self.legacy_path and self.legacy_path.exists()):
            source = self.legacy_path
        raw = self._load_with_backup(source, self.backup_path, self._valid_progress)
        if raw is not None:
            self._import_progress(raw)

        settings = self._load_with_backup(
            self.settings_path, self._backup_for(self.settings_path), self._valid_settings,
            report_missing=False)
        if settings is not None:
            self.settings = settings

        solutions = self._load_with_backup(
            self.solutions_path, self._backup_for(self.solutions_path), self._valid_solutions,
            report_missing=False)
        if solutions is not None:
            self.solutions = solutions

    @staticmethod
    def _backup_for(path):
        return path.with_name(f"{path.stem}.backup.json")

    @staticmethod
    def _valid_progress(raw):
        return (isinstance(raw, dict) and raw.get("version") in (1, 2)
                and isinstance(raw.get("levels"), dict)
                and all(isinstance(value, dict) for value in raw["levels"].values()))

    @staticmethod
    def _valid_settings(raw):
        return (isinstance(raw, dict) and raw.get("version") == 1
                and type(raw.get("sound")) is bool)

    @staticmethod
    def _valid_solutions(raw):
        return (isinstance(raw, dict) and raw.get("version") == 1
                and isinstance(raw.get("levels"), dict)
                and all(isinstance(value, dict) for value in raw["levels"].values()))

    def _load_with_backup(self, path, backup, validator, report_missing=True):
        if not path.exists():
            if backup.exists():
                try:
                    raw = json.loads(backup.read_text(encoding="utf-8"))
                    if validator(raw):
                        self.error = f"{path.name} was restored from backup."
                        return raw
                except (OSError, ValueError, TypeError):
                    pass
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not validator(raw):
                raise ValueError("Invalid data format")
            return raw
        except (OSError, ValueError, TypeError):
            try:
                raw = json.loads(backup.read_text(encoding="utf-8"))
                if not validator(raw):
                    raise ValueError("Invalid backup format")
                self.error = f"{path.name} was restored from backup."
                return raw
            except (OSError, ValueError, TypeError):
                if report_missing or path.exists():
                    self.error = f"{path.name} could not be read; using safe defaults."
                return None

    def _import_progress(self, raw):
        current = raw.get("current", "")
        self.data["current"] = current if isinstance(current, str) else ""
        self.data["levels"] = dict(raw["levels"])
        if raw.get("version") == 1 and type(raw.get("sound")) is bool:
            self.settings["sound"] = raw["sound"]

    @property
    def sound(self):
        return self.settings["sound"]

    @sound.setter
    def sound(self, value):
        self.settings["sound"] = bool(value)

    def register_levels(self, games):
        """Eagerly migrate hash-keyed v1 entries for every known bundled level."""
        for game in games:
            self.entry(game)
            if self.data["current"] == game.current_level_path.name:
                self.data["current"] = game.level_key

    @staticmethod
    def _records(entry):
        keys = ("completed", "stars", "best", "best_assisted")
        return {key: entry[key] for key in keys if key in entry}

    def entry(self, game):
        levels = self.data["levels"]
        entry = levels.get(game.level_key)
        legacy = levels.pop(game.level_id, None)
        if entry is None:
            entry = legacy if legacy is not None else {}
            levels[game.level_key] = entry
        elif legacy:
            for key, value in legacy.items():
                entry.setdefault(key, value)

        legacy_solution = entry.pop("solution", None)
        if legacy_solution is not None and valid_path(
                game, game.initial_state, legacy_solution, require_win=True):
            self.solutions["levels"][game.level_key] = {
                "content_hash": game.level_id,
                "path": legacy_solution,
            }

        content_hash = entry.get("content_hash")
        if content_hash is not None and content_hash != game.level_id:
            entry = self._records(entry)
            levels[game.level_key] = entry
            self.solutions["levels"].pop(game.level_key, None)
        entry["content_hash"] = game.level_id
        return entry

    def restore(self, game):
        entry = self.entry(game)
        path = entry.get("actions", [])
        if not valid_path(game, game.initial_state, path):
            entry["actions"] = []
            entry["assisted"] = False
            self.error = "Saved moves are invalid; level restarted."
            return False
        for move in path:
            game.move_player(*move)
        return bool(entry.get("assisted", False))

    def capture(self, game, assisted=False):
        entry = self.entry(game)
        entry["actions"] = game.actions
        entry["assisted"] = assisted
        self.data["current"] = game.level_key
        if game.game_won:
            entry["completed"] = True
            old_stars = entry.get("stars", 0)
            if type(old_stars) is not int or not 0 <= old_stars <= 3:
                old_stars = 0
            entry["stars"] = max(
                old_stars,
                config.star_rating(game.current_level_path.name, game.moves),
            )
            key = "best_assisted" if assisted else "best"
            score = [game.pushes, game.moves]
            old = entry.get(key)
            if (not isinstance(old, list) or len(old) != 2
                    or not all(type(number) is int and number >= 0 for number in old)
                    or score < old):
                entry[key] = score

    def stars(self, game):
        """Return saved stars, with backward-compatible inference for old saves."""
        entry = self.entry(game)
        if not entry.get("completed"):
            return 0
        saved = entry.get("stars")
        if type(saved) is int and 1 <= saved <= 3:
            return saved
        ratings = [1]
        for key in ("best", "best_assisted"):
            score = entry.get(key)
            if (isinstance(score, list) and len(score) == 2
                    and type(score[1]) is int and score[1] >= 0):
                ratings.append(config.star_rating(game.current_level_path.name, score[1]))
        return max(ratings)

    def remember_solution(self, game, path):
        if valid_path(game, game.state, path, require_win=True):
            full_path = game.actions + list(path)
            if valid_path(game, game.initial_state, full_path, require_win=True):
                self.solutions["levels"][game.level_key] = {
                    "content_hash": game.level_id,
                    "path": full_path,
                }

    def cached_solution(self, game):
        cached = self.solutions["levels"].get(game.level_key, {})
        if cached.get("content_hash") != game.level_id:
            return None
        path = cached.get("path")
        if not valid_path(game, game.initial_state, path, require_win=True):
            return None
        return [tuple(move) for move in path]

    def _atomic_write(self, path, payload, backup, validator):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            if path.is_file():
                try:
                    current = json.loads(path.read_text(encoding="utf-8"))
                    if validator(current):
                        shutil.copy2(path, backup)
                except (OSError, ValueError, TypeError):
                    pass
            os.replace(temporary, path)
            return True
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def save(self):
        writes = (
            self._atomic_write(self.path, self.data, self.backup_path, self._valid_progress),
            self._atomic_write(self.settings_path, self.settings,
                               self._backup_for(self.settings_path), self._valid_settings),
            self._atomic_write(self.solutions_path, self.solutions,
                               self._backup_for(self.solutions_path), self._valid_solutions),
        )
        if all(writes):
            self.error = ""
            return True
        self.error = "Player data could not be saved."
        return False
