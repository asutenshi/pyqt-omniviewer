"""Небольшой модуль-образец исходного кода Python для подсветки синтаксиса."""

from __future__ import annotations

import sys


def greet(name: str) -> str:
    """Вернуть приветствие."""
    return f"Hello, {name}!"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    print(greet(args[0] if args else "world"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
