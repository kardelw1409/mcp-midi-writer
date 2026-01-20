# mcp-midi-writer

An MCP server that generates standard MIDI files based on musical roles and sections.

## Features
- MIDI file generation with grid-aligned notes
- Roles: bass, sub bass, chords, lead, arp, kick pattern, fx rhythm, wobble
- Sections: intro, build, break, drop, outro
- Deterministic output with optional seed

## Running

```bash
python -m mcp_midi_writer
```

## Tools

- `list_roles()`
- `list_section_templates()`
- `generate_midi(role, section, bars, tempo, time_signature, scale, root_note, style_tags, rhythmic_density, output_path, seed=None)`

The server writes MIDI files to the provided `output_path`.
