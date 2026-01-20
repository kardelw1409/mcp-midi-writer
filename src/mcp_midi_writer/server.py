from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass

from fastmcp import FastMCP


mcp = FastMCP(
    "MIDI Writer",
    dependencies=["mido"],
    description="Generate standard MIDI files from musical roles and sections.",
)


PPQ = 480

ROLE_LIST = [
    "kick_pattern",
    "bass",
    "sub_bass",
    "chords",
    "lead",
    "arp",
    "fx_rhythm",
    "wobble",
]

SECTION_LIST = ["intro", "build", "break", "drop", "outro"]


@dataclass(frozen=True)
class TimeSignature:
    numerator: int
    denominator: int

    @property
    def beats_per_bar(self) -> float:
        return self.numerator * (4 / self.denominator)


NOTE_TO_PC = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}

SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
}


@mcp.tool()
def list_roles() -> list[str]:
    """Returns supported musical roles."""
    return ROLE_LIST


@mcp.tool()
def list_section_templates() -> list[str]:
    """Returns supported section archetypes."""
    return SECTION_LIST


@mcp.tool()
def generate_midi(
    role: str,
    section: str,
    bars: int,
    tempo: float,
    time_signature: str,
    scale: str,
    root_note: str,
    style_tags: list[str] | None,
    rhythmic_density: str,
    output_path: str,
    seed: int | None = None,
) -> dict:
    """
    Generate a MIDI file aligned to bars/beats using musical heuristics.
    """
    import mido  # type: ignore

    if role not in ROLE_LIST:
        raise ValueError(f"Unknown role: {role}")
    if section not in SECTION_LIST:
        raise ValueError(f"Unknown section: {section}")
    if bars <= 0:
        raise ValueError("bars must be positive")

    ts = _parse_time_signature(time_signature)
    scale_root, scale_quality = _parse_scale(scale, root_note)
    scale_pcs = _build_scale(scale_root, scale_quality)

    rng = random.Random(_seed_from_inputs(seed, role, section, bars, tempo, scale, root_note))

    midi = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    track = mido.MidiTrack()
    midi.tracks.append(track)

    track.append(mido.MetaMessage("time_signature", numerator=ts.numerator, denominator=ts.denominator, time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo), time=0))

    events: list[tuple[int, int, mido.Message]] = []

    total_beats = bars * ts.beats_per_bar
    if role == "kick_pattern":
        events.extend(_kick_pattern(section, bars, ts, rng))
    elif role in {"bass", "sub_bass", "wobble"}:
        events.extend(_bass_line(role, section, bars, ts, scale_pcs, rng))
    elif role == "chords":
        events.extend(_chord_part(section, bars, ts, scale_pcs, rng, rhythmic_density, style_tags))
    elif role == "lead":
        events.extend(_lead_part(section, bars, ts, scale_pcs, rng, rhythmic_density))
    elif role == "arp":
        events.extend(_arp_part(section, bars, ts, scale_pcs, rng, rhythmic_density))
    elif role == "fx_rhythm":
        events.extend(_fx_rhythm(section, bars, ts, rng, rhythmic_density))
    else:
        raise ValueError(f"Unhandled role: {role}")

    events = [event for event in events if event[0] <= _beats_to_ticks(total_beats)]
    events.sort(key=lambda item: (item[0], item[1]))

    last_tick = 0
    for tick, _, msg in events:
        msg.time = tick - last_tick
        track.append(msg)
        last_tick = tick

    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    midi.save(abs_path)

    return {
        "output_path": abs_path,
        "role": role,
        "section": section,
        "bars": bars,
        "tempo": tempo,
        "time_signature": f"{ts.numerator}/{ts.denominator}",
        "scale": f"{scale_root} {scale_quality}",
    }


def _parse_time_signature(value: str) -> TimeSignature:
    parts = value.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid time signature: {value}")
    numerator = int(parts[0])
    denominator = int(parts[1])
    if numerator <= 0 or denominator <= 0:
        raise ValueError(f"Invalid time signature: {value}")
    return TimeSignature(numerator=numerator, denominator=denominator)


def _parse_scale(scale: str, root_note: str) -> tuple[str, str]:
    scale = (scale or "").strip()
    if scale:
        parts = scale.split()
        if len(parts) >= 2:
            return parts[0].upper(), parts[1].lower()
    if root_note:
        return root_note.strip().upper(), "minor"
    return "C", "minor"


