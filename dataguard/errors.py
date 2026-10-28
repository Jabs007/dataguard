"""Custom exceptions for DataGuard."""


class DataGuardError(Exception):
    """Base exception for DataGuard."""


class InvalidPathError(DataGuardError):
    """The input file cannot be read (missing, not a regular file, etc.)."""


class EncodingError(DataGuardError):
    """The file could not be decoded as text."""


class MalformedCSVError(DataGuardError):
    """The CSV content could not be parsed."""


class EmptyFileError(DataGuardError):
    """The file has no header row at all."""
