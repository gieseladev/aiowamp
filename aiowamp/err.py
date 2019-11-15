import aiowamp


@aiowamp.register_error_response(aiowamp.uri.INVALID_URI)
class InvalidURI(aiowamp.ErrorResponse, ValueError):
    ...


@aiowamp.register_error_response(aiowamp.uri.NO_SUCH_PROCEDURE)
class NoSuchProcedure(aiowamp.ErrorResponse, LookupError):
    ...


@aiowamp.register_error_response(aiowamp.uri.INVALID_ARGUMENT)
class InvalidArgument(aiowamp.ErrorResponse, TypeError):
    ...
