"""
wsz6_play/gsl/errors.py

GSL-specific exception hierarchy.

All GSL errors are subclasses of GSLError so callers can catch the base
class for generic "something went wrong" handling, or narrow to a specific
subclass for finer-grained error reporting.
"""


class GSLError(Exception):
    """Base class for all GSL errors."""


class GSLSyntaxError(GSLError):
    """Unknown keyword, wrong argument count, or malformed token."""


class GSLCommandError(GSLError):
    """Command failed at runtime (e.g. slug not found, role full)."""


class GSLAssertionError(GSLError):
    """An Assert_* command produced a failing result."""


class GSLOrderError(GSLError):
    """Command appeared in the wrong position in the script
    (e.g. Set_rng_seed after Start_game, Op before Start_game)."""


class GSLSecurityError(GSLError):
    """A restricted command (e.g. Set_rng_seed) was used in production."""
