"""python -m aura entry point."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.engine.main import main

if __name__ == "__main__":
    main()