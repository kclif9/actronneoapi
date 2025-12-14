"""Exception classes for Actron Air API errors."""


class ActronAirAuthError(Exception):
    """Exception raised for authentication-related errors.

    Raised when OAuth2 authentication fails, tokens are invalid or expired,
    or authorization is denied. This includes device code flow errors,
    token refresh failures, and 401 unauthorized responses.
    """

    pass


class ActronAirAPIError(Exception):
    """Exception raised for general API errors.

    Raised when API requests fail due to network errors, invalid responses,
    non-200 status codes (except 401), or malformed data. This is the base
    exception for all non-authentication related API failures.
    """

    pass
