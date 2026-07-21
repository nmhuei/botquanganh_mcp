from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EXIT_OK = 0
EXIT_OPERATION_FAILED = 1
EXIT_USAGE = 2
EXIT_CONNECTION = 3
EXIT_AUTH = 4
EXIT_POLICY = 5
EXIT_NOT_FOUND = 6
EXIT_TIMEOUT = 7
EXIT_CONFLICT = 8


@dataclass
class CLIError(Exception):
    message: str
    exit_code: int = EXIT_OPERATION_FAILED
    details: Any = None

    def __str__(self) -> str:
        return self.message


class ConnectionCLIError(CLIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message, EXIT_CONNECTION, details)


class AuthenticationCLIError(CLIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message, EXIT_AUTH, details)


class PolicyCLIError(CLIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message, EXIT_POLICY, details)


class NotFoundCLIError(CLIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message, EXIT_NOT_FOUND, details)


class TimeoutCLIError(CLIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message, EXIT_TIMEOUT, details)


class ConflictCLIError(CLIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message, EXIT_CONFLICT, details)


def error_from_http(status: int, message: str, details: Any = None) -> CLIError:
    if status in {401, 407}:
        return AuthenticationCLIError(message, details)
    if status == 403:
        return PolicyCLIError(message, details)
    if status == 404:
        return NotFoundCLIError(message, details)
    if status in {408, 504}:
        return TimeoutCLIError(message, details)
    if status == 409:
        return ConflictCLIError(message, details)
    return CLIError(message, EXIT_OPERATION_FAILED, details)
