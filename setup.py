# SPDX-License-Identifier: GPL-3.0+
from setuptools import setup

requirements = []
with open('requirements.txt', 'r') as f:
    requirements = f.readlines()

setup(
    name='assayist',
    version='0.1',
    description=('Maps source to shipped artifacts and upstream components to '
                 'artifacts in a graph database'),
    author='Red Hat, Inc.',
    author_email='pnt-factory2-devel@redhat.com',
    license='GPLv3+',
    packages=[
        'assayist',
        'assayist.common'
    ],
    include_package_data=True,
    install_requires=requirements,
)
