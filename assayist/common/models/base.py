# SPDX-License-Identifier: GPL-3.0+

from neomodel import StructuredNode


class AssayistStructuredNode(StructuredNode):
    """Base class for Assayist Neo4j models."""

    __abstract_node__ = True
