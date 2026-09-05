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
PLAYER_ACTION_MS = 160
PLAYER_IDLE_FRAME_MS = 220
GOAL_EFFECT_MS = 800

# (3-star move limit, 2-star move limit). Any completed level earns at least 1 star.
STAR_MOVE_TARGETS = {
    "level01_first_step.txt": (3, 5),
    "level02_two_boxes.txt": (4, 6),
    "level03_corner_turn.txt": (5, 8),
    "level04_split_passage.txt": (9, 14),
    "level05_line_formation.txt": (11, 17),
    "level06_squeeze_corridor.txt": (25, 38),
    "level07_cross_choke.txt": (54, 81),
    "level08_filling_order.txt": (44, 66),
    "level09_parking_bay.txt": (37, 56),
    "level10_storage_warehouse.txt": (98, 147),
    "level11_final_challenge.txt": (57, 86),
}


def star_targets(level):
    return STAR_MOVE_TARGETS.get(Path(level).name)


def star_rating(level, moves, completed=True):
    if not completed:
        return 0
    targets = star_targets(level)
    if not targets or type(moves) is not int or moves < 0:
        return 1
    three_star, two_star = targets
    if moves <= three_star:
        return 3
    if moves <= two_star:
        return 2
    return 1


def level_files():
    # Return levels in natural numbered order (level01_ to level11_)
    return sorted((BASE_DIR / "levels").glob("level*.txt"))
