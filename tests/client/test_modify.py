# SPDX-License-Identifier: GPL-3.0+

import pytest

from assayist.common.models.source import Component, SourceLocation
from assayist.client import modify


def test_set_component_names_new():
    """Test that set_component_names can add a new component."""
    modify.set_component_names('requests', 'pypi', alternatives=['python-requests'])

    component = Component.nodes.get_or_none(
        canonical_namespace='', canonical_name='requests', canonical_type='pypi')
    assert component
    assert component.canonical_namespace == ''
    assert component.canonical_name == 'requests'
    assert component.canonical_type == 'pypi'
    assert component.alternative_names == ['python-requests']


def test_set_component_names_add_alt_names():
    """Test that set_component_names can add alternative names to an existing component."""
    Component.get_or_create_singleton('', 'requests', 'pypi')

    modify.set_component_names('requests', 'pypi', alternatives=['python-requests'])

    component = Component.nodes.get_or_none(
        canonical_namespace='', canonical_name='requests', canonical_type='pypi')
    assert component
    assert component.alternative_names == ['python-requests']


def test_set_component_names_fix_canonical_name():
    """Test that set_component_names fixes a canonical name."""
    c = Component.get_or_create_singleton('', 'python-requests', 'pypi')
    c.alternative_names = ['python3-requests']
    c.save()

    modify.set_component_names('requests', 'pypi', alternatives=['python-requests'])

    component = Component.nodes.get_or_none(
        canonical_namespace='', canonical_name='requests', canonical_type='pypi')
    assert component
    assert component.canonical_name == 'requests'
    assert set(component.alternative_names) == set(['python3-requests', 'python-requests'])


def test_set_component_names_fix_canonical_name_no_alt_input():
    """Test that set_component_names fixes a canonical name with alternatives input."""
    c = Component.get_or_create_singleton('', 'python-requests', 'pypi')
    c.alternative_names = ['requests']
    c.save()

    modify.set_component_names('requests', 'pypi')

    component = Component.nodes.get_or_none(
        canonical_namespace='', canonical_name='requests', canonical_type='pypi')
    assert component
    assert component.canonical_name == 'requests'
    assert component.alternative_names == ['python-requests']


def test_set_component_names_merge_multiple_components():
    """Test that set_component_names merges all the matching components."""
    c1 = Component.get_or_create_singleton('', 'python-requests', 'pypi')
    c1.alternative_names = ['py-requests', 'requests']
    c1.save()
    sl1 = SourceLocation(url='http://domain.local/python-requests', type_='local').save()
    c1.source_locations.connect(sl1)

    c2 = Component.get_or_create_singleton('', 'python2-requests', 'pypi')
    c2.alternative_names = ['python3-requests', 'requests']
    c2.save()
    sl2 = SourceLocation(url='http://domain.local/python2-requests', type_='local').save()
    c2.source_locations.connect(sl2)
    sl3 = SourceLocation(url='http://domain.local/requests', type_='local').save()
    c2.source_locations.connect(sl3)

    modify.set_component_names('requests', 'pypi', alternatives=['python-requests'])

    component = Component.nodes.get_or_none(
        canonical_namespace='', canonical_name='requests', canonical_type='pypi')
    assert component
    assert component.canonical_name == 'requests'
    assert set(component.alternative_names) == set([
        'py-requests', 'python2-requests', 'python3-requests', 'python-requests'])
    assert len(component.source_locations) == 3

    assert Component.nodes.get_or_none(canonical_name='python-requests') is None
    assert Component.nodes.get_or_none(canonical_name='python2-requests') is None


@pytest.mark.parametrize('args,kwargs', [
    ((1, 'string', 'string'), {}),
    (('string', 1, 'string'), {}),
    (('string', 'string', 1), {}),
    (('something', '', 'something'), {}),
    (('string', 'string', 'string'), {'alternatives': 1}),
    (('string', 'string', 'string'), {'alternatives': [1]}),
])
def test_set_component_names_invalid_input(args, kwargs):
    """Test that set_component_names validates the user input."""
    with pytest.raises(ValueError):
        modify.set_component_names(*args, **kwargs)
