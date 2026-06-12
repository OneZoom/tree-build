def tidy_infill_dates_bottomup(tree):
    """
    Working bottom-upwards, fill in missing date properties based on branch lengths.
    """
    for node in tree.traverse(strategy="postorder"):
        if node.is_leaf:
            node.props["date"] = 0
        else:
            for c in node.children:
                if c.props.get("date") is not None and c.dist is not None:
                    c_date = c.props["date"] + c.dist
                    if node.props.get("date") is None or node.props["date"] < c_date:
                        node.props["date"] = c_date


def tidy_clear_conflicting_dates_topdown(parent, mrad=None):
    """
    Work through tree, removing dates older than their most recent ancestor.
    """
    if parent.props.get("date") is not None:
        if mrad is not None and (parent.props["date"] - mrad) > 1e-5:
            # date is greater than mrad, this shouldn't happen
            parent.props["date"] = None
        else:
            mrad = parent.props["date"]
    for c in parent.children:
        tidy_clear_conflicting_dates_topdown(c, mrad)
