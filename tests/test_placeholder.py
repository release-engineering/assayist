# SPDX-License-Identifier: GPL-3.0+

from assayist.common.models.source import Component, SourceLocation


def test_placeholder():
    """Test that the Neo4j test setup works."""
    requests = Component(canonical_name='requests', canonical_type='python').save()
    source_url = 'https://github.com/requests/requests/archive/v2.19.1.tar.gz'
    source = SourceLocation(url=source_url).save()
    requests.source_locations.connect(source)

    # Query the database and test the relationship
    requests = Component.nodes.get(canonical_name='requests', canonical_type='python')
    assert requests is not None
    source_locations = requests.source_locations.all()
    assert len(source_locations) == 1
    assert source_locations[0].url == source_url
