from ..utilities.ete import node_get_ott


def taxon_add_prop(
    tree,
    taxon_map,
):
    """
    Add references to relevant lines in taxon_map to tree nodes

    We should also check that there are not multiple uses of the same Qid
    (https://github.com/OneZoom/OZtree/issues/132)
    """
    for n in tree.traverse():
        node_ott = node_get_ott(n)
        n.props["taxon"] = taxon_map.get(int(node_ott), {}) if node_ott else {}
