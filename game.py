"""Sokoban rules and reversible state, independent of Pygame."""

from collections import deque
from hashlib import sha256
from pathlib import Path

DIRECTIONS = ((0, -1), (0, 1), (-1, 0), (1, 0))


def add(point, direction):
    return point[0] + direction[0], point[1] + direction[1]


def transition(floors, state, direction):
    """Return (new state, pushed), or None for an illegal move."""
    if direction not in DIRECTIONS:
        return None
    player, boxes = state
    target = add(player, direction)
    if target not in floors:
        return None
    pushed = target in boxes
    if pushed:
        destination = add(target, direction)
        if destination not in floors or destination in boxes:
            return None
        boxes = frozenset((boxes - {target}) | {destination})
    return (target, boxes), pushed


def reverse_distances(floors, goals):
    """Distances when pulling a single box on an otherwise empty board."""
    result = {}
    for goal in sorted(goals):
        distances = {goal: 0}
        queue = deque([goal])
        while queue:
            current = queue.popleft()
            for dx, dy in DIRECTIONS:
                previous = current[0] - dx, current[1] - dy
                support = previous[0] - dx, previous[1] - dy
                if previous in floors and support in floors and previous not in distances:
                    distances[previous] = distances[current] + 1
                    queue.append(previous)
        result[goal] = distances
    return result


class Game:
    def __init__(self, level_path):
        self.load_level(level_path)

    def load_level(self, filepath):
        path = Path(filepath).resolve()
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if not lines or not max(map(len, lines)):
            raise ValueError("Empty level")
        if any(set(line) - set("# @+$*.") for line in lines):
            raise ValueError("Unknown level character")
        players, boxes, goals, floors, walls = [], set(), set(), set(), set()
        for y, line in enumerate(lines):
            for x, tile in enumerate(line):
                point = x, y
                (walls if tile == "#" else floors).add(point)
                if tile in "@+":
                    players.append(point)
                if tile in "$*":
                    boxes.add(point)
                if tile in ".+*":
                    goals.add(point)
        if len(players) != 1:
            raise ValueError("A level must contain exactly one player")
        if not boxes or len(boxes) != len(goals):
            raise ValueError("A level needs an equal, nonzero number of boxes and goals")
        # Outside spaces and missing cells are void, never walkable padding.
        reachable = {players[0]}
        queue = deque(reachable)
        while queue:
            point = queue.popleft()
            for direction in DIRECTIONS:
                neighbor = add(point, direction)
                if neighbor not in floors and neighbor not in walls:
                    raise ValueError("The playable area must be enclosed by walls")
                if neighbor in floors and neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append(neighbor)
        if not (boxes | goals) <= reachable:
            raise ValueError("All boxes and goals must be in the playable area")
        self.current_level_path = path
        self.width, self.height = max(map(len, lines)), len(lines)
        self.floors, self.walls, self.goals = map(frozenset, (reachable, walls, goals))
        self.initial_state = players[0], frozenset(boxes)
        self.state = self.initial_state
        self.level_id = sha256("\n".join(lines).encode()).hexdigest()
        self.goal_distances = reverse_distances(self.floors, self.goals)
        safe = set().union(*(set(d) for d in self.goal_distances.values()))
        self.dead_squares = self.floors - safe
        self._undo, self._redo = [], []
        self.moves = self.pushes = 0

    @property
    def player_pos(self):
        return list(self.state[0])

    @property
    def game_won(self):
        return self.state[1] == self.goals

    @property
    def game_map(self):
        board = [["~"] * self.width for _ in range(self.height)]
        for x, y in self.walls:
            board[y][x] = "#"
        for x, y in self.floors:
            board[y][x] = "." if (x, y) in self.goals else " "
        for x, y in self.state[1]:
            board[y][x] = "*" if (x, y) in self.goals else "$"
        x, y = self.state[0]
        board[y][x] = "+" if (x, y) in self.goals else "@"
        return board

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    @property
    def actions(self):
        return [entry[3] for entry in self._undo]

    def is_deadlocked(self, boxes=None):
        boxes = self.state[1] if boxes is None else boxes
        if boxes & self.dead_squares:
            return True
        # A filled 2x2 containing a box off goal cannot be opened by pushing.
        for x, y in boxes - self.goals:
            for dx, dy in ((0, 0), (-1, 0), (0, -1), (-1, -1)):
                block = {(x + dx + i, y + dy + j) for i in (0, 1) for j in (0, 1)}
                if all(p in boxes or p not in self.floors for p in block):
                    return True
        return False

    def reset_level(self):
        self.state = self.initial_state
        self.moves = self.pushes = 0
        self._undo.clear()
        self._redo.clear()

    def move_player(self, dx, dy):
        if self.game_won:
            return False
        result = transition(self.floors, self.state, (dx, dy))
        if result is None:
            return False
        self._undo.append((self.state, self.moves, self.pushes, (dx, dy)))
        self.state, pushed = result
        self.moves += 1
        self.pushes += int(pushed)
        self._redo.clear()
        return True

    def undo(self):
        if not self._undo:
            return False
        previous = self._undo.pop()
        self._redo.append((self.state, self.moves, self.pushes, previous[3]))
        self.state, self.moves, self.pushes = previous[:3]
        return True

    def redo(self):
        if not self._redo:
            return False
        following = self._redo.pop()
        self._undo.append((self.state, self.moves, self.pushes, following[3]))
        self.state, self.moves, self.pushes = following[:3]
        return True

    def check_win(self):
        return self.game_won
