"""
wsz6_play/gsl/parser.py

Converts a .gsl text file into a flat list of Command objects.

Pipeline per line:
  1. Strip trailing newline.
  2. Strip inline comments (first unquoted '#' and everything after it).
  3. Expand $VAR references from os.environ.
  4. Tokenise with shlex.split() (handles double-quoted strings).
  5. Lowercase the first token to get the keyword.
  6. Inline-expand 'include' directives (recursive, cycle-detected).
  7. Emit all other keywords as Command objects.

Repeat / End_repeat pairs are left in the flat list; the executor's
_expand_repeats() converts them to RepeatBlock nodes at runtime.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from typing import FrozenSet, List

from .errors import GSLSyntaxError


@dataclass
class Command:
    """One parsed GSL command."""
    line_no:     int
    keyword:     str        # lowercased first token
    args:        list[str]  # remaining tokens (already $VAR-expanded, unquoted)
    source_file: str = ''   # absolute path of the file this came from


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(path: str, _seen: FrozenSet[str] = frozenset()) -> List[Command]:
    """Parse ``path`` and return a flat list of Command objects.

    Args:
        path:   Path to the .gsl file (relative or absolute).
        _seen:  Internal set used for circular-include detection; callers
                should not pass this argument.

    Raises:
        GSLSyntaxError: on file-not-found, circular include, tokenisation
                        error, or unknown structural issue.
    """
    path = os.path.abspath(path)
    if path in _seen:
        raise GSLSyntaxError(f'Circular Include detected: {path}')
    _seen = _seen | {path}
    script_dir = os.path.dirname(path)

    try:
        with open(path, encoding='utf-8') as fh:
            raw_lines = fh.readlines()
    except OSError as exc:
        raise GSLSyntaxError(f'Cannot read GSL file "{path}": {exc}') from exc

    commands: List[Command] = []

    for line_no, raw_line in enumerate(raw_lines, start=1):
        # 1. Strip trailing newline / whitespace
        line = raw_line.rstrip('\n')

        # 2. Strip inline comments (first unquoted '#')
        line = _strip_comment(line)
        line = line.strip()
        if not line:
            continue

        # 3. $VAR expansion (uppercase identifiers only, per spec)
        line = re.sub(
            r'\$([A-Z_][A-Z0-9_]*)',
            lambda m: os.environ.get(m.group(1), ''),
            line,
        )

        # 4. Tokenise with shlex (handles double-quoted strings as one token)
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            raise GSLSyntaxError(
                f'Line {line_no} in "{path}": tokenisation error: {exc}'
            ) from exc

        if not tokens:
            continue

        keyword = tokens[0].lower()
        args = tokens[1:]

        # 5. Inline-expand Include
        if keyword == 'include':
            if len(args) != 1:
                raise GSLSyntaxError(
                    f'Line {line_no}: Include requires exactly one filename argument'
                )
            inc_path = args[0]
            if not os.path.isabs(inc_path):
                inc_path = os.path.join(script_dir, inc_path)
            commands.extend(parse_file(inc_path, _seen))
        else:
            commands.append(Command(
                line_no=line_no,
                keyword=keyword,
                args=args,
                source_file=path,
            ))

    return commands


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Return the portion of *line* before the first unquoted '#'."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == '#' and not in_single and not in_double:
            return line[:i]
    return line
