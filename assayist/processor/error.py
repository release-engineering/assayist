# SPDX-License-Identifier: GPL-3.0+


class BuildSourceNotFound(RuntimeError):
    """Signify that the source of a Koji build couldn't be determined."""

    pass
