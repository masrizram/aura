import sys

from .cli import main_cli


def main():
    sys.exit(main_cli(standalone_mode=False) or 0)


if __name__ == "__main__":
    main()