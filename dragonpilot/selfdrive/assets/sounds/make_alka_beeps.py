#!/usr/bin/env python3
"""Generate the ALKA chimes, mirroring selfdrive/assets/sounds/make_beeps.py.

Rising = ALKA on, falling = ALKA off. Two notes rather than one so ALKA cannot be
confused with engage/disengage, which are single tones; the notes also avoid stock's
exact pitches (E6 1319 = disengage, G#6 1661 = engage).

Pitch matters more than it looks: the first version of these sat at 370/294 Hz, below
where the device speaker responds usefully, and sounded muddy however loud it was. These
sit in the band comma uses for engage/disengage.
"""
import wave

import numpy as np

sr = 48000
max_int16 = 2**15 - 1

D6, G6 = 1174.659, 1567.982


def beep(freq, duration_seconds, attack_seconds=0.004):
  n = int(sr * duration_seconds)
  t = np.arange(n)
  signal = np.sin(2 * np.pi * freq * t / sr) * np.exp(-t / 5.5e3)  # same decay as make_beeps.py
  # make_beeps.py starts at full amplitude; that click reads as harsh on these higher
  # notes, so ramp the first few ms in.
  a = int(sr * attack_seconds)
  signal[:a] *= np.linspace(0, 1, a) ** 2
  return max_int16 * signal


def two_note(f1, f2, duration=0.15, gap=0.05):
  return np.concatenate([beep(f1, duration), np.zeros(int(sr * gap)), beep(f2, duration)])


def write(path, samples):
  # stdlib wave, not scipy.io: scipy is not an openpilot dependency (make_beeps.py only
  # gets away with it because nothing runs it). soundd asserts mono/16-bit/48kHz on load.
  with wave.open(path, "w") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(sr)
    f.writeframes(samples.astype(np.int16).tobytes())


if __name__ == "__main__":
  write("autosteer_enabled.wav", two_note(D6, G6))
  write("autosteer_disabled.wav", two_note(G6, D6))
