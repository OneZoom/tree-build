import io

import oz_tree_build.newick.format_newick as format_newick

test_tree = "(A,(BA,((BBAA_ott123[Comment 1],BBAB,BBAC,'BBAD (foo)')'BAA (bar)'[Comment 2 (Hello)],(BBBA)BBB,(BBCA:12.34,BBCB)BBC_ott456:78.9)BB)B_ott789,((CAA,CAB),CB)C,D)Root;"

formatted_test_tree = """(
  A,
  (
    BA,
    (
      (
        BBAA_ott123[Comment 1],
        BBAB,
        BBAC,
        'BBAD (foo)'
      )'BAA (bar)'[Comment 2 (Hello)],
      (
        BBBA
      )BBB,
      (
        BBCA:12.34,
        BBCB
      )BBC_ott456:78.9
    )BB
  )B_ott789,
  (
    (
      CAA,
      CAB
    ),
    CB
  )C,
  D
)Root;
"""


def test_format_newick():
    # Create an in memory file object
    f = io.StringIO()
    format_newick.format_nwk(test_tree, f, 2)
    f.seek(0)
    assert f.read() == formatted_test_tree


# def test_format_newick_with_comments():
#     # Create an in memory file object
#     f = io.StringIO()
#     format_newick.format("(A[QQQ],B[ZZZ]);", f, 2)
#     f.seek(0)
#     assert f.read() == formatted_test_tree
