'''
Unit test for extract_minimal_tree
'''

from oz_tree_build.newick.extract_minimal_tree import extract_minimal_tree

test_tree = "(A,(BA,((BBAA_ott123,BBAB,BBAC,BBAD)BAA,(BBBA)BBB,(BBCA:12.34,BBCB)BBC_ott456:78.9)BB)B_ott789,((CAA,CAB):5.25,CB)C,D)Root;"

def test_some_missing_taxa():
    tree = extract_minimal_tree(test_tree, {"X", "BBC", "Y"})

    assert tree == 'BBC_ott456:78.9'

def test_all_missing_taxa():
    tree = extract_minimal_tree(test_tree, {"X", "6789"})

    assert tree is None

def test_two_taxa():
    tree = extract_minimal_tree(test_tree, {"BA", "BBBA"})

    assert tree == '(BA,BBBA)B_ott789'

def test_two_taxa_no_root_name():
    tree = extract_minimal_tree(test_tree, {"CAA", "CAB"})

    assert tree == '(CAA,CAB):5.25'

def test_three_taxa():
    tree = extract_minimal_tree(test_tree, {"BA", "C", "BBC"})

    assert tree == '((BA,BBC_ott456:78.9)B_ott789,C)Root'

def test_three_taxa_polytomy():
    tree = extract_minimal_tree(test_tree, {"BBAD", "BBAA", "BBAC"})

    assert tree == '(BBAA_ott123,BBAC,BBAD)BAA'

def test_two_nested_taxa():
    tree = extract_minimal_tree(test_tree, {"B", "BBC"})

    assert tree == '(BBC_ott456:78.9)B_ott789'

def test_three_nested_taxa():
    tree = extract_minimal_tree(test_tree, {"BB", "BBC", "B"})

    assert tree == '((BBC_ott456:78.9)BB)B_ott789'

def test_nested_with_implied_taxon():
    tree = extract_minimal_tree(test_tree, {"BBAB", "B", "BBAD"})

    assert tree == '((BBAB,BBAD)BAA)B_ott789'

def test_mixed_scenarios():
    tree = extract_minimal_tree(test_tree, {"BBB", "789", "BBCA", "BBCB"})

    assert tree == '((BBB,(BBCA:12.34,BBCB)BBC_ott456:78.9)BB)B_ott789'

def test_find_by_ott():
    tree = extract_minimal_tree(test_tree, {"123", "789", "456"})

    assert tree == '((BBAA_ott123,BBC_ott456:78.9)BB)B_ott789'
