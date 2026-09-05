from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INITIAL_SCREEN_WIDTH = 900
INITIAL_SCREEN_HEIGHT = 760
MIN_SCREEN_WIDTH = 480
MIN_SCREEN_HEIGHT = 520
LEVEL_FILE = BASE_DIR / "levels" / "level01_first_step.txt"
FONT_PATH = BASE_DIR / "fonts" / "Roboto-Bold.ttf"
SAVE_FILE = BASE_DIR / "data" / "progress.json"
SOLVER_SECONDS = 15.0
SOLVER_STATES = 50000
PLAYBACK_MS = 130
MOVE_ANIMATION_MS = 85
GOAL_EFFECT_MS = 800


def level_files():
    # Return levels in natural numbered order (level01_ to level11_)
    return sorted((BASE_DIR / "levels").glob("level*.txt"))
