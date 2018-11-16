# SPDX-License-Identifier: GPL-3.0+


class BuildSourceNotFound(RuntimeError):
    """Signify that the source of a Koji build couldn't be determined."""

    pass


class AnalysisFailure(RuntimeError):
    """Signify that an Analyzer completed its analysis but wasn't completely successful."""

    pass
