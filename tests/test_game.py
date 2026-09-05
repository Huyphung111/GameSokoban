import json
import sys
import tempfile
import unittest
from collections import deque
from pathlib import Path
from threading import Event
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

try:
    from src import config
    from src.ai.ai_solver import solve_a_star, solve_hill_climbing_full
    from src.ai.solutions import valid_path
    from src.core.game import DIRECTIONS, Game, transition
    from src.core.progress import Progress
except ImportError:
    import config
    from ai_solver import solve_a_star, solve_hill_climbing_full
    from game import DIRECTIONS, Game, transition
    from progress import Progress, valid_path


class GameTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "map.txt"
        self.game = Game(config.LEVEL_FILE)

    def level(self, content):
        self.path.write_text(content, encoding="utf-8")
        return Game(self.path)

    def test_moves_push_win_and_undo_redo(self):
        game = self.game
        initial = game.state
        self.assertFalse(game.move_player(1, 0))
        self.assertFalse(game.move_player(2, 0))
        self.assertEqual(game.moves, 0)
        for move in [(-1, 0), (-1, 0), (0, 1)]:
            self.assertTrue(game.move_player(*move))
        self.assertTrue(game.game_won)
        self.assertEqual((game.moves, game.pushes), (3, 1))
        self.assertFalse(game.move_player(1, 0))
        self.assertTrue(game.undo())
        self.assertFalse(game.game_won)
        self.assertEqual((game.moves, game.pushes), (2, 0))
        self.assertTrue(game.redo())
        self.assertTrue(game.game_won)
        game.reset_level()
        self.assertEqual(game.state, initial)
        self.assertFalse(game.can_undo)
        self.assertFalse(game.can_redo)

    def test_new_move_discards_redo(self):
        self.game.move_player(-1, 0)
        self.game.undo()
        self.game.move_player(0, 1)
        self.assertFalse(self.game.can_redo)

    def test_box_on_goal_can_be_moved_and_restores_goal(self):
        game = self.level("########\n# @*   #\n# $ .  #\n########\n")
        self.assertTrue(game.move_player(1, 0))
        self.assertEqual(game.game_map[1][3], "+")
        self.assertTrue(game.move_player(1, 0))
        self.assertEqual(game.game_map[1][3], ".")
        game.undo()
        game.undo()
        self.assertEqual(game.game_map[1][3], "*")

    def test_initially_solved(self):
        game = self.level("#####\n#@* #\n#####\n")
        self.assertTrue(game.game_won)
        result = solve_a_star(game)
        self.assertEqual((result.status, result.path), ("solved", []))

    def test_invalid_levels_rejected(self):
        cases = ["", "#####\n#@@$#\n# . #\n#####", "#####\n# $ #\n# . #\n#####",
                 "#####\n#@  #\n#####", "######\n#@$$.#\n######",
                 "######\n#@x$.#\n######", "#####\n#@$. \n#####",
                 "#########\n#@  #$. #\n#########"]
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.level(content)

    def test_padding_is_not_floor(self):
        game = self.level("#####   \n#@$.#\n#####\n")
        self.assertNotIn((6, 1), game.floors)
        self.assertEqual(game.game_map[1][6], "~")

    def test_static_deadlock(self):
        game = self.level("######\n#$ @ #\n#  . #\n######\n")
        self.assertTrue(game.is_deadlocked())
        self.assertEqual(solve_a_star(game).status, "deadlock")

    def test_box_block_deadlock(self):
        game = self.level("########\n#@     #\n# $$   #\n# $$   #\n# .... #\n#      #\n########\n")
        self.assertFalse(game.state[1] & game.dead_squares)
        self.assertTrue(game.is_deadlocked())

    def test_all_bundled_levels_validate(self):
        self.assertEqual(config.USER_DATA_DIR, config.BASE_DIR / "data")
        for path in config.level_files():
            with self.subTest(level=path.name):
                game = Game(path)
                self.assertEqual(len(game.state[1]), len(game.goals))
                self.assertEqual(game.level_key, path.stem.split("_", 1)[0])


