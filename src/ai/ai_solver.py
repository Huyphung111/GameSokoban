"""Bounded push-based search. No UI calls or mutation of the live game."""

from collections import deque
from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import count
from random import Random
from time import monotonic

try:
    from src.core.game import DIRECTIONS, add
except ImportError:
    from game import DIRECTIONS, add


@dataclass
class SolveResult:
    status: str
    path: list = field(default_factory=list)
    explored: int = 0
    elapsed: float = 0.0
    pushes: int = 0


def get_state_tuple(game_map, player_pos):
    return tuple(player_pos), frozenset(
        (x, y) for y, row in enumerate(game_map) for x, tile in enumerate(row) if tile in "$*"
    )


def calculate_heuristic(level_map):
    boxes, goals = [], []
    for y, row in enumerate(level_map):
        for x, tile in enumerate(row):
            if tile in "$*":
                boxes.append((x, y))
            if tile in ".+*":
                goals.append((x, y))
    if not boxes:
        return 0
    if len(boxes) != len(goals):
        return float("inf")
    return sum(min(abs(x - gx) + abs(y - gy) for gx, gy in goals) for x, y in boxes)


def heuristic(game, boxes):
    # Both bounds ignore other boxes and are admissible for the number of pushes.
    maps = game.goal_distances.values()
    box_bound = sum(min(d.get(box, float("inf")) for d in maps) for box in boxes)
    goal_bound = sum(min(d.get(box, float("inf")) for box in boxes) for d in maps)
    return max(box_bound, goal_bound)


def walking_routes(game, state):
    player, boxes = state
    parents = {player: None}
    queue = deque([player])
    while queue:
        current = queue.popleft()
        for direction in DIRECTIONS:
            target = add(current, direction)
            if target in game.floors and target not in boxes and target not in parents:
                parents[target] = current, direction
                queue.append(target)
    return parents


def push_neighbors(game, state, routes):
    _, boxes = state
    for box in sorted(boxes):
        for dx, dy in DIRECTIONS:
            support = box[0] - dx, box[1] - dy
            destination = box[0] + dx, box[1] + dy
            if support not in routes or destination not in game.floors or destination in boxes:
                continue
            new_boxes = frozenset((boxes - {box}) | {destination})
            if game.is_deadlocked(new_boxes):
                continue
            segment, cursor = [], support
            while routes[cursor] is not None:
                cursor, direction = routes[cursor]
                segment.append(direction)
            segment.reverse()
            segment.append((dx, dy))
            yield (box, new_boxes), segment


def solve_a_star(game_instance, cancel=None, max_seconds=15.0, max_states=50000):
    """Minimize pushes; walking segments are shortest for each chosen push."""
    game = game_instance
    started = monotonic()
    explored = 0

    def finish(status, path=None, pushes=0):
        return SolveResult(status, path or [], explored, monotonic() - started, pushes)

    if cancel is not None and cancel.is_set():
        return finish("cancelled")
    if game.game_won:
        return finish("solved")
    if game.is_deadlocked():
        return finish("deadlock")
    serial = count()
    start = game.state
    queue = [(heuristic(game, start[1]), next(serial), 0, start)]
    costs, parents = {start: 0}, {}
    while queue:
        if cancel is not None and cancel.is_set():
            return finish("cancelled")
        if monotonic() - started >= max_seconds or explored >= max_states:
            return finish("limit")
        _, _, cost, state = heappop(queue)
        if cost != costs.get(state):
            continue
        if state[1] == game.goals:
            segments, cursor = [], state
            while cursor != start:
                cursor, segment = parents[cursor]
                segments.append(segment)
            path = [move for segment in reversed(segments) for move in segment]
            return finish("solved", path, cost)
        explored += 1
        routes = walking_routes(game, state)
        for following, segment in push_neighbors(game, state, routes):
            next_cost = cost + 1
            if next_cost >= costs.get(following, float("inf")):
                continue
            estimate = heuristic(game, following[1])
            if estimate == float("inf"):
                continue
            # Bound discovered states too, not just nodes removed from the queue.
            if following not in costs and len(costs) >= max_states:
                return finish("limit")
            costs[following] = next_cost
            parents[following] = state, segment
            heappush(queue, (next_cost + estimate, next(serial), next_cost, following))
    return finish("unsolvable")


def solve_hill_climbing_full(game_instance, cancel=None, max_seconds=15.0,
                             max_steps=500, seed=0):
    """Educational greedy push search with seeded sideways moves, no revisits."""
    game = game_instance
    started = monotonic()
    state, path, visited = game.state, [], {game.state}
    rng = Random(seed)
    pushes = 0
    while True:
        status = None
        if cancel is not None and cancel.is_set():
            status = "cancelled"
        elif state[1] == game.goals:
            status = "solved"
        elif game.is_deadlocked(state[1]):
            status = "deadlock"
        elif pushes >= max_steps or monotonic() - started >= max_seconds:
            status = "limit"
        if status:
            return SolveResult(status, path, pushes, monotonic() - started, pushes)
        options = [(heuristic(game, s[1]), s, moves)
                   for s, moves in push_neighbors(game, state, walking_routes(game, state))
                   if s not in visited]
        if not options:
            return SolveResult("stuck", path, pushes, monotonic() - started, pushes)
        best = min(option[0] for option in options)
        _, state, segment = rng.choice([option for option in options if option[0] == best])
        visited.add(state)
        path.extend(segment)
        pushes += 1


def solve_hill_climbing(game_instance):
    """Return one greedy push and its approach without mutating the game."""
    return solve_hill_climbing_full(game_instance, max_steps=1)
