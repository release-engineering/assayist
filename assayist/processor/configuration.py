# SPDX-License-Identifier: GPL-3.0+

import os
import logging


class Config(object):
    """The base Assayist Processor configuration."""

    koji_profile = 'brew'
    log_level = logging.INFO


class ProdConfig(Config):
    """The production Assayist application configuration."""

    pass


class DevConfig(Config):
    """The development Assayist application configuration."""

    log_level = logging.DEBUG


class TestConfig(Config):
    """The test Assayist application configuration."""

    pass


if os.getenv('ASSAYIST_DEV', '').lower() == 'true':
    config = DevConfig
elif os.getenv('ASSAYIST_TESTING', '').lower() == 'true':
    config = TestConfig
else:
    config = ProdConfig
