from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INITIAL_SCREEN_WIDTH = 900
INITIAL_SCREEN_HEIGHT = 760
MIN_SCREEN_WIDTH = 480
MIN_SCREEN_HEIGHT = 520
LEVEL_FILE = BASE_DIR / "levels" / "level1.txt"
FONT_PATH = BASE_DIR / "fonts" / "Roboto-Bold.ttf"
SAVE_FILE = BASE_DIR / "data" / "progress.json"
SOLVER_SECONDS = 15.0
SOLVER_STATES = 50000
PLAYBACK_MS = 130
MOVE_ANIMATION_MS = 85
GOAL_EFFECT_MS = 800


def level_files():
    # Keep the corridor puzzle as the final challenge.
    files = sorted((BASE_DIR / "levels").glob("*.txt"))
    return sorted(files, key=lambda path: (path.name == "level2.txt", path.name))
