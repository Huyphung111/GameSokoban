import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import sys
import tempfile
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

import pygame

try:
    from src import config
    from src.ai.ai_solver import SolveResult, solve_hill_climbing_full
except ImportError:
    import config
    from ai_solver import SolveResult, solve_hill_climbing_full

from main import App


class AppTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = App(Path(self.folder.name) / "save.json")

    def tearDown(self):
        self.app.close()
        self.folder.cleanup()

    def await_solver(self):
        deadline = time.monotonic() + 3
        while self.app.busy and time.monotonic() < deadline:
            self.app.poll_solver()
            time.sleep(.005)
        self.assertFalse(self.app.busy)

    def finish_playback(self):
        for _ in range(200):
            if not self.app.playback:
                break
            self.app.next_step = 0
            self.app.update()
        self.assertFalse(self.app.playback)

    def test_current_state_playback_and_cached_replay(self):
        self.app.move((-1, 0))
        self.app.move((-1, 0))
        self.app.start_solver("solve")
        self.await_solver()
        self.assertEqual(self.app.game.moves, 2)
        self.finish_playback()
        self.assertTrue(self.app.game.game_won)
        self.assertEqual(self.app.game.moves, 3)
        self.assertTrue(self.app.assisted)
        self.assertTrue(self.app.completion_open)
        self.app.action("replay")
        self.assertEqual(self.app.game.moves, 0)
        self.finish_playback()
        self.assertTrue(self.app.game.game_won)

    def test_hint_is_one_move_and_undoable(self):
        self.app.start_solver("hint")
        self.await_solver()
        self.assertEqual(self.app.game.moves, 1)
        self.assertFalse(self.app.playback)
        self.app.action("undo")
        self.assertEqual(self.app.game.moves, 0)
        self.app.action("redo")
        self.assertEqual(self.app.game.moves, 1)

    def test_cancelled_worker_cannot_apply_stale_result(self):
        entered, exited = Event(), Event()

        def delayed(game, cancel, **kwargs):
            entered.set()
            cancel.wait(2)
            exited.set()
            return SolveResult("solved", [(-1, 0), (-1, 0), (0, 1)])

        with patch("main.solve_a_star", delayed):
            self.app.start_solver("solve")
            self.assertTrue(entered.wait(1))
            self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
            self.assertTrue(exited.wait(1))
            self.app.update()
            self.assertEqual(self.app.game.moves, 1)
            self.assertFalse(self.app.playback)
            self.assertFalse(self.app.busy)

    def test_partial_hill_result_never_autoplays(self):
        future = Future()
        future.set_result(SolveResult("limit", [(-1, 0)]))
        self.app.future = future
        self.app.job_revision = self.app.revision
        self.app.poll_solver()
        self.assertFalse(self.app.playback)
        self.assertEqual(self.app.game.moves, 0)
        self.assertEqual(self.app.status, "Search limit reached")

    def test_level_switch_starts_fresh(self):
        self.app.move((-1, 0))
        self.app.select_level(1)
        self.assertEqual(self.app.game.moves, 0)
        self.app.select_level(0)
        self.assertEqual(self.app.game.moves, 0)
        self.assertFalse(self.app.assisted)
        self.assertFalse(self.app.completion_open)

    def test_selecting_completed_level_starts_fresh_and_keeps_stars(self):
        self.win_level()
        self.assertEqual(self.app.progress.stars(self.app.game), 3)
        self.app.select_level(1)
        self.app.select_level(0)
        self.assertEqual(self.app.game.state, self.app.game.initial_state)
        self.assertEqual(self.app.game.moves, 0)
        self.assertFalse(self.app.game.game_won)
        self.assertFalse(self.app.completion_open)
        self.assertEqual(self.app.progress.stars(self.app.game), 3)

    def test_save_survives_app_restart(self):
        self.app.move((-1, 0))
        self.app.close()
        self.app = App(Path(self.folder.name) / "save.json")
        self.assertEqual(self.app.game.moves, 1)

    def test_background_music_stops_only_after_entering_a_level(self):
        self.assertTrue(self.app.audio.music_available)
        self.assertFalse(self.app.audio.music_started)
        self.assertFalse(pygame.mixer.music.get_busy())

        self.app.action("home")
        self.assertTrue(self.app.title_screen)
        self.assertTrue(self.app.audio.music_started)
        self.assertTrue(pygame.mixer.music.get_busy())

        self.app.action("select_level_menu")
        self.assertTrue(self.app.menu_open)
        self.assertTrue(pygame.mixer.music.get_busy())

        self.app.select_level(0)
        self.assertFalse(pygame.mixer.music.get_busy())
        self.app.action("home")
        self.assertTrue(pygame.mixer.music.get_busy())

        self.app.action("sound")
        self.assertFalse(self.app.audio.enabled)
        self.assertFalse(pygame.mixer.music.get_busy())
        self.app.action("sound")
        self.assertTrue(self.app.audio.enabled)
        self.assertTrue(pygame.mixer.music.get_busy())

        self.app.action("start_game")
        self.assertFalse(self.app.title_screen)
        self.assertFalse(pygame.mixer.music.get_busy())
        self.assertTrue(self.app.audio.enabled)

    def win_level(self):
        for move in [(-1, 0), (-1, 0), (0, 1)]:
            self.app.move(move)
        self.assertTrue(self.app.game.game_won)

    def click_action(self, action):
        if self.app.completion_open:
            with patch("src.ui.renderer.pygame.time.get_ticks",
                       return_value=self.app.completion_due):
                self.app.renderer.draw(self.app.screen, self.app)
        else:
            self.app.renderer.draw(self.app.screen, self.app)
        rect = next(rect for rect, name, enabled, _ in self.app.renderer.buttons if name == action and enabled)
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))

    def test_win_menu_next_level_by_mouse(self):
        self.win_level()
        self.assertTrue(self.app.completion_open)
        self.click_action("next")
        self.assertEqual(self.app.level_index, 1)
        self.assertFalse(self.app.completion_open)
        self.assertEqual(self.app.game.moves, 0)

    def test_win_menu_waits_for_every_box(self):
        self.app.select_level(1)
        goal_sound = Mock()
        self.app.audio.sounds["goal"] = goal_sound
        result = solve_hill_climbing_full(self.app.game, max_steps=1)
        for move in result.path:
            self.app.move(move)
        self.assertEqual(len(self.app.game.state[1] & self.app.game.goals), 1)
        self.assertFalse(self.app.completion_open)
        goal_sound.play.assert_called_once_with()

    def test_win_menu_dismiss_undo_redo_restart(self):
        self.win_level()
        self.click_action("dismiss_completion")
        self.app.update()
        self.assertFalse(self.app.completion_open)
        self.assertTrue(self.app.game.game_won)
        self.app.action("undo")
        self.assertFalse(self.app.completion_open)
        self.app.action("redo")
        self.assertTrue(self.app.completion_open)
        self.click_action("reset")
        self.assertFalse(self.app.completion_open)
        self.assertFalse(self.app.game.game_won)
        self.assertEqual(self.app.game.moves, 0)

    def test_completion_animation_starts_once_and_restarts(self):
        self.win_level()
        self.app.completion_due = 0
        with patch("src.ui.renderer.pygame.time.get_ticks", return_value=1000):
            self.app.renderer.draw(self.app.screen, self.app)
        self.assertEqual(self.app.renderer.completion_animation_start, 1000)

        with patch("src.ui.renderer.pygame.time.get_ticks", return_value=1500):
            self.app.renderer.draw(self.app.screen, self.app)
        self.assertEqual(self.app.renderer.completion_animation_start, 1000)

        self.app.action("dismiss_completion")
        self.app.renderer.draw(self.app.screen, self.app)
        self.app.action("undo")
        self.app.action("redo")
        with patch("src.ui.renderer.pygame.time.get_ticks", return_value=2000):
            self.app.renderer.draw(self.app.screen, self.app)
        self.assertEqual(self.app.renderer.completion_animation_start, 2000)

    def test_completion_waits_for_final_goal_effect(self):
        self.app.move((-1, 0))
        self.app.move((-1, 0))
        self.app.renderer.draw(self.app.screen, self.app)

        with patch("main.pygame.time.get_ticks", return_value=1000):
            self.app.move((0, 1))

        self.assertTrue(self.app.completion_open)
        self.assertEqual(
            self.app.completion_due,
            1000 + config.MOVE_ANIMATION_MS + config.GOAL_EFFECT_MS,
        )
        with patch("main.pygame.time.get_ticks", return_value=self.app.completion_due - 1):
            self.assertFalse(self.app.completion_visible)
        with patch("main.pygame.time.get_ticks", return_value=self.app.completion_due):
            self.assertTrue(self.app.completion_visible)

    def test_win_menu_enter_and_final_level(self):
        self.win_level()
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(self.app.level_index, 1)
        self.app.select_level(len(self.app.levels) - 1)
        # Only the final-level menu is under test; avoid searching the 14-box map.
        self.app.game.state = self.app.game.state[0], self.app.game.goals
        self.app.changed()
        self.app.renderer.draw(self.app.screen, self.app)
        self.assertNotIn("next", [name for _, name, _, _ in self.app.renderer.buttons])
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertTrue(self.app.menu_open)
        self.assertFalse(self.app.completion_open)

    def test_completion_blocks_background_controls(self):
        self.app.renderer.draw(self.app.screen, self.app)
        background = next(rect.center for rect, name, _, _ in self.app.renderer.buttons if name == "levels")
        self.win_level()
        self.app.renderer.draw(self.app.screen, self.app)
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=background))
        self.assertFalse(self.app.menu_open)
        self.assertTrue(self.app.completion_open)
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
        self.assertTrue(self.app.completion_open)
        self.assertEqual(self.app.game.moves, 3)

    def test_upscaled_assets_preserve_source_colors(self):
        self.app.renderer.draw(self.app.screen, self.app)
        self.assertGreater(self.app.renderer.tile_size, 64)
        box = self.app.renderer.assets["$"]
        self.assertEqual(box.get_bounding_rect(min_alpha=8), box.get_rect())

        def colors(surface):
            pixels = pygame.image.tobytes(surface, "RGBA")
            return {pixels[i:i + 4] for i in range(0, len(pixels), 4)}

        for tile, resized in self.app.renderer.assets.items():
            with self.subTest(tile=tile):
                self.assertLessEqual(colors(resized), colors(self.app.renderer.originals[tile]))

    def test_player_animation_frames_and_actions(self):
        self.app.renderer.draw(self.app.screen, self.app)
        frames = self.app.renderer.player_frames
        self.assertEqual(set(frames), {"idle", "walk", "push"})
        for directions in frames.values():
            self.assertEqual(set(directions), {"up", "down", "left", "right"})
            for action_frames in directions.values():
                self.assertEqual(len(action_frames), 4)
                for frame in action_frames:
                    self.assertEqual(frame.get_size(), (self.app.renderer.tile_size,) * 2)

        first_idle_frames = [pygame.image.tobytes(frames["idle"][direction][0], "RGBA")
                             for direction in ("up", "down", "left", "right")]
        self.assertEqual(len(set(first_idle_frames)), 4)
        for source in self.app.renderer.player_direction_sources.values():
            self.assertEqual(source.get_at((0, 0)).a, 0)

        self.app.move((-1, 0))
        self.app.renderer.draw(self.app.screen, self.app)
        self.assertEqual(self.app.renderer.player_action, "walk")
        self.assertEqual(self.app.renderer.player_facing, (-1, 0))

        self.app.move((-1, 0))
        self.app.renderer.draw(self.app.screen, self.app)
        self.app.move((0, 1))
        self.app.renderer.draw(self.app.screen, self.app)
        self.assertEqual(self.app.renderer.player_action, "push")
        self.assertEqual(self.app.renderer.player_facing, (0, 1))

    def test_player_faces_each_keyboard_direction(self):
        self.app.select_level(1)
        self.app.renderer.draw(self.app.screen, self.app)
        for key, direction in ((pygame.K_UP, (0, -1)), (pygame.K_RIGHT, (1, 0)),
                               (pygame.K_DOWN, (0, 1)), (pygame.K_LEFT, (-1, 0))):
            self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
            self.app.renderer.draw(self.app.screen, self.app)
            self.assertEqual(self.app.renderer.player_facing, direction)

    def test_undoing_push_does_not_play_push_animation(self):
        for move in ((-1, 0), (-1, 0), (0, 1)):
            self.app.move(move)
            self.app.renderer.draw(self.app.screen, self.app)
        self.app.action("undo")
        self.app.renderer.draw(self.app.screen, self.app)
        self.assertEqual(self.app.renderer.player_action, "walk")

    def test_completion_layout_at_all_window_sizes(self):
        self.win_level()
        output = config.BASE_DIR / "test-artifacts"
        output.mkdir(exist_ok=True)
        for width, height in ((480, 520), (900, 760), (1200, 800)):
            self.app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=width, h=height))
            self.app.renderer.draw(self.app.screen, self.app)
            rects = [rect for rect, _, _, _ in self.app.renderer.buttons]
            for index, rect in enumerate(rects):
                self.assertTrue(self.app.screen.get_rect().contains(rect))
                self.assertFalse(any(rect.colliderect(other) for other in rects[index + 1:]))
            pygame.image.save(self.app.screen, str(output / f"completed-{width}.png"))

    def test_responsive_layout_and_assets(self):
        output = config.BASE_DIR / "test-artifacts"
        output.mkdir(exist_ok=True)
        for size in ((480, 520), (900, 760), (1200, 800)):
            with self.subTest(size=size):
                self.app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=size[0], h=size[1]))
                self.app.renderer.draw(self.app.screen, self.app)
                rects = [rect for rect, _, _, _ in self.app.renderer.buttons]
                for index, rect in enumerate(rects):
                    self.assertTrue(self.app.screen.get_rect().contains(rect))
                    self.assertFalse(any(rect.colliderect(other) for other in rects[index + 1:]))
                center = self.app.screen.subsurface((16, 180, size[0] - 32, size[1] - 300))
                pixels = pygame.image.tobytes(center, "RGB")
                colors = {pixels[index:index + 3] for index in range(0, len(pixels), 3)}
                self.assertGreater(len(colors), 20)
                pygame.image.save(self.app.screen, str(output / f"game-{size[0]}.png"))
                self.app.menu_open = True
                self.app.renderer.draw(self.app.screen, self.app)
                pygame.image.save(self.app.screen, str(output / f"levels-{size[0]}.png"))
                self.app.menu_open = False
        self.app.select_level(len(self.app.levels) - 1)
        self.app.renderer.draw(self.app.screen, self.app)
        pygame.image.save(self.app.screen, str(output / "challenge.png"))

    def test_title_screen_layout_at_all_window_sizes(self):
        output = config.BASE_DIR / "test-artifacts"
        output.mkdir(exist_ok=True)
        self.app.title_screen = True
        for width, height in ((480, 520), (900, 760), (1200, 800)):
            self.app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=width, h=height))
            self.app.renderer.draw(self.app.screen, self.app)
            rects = [rect for rect, _, _, _ in self.app.renderer.buttons]
            for index, rect in enumerate(rects):
                self.assertTrue(self.app.screen.get_rect().contains(rect))
                self.assertFalse(any(rect.colliderect(other) for other in rects[index + 1:]))
            pygame.image.save(self.app.screen, str(output / f"title-{width}.png"))


if __name__ == "__main__":
    unittest.main()
