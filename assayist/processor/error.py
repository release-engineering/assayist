# SPDX-License-Identifier: GPL-3.0+


class BuildTypeNotSupported(NotImplementedError):
    """Signify that a build type is not yet properly handled by analyzers."""

    pass


class BuildSourceNotFound(RuntimeError):
    """Signify that the source of a Koji build couldn't be determined."""

    pass


class BuildInvalidState(RuntimeError):
    """Signify that a build is in a non-complete state."""

    pass


class AnalysisFailure(RuntimeError):
    """Signify that an Analyzer completed its analysis but wasn't completely successful."""

    pass
