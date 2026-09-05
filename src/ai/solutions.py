"""Validate cached solutions and saved move sequences against Sokoban rules."""

try:
    from src.core.game import DIRECTIONS, transition
except ImportError:
    from game import DIRECTIONS, transition


def valid_path(game, state, path, require_win=False):
    if not isinstance(path, list) or len(path) > 100000:
        return False
    for move in path:
        if not isinstance(move, (list, tuple)) or len(move) != 2:
            return False
        if any(type(value) is not int for value in move) or tuple(move) not in DIRECTIONS:
            return False
        if state[1] == game.goals:
            return False
        result = transition(game.floors, state, tuple(move))
        if result is None:
            return False
        state = result[0]
    return not require_win or state[1] == game.goals
