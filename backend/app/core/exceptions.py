class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class LoginRateLimitExceededError(Exception):
    pass


class InactiveUserError(Exception):
    pass


class InvalidAccessTokenError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class UserSessionNotFoundError(Exception):
    pass
