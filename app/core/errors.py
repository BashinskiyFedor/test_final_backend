"""Доменные ошибки. Соответствие HTTP-статусам задаётся в app/api/errors.py."""


class DomainError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class InvalidInputError(DomainError):
    pass


class KeitaroError(DomainError):
    """Keitaro недоступен или ответил ошибкой."""
