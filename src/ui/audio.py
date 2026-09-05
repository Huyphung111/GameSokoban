"""Looping background music and synthesized cues with graceful mixer fallback."""

from array import array
from math import pi, sin

import pygame

try:
    from src import config
except ImportError:
    import config


class Audio:
    def __init__(self, enabled=True, music_active=False):
        self._enabled = bool(enabled)
        self.music_active = bool(music_active)
        self.sounds = {}
        self.music_available = False
        self.music_started = False
        self.available = bool(pygame.mixer.get_init())
        if not self.available:
            return
        rate, sample_format, channels = pygame.mixer.get_init()
        if sample_format != -16:
            self.available = False
            return
        for name, frequency, duration in (("move", 360, .035), ("push", 200, .07),
                                          ("goal", 880, .13), ("win", 740, .22)):
            samples = array("h")
            length = int(rate * duration)
            for index in range(length):
                value = int(2600 * sin(2 * pi * frequency * index / rate) * (1 - index / length))
                samples.extend([value] * channels)
            self.sounds[name] = pygame.mixer.Sound(buffer=samples.tobytes())
        if config.MUSIC_FILE.exists():
            try:
                pygame.mixer.music.load(str(config.MUSIC_FILE))
                pygame.mixer.music.set_volume(config.MUSIC_VOLUME)
                self.music_available = True
                self._sync_music()
            except pygame.error:
                # Sound effects remain available if this machine cannot decode MP3.
                self.music_available = False

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = bool(value)
        self._sync_music()

    def _sync_music(self):
        if not self.music_available:
            return
        if self._enabled and self.music_active:
            if self.music_started:
                pygame.mixer.music.unpause()
            else:
                pygame.mixer.music.play(loops=-1)
                self.music_started = True
        elif self.music_started:
            pygame.mixer.music.pause()

    def set_music_active(self, active):
        self.music_active = bool(active)
        self._sync_music()

    def play(self, name):
        if self.available and self.enabled:
            self.sounds[name].play()

    def close(self):
        if self.music_available:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            self.music_started = False
