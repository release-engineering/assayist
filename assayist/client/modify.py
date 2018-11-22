# SPDX-License-Identifier: GPL-3.0+

import itertools

import neomodel

from assayist.common.models.source import Component
from assayist.client.logging import log


@neomodel.db.transaction
def set_component_names(c_name, c_type, c_namespace='', alternatives=None):
    """
    Create, update, and/or merge components to ensure one canonical component remains.

    :param str c_name: the canonical name of the component
    :param str c_type: the canonical type of the component
    :param str c_namespace: the canonical namespace of the component
    :kwarg list alternatives: the alternative names associated with the component
    :raises ValueError: if the input isn't the proper type or c_name's value is also in alternatives
    """
    for arg in (c_name, c_type, c_namespace):
        if not isinstance(arg, str):
            raise ValueError('c_name, c_type, and c_namespace must be strings')

    for arg in (c_name, c_type):
        if arg == '':
            raise ValueError('c_name and c_type cannot be empty')

    if alternatives is None:
        alternatives = []
    if type(alternatives) not in (list, tuple, set):
        raise ValueError('The alternatives keyword argument must be None or a list, tuple, or set')

    for alternative in alternatives:
        if not isinstance(alternative, str):
            raise ValueError('The alternatives keyword argument must only contain strings')

    # Create a WHERE clause that checks to see if there is a component with the canonical name or
    # alternative name with the passed in canonical name and alternatives
    names_where_clause = [
        'c.canonical_name = "{0}" OR "{0}" in c.alternative_names'.format(name)
        for name in itertools.chain([c_name], alternatives)
    ]
    query = """
    MATCH (c:Component {{canonical_type: "{}", canonical_namespace: "{}" }})
    WHERE {}
    RETURN c
    """.format(c_type, c_namespace, ' OR '.join(names_where_clause))

    results, _ = neomodel.db.cypher_query(query)
    components = [Component.inflate(row[0]) for row in results]

    # If no matching component is returned, just create one
    if not components:
        component = Component(canonical_namespace=c_namespace, canonical_name=c_name,
                              canonical_type=c_type, alternative_names=alternatives).save()
        log.info(f'Creating the component "{component}"')
        return

    # Merge all the current canonical names and alternative names
    all_alt_names = set(alternatives)
    for c in components:
        all_alt_names.add(c.canonical_name)
        all_alt_names.update(c.alternative_names)

    # By removing the correct canonical name, we have a set of the correct alternative names
    all_alt_names.discard(c_name)

    # This will be the only remaining component if there is more than one component returned, as
    # the information stored in the others will be merged into this one
    component = components[0]
    if component.canonical_name != c_name:
        log.info(f'Setting the canonical name of "{c_name}" on "{component}"')
        component.canonical_name = c_name
    if set(component.alternative_names) != set(all_alt_names):
        log.info(f'Setting the alternative names of "{all_alt_names}" on "{component}"')
        component.alternative_names = list(all_alt_names)

    # If there was more than one component that matched, we must merge them
    for c in components[1:]:
        log.info(f'Merging the source locations of "{c}" in the existing component "{component}"')
        # Merge all the source locations on the first component
        for sl in c.source_locations.all():
            component.source_locations.connect(sl)

        # Delete this component since all its information is now stored in the first component
        log.warning(f'Deleting the component "{c}" since it was merged into "{component}"')
        c.delete()

    component.save()
