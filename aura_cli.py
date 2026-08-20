#!/usr/bin/env python3
"""AURA CLI entry point — works from repo root and pip-installed environments."""
import sys
import os


def main():
    try:
        from src.engine.main import main as engine_main
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from src.engine.main import main as engine_main
    sys.exit(engine_main() or 0)


if __name__ == "__main__":
    main()