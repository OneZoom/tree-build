def find_wikicode_node(wikicode, start_index, type, func):
    for i, node in enumerate(wikicode.nodes[start_index:], start=start_index):
        assert wikicode.nodes[i] == node
        if isinstance(node, type) and func(node):
            return i, node
    return None, None
