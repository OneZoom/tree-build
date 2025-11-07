import copy
import numpy as np

__author__ = "Jonathan Duke"


def use_shortest_path(x):
    """For use in date_labelling, in max(a, b, key=use_shortest_path) so that the shortest path is used
    as a tiebreaker rather than the longest.
    """
    return [x[0], -x[1]]


def date_labelling(parent):
    """Recurse in postorder through the tree, labelling each node with the oldest date below it
    and the path length (number of nodes) to that date. If the oldest date is a tie (usually 0),
    we must choose a path to it. This computes both the longest path (most nodes) and the shortest.
    Assumes leaf nodes have a date zero.

    Return value is: [oldest date found so far below this node, longest path length to it],
                     [oldest date found so far below this node, shortest path length to it]
    """
    if not parent.is_leaf:
        oldest_path_long = [0, -1e8]
        oldest_path_short = [0, 1e8]
        for child in parent.children:
            new_path_long, new_path_short = date_labelling(child)
            oldest_path_long = max(oldest_path_long, new_path_long)
            oldest_path_short = max(oldest_path_short, new_path_short, key=use_shortest_path)

    if parent.props["date"] is None:
        parent.props["oldest_path_long"] = copy.copy(oldest_path_long)
        parent.props["oldest_path_short"] = copy.copy(oldest_path_short)
        oldest_path_long[1] += 1
        oldest_path_short[1] += 1
    else:
        # if there is a date, doesn't matter what was received; just return this date
        oldest_path_long = [parent.props["date"], 0]
        oldest_path_short = [parent.props["date"], 0]
        parent.props["oldest_path_long"] = copy.copy(oldest_path_long)
        parent.props["oldest_path_short"] = copy.copy(oldest_path_short)
        oldest_path_long[1] += 1
        oldest_path_short[1] += 1

    return oldest_path_long, oldest_path_short


def impute_missing_dates(tre, l=0.25, m=0):
    """Traverse the tree in preorder, giving each undated node a date spaced along the path between between
    its parent (which always has a date, since this is preorder traversal) and the oldest date found below
    it (as labelled by the date_labelling function). Assumes root node is dated.

    When the oldest date beneath is a tie (usually because the oldest date is 0), the tie can be broken
    by using the longest path or the shortest path. This function computes both versions, then interpolates
    between the two solutions based on the parameter l:
        date = l * date_from_longest_path + (1-l) * date_from_shortest_path

    In addition, interpolation along a path can use equal spacing (m=0), or spacing that biases dates older
    (m > 0) or younger (m < 0). Uses spacing along an exponential function, i.e. y = exp(m*x).
    Values of m between -2 and 2 are pretty sensible.
    """

    for node in tre.traverse(strategy="preorder"):
        if node.props["date"] is None:
            node.props["date_above_long"] = node.up.props["date"]
            node.props["date_above_short"] = node.up.props["date"]

            mu_spacing_long = np.exp(m * np.linspace(0, 1, node.props["oldest_path_long"][1] + 1))
            mu_spacing_short = np.exp(m * np.linspace(0, 1, node.props["oldest_path_short"][1] + 1))

            node.props["mu_spacing_long"] = np.cumsum(mu_spacing_long / np.sum(mu_spacing_long))
            node.props["mu_spacing_short"] = np.cumsum(mu_spacing_short / np.sum(mu_spacing_short))

            node.props["date_long"] = (
                node.props["date_above_long"]
                - (node.props["date_above_long"] - node.props["oldest_path_long"][0])
                * node.props["mu_spacing_long"][-(node.props["oldest_path_long"][1] + 1)]
            )
            node.props["date_short"] = (
                node.props["date_above_short"]
                - (node.props["date_above_short"] - node.props["oldest_path_short"][0])
                * node.props["mu_spacing_short"][-(node.props["oldest_path_short"][1] + 1)]
            )

            node.props["date"] = l * node.props["date_long"] + (1 - l) * node.props["date_short"]


def date_tree(tre):
    """Interpolate dates on an ete3 tree using the default interpolation parameters. Assumes all tree nodes have an
    attribute 'date' which is either a floating point number or None. Nodes with a date of None will be interpolated;
    the root node must be dated; assumes leaf nodes have a date of zero.
    """
    date_labelling(tre)
    impute_missing_dates(tre)


def compute_branch_lengths(tre):
    """Fill in 'dist' attribute with branch lengths. Intended for a fully dated tree."""
    for node in tre.traverse():
        if node.up:
            branch_length = node.up.props["date"] - node.props["date"]
            if branch_length < 0:
                raise Exception("Negative branch length found in compute_branch_lengths.")

            node.dist = branch_length


def compute_dates(parent):
    """Fill in 'date' attribute with dates, given a tree with branch lengths in units of time.
    Assume leaf nodes have a date of 0.
    """
    if parent.is_leaf:
        parent.props["date"] = 0
    else:
        for child in parent.children:
            compute_dates(child)
            parent.props["date"] = child.props["date"] + child.dist
