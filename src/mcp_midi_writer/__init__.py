"""MCP MIDI Writer package."""

__version__ = "0.1.0"
__all__ = ["main", "generate_midi_core", "list_roles_core", "list_section_templates_core"]

from .server import generate_midi_core, list_roles_core, list_section_templates_core, main


def main() -> None:
    # Import lazily to keep MCP stdio handshake fast.
    from .server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
