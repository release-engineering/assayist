# SPDX-License-Identifier: GPL-3.0+

import logging

from assayist.processor.configuration import config

log = logging.getLogger('assayist_processor')
logging.basicConfig(level=config.log_level)
