"""Interactive Sokoban with cancellable background assistance."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import copy
import os
from threading import Event
from time import monotonic

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

import pygame

try:
    from src import config
    from src.ai.ai_solver import solve_a_star, solve_hill_climbing_full
    from src.ai.solutions import valid_path
    from src.core.game import Game
    from src.core.progress import Progress
    from src.ui.audio import Audio
    from src.ui.renderer import Renderer
except ImportError:
    import config
    from ai_solver import solve_a_star, solve_hill_climbing_full
    from audio import Audio
    from game import Game
    from progress import Progress
    from renderer import Renderer
    from solutions import valid_path


class App:
    def __init__(self, save_path=None, start_title=None):
        # Prevent Windows from stretching the entire window as a bitmap.
        os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Sokoban")
        self.screen = pygame.display.set_mode(
            (config.INITIAL_SCREEN_WIDTH, config.INITIAL_SCREEN_HEIGHT), pygame.RESIZABLE)
        self.renderer = Renderer(config.FONT_PATH)
        self.progress = Progress(save_path or config.SAVE_FILE)
        self.audio = Audio(bool(self.progress.data.get("sound", True)))
        self.levels, self.catalog, errors = [], [], []
        for path in config.level_files():
            try:
                self.catalog.append(Game(path))
                self.levels.append(path)
            except (OSError, ValueError) as error:
                errors.append(f"{path.name}: {error}")
        if not self.levels:
            raise ValueError("No valid levels found: " + "; ".join(errors))
        selected = self.progress.data.get("current")
        self.level_index = next((i for i, path in enumerate(self.levels) if path.name == selected), 0)
        self.game = Game(self.levels[self.level_index])
        self.assisted = self.progress.restore(self.game)
        self.status = f"{len(errors)} invalid level(s) skipped" if errors else "Ready"
        for error in errors:
            print(error)
        self.metrics = ""
        self.title_screen = (save_path is None) if start_title is None else bool(start_title)
        self.menu_open = False
        self.completion_open = self.game.game_won
        self.completion_due = 0
        self.deadlock_open = False
        self.menu_offset = 0
        self.fullscreen = False
        self.window_size = self.screen.get_size()
        self.playback = deque()
        self.playback_ms = config.PLAYBACK_MS
        self.next_step = 0
        self.future = None
        self.cancel_event = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sokoban-solver")
        self.revision = 0
        self.job_revision = 0
        self.job_mode = "solve"
        self.job_started = 0
        self.running = True
        self.refresh()
        self.deadlock_open = self.deadlocked

    @property
    def busy(self):
        return self.future is not None

    @property
    def completion_visible(self):
        return self.completion_open and pygame.time.get_ticks() >= self.completion_due

    def refresh(self):
        self.deadlocked = self.game.is_deadlocked()
        self.has_cached_solution = self.progress.cached_solution(self.game) is not None

    def save(self):
        self.progress.capture(self.game, self.assisted)
        self.progress.data["sound"] = self.audio.enabled
        self.progress.save()

    def stop(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
        if self.future is not None:
            self.future.cancel()
        self.future = None
        self.playback.clear()
        self.revision += 1

    def changed(self, preserve_effects=False):
        self.revision += 1
        was_deadlocked = self.deadlocked
        if not preserve_effects:
            self.renderer.clear_effects()
            self.completion_due = 0
        self.completion_open = self.game.game_won
        if self.completion_open:
            self.menu_open = False
        self.refresh()
        if not self.deadlocked:
            self.deadlock_open = False
        elif not was_deadlocked or not preserve_effects:
            self.deadlock_open = True
            self.menu_open = False
            self.stop()
        self.save()

    def move(self, direction, assisted=False):
        previous_pushes = self.game.pushes
        previous_boxes = self.game.state[1]
        if not self.game.move_player(*direction):
            return False
        self.assisted |= assisted
        new_goals = (self.game.state[1] - previous_boxes) & self.game.goals
        self.audio.play("win" if self.game.game_won else "goal" if new_goals
                        else "push" if self.game.pushes > previous_pushes else "move")
        self.changed(preserve_effects=True)
        if new_goals:
            deadline = self.renderer.add_goal_effects(new_goals)
            if self.game.game_won:
                self.completion_due = deadline
                self.renderer.modal_buttons.clear()
        return True

    def start_solver(self, mode):
        if self.game.game_won:
            return
        self.stop()
        self.menu_open = False
        self.cancel_event = Event()
        self.job_revision, self.job_mode = self.revision, mode
        self.job_started = monotonic()
        snapshot = copy(self.game)
        # Search only reads immutable board/state fields, never the undo history.
        solver = solve_hill_climbing_full if mode == "hill" else solve_a_star
        options = {"cancel": self.cancel_event, "max_seconds": config.SOLVER_SECONDS}
        if mode != "hill":
            options["max_states"] = config.SOLVER_STATES
        self.future = self.executor.submit(solver, snapshot, **options)
        self.status = "Hill climbing..." if mode == "hill" else "Searching..."
        self.metrics = ""

    def poll_solver(self):
        if not self.future:
            return
        if not self.future.done():
            self.metrics = f"{monotonic() - self.job_started:.1f}s / {config.SOLVER_SECONDS:.0f}s"
            return
        future, self.future = self.future, None
        if self.job_revision != self.revision:
            return
        try:
            result = future.result()
        except Exception as error:
            self.status = "Solver failed"
            print(f"Solver failed: {error}")
            return
        self.metrics = f"{result.explored} states  /  {result.elapsed:.2f}s  /  {result.pushes} pushes"
        messages = {"solved": "Solution found", "limit": "Search limit reached",
                    "deadlock": "Deadlock detected", "unsolvable": "No solution",
                    "stuck": "Hill climbing stuck", "cancelled": "Search cancelled"}
        self.status = messages.get(result.status, "Solver failed")
        if result.status != "solved":
            return
        if not valid_path(self.game, self.game.state, result.path, require_win=True):
            self.status = "Invalid solution rejected"
            return
        self.progress.remember_solution(self.game, result.path)
        self.refresh()
        self.save()
        if self.job_mode == "hint":
            if result.path:
                self.move(result.path[0], assisted=True)
                self.status = "Hint applied"
        else:
            self.playback = deque(result.path)
            self.next_step = pygame.time.get_ticks() + self.playback_ms

    def select_level(self, index):
        if not 0 <= index < len(self.levels):
            return
        self.stop()
        self.save()
        self.level_index = index
        self.game = Game(self.levels[index])
        self.assisted = self.progress.restore(self.game)
        self.title_screen = False
        self.menu_open = False
        self.status, self.metrics = "Ready", ""
        self.changed()

    def action(self, action):
        if not action:
            return
        if action == "start_game":
            self.title_screen = False
            self.menu_open = False
        elif action == "select_level_menu":
            self.title_screen = False
            self.menu_open = True
            self.menu_offset = self.level_index
        elif action == "home":
            self.stop()
            self.completion_open = False
            self.deadlock_open = False
            self.menu_open = False
            self.title_screen = True
        elif action == "exit":
            self.running = False
        elif action == "dismiss_completion":
            self.completion_open = False
        elif action == "dismiss_deadlock":
            self.deadlock_open = False
        elif action.startswith("level:"):
            self.select_level(int(action.split(":")[1]))
        elif action in ("hint", "solve", "hill"):
            self.start_solver(action)
        elif action == "sound":
            self.audio.enabled = not self.audio.enabled
            self.save()
        elif action == "levels":
            self.stop()
            self.completion_open = False
            self.deadlock_open = False
            self.renderer.clear_effects()
            self.menu_open = not self.menu_open
            self.menu_offset = self.level_index
        elif action in ("previous", "next"):
            self.select_level(self.level_index + (1 if action == "next" else -1))
        elif action == "replay":
            path = self.progress.cached_solution(self.game)
            if path is None:
                self.status = "No saved solution"
                return
            self.stop()
            self.menu_open = False
            self.game.reset_level()
            self.assisted = True
            self.changed()
            self.playback = deque(path)
            self.next_step = pygame.time.get_ticks() + self.playback_ms
            self.status = "Replaying saved solution"
        elif action in ("undo", "redo", "reset", "stop"):
            self.stop()
            self.status = "Stopped" if action == "stop" else "Ready"
            if action == "reset":
                self.game.reset_level()
                self.assisted = False
                self.changed()
            elif action in ("undo", "redo") and getattr(self.game, action)():
                self.changed()

    def set_speed(self, x):
        slider = self.renderer.slider
        fraction = max(0.0, min(1.0, (x - slider.x) / max(1, slider.width)))
        self.playback_ms = int(350 - 280 * fraction)

    def handle_event(self, event):
        if self.title_screen:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.window_size = max(config.MIN_SCREEN_WIDTH, event.w), max(config.MIN_SCREEN_HEIGHT, event.h)
                self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.action(self.renderer.action_at(event.pos))
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.action("start_game")
                elif event.key in (pygame.K_TAB, pygame.K_l):
                    self.action("select_level_menu")
                elif event.key == pygame.K_m:
                    self.action("sound")
                elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.running = False
                elif event.key == pygame.K_F11:
                    self.fullscreen = not self.fullscreen
                    self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if self.fullscreen else pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
            return

        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self.window_size = max(config.MIN_SCREEN_WIDTH, event.w), max(config.MIN_SCREEN_HEIGHT, event.h)
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.completion_open or self.deadlock_open:
                self.action(self.renderer.action_at(event.pos, modal=True))
            elif self.renderer.slider.inflate(16, 24).collidepoint(event.pos):
                self.set_speed(event.pos[0])
            else:
                self.action(self.renderer.action_at(event.pos))
        elif event.type == pygame.MOUSEMOTION and event.buttons[0] and not (self.completion_open or self.deadlock_open):
            if self.renderer.slider.inflate(24, 30).collidepoint(event.pos):
                self.set_speed(event.pos[0])
        elif event.type == pygame.MOUSEWHEEL and self.menu_open:
            self.menu_offset -= event.y
        elif event.type == pygame.KEYDOWN:
            if self.completion_open or self.deadlock_open:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if self.deadlock_open:
                        self.action("reset")
                    else:
                        self.action("next" if self.level_index < len(self.levels) - 1 else "levels")
                    return
                if event.key not in (pygame.K_ESCAPE, pygame.K_F11, pygame.K_z, pygame.K_y,
                                     pygame.K_r, pygame.K_TAB, pygame.K_n, pygame.K_m):
                    return
            directions = {pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1),
                          pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0)}
            actions = {pygame.K_z: "undo", pygame.K_y: "redo", pygame.K_r: "reset",
                       pygame.K_h: "hint", pygame.K_a: "solve", pygame.K_j: "hill",
                       pygame.K_l: "replay", pygame.K_TAB: "levels", pygame.K_n: "next",
                       pygame.K_m: "sound", pygame.K_SPACE: "stop"}
            if event.key == pygame.K_ESCAPE:
                self.stop()
                if self.completion_open or self.deadlock_open:
                    self.completion_open = False
                    self.deadlock_open = False
                elif self.menu_open:
                    self.menu_open = False
                else:
                    self.title_screen = True
                self.status = "Ready"
            elif event.key == pygame.K_F11:
                self.fullscreen = not self.fullscreen
                self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if self.fullscreen else pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
            elif event.key in directions:
                if self.menu_open:
                    if event.key in (pygame.K_DOWN, pygame.K_UP):
                        self.menu_offset += 1 if event.key == pygame.K_DOWN else -1
                else:
                    self.stop()
                    self.status = "Ready"
                    self.move(directions[event.key])
            elif event.key in actions:
                self.action(actions[event.key])

    def update(self):
        if self.title_screen:
            return
        self.poll_solver()
        now = pygame.time.get_ticks()
        if self.playback and now >= self.next_step and not self.menu_open:
            move = self.playback.popleft()
            if not self.move(move, assisted=True):
                self.playback.clear()
                self.status = "Playback stopped: invalid move"
            self.next_step = now + self.playback_ms
            if not self.playback and not self.game.game_won:
                self.status = "Playback ended without a solution"
        if self.game.game_won:
            self.playback.clear()

    def close(self):
        self.stop()
        self.executor.shutdown(wait=True)
        self.save()
        pygame.quit()

    def run(self):
        clock = pygame.time.Clock()
        try:
            while self.running:
                for event in pygame.event.get():
                    self.handle_event(event)
                self.update()
                self.renderer.draw(self.screen, self)
                pygame.display.flip()
                clock.tick(60)
        finally:
            self.close()


def main():
    try:
        App().run()
    except (OSError, ValueError, pygame.error) as error:
        pygame.quit()
        raise SystemExit(f"Cannot start Sokoban: {error}") from error


if __name__ == "__main__":
    main()
