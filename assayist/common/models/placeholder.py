# SPDX-License-Identifier: GPL-3.0+

from neomodel import UniqueIdProperty, StringProperty

from assayist.common.models.base import AssayistStructuredNode


class Placeholder(AssayistStructuredNode):
    """Definition of a placeholder node for testing in Neo4j."""

    # Call it "id_" to not overshadow the Neo4j internal ID used by neomodel, but call
    # it "id" in Neo4j
    id_ = UniqueIdProperty(db_property='id')
    description = StringProperty()
