import re

NODE_OTT_RE = re.compile(r"[_ ]ott(\d+)$")


def node_get_ott(n):
    """
    Extract OTT from node if present, None otherwise

    NB: OTT is returned as string, not int
    """
    if not n.name:
        return None
    m = NODE_OTT_RE.search(n.name)
    return m.group(1) if m else None
