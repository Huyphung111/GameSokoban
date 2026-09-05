import sys
import tempfile
import unittest
from collections import deque
from pathlib import Path
from threading import Event

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
        for path in config.level_files():
            with self.subTest(level=path.name):
                game = Game(path)
                self.assertEqual(len(game.state[1]), len(game.goals))


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
        self.assertTrue(self.progress.save())
        loaded = Progress(self.path)
        game = Game(config.LEVEL_FILE)
        self.assertTrue(loaded.restore(game))
        self.assertEqual(game.state, self.game.state)
        self.assertEqual(game.moves, 2)
        self.assertTrue(game.undo())

    def test_cache_is_validated_and_scoped_to_map(self):
        self.game.move_player(-1, 0)
        result = solve_a_star(self.game)
        self.progress.remember_solution(self.game, result.path)
        cached = self.progress.cached_solution(self.game)
        self.assertTrue(valid_path(self.game, self.game.initial_state, cached, True))
        other = Game(config.BASE_DIR / "levels" / "level02_two_boxes.txt")
        self.assertIsNone(self.progress.cached_solution(other))
        self.progress.entry(self.game)["solution"] = [[99, 0]]
        self.assertIsNone(self.progress.cached_solution(self.game))

    def test_invalid_saved_path_never_partially_restores(self):
        self.progress.entry(self.game)["actions"] = [[-1, 0], [99, 0]]
        self.progress.restore(self.game)
        self.assertEqual(self.game.state, self.game.initial_state)
        self.assertEqual(self.game.moves, 0)
        self.assertTrue(self.progress.error)

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

    def test_write_failure_is_reported(self):
        self.path.mkdir()
        self.assertFalse(self.progress.save())
        self.assertTrue(self.progress.error)


if __name__ == "__main__":
    unittest.main()
