class AppError(Exception):
    """Expected error that can be safely shown to an API client."""

    status_code = 400


class SessionNotFoundError(AppError):
    status_code = 404


class UploadValidationError(AppError):
    status_code = 422


class UnsafeQueryError(AppError):
    status_code = 400


class ModelConfigurationError(AppError):
    status_code = 503

