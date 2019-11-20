from .errors import ErrorResponse, register_error_response
from .uri import INVALID_ARGUMENT, INVALID_URI, PROCEDURE_ALREADY_EXISTS

__all__ = ["InvalidURI", "ProcedureAlreadyExists", "InvalidArgument"]


@register_error_response(INVALID_URI)
class InvalidURI(ErrorResponse):
    ...


@register_error_response(PROCEDURE_ALREADY_EXISTS)
class ProcedureAlreadyExists(ErrorResponse):
    ...


@register_error_response(INVALID_ARGUMENT)
class InvalidArgument(ErrorResponse):
    ...
