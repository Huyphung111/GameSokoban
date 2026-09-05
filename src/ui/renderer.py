"""Pygame board, compact controls and level selection."""

from pathlib import Path
from math import cos, pi, sin

import pygame

try:
    from src import config
except ImportError:
    import config

BG = (12, 18, 18)
PANEL = (72, 43, 25)
INK = (255, 229, 164)
MUTED = (211, 174, 111)
GREEN = (145, 224, 75)
RED = (248, 133, 96)
WOOD = (126, 72, 27)
WOOD_LIGHT = (184, 111, 39)
WOOD_DARK = (48, 28, 18)
GOLD = (255, 190, 48)
TOP = 174
BOTTOM = 108
DIRECTION_NAMES = {(0, -1): "up", (0, 1): "down", (-1, 0): "left", (1, 0): "right"}


class Renderer:
    def __init__(self, font_path=None):
        font = str(font_path) if font_path and Path(font_path).exists() else None
        self.font_path = font
        self.fonts = {size: pygame.font.Font(font, size) for size in (18, 22, 26, 32, 38)}
        self.symbol_font = pygame.font.SysFont("segoeuisymbol", 26)
        self.originals = {
            tile: pygame.image.load(str(config.BASE_DIR / "assets" / name)).convert_alpha()
            for tile, name in {"#": "wall.png", " ": "floor.png", "@": "player.png",
                               "$": "box.png", ".": "goal.png"}.items()
        }
        box_bounds = self.originals["$"].get_bounding_rect(min_alpha=8)
        if box_bounds.width and box_bounds.height:
            self.originals["$"] = self.originals["$"].subsurface(box_bounds).copy()
        self.assets = {}
        self.player_direction_sources = self._load_player_directions(self.originals["@"])
        direction_frames = {
            direction: self._make_player_frames(source, direction)
            for direction, source in self.player_direction_sources.items()
        }
        self.player_frame_originals = {
            action: {direction: frames[action]
                     for direction, frames in direction_frames.items()}
            for action in ("idle", "walk", "push")
        }
        self.player_frames = {}
        self.tile_size = 0
        self.buttons = []
        self.button_cache = {}
        self.modal_buttons = []
        self.goal_effects = []
        self.slider = pygame.Rect(0, 0, 0, 0)
        self.previous_state = self.current_state = None
        self.current_level = None
        self.animation_start = 0
        self.player_action = "idle"
        self.player_facing = (0, 1)
        self.completion_was_visible = False
        self.completion_animation_start = 0
        self.completion_veil = None
        self.completion_veil_size = (0, 0)
        self.completion_background = None
        self.completion_dimmed_background = None
        self.completion_background_size = (0, 0)
        title_path = config.BASE_DIR / "assets" / "title_screen.jpg"
        self.title_bg = pygame.image.load(str(title_path)).convert() if title_path.exists() else None
        self.cached_title_surf = None
        self.cached_title_size = (0, 0)
        cave_path = config.BASE_DIR / "assets" / "cave_background.png"
        self.cave_bg = pygame.image.load(str(cave_path)).convert() if cave_path.exists() else None
        self.cached_cave_surf = None
        self.cached_cave_size = (0, 0)

    def _load_player_directions(self, fallback):
        """Load down/up/left/right cells, preserving a safe single-sprite fallback."""
        assets_dir = config.BASE_DIR / "assets"
        paths = (assets_dir / "player_directions.png",
                 assets_dir / "player_directions.png.jpg")
        path = next((candidate for candidate in paths if candidate.exists()), None)
        if path is None:
            return {"down": fallback, "up": fallback,
                    "left": pygame.transform.flip(fallback, True, False), "right": fallback}

        atlas = pygame.image.load(str(path)).convert_alpha()
        white = pygame.mask.from_threshold(
            atlas, (255, 255, 255, 255), (120, 120, 120, 255))
        background = white.connected_component((0, 0))
        if background.count():
            # JPEG compression leaves a thin neutral halo outside the black outline.
            neutral = pygame.mask.from_threshold(
                atlas, (255, 255, 255, 255), (150, 150, 150, 255))
            for _ in range(4):
                expanded = background.copy()
                for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    expanded.draw(background, offset)
                background = expanded.overlap_mask(neutral, (0, 0))
            alpha_limiter = background.to_surface(
                setcolor=(255, 255, 255, 0), unsetcolor=(255, 255, 255, 255))
            atlas.blit(alpha_limiter, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        cell_width = atlas.get_width() // 4
        if cell_width <= 0:
            return {"down": fallback, "up": fallback,
                    "left": pygame.transform.flip(fallback, True, False), "right": fallback}
        directions = {}
        for index, direction in enumerate(("down", "up", "left", "right")):
            width = cell_width if index < 3 else atlas.get_width() - cell_width * index
            cell = atlas.subsurface((cell_width * index, 0, width, atlas.get_height())).copy()
            bounds = cell.get_bounding_rect(min_alpha=8)
            if not bounds.width or not bounds.height:
                directions[direction] = fallback
                continue
            character = cell.subsurface(bounds).copy()
            target_width, target_height = fallback.get_size()
            scale = min((target_width - 6) / bounds.width,
                        (target_height - 6) / bounds.height)
            size = max(1, round(bounds.width * scale)), max(1, round(bounds.height * scale))
            character = pygame.transform.scale(character, size)
            normalized = pygame.Surface(fallback.get_size(), pygame.SRCALPHA)
            normalized.blit(character, ((target_width - size[0]) // 2,
                                        target_height - size[1] - 2))
            directions[direction] = normalized
        return directions

    @staticmethod
    def _make_player_frames(source, direction):
        """Create small pixel-safe pose changes from the existing player sprite."""
        width, height = source.get_size()

        def pose(scale_x=1.0, scale_y=1.0, offset_x=0, offset_y=0):
            frame = pygame.Surface((width, height), pygame.SRCALPHA)
            scaled_size = max(1, round(width * scale_x)), max(1, round(height * scale_y))
            scaled = pygame.transform.scale(source, scaled_size)
            x = max(0, min(width - scaled_size[0],
                           (width - scaled_size[0]) // 2 + offset_x))
            y = max(0, min(height - scaled_size[1],
                           height - scaled_size[1] - offset_y))
            frame.blit(scaled, (x, y))
            return frame

        push_x = {"left": -1, "right": 1}.get(direction, 0)
        return {
            "idle": [pose(), pose(.99, .98, 0, 1), pose(.98, .95, 0, 2),
                     pose(.99, .98, 0, 1)],
            "walk": [pose(.99, .96, 0, 2), pose(1.0, .99, 0, 0),
                     pose(.99, .96, 0, 2), pose(1.0, .98, 0, 1)],
            "push": [pose(), pose(.98, .97, push_x, 2),
                     pose(.96, .93, push_x * 3, 4), pose(.98, .96, push_x, 2)],
        }

    @staticmethod
    def _is_forward_push(previous_state, current_state):
        old_player, old_boxes = previous_state
        player, boxes = current_state
        dx, dy = player[0] - old_player[0], player[1] - old_player[1]
        if abs(dx) + abs(dy) != 1:
            return False
        destination = player[0] + dx, player[1] + dy
        return player in old_boxes and player not in boxes and destination in boxes

    def _player_surface(self, now):
        elapsed = max(0, now - self.animation_start)
        action = self.player_action if elapsed < config.PLAYER_ACTION_MS else "idle"
        direction = DIRECTION_NAMES.get(self.player_facing, "down")
        frames = self.player_frames[action][direction]
        if action == "idle":
            index = (elapsed // config.PLAYER_IDLE_FRAME_MS) % len(frames)
        else:
            index = min(len(frames) - 1,
                        elapsed * len(frames) // config.PLAYER_ACTION_MS)
        return frames[index]

    def background(self, surface):
        """Cover the window with the cave art while preserving its aspect ratio."""
        surface.fill(BG)
        if not self.cave_bg:
            return
        width, height = surface.get_size()
        source_width, source_height = self.cave_bg.get_size()
        scale = max(width / source_width, height / source_height)
        size = round(source_width * scale), round(source_height * scale)
        if self.cached_cave_surf is None or size != self.cached_cave_size:
            self.cached_cave_size = size
            self.cached_cave_surf = pygame.transform.smoothscale(self.cave_bg, size)
        surface.blit(self.cached_cave_surf, ((width - size[0]) // 2, (height - size[1]) // 2))

    def panel(self, surface, rect, fill=PANEL, border=WOOD_LIGHT, radius=10):
        """Draw a layered carved-wood panel used by every part of the HUD."""
        rect = pygame.Rect(rect)
        pygame.draw.rect(surface, (0, 0, 0, 90), rect.move(0, 4), border_radius=radius)
        pygame.draw.rect(surface, WOOD_DARK, rect, border_radius=radius)
        inner = rect.inflate(-4, -4)
        pygame.draw.rect(surface, fill, inner, border_radius=max(2, radius - 2))
        pygame.draw.line(surface, border, (inner.left + 8, inner.top + 2),
                         (inner.right - 8, inner.top + 2), 2)
        pygame.draw.rect(surface, border, rect, 2, border_radius=radius)
        return rect

    def text(self, surface, value, rect, size=22, color=INK, center=False, symbol=False):
        rect = pygame.Rect(rect)
        if symbol:
            font = self.symbol_font
        else:
            if size not in self.fonts:
                self.fonts[size] = pygame.font.Font(self.font_path, size)
            font = self.fonts[size]
        value = str(value)
        # Render at the final font size rather than resampling text pixels.
        while not symbol and size > 12 and (font.size(value)[0] > rect.width or font.get_height() > rect.height):
            size -= 1
            if size not in self.fonts:
                self.fonts[size] = pygame.font.Font(self.font_path, size)
            font = self.fonts[size]
        if font.size(value)[0] > rect.width:
            while value and font.size(value + "...")[0] > rect.width:
                value = value[:-1]
            value += "..."
        rendered = font.render(value, True, color)
        position = rendered.get_rect(center=rect.center) if center else rendered.get_rect(midleft=rect.midleft)
        surface.blit(rendered, position)

    def button(self, surface, action, label, rect, enabled=True, tooltip="", active=False,
               symbol=False, origin=(0, 0)):
        rect = pygame.Rect(rect)
        screen_rect = rect.move(origin)
        hovered = screen_rect.collidepoint(pygame.mouse.get_pos())
        if not enabled:
            fill, border, color = (70, 58, 45), (92, 73, 52), (145, 123, 88)
        elif active:
            fill, border, color = (111, 126, 29), (213, 222, 64), (255, 242, 141)
        elif hovered:
            fill, border, color = (166, 96, 29), GOLD, (255, 240, 190)
        else:
            fill, border, color = WOOD, WOOD_LIGHT, INK
        cache_key = (rect.size, label, enabled, active, hovered, symbol)
        button_image = self.button_cache.get(cache_key)
        if button_image is None:
            button_image = pygame.Surface((rect.width, rect.height + 3), pygame.SRCALPHA)
            local_rect = pygame.Rect(0, 0, rect.width, rect.height)
            pygame.draw.rect(button_image, (31, 18, 12), local_rect.move(0, 3), border_radius=7)
            pygame.draw.rect(button_image, fill, local_rect, border_radius=7)
            pygame.draw.line(button_image, tuple(min(255, value + 35) for value in fill),
                             (local_rect.left + 7, local_rect.top + 2),
                             (local_rect.right - 7, local_rect.top + 2), 2)
            pygame.draw.rect(button_image, border, local_rect, 2, border_radius=7)
            self.text(button_image, label, local_rect.inflate(-4 if symbol else -12, -4),
                      color=color, center=True, symbol=symbol)
            self.button_cache[cache_key] = button_image
        surface.blit(button_image, rect.topleft)
        self.buttons.append((screen_rect, action, enabled, tooltip))

    def calculate_and_load_assets(self, game_map, screen_width, screen_height):
        if not game_map:
            return
        size = max(1, min((screen_width - 32) // len(game_map[0]),
                          max(1, screen_height - TOP - BOTTOM - 20) // len(game_map)))
        if size != self.tile_size:
            self.tile_size = size
            self.assets = {tile: pygame.transform.scale(img, (size, size))
                           for tile, img in self.originals.items()}
            self.player_frames = {
                action: {
                    direction: [pygame.transform.scale(frame, (size, size))
                                for frame in frames]
                    for direction, frames in directions.items()
                }
                for action, directions in self.player_frame_originals.items()
            }
            # Cache a compact feathered contact shadow at the current tile size.
            shadow_width = max(3, round(size * 1.08))
            shadow_height = max(3, round(size * .22))
            self.box_shadow = pygame.Surface((shadow_width, shadow_height), pygame.SRCALPHA)
            for sy in range(shadow_height):
                for sx in range(shadow_width):
                    radius = ((sx + .5 - shadow_width / 2) / (shadow_width / 2)) ** 2
                    radius += ((sy + .5 - shadow_height / 2) / (shadow_height / 2)) ** 2
                    alpha = round(44 * max(0, 1 - radius) ** 2)
                    self.box_shadow.set_at((sx, sy), (0, 0, 0, alpha))

    def draw_board(self, surface, game):
        width, height = surface.get_size()
        board = game.game_map
        self.calculate_and_load_assets(board, width, height)
        size = self.tile_size
        ox = (width - game.width * size) // 2
        oy = TOP + (height - TOP - BOTTOM - game.height * size) // 2
        board_rect = pygame.Rect(ox, oy, game.width * size, game.height * size)
        pygame.draw.rect(surface, (4, 8, 8), board_rect.inflate(14, 14), border_radius=8)
        pygame.draw.rect(surface, (91, 55, 29), board_rect.inflate(8, 8), 4, border_radius=6)
        now = pygame.time.get_ticks()
        if game.level_id != self.current_level:
            self.previous_state = self.current_state = game.state
            self.current_level = game.level_id
            self.animation_start = now
            self.player_action = "idle"
        elif game.state != self.current_state:
            self.previous_state, self.current_state = self.current_state, game.state
            self.animation_start = now
            old_player = self.previous_state[0]
            player = self.current_state[0]
            direction = player[0] - old_player[0], player[1] - old_player[1]
            if abs(direction[0]) + abs(direction[1]) == 1:
                self.player_facing = direction
                self.player_action = ("push" if self._is_forward_push(
                    self.previous_state, self.current_state) else "walk")
            else:
                self.player_action = "idle"
        amount = min(1.0, (now - self.animation_start) / config.MOVE_ANIMATION_MS)
        old_player, old_boxes = self.previous_state
        player, boxes = game.state
        animate = abs(old_player[0] - player[0]) + abs(old_player[1] - player[1]) == 1
        if not animate:
            amount = 1.0
        for y, row in enumerate(board):
            for x, tile in enumerate(row):
                if tile == "~":
                    continue
                position = ox + x * size, oy + y * size
                surface.blit(self.assets[" "], position)
                if tile == "#":
                    surface.blit(self.assets["#"], position)
                elif (x, y) in game.goals:
                    surface.blit(self.assets["."], position)

        removed, added = old_boxes - boxes, boxes - old_boxes

        def sprite_position(point, start=None):
            x, y = point
            if start is not None:
                x = start[0] + (x - start[0]) * amount
                y = start[1] + (y - start[1]) * amount
            return round(ox + x * size), round(oy + y * size)

        def sprite(tile, point, start=None):
            surface.blit(self.assets[tile], sprite_position(point, start))

        # All shadows go below all crates, and follow the same push animation.
        for box in boxes:
            start = next(iter(removed)) if box in added and len(removed) == len(added) == 1 else None
            px, py = sprite_position(box, start)
            surface.blit(self.box_shadow,
                         (round(px + (size - self.box_shadow.get_width()) / 2),
                          round(py + size * 1.01 - self.box_shadow.get_height() / 2)))

        for box in boxes:
            start = next(iter(removed)) if box in added and len(removed) == len(added) == 1 else None
            sprite("$", box, start)
            if box in game.goals and (start is None or amount == 1):
                pygame.draw.rect(surface, GREEN,
                                 (ox + box[0] * size + 2, oy + box[1] * size + 2, size - 4, size - 4),
                                 max(1, size // 22), border_radius=min(4, size // 4))
        surface.blit(self._player_surface(now), sprite_position(player, old_player))
        self.draw_goal_effects(surface, game, ox, oy, size)

    def add_goal_effects(self, goals):
        start = pygame.time.get_ticks() + config.MOVE_ANIMATION_MS
        self.goal_effects.extend((point, start) for point in sorted(goals))
        return start + config.GOAL_EFFECT_MS

    def clear_effects(self):
        self.goal_effects.clear()
        self.modal_buttons.clear()
        self.completion_was_visible = False
        self.completion_background = None
        self.completion_dimmed_background = None
        self.completion_background_size = (0, 0)

    @staticmethod
    def _animation_phase(elapsed, delay, duration):
        return max(0.0, min(1.0, (elapsed - delay) / duration))

    @staticmethod
    def _ease_out_cubic(value):
        return 1 - (1 - value) ** 3

    @staticmethod
    def _ease_out_back(value):
        offset = value - 1
        return 1 + 2.4 * offset ** 3 + 1.4 * offset ** 2

    def _start_completion_animation(self, now):
        self.completion_animation_start = now

    def draw_goal_effects(self, surface, game, ox, oy, size):
        now = pygame.time.get_ticks()
        self.goal_effects = [(point, start) for point, start in self.goal_effects
                             if now - start < config.GOAL_EFFECT_MS and point in game.state[1] & game.goals]
        old_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(0, TOP, surface.get_width(), surface.get_height() - TOP - BOTTOM))
        for (x, y), start in self.goal_effects:
            if now < start:
                continue
            phase = (now - start) / config.GOAL_EFFECT_MS
            extent = max(12, int(size * 2.5))
            effect = pygame.Surface((extent, extent), pygame.SRCALPHA)
            center = extent // 2
            alpha = round(255 * (1 - phase))
            radius = max(2, round(size * (.35 + .45 * phase)))
            pygame.draw.circle(effect, (*GREEN, alpha), (center, center), radius, max(1, size // 24))
            for index in range(12):
                angle = index * pi / 6
                distance = size * (.5 + .55 * phase)
                px = round(center + cos(angle) * distance)
                py = round(center + sin(angle) * distance + size * .2 * phase * phase)
                side = max(2, round(size * .075 * (1 - .6 * phase)))
                color = (255, 225, 115, alpha) if index % 2 else (139, 242, 221, alpha)
                pygame.draw.rect(effect, color, (px - side // 2, py - side // 2, side, side))
            surface.blit(effect, (ox + x * size + size // 2 - center, oy + y * size + size // 2 - center))
        surface.set_clip(old_clip)

    def draw_title_screen(self, surface, app):
        width, height = surface.get_size()
        self.buttons = []
        self.modal_buttons = []

        surface.fill(BG)
        if self.title_bg:
            bg_w, bg_h = self.title_bg.get_size()
            scale = max(width / bg_w, height / bg_h)
            sw, sh = int(bg_w * scale), int(bg_h * scale)
            if self.cached_title_size != (sw, sh) or self.cached_title_surf is None:
                self.cached_title_size = (sw, sh)
                self.cached_title_surf = pygame.transform.smoothscale(self.title_bg, (sw, sh))
            ox = (width - sw) // 2
            oy = (height - sh) // 2
            surface.blit(self.cached_title_surf, (ox, oy))

        center_x = width // 2
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((0, 8, 10, 35))
        surface.blit(veil, (0, 0))

        logo_width = min(520, width - 40)
        logo = pygame.Rect(0, 0, logo_width, 88)
        logo.midtop = center_x, 22
        self.panel(surface, logo, fill=(94, 50, 22), border=GOLD, radius=14)
        self.text(surface, "SOKOBAN", (logo.x + 18, logo.y + 8, logo.width - 36, 52),
                  size=46, color=GOLD, center=True)
        self.text(surface, "PUSH  /  PLAN  /  SOLVE",
                  (logo.x + 18, logo.y + 58, logo.width - 36, 20),
                  size=16, color=(236, 198, 119), center=True)

        base_y = max(300, min(height - 190, int(height * .62)))

        # Check progress for button label
        entry = app.progress.entry(app.game)
        has_progress = bool(entry.get("actions")) or entry.get("completed")
        play_label = f"CONTINUE (LEVEL {app.level_index + 1:02d})" if has_progress else "START GAME"

        btn_w = min(320, width - 40)
        menu_panel = pygame.Rect(0, 0, btn_w + 28, 184)
        menu_panel.midtop = center_x, base_y - 38
        self.panel(surface, menu_panel, fill=(55, 34, 22), border=(132, 82, 38), radius=12)

        btn1 = pygame.Rect(0, 0, btn_w, 52)
        btn1.center = (center_x, base_y)
        self.button(surface, "start_game", play_label, btn1, active=True, tooltip="Play")

        btn2 = pygame.Rect(0, 0, btn_w, 46)
        btn2.center = (center_x, base_y + 64)
        self.button(surface, "select_level_menu", "CHOOSE LEVEL", btn2, tooltip="Levels")

        sub_w = min(152, (btn_w - 12) // 2)
        btn3 = pygame.Rect(center_x - sub_w - 6, base_y + 120, sub_w, 40)
        sound_label = "Sound: ON" if app.audio.enabled else "Sound: OFF"
        self.button(surface, "sound", sound_label, btn3, app.audio.available, tooltip="Sound")

        btn4 = pygame.Rect(center_x + 6, base_y + 120, sub_w, 40)
        self.button(surface, "exit", "EXIT", btn4, tooltip="Exit")

        hint_text = "[ENTER / SPACE] Play   *   [TAB] Levels   *   [M] Sound   *   [ESC] Exit"
        self.text(surface, hint_text, (16, height - 30, width - 32, 22), size=14,
                  color=(220, 195, 150), center=True)

    def draw(self, surface, app):
        if getattr(app, "title_screen", False):
            self.draw_title_screen(surface, app)
            return

        width, height = surface.get_size()
        if (app.completion_visible and self.completion_was_visible
                and self.completion_background_size == (width, height)):
            now = pygame.time.get_ticks()
            veil_complete = now - self.completion_animation_start >= 280
            background = (self.completion_dimmed_background if veil_complete
                          else self.completion_background)
            surface.blit(background, (0, 0))
            self.draw_completion(surface, app, now=now, draw_veil=not veil_complete)
            return
        self.background(surface)
        self.buttons = []
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((0, 10, 12, 28))
        surface.blit(veil, (0, 0))

        logo_width = min(330, max(230, width - 190))
        self.panel(surface, (16, 8, logo_width, 52), fill=(94, 50, 22), border=(194, 116, 38))
        self.text(surface, "SOKOBAN", (28, 10, logo_width - 24, 46), size=38, color=GOLD, center=True)
        badge = pygame.Rect(width - 152, 8, 136, 52)
        self.panel(surface, badge, fill=(132, 91, 46), border=(220, 167, 82))
        self.text(surface, "LEVEL", (badge.x + 8, badge.y + 5, badge.width - 16, 18),
                  size=18, color=(55, 31, 18), center=True)
        self.text(surface, f"{app.level_index + 1:02d} / {len(app.levels):02d}",
                  (badge.x + 8, badge.y + 22, badge.width - 16, 26), size=26,
                  color=(48, 27, 17), center=True)
        self.panel(surface, (10, 68, width - 20, 94), fill=(55, 35, 24), border=(105, 67, 38))
        gap, left = 6, 16
        icon_w = 40
        controls = [("home", "Home", 72, True, False),
                    ("levels", "Levels", 78, True, False),
                    ("previous", "\u2039", icon_w, app.level_index > 0, True),
                    ("next", "\u203a", icon_w, app.level_index < len(app.levels) - 1, True),
                    ("undo", "\u21b6", icon_w, app.game.can_undo, True),
                    ("redo", "\u21b7", icon_w, app.game.can_redo, True),
                    ("reset", "\u21bb", icon_w, True, True),
                    ("sound", "\u266a", icon_w, app.audio.available, True)]
        for action, label, button_width, enabled, symbol in controls:
            self.button(surface, action, label, (left, 74, button_width, 36), enabled,
                        tooltip=action.title(), active=action == "sound" and app.audio.enabled,
                        symbol=symbol)
            left += button_width + gap
        commands = [("hint", "Hint"), ("solve", "Solve"), ("replay", "Replay"),
                    ("hill", "Hill climb"), ("stop", "Stop")]
        button_width = (width - 32 - 4 * gap) // 5
        for index, (action, label) in enumerate(commands):
            enabled = (app.busy or bool(app.playback)) if action == "stop" else not app.game.game_won
            if action == "replay":
                enabled = app.has_cached_solution
            if action in ("hint", "solve", "hill") and app.busy:
                enabled = False
            self.button(surface, action, label, (16 + index * (button_width + gap), 120, button_width, 36), enabled)

        if app.menu_open:
            self.draw_levels(surface, app)
        else:
            self.draw_board(surface, app.game)

        self.panel(surface, (10, height - BOTTOM + 4, width - 20, BOTTOM - 14),
                   fill=(58, 36, 23), border=(116, 73, 37))
        game = app.game
        label = (f"Moves {game.moves}    Pushes {game.pushes}    "
                 f"Goals {len(game.state[1] & game.goals)}/{len(game.goals)}")
        self.text(surface, label, (24, height - 98, width - 210, 28))
        self.text(surface, "AI assisted" if app.assisted else "Solo", (width - 176, height - 98, 144, 28), color=GOLD)
        message, color = app.status, MUTED
        if game.game_won:
            message, color = "Level complete", GREEN
        elif app.deadlocked:
            message, color = "Deadlock detected", RED
        if app.progress.error:
            message, color = app.progress.error, RED
        self.text(surface, message, (16, height - 70, width - 32, 26), color=color)
        self.text(surface, app.metrics, (16, height - 36, width - 220, 24), size=18, color=MUTED)
        self.text(surface, "Speed", (width - 192, height - 36, 52, 24), size=18, color=MUTED)
        self.slider = pygame.Rect(width - 126, height - 26, 100, 4)
        pygame.draw.rect(surface, (85, 98, 98), self.slider, border_radius=2)
        fraction = (350 - app.playback_ms) / 280
        pygame.draw.circle(surface, GREEN, (int(self.slider.x + fraction * self.slider.width), self.slider.centery), 7)
        if not app.completion_visible:
            self.completion_was_visible = False
            self.completion_background = None
            self.completion_dimmed_background = None
            self.completion_background_size = (0, 0)
        if app.deadlock_open:
            self.draw_deadlock(surface, app)
            return
        if app.completion_visible:
            self.completion_background = surface.copy()
            self.completion_dimmed_background = self.completion_background.copy()
            self.completion_dimmed_background.fill(
                (112, 112, 112), special_flags=pygame.BLEND_RGB_MULT)
            self.completion_background_size = width, height
            self.draw_completion(surface, app)
            return
        self.modal_buttons = []
        for rect, _, enabled, tooltip in self.buttons:
            if enabled and tooltip and rect.collidepoint(pygame.mouse.get_pos()):
                tip = pygame.Rect(rect.x, rect.bottom + 4, max(80, len(tooltip) * 10), 26)
                tip.clamp_ip(surface.get_rect())
                pygame.draw.rect(surface, (75, 85, 83), tip, border_radius=4)
                self.text(surface, tooltip, tip.inflate(-8, 0), size=18, center=True)

    def draw_completion(self, surface, app, now=None, draw_veil=True):
        width, height = surface.get_size()
        now = pygame.time.get_ticks() if now is None else now
        if not self.completion_was_visible:
            self._start_completion_animation(now)
            self.completion_was_visible = True
        elapsed = max(0, now - self.completion_animation_start)

        overlay_phase = self._ease_out_cubic(self._animation_phase(elapsed, 0, 280))
        if draw_veil:
            if self.completion_veil_size != (width, height):
                self.completion_veil = pygame.Surface((width, height)).convert()
                self.completion_veil.fill((0, 0, 0))
                self.completion_veil_size = width, height
            self.completion_veil.set_alpha(round(143 * overlay_phase))
            surface.blit(self.completion_veil, (0, 0))

        panel = pygame.Rect(0, 0, min(420, width - 40), 270)
        panel.center = width // 2, height // 2
        padding = 36
        canvas_origin = panel.x - padding, panel.y - padding
        canvas = pygame.Surface((panel.width + padding * 2,
                                 panel.height + padding * 2), pygame.SRCALPHA)
        local_panel = pygame.Rect(padding, padding, panel.width, panel.height)
        glow_phase = self._animation_phase(elapsed, 0, 800)
        glow_alpha = (glow_phase / .45 if glow_phase < .45
                      else .45 + .55 * (1 - glow_phase))
        for spread, alpha in ((30, 16), (20, 24), (10, 34)):
            pygame.draw.rect(canvas, (*GREEN, round(alpha * glow_alpha)),
                             local_panel.inflate(spread * 2, spread * 2),
                             border_radius=18 + spread // 2)
        pygame.draw.rect(canvas, (0, 0, 0, 115), local_panel.move(0, 12), border_radius=10)
        pygame.draw.rect(canvas, PANEL, local_panel, border_radius=8)
        pygame.draw.rect(canvas, GREEN, local_panel, 2, border_radius=8)
        self.buttons = []
        last_level = app.level_index == len(app.levels) - 1
        title = "Final level complete" if last_level else "Level complete"
        self.button(canvas, "dismiss_completion", "\u00d7",
                    (local_panel.right - 40, local_panel.y + 10, 28, 28),
                    tooltip="Close", symbol=True, origin=canvas_origin)

        title_phase = self._ease_out_cubic(self._animation_phase(elapsed, 120, 380))
        self.text(canvas, title,
                  (local_panel.x + 22, local_panel.y + 24 + round(8 * (1 - title_phase)),
                   local_panel.width - 70, 38),
                  size=32, color=(*GREEN, round(255 * title_phase)))

        stats_phase = self._ease_out_cubic(self._animation_phase(elapsed, 200, 380))
        stats_offset = round(8 * (1 - stats_phase))
        stats_alpha = round(255 * stats_phase)
        goals = len(app.game.goals)
        self.text(canvas, f"Level {app.level_index + 1:02d}  /  {goals} {'goal' if goals == 1 else 'goals'} filled",
                  (local_panel.x + 24, local_panel.y + 70 + stats_offset,
                   local_panel.width - 48, 26), color=(*MUTED, stats_alpha))
        push_label = "push" if app.game.pushes == 1 else "pushes"
        self.text(canvas, f"{app.game.moves} moves     {app.game.pushes} {push_label}",
                  (local_panel.x + 24, local_panel.y + 100 + stats_offset,
                   local_panel.width - 48, 28), size=26,
                  color=(*INK, stats_alpha))

        stars = config.star_rating(
            app.game.current_level_path.name, app.game.moves, app.game.game_won)
        for index in range(3):
            phase = self._animation_phase(elapsed, 310 + index * 110, 480)
            if phase <= 0:
                continue
            if phase < .65:
                first = self._ease_out_cubic(phase / .65)
                scale = .25 + first
                angle = -30 + 38 * first
            else:
                settle = self._ease_out_cubic((phase - .65) / .35)
                scale = 1.25 - .25 * settle
                angle = 8 * (1 - settle)
            color = GOLD if index < stars else (136, 111, 67)
            glyph = self.symbol_font.render("\u2605" if index < stars else "\u2606", True, color)
            glyph = pygame.transform.rotozoom(glyph, -angle, scale)
            glyph.set_alpha(round(255 * min(1, phase / .65)))
            center = local_panel.centerx + (index - 1) * 30, local_panel.y + 145
            canvas.blit(glyph, glyph.get_rect(center=center))

        buttons_phase = self._ease_out_cubic(self._animation_phase(elapsed, 660, 400))
        buttons_layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
        self.button(buttons_layer, "levels" if last_level else "next", "Choose level" if last_level else "Next level",
                    (local_panel.x + 24, local_panel.y + 166, local_panel.width - 48, 42),
                    active=True, origin=canvas_origin)
        secondary_width = (local_panel.width - 58) // 2
        self.button(buttons_layer, "reset", "Play again",
                    (local_panel.x + 24, local_panel.y + 224, secondary_width, 38),
                    origin=canvas_origin)
        self.button(buttons_layer, "dismiss_completion" if last_level else "levels", "View board" if last_level else "Levels",
                    (local_panel.x + 34 + secondary_width, local_panel.y + 224,
                     secondary_width, 38), origin=canvas_origin)
        buttons_layer.set_alpha(round(255 * buttons_phase))
        canvas.blit(buttons_layer, (0, round(10 * (1 - buttons_phase))))
        self.modal_buttons = list(self.buttons)

        modal_phase = self._ease_out_back(self._animation_phase(elapsed, 0, 420))
        modal_scale = max(.01, .88 + .12 * modal_phase)
        offset_y = round(28 * (1 - modal_phase))
        modal_image = canvas
        scaled_size = (max(1, round(canvas.get_width() * modal_scale)),
                       max(1, round(canvas.get_height() * modal_scale)))
        if scaled_size != canvas.get_size():
            modal_image = pygame.transform.smoothscale(canvas, scaled_size)
        modal_image.set_alpha(round(255 * overlay_phase))
        target = modal_image.get_rect(center=(panel.centerx, panel.centery + offset_y))
        surface.blit(modal_image, target)

    def draw_deadlock(self, surface, app):
        width, height = surface.get_size()
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 110))
        surface.blit(veil, (0, 0))
        panel = pygame.Rect(0, 0, min(420, width - 40), 270)
        panel.center = width // 2, height // 2
        pygame.draw.rect(surface, PANEL, panel, border_radius=8)
        pygame.draw.rect(surface, RED, panel, 2, border_radius=8)
        self.buttons = []
        self.text(surface, "Box stuck", (panel.x + 22, panel.y + 24, panel.width - 70, 38), size=32, color=RED)
        self.button(surface, "dismiss_deadlock", "\u00d7",
                    (panel.right - 40, panel.y + 10, 28, 28), symbol=True)
        self.text(surface, "A box cannot reach a goal.",
                  (panel.x + 24, panel.y + 76, panel.width - 48, 28), color=MUTED)
        self.button(surface, "reset", "Play again",
                    (panel.x + 24, panel.y + 142, panel.width - 48, 42), active=True)
        secondary_width = (panel.width - 58) // 2
        self.button(surface, "undo", "Undo", (panel.x + 24, panel.y + 202, secondary_width, 38), app.game.can_undo)
        self.button(surface, "levels", "Levels", (panel.x + 34 + secondary_width, panel.y + 202, secondary_width, 38))
        self.modal_buttons = list(self.buttons)

    def draw_levels(self, surface, app):
        width, height = surface.get_size()
        self.text(surface, "Levels", (22, TOP + 2, width - 44, 34), size=32)
        visible = max(1, (height - TOP - BOTTOM - 48) // 48)
        app.menu_offset = max(0, min(app.menu_offset, max(0, len(app.levels) - visible)))
        for index in range(app.menu_offset, min(len(app.levels), app.menu_offset + visible)):
            game = app.catalog[index]
            title = game.current_level_path.stem.replace("_", " ").title()
            stars = app.progress.stars(game)
            rating = "\u2605" * stars + "\u2606" * (3 - stars) if stars else ""
            label = f"{index + 1:02d}   {title}   /   {len(game.goals)} boxes"
            if rating:
                label = f"{rating}   {label}"
            y = TOP + 42 + (index - app.menu_offset) * 48
            self.button(surface, f"level:{index}", label, (22, y, width - 44, 40),
                        active=index == app.level_index, symbol=bool(rating))
        if len(app.levels) > visible:
            track_h = visible * 48
            thumb_h = max(20, track_h * visible // len(app.levels))
            thumb_y = TOP + 42 + (track_h - thumb_h) * app.menu_offset // max(1, len(app.levels) - visible)
            pygame.draw.rect(surface, GREEN, (width - 12, thumb_y, 3, thumb_h))

    def action_at(self, position, modal=False):
        buttons = self.modal_buttons if modal else self.buttons
        for rect, action, enabled, _ in reversed(buttons):
            if enabled and rect.collidepoint(position):
                return action
        return None