def _build_scale(root: str, quality: str) -> list[int]:
    root_pc = _parse_note_pc(root)
    intervals = SCALE_INTERVALS.get(quality.lower())
    if not intervals:
        raise ValueError(f"Unsupported scale quality: {quality}")
    return [((root_pc + interval) % 12) for interval in intervals]


def _parse_note_pc(note: str) -> int:
    normalized = note.strip().upper().replace(" ", "")
    if len(normalized) >= 2 and normalized[1] in {"#", "B"}:
        key = normalized[:2]
    else:
        key = normalized[:1]
    if key not in NOTE_TO_PC:
        raise ValueError(f"Invalid root note: {note}")
    return NOTE_TO_PC[key]


def _seed_from_inputs(
    seed: int | None,
    role: str,
    section: str,
    bars: int,
    tempo: float,
    scale: str,
    root_note: str,
) -> int:
    if seed is not None:
        return int(seed)
    payload = f"{role}|{section}|{bars}|{tempo}|{scale}|{root_note}"
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest(), 16) % (2**31)


def _beats_to_ticks(beats: float) -> int:
    return int(round(beats * PPQ))


def _note_length_from_density(rhythmic_density: str) -> float:
    density = (rhythmic_density or "medium").lower()
    if density == "low":
        return 2.0
    if density == "high":
        return 0.5
    return 1.0


def _velocity(rng: random.Random, base: int, spread: int = 10) -> int:
    return max(1, min(127, base + rng.randint(-spread, spread)))


def _pick_pitch(scale_pcs: list[int], low: int, high: int, rng: random.Random) -> int:
    options = [n for n in range(low, high + 1) if n % 12 in scale_pcs]
    if not options:
        return low
    return rng.choice(options)


def _chord_tones(scale_pcs: list[int], degree: int, base_octave: int) -> list[int]:
    root_pc = scale_pcs[degree % 7]
    third_pc = scale_pcs[(degree + 2) % 7]
    fifth_pc = scale_pcs[(degree + 4) % 7]
    root = base_octave * 12 + root_pc
    third = base_octave * 12 + third_pc
    fifth = base_octave * 12 + fifth_pc
    return [root, third, fifth]


def _progression_for_section(section: str) -> list[int]:
    if section == "intro":
        return [0, 5]
    if section == "break":
        return [0, 3, 5]
    if section == "build":
        return [0, 5, 6]
    if section == "drop":
        return [0, 5, 6, 3]
    return [0, 5, 6, 0]


def _add_note(events: list[tuple[int, int, object]], start_beats: float, length_beats: float, pitch: int, velocity: int) -> None:
    import mido  # type: ignore

    start_tick = _beats_to_ticks(start_beats)
    end_tick = _beats_to_ticks(start_beats + length_beats)
    events.append((start_tick, 1, mido.Message("note_on", note=pitch, velocity=velocity, time=0)))
    events.append((end_tick, 0, mido.Message("note_off", note=pitch, velocity=0, time=0)))


def _kick_pattern(section: str, bars: int, ts: TimeSignature, rng: random.Random) -> list[tuple[int, int, object]]:
    events: list[tuple[int, int, object]] = []
    beats_per_bar = ts.beats_per_bar
    for bar in range(bars):
        base = bar * beats_per_bar
        if section in {"intro", "break", "outro"}:
            hits = [0.0, beats_per_bar / 2]
        elif section == "build":
            hits = [0.0, beats_per_bar / 2, beats_per_bar - 0.5]
        else:
            hits = [float(b) for b in range(int(beats_per_bar))]
        for beat in hits:
            _add_note(events, base + beat, 0.25, 36, _velocity(rng, 110, 5))
    return events


def _bass_line(
    role: str,
    section: str,
    bars: int,
    ts: TimeSignature,
    scale_pcs: list[int],
    rng: random.Random,
) -> list[tuple[int, int, object]]:
    events: list[tuple[int, int, object]] = []
    beats_per_bar = ts.beats_per_bar
    low, high = (24, 36) if role == "sub_bass" else (36, 48)

    for bar in range(bars):
        base = bar * beats_per_bar
        if section == "drop":
            pattern = [0.0, 1.5, 2.0, 3.5]
        elif section == "build":
            pattern = [0.0, 2.0, 3.0]
        else:
            pattern = [0.0, 2.0]

        for idx, beat in enumerate(pattern):
            pitch = _pick_pitch(scale_pcs, low, high, rng)
            if idx % 2 == 1:
                pitch = _pick_pitch([scale_pcs[0], scale_pcs[4]], low, high, rng)
            desired = 0.75 if role != "wobble" else 1.25
            next_beat = pattern[idx + 1] if idx + 1 < len(pattern) else beats_per_bar
            length = min(desired, max(0.25, next_beat - beat - 0.05))
            _add_note(events, base + beat, length, pitch, _velocity(rng, 95, 12))
    return events


