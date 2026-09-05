"""Pygame board, compact controls and level selection."""

from pathlib import Path
from math import cos, pi, sin

import pygame

try:
    from src import config
except ImportError:
    import config

BG = (23, 27, 29)
PANEL = (34, 40, 42)
INK = (235, 240, 238)
MUTED = (162, 174, 172)
GREEN = (111, 214, 160)
RED = (248, 133, 132)
TOP = 174
BOTTOM = 108


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
        self.assets = {}
        self.tile_size = 0
        self.buttons = []
        self.modal_buttons = []
        self.goal_effects = []
        self.slider = pygame.Rect(0, 0, 0, 0)
        self.previous_state = self.current_state = None
        self.current_level = None
        self.animation_start = 0
        title_path = config.BASE_DIR / "assets" / "title_screen.jpg"
        self.title_bg = pygame.image.load(str(title_path)).convert() if title_path.exists() else None
        self.cached_title_surf = None
        self.cached_title_size = (0, 0)

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

    def button(self, surface, action, label, rect, enabled=True, tooltip="", active=False, symbol=False):
        rect = pygame.Rect(rect)
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        fill = (58, 80, 69) if active else ((59, 68, 68) if hovered and enabled else PANEL)
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        if active:
            pygame.draw.rect(surface, GREEN, rect, 1, border_radius=6)
        self.text(surface, label, rect.inflate(-4 if symbol else -12, -4), color=INK if enabled else (92, 104, 104),
                  center=True, symbol=symbol)
        self.buttons.append((rect, action, enabled, tooltip))

    def calculate_and_load_assets(self, game_map, screen_width, screen_height):
        if not game_map:
            return
        size = max(1, min((screen_width - 32) // len(game_map[0]),
                          max(1, screen_height - TOP - BOTTOM - 20) // len(game_map)))
        if size != self.tile_size:
            self.tile_size = size
            self.assets = {tile: pygame.transform.scale(img, (size, size))
                           for tile, img in self.originals.items()}

    def draw_board(self, surface, game):
        width, height = surface.get_size()
        board = game.game_map
        self.calculate_and_load_assets(board, width, height)
        size = self.tile_size
        ox = (width - game.width * size) // 2
        oy = TOP + (height - TOP - BOTTOM - game.height * size) // 2
        if game.level_id != self.current_level:
            self.previous_state = self.current_state = game.state
            self.current_level = game.level_id
        elif game.state != self.current_state:
            self.previous_state, self.current_state = self.current_state, game.state
            self.animation_start = pygame.time.get_ticks()
        amount = min(1.0, (pygame.time.get_ticks() - self.animation_start) / config.MOVE_ANIMATION_MS)
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

        def sprite(tile, point, start=None):
            x, y = point
            if start is not None:
                x = start[0] + (x - start[0]) * amount
                y = start[1] + (y - start[1]) * amount
            surface.blit(self.assets[tile], (round(ox + x * size), round(oy + y * size)))

        for box in boxes:
            start = next(iter(removed)) if box in added and len(removed) == len(added) == 1 else None
            sprite("$", box, start)
            if box in game.goals and (start is None or amount == 1):
                pygame.draw.rect(surface, GREEN,
                                 (ox + box[0] * size + 2, oy + box[1] * size + 2, size - 4, size - 4),
                                 max(1, size // 22), border_radius=min(4, size // 4))
        sprite("@", player, old_player)
        self.draw_goal_effects(surface, game, ox, oy, size)

    def add_goal_effects(self, goals):
        start = pygame.time.get_ticks() + config.MOVE_ANIMATION_MS
        self.goal_effects.extend((point, start) for point in sorted(goals))
        return start + config.GOAL_EFFECT_MS

    def clear_effects(self):
        self.goal_effects.clear()
        self.modal_buttons.clear()

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

        # Warm background fill
        surface.fill((210, 186, 155))
        floor_h = max(60, int(height * 0.12))
        pygame.draw.rect(surface, (119, 84, 62), (0, height - floor_h, width, floor_h))

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
        base_y = max(360, int(height * 0.60))

        # Check progress for button label
        entry = app.progress.entry(app.game)
        has_progress = bool(entry.get("actions")) or entry.get("completed")
        play_label = f"CONTINUE (LEVEL {app.level_index + 1:02d})" if has_progress else "START GAME"

        # Button 1: Play
        btn_w = min(320, width - 40)
        btn1 = pygame.Rect(0, 0, btn_w, 52)
        btn1.center = (center_x, base_y)
        hover1 = btn1.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (25, 75, 40), btn1.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, (56, 180, 95) if hover1 else (46, 160, 85), btn1, border_radius=12)
        pygame.draw.rect(surface, (210, 255, 230) if hover1 else (160, 235, 185), btn1, 2, border_radius=12)
        tx = btn1.x + 28
        ty = btn1.centery
        pygame.draw.polygon(surface, INK, [(tx - 6, ty - 8), (tx - 6, ty + 8), (tx + 7, ty)])
        self.text(surface, play_label, (btn1.x + 36, btn1.y, btn1.width - 48, btn1.height), size=24, color=INK, center=True)
        self.buttons.append((btn1, "start_game", True, "Play"))

        # Button 2: Levels
        btn2 = pygame.Rect(0, 0, btn_w, 46)
        btn2.center = (center_x, base_y + 64)
        hover2 = btn2.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (60, 45, 30), btn2.move(0, 3), border_radius=10)
        pygame.draw.rect(surface, (125, 92, 65) if hover2 else (105, 78, 55), btn2, border_radius=10)
        pygame.draw.rect(surface, (240, 215, 180) if hover2 else (215, 185, 150), btn2, 2, border_radius=10)
        self.text(surface, "CHOOSE LEVEL", btn2, size=22, color=INK, center=True)
        self.buttons.append((btn2, "select_level_menu", True, "Levels"))

        # Buttons 3 & 4: Sound & Exit
        sub_w = min(152, (btn_w - 12) // 2)
        btn3 = pygame.Rect(center_x - sub_w - 6, base_y + 120, sub_w, 40)
        hover3 = btn3.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (45, 52, 52), btn3.move(0, 2), border_radius=8)
        pygame.draw.rect(surface, (90, 102, 102) if hover3 else (75, 85, 85), btn3, border_radius=8)
        pygame.draw.rect(surface, (190, 205, 205), btn3, 1, border_radius=8)
        sound_label = "Sound: ON" if app.audio.enabled else "Sound: OFF"
        self.text(surface, sound_label, btn3, size=18, color=INK, center=True)
        self.buttons.append((btn3, "sound", app.audio.available, "Sound"))

        btn4 = pygame.Rect(center_x + 6, base_y + 120, sub_w, 40)
        hover4 = btn4.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (75, 35, 35), btn4.move(0, 2), border_radius=8)
        pygame.draw.rect(surface, (160, 70, 70) if hover4 else (140, 60, 60), btn4, border_radius=8)
        pygame.draw.rect(surface, (255, 180, 180), btn4, 1, border_radius=8)
        self.text(surface, "EXIT", btn4, size=18, color=INK, center=True)
        self.buttons.append((btn4, "exit", True, "Exit"))

        # Shortcut footer hint
        hint_text = "[ENTER / SPACE] Play   *   [TAB] Levels   *   [M] Sound   *   [ESC] Exit"
        self.text(surface, hint_text, (16, height - 34, width - 32, 24), size=14, color=(220, 195, 170), center=True)

    def draw(self, surface, app):
        if getattr(app, "title_screen", False):
            self.draw_title_screen(surface, app)
            return

        width, height = surface.get_size()
        surface.fill(BG)
        self.buttons = []
        pygame.draw.rect(surface, PANEL, (0, 0, width, 64))
        self.text(surface, "SOKOBAN", (18, 10, 180, 40), size=38)
        self.text(surface, f"{app.level_index + 1:02d} / {len(app.levels):02d}",
                  (width - 108, 14, 90, 32), size=26, color=GREEN, center=True)
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

        pygame.draw.rect(surface, PANEL, (0, height - BOTTOM, width, BOTTOM))
        game = app.game
        label = f"Moves {game.moves}    Pushes {game.pushes}    Goals {len(game.state[1] & game.goals)}/{len(game.goals)}"
        self.text(surface, label, (16, height - 102, width - 190, 28))
        self.text(surface, "AI assisted" if app.assisted else "Solo", (width - 160, height - 102, 144, 28), color=MUTED)
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
        if app.deadlock_open:
            self.draw_deadlock(surface, app)
            return
        if app.completion_visible:
            self.draw_completion(surface, app)
            return
        self.modal_buttons = []
        for rect, _, enabled, tooltip in self.buttons:
            if enabled and tooltip and rect.collidepoint(pygame.mouse.get_pos()):
                tip = pygame.Rect(rect.x, rect.bottom + 4, max(80, len(tooltip) * 10), 26)
                tip.clamp_ip(surface.get_rect())
                pygame.draw.rect(surface, (75, 85, 83), tip, border_radius=4)
                self.text(surface, tooltip, tip.inflate(-8, 0), size=18, center=True)

    def draw_completion(self, surface, app):
        width, height = surface.get_size()
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 110))
        surface.blit(veil, (0, 0))
        panel = pygame.Rect(0, 0, min(420, width - 40), 270)
        panel.center = width // 2, height // 2
        pygame.draw.rect(surface, PANEL, panel, border_radius=8)
        pygame.draw.rect(surface, GREEN, panel, 2, border_radius=8)
        self.buttons = []
        last_level = app.level_index == len(app.levels) - 1
        title = "Final level complete" if last_level else "Level complete"
        self.text(surface, title, (panel.x + 22, panel.y + 24, panel.width - 70, 38), size=32, color=GREEN)
        self.button(surface, "dismiss_completion", "\u00d7",
                    (panel.right - 40, panel.y + 10, 28, 28), tooltip="Close", symbol=True)
        goals = len(app.game.goals)
        self.text(surface, f"Level {app.level_index + 1:02d}  /  {goals} {'goal' if goals == 1 else 'goals'} filled",
                  (panel.x + 24, panel.y + 70, panel.width - 48, 26), color=MUTED)
        push_label = "push" if app.game.pushes == 1 else "pushes"
        self.text(surface, f"{app.game.moves} moves     {app.game.pushes} {push_label}",
                  (panel.x + 24, panel.y + 100, panel.width - 48, 28), size=26)
        self.button(surface, "levels" if last_level else "next", "Choose level" if last_level else "Next level",
                    (panel.x + 24, panel.y + 148, panel.width - 48, 42), active=True)
        secondary_width = (panel.width - 58) // 2
        self.button(surface, "reset", "Play again",
                    (panel.x + 24, panel.y + 206, secondary_width, 38))
        self.button(surface, "dismiss_completion" if last_level else "levels", "View board" if last_level else "Levels",
                    (panel.x + 34 + secondary_width, panel.y + 206, secondary_width, 38))
        self.modal_buttons = list(self.buttons)

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
            entry = app.progress.entry(game)
            title = game.current_level_path.stem.replace("_", " ").title()
            complete = "  /  Complete" if entry.get("completed") else ""
            label = f"{index + 1:02d}   {title}   /   {len(game.goals)} boxes{complete}"
            score = entry.get("best")
            if isinstance(score, list) and len(score) == 2:
                label += f"   /   Best {score[0]} pushes"
            y = TOP + 42 + (index - app.menu_offset) * 48
            self.button(surface, f"level:{index}", label, (22, y, width - 44, 40),
                        active=index == app.level_index)
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
