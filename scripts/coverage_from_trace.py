#!/usr/bin/env python3
"""Line coverage from the counts that `python3 -m trace` writes.

`trace --summary` reports 100% for every module unless `--missing` is
given, since it only counts the lines that ran.  This reads the
`.cover` files that `trace --count -C COVER_DIR` wrote and compares
the lines that ran with each module's executable lines:

```
python3 -m trace --count --summary -C COVER_DIR \
    --ignore-dir=/usr/lib/python3.12 \
    --module unittest discover -s tests -t .
./scripts/coverage_from_trace.py COVER_DIR
```

It prints, for each module (tests left out), its executable lines and
the percent of them that ran, then a total.
"""

import argparse
import re
import sys
import trace
from pathlib import Path

# A counted line in a `.cover` file starts with its count and a colon.
COUNTED: re.Pattern[str] = re.compile(r"\s*\d+:")


def coverage(cover: Path, source: Path) -> tuple[int, int]:
    """Return a module's executable lines and how many of them ran.

    Arguments:
    * `cover` (`Path`): The module's `.cover` file.
    * `source` (`Path`): The module's source file.

    Returns:
    * (`tuple[int, int]`): The executable lines, and those that ran.
    """
    # `trace` has no public way to list executable lines, and its
    # private one is not in `typeshed`, so it is looked up by name.
    private: str = "_find_executable_linenos"
    executable: set[int] = set(getattr(trace, private)(str(source)))
    ran: set[int] = {
        number
        for number, line in enumerate(cover.read_text().splitlines(), 1)
        if COUNTED.match(line)
    }
    return len(executable), len(executable & ran)


def main() -> int:
    """Print the coverage of each module, and the total.

    Returns:
    * (`int`): 0, or 1 when no module was found.
    """
    # Read the arguments.
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "cover_dir", type=Path, help="the directory given to `trace -C`"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="where the modules' dotted names start (the repository)",
    )
    arguments: argparse.Namespace = parser.parse_args()
    cover_dir: Path = arguments.cover_dir
    root: Path = arguments.root

    # Each module's line, leaving out tests and files that are gone.
    total_lines: int = 0
    total_ran: int = 0
    cover: Path
    for cover in sorted(cover_dir.glob("*.cover")):
        name: str = cover.stem
        if name.split(".")[-1].startswith("test_"):
            continue
        source: Path = root / (name.replace(".", "/") + ".py")
        if not source.exists():
            continue
        lines: int
        ran: int
        lines, ran = coverage(cover, source)
        if lines:
            total_lines += lines
            total_ran += ran
            print(f"{lines:6d} {100 * ran / lines:5.1f}%  {name}")

    # The total.
    if not total_lines:
        print(f"No modules in {cover_dir}", file=sys.stderr)
        return 1
    print(f"{total_lines:6d} {100 * total_ran / total_lines:5.1f}%  TOTAL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