def _chord_part(
    section: str,
    bars: int,
    ts: TimeSignature,
    scale_pcs: list[int],
    rng: random.Random,
    rhythmic_density: str,
    style_tags: list[str] | None,
) -> list[tuple[int, int, object]]:
    events: list[tuple[int, int, object]] = []
    beats_per_bar = ts.beats_per_bar
    chord_len = _note_length_from_density(rhythmic_density)
    progression = _progression_for_section(section)
    broken = bool(style_tags and any(tag.lower() in {"broken", "arp", "rhythmic"} for tag in style_tags))

    for bar in range(bars):
        base = bar * beats_per_bar
        degree = progression[bar % len(progression)]
        chord = _chord_tones(scale_pcs, degree, base_octave=4)
        if rng.random() < 0.35:
            chord.append(chord[0] + 12)
        if broken or rhythmic_density == "high":
            step = chord_len / len(chord)
            for idx, note in enumerate(chord):
                _add_note(events, base + idx * step, chord_len, note, _velocity(rng, 88, 8))
        else:
            for note in chord:
                _add_note(events, base, chord_len * 1.5, note, _velocity(rng, 86, 6))
    return events


def _lead_part(
    section: str,
    bars: int,
    ts: TimeSignature,
    scale_pcs: list[int],
    rng: random.Random,
    rhythmic_density: str,
) -> list[tuple[int, int, object]]:
    events: list[tuple[int, int, object]] = []
    beats_per_bar = ts.beats_per_bar
    step = _note_length_from_density(rhythmic_density)
    motif_notes = rng.randint(3, 6)
    last_pitch = _pick_pitch(scale_pcs, 60, 72, rng)

    for bar in range(bars):
        base = bar * beats_per_bar
        if section in {"break", "outro"} and rng.random() < 0.4:
            continue
        for i in range(motif_notes):
            if rng.random() < 0.25:
                continue
            direction = rng.choice([-2, -1, 1, 2])
            candidate = last_pitch + direction
            if candidate < 60 or candidate > 76 or candidate % 12 not in scale_pcs:
                candidate = _pick_pitch(scale_pcs, 60, 76, rng)
            last_pitch = candidate
            beat = (i * step) % beats_per_bar
            _add_note(events, base + beat, step * 0.9, last_pitch, _velocity(rng, 96, 12))
    return events


def _arp_part(
    section: str,
    bars: int,
    ts: TimeSignature,
    scale_pcs: list[int],
    rng: random.Random,
    rhythmic_density: str,
) -> list[tuple[int, int, object]]:
    events: list[tuple[int, int, object]] = []
    beats_per_bar = ts.beats_per_bar
    step = 0.5 if rhythmic_density == "high" else 1.0
    progression = _progression_for_section(section)

    for bar in range(bars):
        base = bar * beats_per_bar
        degree = progression[bar % len(progression)]
        chord = _chord_tones(scale_pcs, degree, base_octave=5)
        pattern = chord + chord[::-1]
        for idx, note in enumerate(pattern):
            beat = (idx * step) % beats_per_bar
            _add_note(events, base + beat, step * 0.95, note, _velocity(rng, 84, 10))
    return events


def _fx_rhythm(
    section: str,
    bars: int,
    ts: TimeSignature,
    rng: random.Random,
    rhythmic_density: str,
) -> list[tuple[int, int, object]]:
    events: list[tuple[int, int, object]] = []
    beats_per_bar = ts.beats_per_bar
    step = 0.5 if rhythmic_density == "high" else 1.0
    pitch = 84

    for bar in range(bars):
        base = bar * beats_per_bar
        if section == "intro" and rng.random() < 0.5:
            continue
        beat = 0.0
        while beat < beats_per_bar:
            if rng.random() < 0.8:
                _add_note(events, base + beat, step * 0.6, pitch, _velocity(rng, 70, 15))
            beat += step
    return events


@mcp.prompt()
def usage_prompt() -> str:
    return (
        "MIDI Writer MCP ready. Use list_roles(), list_section_templates(), "
        "and generate_midi(...) to create grid-aligned MIDI files."
    )


if __name__ == "__main__":
    mcp.run()


def main() -> None:
    # Run the MCP server. Important: don't print to stdout in stdio transport.
    mcp.run()
