#! /usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0+

import argparse
import datetime
from neomodel import db

from assayist.common.models.content import Build
from assayist.processor.configuration import config
from assayist.processor.utils import get_koji_session


def batch_dates_for_range(start_date, end_date):
    """
    Generate batches of dates that cover the given time period.

    Koji runs out of memory if we ask about a whole year's worth of builds at a time, so
    let's batch the requests up.

    :param Date start_date: First start date to return.
    :param Date end_date: Date to continue until, inclusive.
    :return: An interable of tuples of ISO-formatted string datetimes, start and end respectively.
    :rtype: [(string, string)]
    """
    period = datetime.timedelta(days=10)
    end_date = end_date + datetime.timedelta(days=1)  # We want to find builds done on end_date too.

    def dt_string(x):
        return str(x) + ' 00:00:00'

    while (start_date + period) < end_date:
        yield dt_string(start_date), dt_string(start_date + period)
        start_date = start_date + period

    yield dt_string(start_date), dt_string(end_date)


def valid_date(s):
    """
    Convert input string to a date, or error.

    https://stackoverflow.com/questions/25470844/specify-format-for-input-arguments-argparse-python
    """
    try:
        return datetime.datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


desc = 'Create stubbed build entries for containers built in the given date range'
parser = argparse.ArgumentParser(description=desc)
parser.add_argument('-s', '--start', required=True, type=valid_date,
                    help='Import builds created on or after this date. YYYY-MM-DD. Required.')
parser.add_argument('-e', '--end', type=valid_date, default=datetime.date.today(),
                    help='Import builds created on or before this date. YYYY-MM-DD. Default today.')
args = parser.parse_args()

db.set_connection(config.DATABASE_URL)
koji = get_koji_session()
for start, end in batch_dates_for_range(args.start, args.end):
    print(f'Stubbing container builds between {start} and {end}.')
    for build in koji.listBuilds(createdAfter=start, createdBefore=end, type='image', state=1):
        Build.get_or_create({'id_': build['build_id'], 'type_': 'buildContainer'})
