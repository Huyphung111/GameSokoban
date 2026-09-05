"""Small synthesized cues; audio is optional on machines without a mixer."""

from array import array
from math import pi, sin

import pygame


class Audio:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.sounds = {}
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

    def play(self, name):
        if self.available and self.enabled:
            self.sounds[name].play()
