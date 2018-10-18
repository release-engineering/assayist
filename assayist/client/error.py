# SPDX-License-Identifier: GPL-3.0+


class NotFound(RuntimeError):
    """Signify that a node was not found in the database."""

    pass


class InvalidInput(RuntimeError):
    """Signify that the input to the API was invalid."""

    pass
