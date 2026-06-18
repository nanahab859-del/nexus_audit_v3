from __future__ import annotations
import argparse
from typing import List, Optional, Tuple


class CommandParser:
    """
    Thin argparse wrapper for REPL argument parsing.

    - Never calls sys.exit() (exit_on_error=False, Python >= 3.9)
    - Returns (dict, None) on success or (None, error_str) on failure
    - Fluent .add_argument() interface for inline parser construction
    """

    def __init__(self, prog: str, description: str = ""):
        self._parser = argparse.ArgumentParser(
            prog=prog,
            description=description,
            exit_on_error=False,
            add_help=True,
        )

    def add_argument(self, *args, **kwargs) -> "CommandParser":
        """Fluent interface — returns self so calls can be chained."""
        self._parser.add_argument(*args, **kwargs)
        return self

    def parse(self, args: List[str]) -> Tuple[Optional[dict], Optional[str]]:
        """
        Parse args list.
        Returns (params_dict, None) on success.
        Returns (None, error_message) on any failure — no sys.exit.
        """
        try:
            ns = self._parser.parse_args(args)
            return vars(ns), None
        except argparse.ArgumentError as e:
            return None, str(e)
        except SystemExit:
            # --help raises SystemExit even with exit_on_error=False on some Python builds
            return None, self._parser.format_help()

    def format_help(self) -> str:
        return self._parser.format_help()