class SolverTests(unittest.TestCase):
    def test_solution_from_current_state_does_not_reset_or_mutate(self):
        game = Game(config.LEVEL_FILE)
        game.move_player(-1, 0)
        game.move_player(-1, 0)
        before = game.state, game.actions, game.moves
        result = solve_a_star(game)
        self.assertEqual(result.status, "solved")
        self.assertEqual(result.path, [(0, 1)])
        self.assertEqual((game.state, game.actions, game.moves), before)
        for move in result.path:
            game.move_player(*move)
        self.assertTrue(game.game_won)

    def test_small_levels_match_independent_minimum_push_search(self):
        # 0-1 BFS over individual player moves is independent of macro-push A*.
        for path in config.level_files():
            if path.name == "level11_final_challenge.txt":
                continue
            with self.subTest(level=path.name):
                game = Game(path)
                costs, queue = {game.state: 0}, deque([game.state])
                best = None
                while queue:
                    state = queue.popleft()
                    if state[1] == game.goals:
                        best = costs[state]
                        break
                    for direction in DIRECTIONS:
                        result = transition(game.floors, state, direction)
                        if result is None:
                            continue
                        following, pushed = result
                        cost = costs[state] + int(pushed)
                        if cost < costs.get(following, float("inf")):
                            costs[following] = cost
                            (queue.append if pushed else queue.appendleft)(following)
                result = solve_a_star(game)
                self.assertEqual(result.status, "solved")
                self.assertEqual(result.pushes, best)
                self.assertTrue(valid_path(game, game.state, result.path, True))

    def test_cancel_and_limits(self):
        game = Game(config.LEVEL_FILE)
        event = Event()
        event.set()
        self.assertEqual(solve_a_star(game, cancel=event).status, "cancelled")
        self.assertEqual(solve_a_star(game, max_states=0).status, "limit")
        self.assertEqual(solve_a_star(game, max_seconds=0).status, "limit")
        self.assertEqual(solve_hill_climbing_full(game, cancel=event).status, "cancelled")

    def test_hill_partial_path_is_not_solution(self):
        game = Game(config.BASE_DIR / "levels" / "level02_two_boxes.txt")
        result = solve_hill_climbing_full(game, max_steps=1)
        self.assertEqual(result.status, "limit")
        self.assertTrue(result.path)
        self.assertFalse(valid_path(game, game.state, result.path, True))
        again = solve_hill_climbing_full(game, max_steps=1)
        self.assertEqual(result.path, again.path)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "progress.json"
        self.progress = Progress(self.path)
        self.game = Game(config.LEVEL_FILE)

    def test_save_restore_and_undo_after_reload(self):
        self.game.move_player(-1, 0)
        self.game.move_player(-1, 0)
        self.progress.capture(self.game, True)
        result = solve_a_star(self.game)
        self.progress.remember_solution(self.game, result.path)
        self.assertTrue(self.progress.save())
        progress_raw = json.loads(self.path.read_text(encoding="utf-8"))
        solutions_raw = json.loads(
            self.progress.solutions_path.read_text(encoding="utf-8"))
        self.assertEqual(progress_raw["version"], 3)
        self.assertEqual(progress_raw["levels"][self.game.level_key]["actions"], "LL")
        self.assertEqual(solutions_raw["version"], 2)
        self.assertEqual(solutions_raw["levels"][self.game.level_key]["path"], "LLD")
        loaded = Progress(self.path)
        game = Game(config.LEVEL_FILE)
        self.assertTrue(loaded.restore(game))
        self.assertEqual(game.state, self.game.state)
        self.assertEqual(game.moves, 2)
        self.assertTrue(game.undo())
        self.assertTrue(valid_path(game, game.initial_state,
                                   loaded.cached_solution(game), True))

    def test_cache_is_validated_and_scoped_to_map(self):
        self.game.move_player(-1, 0)
        result = solve_a_star(self.game)
        self.progress.remember_solution(self.game, result.path)
        cached = self.progress.cached_solution(self.game)
        self.assertTrue(valid_path(self.game, self.game.initial_state, cached, True))
        other = Game(config.BASE_DIR / "levels" / "level02_two_boxes.txt")
        self.assertIsNone(self.progress.cached_solution(other))
        self.progress.solutions["levels"][self.game.level_key]["path"] = [[99, 0]]
        self.assertIsNone(self.progress.cached_solution(self.game))

    def test_v1_save_migrates_to_stable_level_keys_and_split_files(self):
        result = solve_a_star(self.game)
        legacy = {
            "version": 1,
            "current": self.game.current_level_path.name,
            "sound": False,
            "levels": {
                self.game.level_id: {
                    "actions": [[-1, 0]],
                    "assisted": True,
                    "completed": True,
                    "stars": 2,
                    "solution": result.path,
                }
            },
        }
        self.path.write_text(json.dumps(legacy), encoding="utf-8")

        migrated = Progress(self.path)
        migrated.register_levels([self.game])
        entry = migrated.entry(self.game)
        self.assertNotIn(self.game.level_id, migrated.data["levels"])
        self.assertIn(self.game.level_key, migrated.data["levels"])
        self.assertEqual(entry["content_hash"], self.game.level_id)
        self.assertEqual(migrated.data["current"], self.game.level_key)
        self.assertFalse(migrated.sound)
        self.assertEqual(migrated.cached_solution(self.game), result.path)
        self.assertTrue(migrated.save())

        self.assertEqual(json.loads(self.path.read_text())["version"], 3)
        self.assertTrue(migrated.settings_path.is_file())
        self.assertTrue(migrated.solutions_path.is_file())

    def test_save_only_writes_changed_data_file(self):
        self.assertTrue(self.progress.save())
        with patch.object(self.progress, "_atomic_write",
                          wraps=self.progress._atomic_write) as writer:
            self.progress.data["current"] = "level02"
            self.assertTrue(self.progress.save())
            self.assertEqual([call.args[0] for call in writer.call_args_list],
                             [self.progress.path])

            writer.reset_mock()
            self.progress.sound = False
            self.assertTrue(self.progress.save())
            self.assertEqual([call.args[0] for call in writer.call_args_list],
                             [self.progress.settings_path])

            writer.reset_mock()
            result = solve_a_star(self.game)
            self.progress.remember_solution(self.game, result.path)
            self.assertTrue(self.progress.save())
            self.assertEqual([call.args[0] for call in writer.call_args_list],
                             [self.progress.solutions_path])

            writer.reset_mock()
            self.assertTrue(self.progress.save())
            writer.assert_not_called()
        self.assertFalse(self.progress.settings_path.with_name(
            f"{self.progress.settings_path.stem}.backup.json").exists())
        self.assertFalse(self.progress.solutions_path.with_name(
            f"{self.progress.solutions_path.stem}.backup.json").exists())

    def test_legacy_location_is_imported_without_modifying_source(self):
        legacy_path = Path(self.folder.name) / "legacy" / "progress.json"
        new_path = Path(self.folder.name) / "user-data" / "progress.json"
        legacy_path.parent.mkdir()
        legacy = {"version": 1, "current": self.game.current_level_path.name,
                  "sound": False, "levels": {self.game.level_id: {"stars": 2,
                  "completed": True}}}
        original = json.dumps(legacy)
        legacy_path.write_text(original, encoding="utf-8")

        migrated = Progress(new_path, legacy_path=legacy_path)
        migrated.register_levels([self.game])
        self.assertFalse(migrated.sound)
        self.assertEqual(migrated.stars(self.game), 2)
        self.assertTrue(migrated.save())
        self.assertEqual(legacy_path.read_text(encoding="utf-8"), original)
        self.assertTrue(new_path.is_file())

    def test_level_content_change_keeps_records_but_resets_volatile_data(self):
        entry = self.progress.entry(self.game)
        entry.update({"content_hash": "old", "actions": [[-1, 0]],
                      "assisted": True, "completed": True, "stars": 3,
                      "best": [1, 3]})
        self.progress.solutions["levels"][self.game.level_key] = {
            "content_hash": "old", "path": [[-1, 0]]}

        refreshed = self.progress.entry(self.game)
        self.assertTrue(refreshed["completed"])
        self.assertEqual(refreshed["stars"], 3)
        self.assertEqual(refreshed["best"], [1, 3])
        self.assertNotIn("actions", refreshed)
        self.assertNotIn(self.game.level_key, self.progress.solutions["levels"])

    def test_corrupt_progress_recovers_from_last_valid_backup(self):
        self.progress.data["current"] = "first"
        self.assertTrue(self.progress.save())
        self.progress.data["current"] = "second"
        self.assertTrue(self.progress.save())
        self.path.write_text("{broken", encoding="utf-8")

        recovered = Progress(self.path)
        self.assertEqual(recovered.data["current"], "first")
        self.assertIn("restored from backup", recovered.error)

        self.path.unlink()
        recovered = Progress(self.path)
        self.assertEqual(recovered.data["current"], "first")
        self.assertIn("restored from backup", recovered.error)

    def test_invalid_saved_path_never_partially_restores(self):
        self.progress.entry(self.game)["actions"] = [[-1, 0], [99, 0]]
        self.progress.restore(self.game)
        self.assertEqual(self.game.state, self.game.initial_state)
        self.assertEqual(self.game.moves, 0)
        self.assertTrue(self.progress.error)

    def test_invalid_encoded_moves_are_rejected(self):
        payload = {"version": 3, "current": self.game.level_key, "levels": {
            self.game.level_key: {"content_hash": self.game.level_id,
                                  "actions": "LX", "assisted": False}}}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = Progress(self.path)
        game = Game(config.LEVEL_FILE)
        self.assertFalse(loaded.restore(game))
        self.assertEqual(game.state, game.initial_state)
        self.assertTrue(loaded.error)

    def test_corrupt_json_and_schema(self):
        for raw in ("{bad", "null", "[]", '{"version":1,"levels":{"a":[]}}'):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                loaded = Progress(self.path)
                self.assertTrue(loaded.error)
                self.assertEqual(loaded.data["levels"], {})

    def test_assisted_scores_do_not_replace_solo_scores(self):
        result = solve_a_star(self.game)
        for move in result.path:
            self.game.move_player(*move)
        self.progress.capture(self.game, True)
        self.assertNotIn("best", self.progress.entry(self.game))
        self.progress.capture(self.game, False)
        self.assertEqual(self.progress.entry(self.game)["best"], [1, 3])

    def test_star_thresholds_and_completion_floor(self):
        level = "level01_first_step.txt"
        self.assertEqual(config.star_rating(level, 3), 3)
        self.assertEqual(config.star_rating(level, 4), 2)
        self.assertEqual(config.star_rating(level, 99), 1)
        self.assertEqual(config.star_rating(level, 3, completed=False), 0)

    def test_stars_are_saved_and_old_completions_are_inferred(self):
        for move in ((-1, 0), (-1, 0), (0, 1)):
            self.game.move_player(*move)
        self.progress.capture(self.game, False)
        self.assertEqual(self.progress.entry(self.game)["stars"], 3)
        self.assertEqual(self.progress.stars(self.game), 3)

        entry = self.progress.entry(self.game)
        entry.pop("stars")
        entry["best"] = [1, 99]
        self.assertEqual(self.progress.stars(self.game), 1)

    def test_write_failure_is_reported(self):
        self.path.mkdir()
        self.assertFalse(self.progress.save())
        self.assertTrue(self.progress.error)


if __name__ == "__main__":
    unittest.main()
