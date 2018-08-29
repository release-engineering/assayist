# SPDX-License-Identifier: GPL-3.0+

from assayist.common.models.placeholder import Placeholder


def test_placeholder():
    """Test that the Neo4j test setup works."""
    placeholder = Placeholder.nodes.get_or_none(id_='123')
    assert placeholder is None

    Placeholder(id_='123', description='This is a temporary placeholder').save()
    placeholder = Placeholder.nodes.get_or_none(id_='123')
    assert placeholder is not None
    assert placeholder.description == 'This is a temporary placeholder'
