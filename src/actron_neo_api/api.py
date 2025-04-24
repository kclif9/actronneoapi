from typing import List

from .auth import TokenManager


class ActronNeoAPI:
    """Class to communicate with the ActronAirNeo API."""

    def __init__(self, auth: TokenManager):
        """Initialize the API and store the auth so we can make requests."""
        self.auth = auth
