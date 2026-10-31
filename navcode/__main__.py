"""Unified CLI; individual runners remain importable and executable."""
import argparse
import runpy
import sys


def main():
    commands = {"navigate": "navcode.runners.grounded", "develop": "navcode.runners.development",
                "smoke": "navcode.benchmark", "model-probe": "navcode.models.api"}
    parser = argparse.ArgumentParser(description="NavCode navigation experiments")
    parser.add_argument("command", choices=commands)
    argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return
    args = parser.parse_args(argv[:1])
    remaining = argv[1:]
    sys.argv = [commands[args.command], *remaining]
    runpy.run_module(commands[args.command], run_name="__main__")


if __name__ == "__main__":
    main()
