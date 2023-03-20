'''
Unit tests for extract_trees
'''

from oz_tree_build.newick.extract_trees import extract_trees

test_tree = "(A,(BA,((BBAA_ott123,BBAB,BBAC,BBAD)BAA,(BBBA)BBB,(BBCA:12.34,BBCB)BBC_ott456:78.9)BB)B_ott789,((CAA,CAB):5.25,CB)C,D)Root;"

def test_some_missing_taxa():
    tree = extract_trees(test_tree, {"X", "BBC", "Y"})

    assert tree == {'456': '(BBCA:12.34,BBCB)BBC_ott456:78.9'}

def test_all_missing_taxa():
    tree = extract_trees(test_tree, {"X", "6789"})

    assert tree == {}

def test_one_taxon():
    tree = extract_trees(test_tree, {"B"})

    assert tree == {'789': '(BA,((BBAA_ott123,BBAB,BBAC,BBAD)BAA,(BBBA)BBB,(BBCA:12.34,BBCB)BBC_ott456:78.9)BB)B_ott789'}

def test_one_taxon_with_exclusion():
    tree = extract_trees(test_tree, {"C"}, excluded_taxa={"CAA"})

    assert tree == {'C': '((CAB):5.25,CB)C'}

def test_two_taxa():
    tree = extract_trees(test_tree, {"BBC", "C"})

    assert tree == {'456': '(BBCA:12.34,BBCB)BBC_ott456:78.9', 'C': '((CAA,CAB):5.25,CB)C'}

def test_two_nested_taxa():
    tree = extract_trees(test_tree, {"123", "BAA"})

    assert tree == {'123': 'BBAA_ott123', 'BAA': '(BBAA_ott123,BBAB,BBAC,BBAD)BAA'}

def test_two_taxa_with_exclusions():
    tree = extract_trees(test_tree, {"C", "BB"}, excluded_taxa={"BAA", "CAA"})

    assert tree == {'BB': '((BBBA)BBB,(BBCA:12.34,BBCB)BBC_ott456:78.9)BB', 'C': '((CAB):5.25,CB)C'}

def test_nested_exclusions():
    tree = extract_trees("((A,B)C,D)E;", {"E"}, excluded_taxa={"B", "C"})

    assert tree == {'E': '(D)E'}
