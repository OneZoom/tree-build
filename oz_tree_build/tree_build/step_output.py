import csv
import json
import os.path
import struct

from ..utilities.ete import node_name_without_ott


def output_add_prop_ids(tree):
    """
    Annotate every internal node with the integer ids the OneZoom MySQL
    schema uses for nested-set descendant queries.

    Sets four props on each internal node:
      - ``id``       : 1-based preorder index among internal nodes.
      - ``leaf_lft`` : preorder position of the leftmost leaf in the subtree.
      - ``leaf_rgt`` : preorder position of the rightmost leaf in the subtree.
      - ``node_rgt`` : id of the rightmost internal-node descendant
                       (equals ``id`` when every child is a leaf).

    Leaves are not annotated — they are implicitly numbered by their
    preorder position. Ids and leaf positions both start at 1 to line up
    with MySQL row numbering.

    Assumes the tree is ladderized *ascending* (smallest subtree first):
    ``node_rgt`` is derived by walking postorder and trusting that the
    last-visited child sits at the right of its parent, which only holds
    when the rightmost child carries the largest subtree. A descending
    tree where a leaf sits to the right of an internal sibling will get
    the wrong ``node_rgt`` (the parent will look terminal).
    """
    # allocate node numbers
    internal_node_number = 0
    leaf_count = 1
    for node in tree.traverse("preorder"):
        if node.is_leaf:
            leaf_count += 1
        else:
            # NB: increment first, since we use a 1-base numbering system, for mySQL row numbering
            internal_node_number += 1
            node.props["id"] = internal_node_number
            node.props["leaf_lft"] = leaf_count

    # postorder traversal to allocate rgt side of ranges
    internal_leaf_count = 0
    prev_node = None
    for node in tree.traverse("postorder"):
        # find rightmost leaf by postorder iteration.
        # For rightmost node, if previously visited node is a leaf, then (because we ladderize
        # ascending) the rightmost node must be self (i.e. this is a terminal internal node).
        # Otherwise it is the previously visted node
        if node.is_leaf:
            internal_leaf_count += 1
        else:
            node.props["leaf_rgt"] = internal_leaf_count  # should have counted all the internal leaves by now
            if prev_node.is_leaf:
                node.props["node_rgt"] = node.props["id"]  # node_rgt == self
            else:
                # the node_rgt should be the same as the node_rgt of the previous node
                node.props["node_rgt"] = prev_node.props["node_rgt"]
        prev_node = node


def output_mysqlexport(tree, out_dir):
    """
    Write the three files needed to load the tree into the OneZoom MySQL
    database:

      - ``ordered_leaves.csv`` : one row per leaf, in preorder.
      - ``ordered_nodes.csv``  : one row per internal node, in preorder.
      - ``import.sql``         : TRUNCATE + ``LOAD DATA LOCAL INFILE``
                                 script that loads both CSVs.

    Preconditions
    -------------
    Every node must carry ``props["taxon"]``, a dict of taxon-derived
    columns (``ott``, ``wikidata``, ``ncbi``, ...); missing keys are
    written as ``\\N``. Every internal node must additionally carry
    ``id`` / ``node_rgt`` / ``leaf_lft`` / ``leaf_rgt`` as produced by
    `output_add_prop_ids`.

    Encoding conventions
    --------------------
    - ``\\N`` is the marker for missing values (MySQL ``LOAD DATA``
      treats it as NULL).
    - ``real_parent`` walks past randomly-resolved polytomies: any
      ancestor with ``dist == 0`` is skipped so the column points at the
      nearest biologically meaningful parent. The raw ``parent`` column
      still references the immediate parent.
    - A node that is itself a polytomy resolution (``dist == 0``) records
      its ``real_parent`` as the *negative* of the resolved parent's id,
      flagging the relationship as artificial.
    - The leaf ``name`` column has any trailing ``_ottNNN`` suffix
      stripped (the OTT is carried separately in its own column).
    - An internal node's ``date`` prop is exposed via the ``age`` column.
    - The root's ``parent`` is ``\\N`` but its ``real_parent`` is the
      sentinel ``0``.
    """

    with (
        open(os.path.join(out_dir, "ordered_leaves.csv"), "w+", encoding="utf-8") as leaf_file,
        open(os.path.join(out_dir, "ordered_nodes.csv"), "w+", encoding="utf-8") as node_file,
    ):
        leaf_csv = csv.writer(leaf_file, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        node_csv = csv.writer(node_file, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        leaf_csv.writerow(
            [
                "parent",
                "real_parent",
                "name",
                "extinction_date",
                "ott",
                "wikidata",
                "wikipedia_lang_flag",
                "iucn",
                "eol",
                "raw_popularity",
                "popularity",
                "popularity_rank",
                "price",
                "ncbi",
                "ifung",  # NB: the DB's name for the taxonomy's "if" source
                "worms",
                "irmng",
                "gbif",
                "ipni",
            ]
        )
        node_csv.writerow(
            [
                "parent",
                "real_parent",
                "node_rgt",
                "leaf_lft",
                "leaf_rgt",
                "name",
                "age",
                "ott",
                "wikidata",
                "wikipedia_lang_flag",
                "eol",
                "rnk",  # We avoid using 'rank' as it is a reserved word in mysql
                "raw_popularity",
                "popularity",
                "ncbi",
                "ifung",  # NB: the DB's name for the taxonomy's "if" source
                "worms",
                "irmng",
                "gbif",
                "ipni",
                "vern_synth",
            ]
            + [rit + str(i + 1) for rit in ("rep", "rtr", "rpd") for i in range(8)]
            + ["iucn" + t for t in ("NE", "DD", "LC", "NT", "VU", "EN", "CR", "EW", "EX")]
        )

        for node in tree.traverse("preorder"):
            # Find our real parent, ignoring randomly resolved polytomies
            real_parent = node.parent
            while real_parent and real_parent.dist == 0:  # TODO: Is this still how we identify polytomies?
                real_parent = real_parent.parent

            if not real_parent:
                real_parent_id = 0
            elif node.dist == 0:
                # real_parent is negative iff we're a polytomy
                real_parent_id = -real_parent.props["id"]
            else:
                real_parent_id = real_parent.props["id"]

            if node.is_leaf:
                leaf_csv.writerow(
                    [
                        node.parent.props["id"] if node.parent else "\\N",  # "parent"
                        # TODO: negative real_parent ids if this is a polytomy
                        real_parent_id,
                        node_name_without_ott(node),
                        node.props.get("extinction_date", "\\N"),
                        node.props["taxon"].get("ott", "\\N"),
                        node.props["taxon"].get("wikidata", "\\N"),
                        node.props["taxon"].get("wikipedia_lang_flag", "\\N"),
                        node.props["taxon"].get("iucn", "\\N"),
                        node.props["taxon"].get("eol", "\\N"),
                        node.props["taxon"].get("raw_popularity", "\\N"),
                        node.props.get("popularity", "\\N"),
                        node.props.get("popularity_rank", "\\N"),
                        None,  # "price"
                        node.props["taxon"].get("ncbi", "\\N"),
                        node.props["taxon"].get("if", "\\N"),  # NB: "ifung" in the DB
                        node.props["taxon"].get("worms", "\\N"),
                        node.props["taxon"].get("irmng", "\\N"),
                        node.props["taxon"].get("gbif", "\\N"),
                        node.props["taxon"].get("ipni", "\\N"),
                    ]
                )
            else:
                node_csv.writerow(
                    [
                        node.parent.props["id"] if node.parent else "\\N",  # "parent"
                        real_parent_id,
                        node.props["node_rgt"],
                        node.props["leaf_lft"],
                        node.props["leaf_rgt"],
                        node_name_without_ott(node),
                        node.props.get("date", "\\N"),  # TODO: But only if it's not imputed
                        node.props["taxon"].get("ott", "\\N"),
                        node.props["taxon"].get("wikidata", "\\N"),
                        node.props["taxon"].get("wikipedia_lang_flag", "\\N"),
                        node.props["taxon"].get("eol", "\\N"),
                        node.props["taxon"].get("rnk", "\\N"),
                        node.props["taxon"].get("raw_popularity", "\\N"),
                        node.props.get("popularity", "\\N"),
                        node.props["taxon"].get("ncbi", "\\N"),
                        node.props["taxon"].get("if", "\\N"),  # NB: "ifung" in the DB
                        node.props["taxon"].get("worms", "\\N"),
                        node.props["taxon"].get("irmng", "\\N"),
                        node.props["taxon"].get("gbif", "\\N"),
                        node.props["taxon"].get("ipni", "\\N"),
                        None,  # "vern_synth"
                    ]
                    + ["\\N" for _ in ("rep", "rtr", "rpd") for _ in range(8)]
                    + ["\\N" for _ in ("NE", "DD", "LC", "NT", "VU", "EN", "CR", "EW", "EX")]
                )

    with open(os.path.join(out_dir, "import.sql"), "w", encoding="utf-8") as sql_f:
        for csvfile in ("ordered_leaves.csv", "ordered_nodes.csv"):
            table = os.path.splitext(csvfile)[0]
            sql_f.writelines(
                [
                    f"TRUNCATE TABLE {table};\n"
                    f"LOAD DATA LOCAL INFILE '{csvfile}' REPLACE INTO TABLE `{table}` \n"
                    f"    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' \n"
                    f"    IGNORE 1 LINES ({open(os.path.join(out_dir,csvfile)).readline().rstrip()}) SET id = NULL;\n"
                ]
            )


def output_jssource(tree, out_dir, file_name, data):
    """
    Turn ``data`` dict into a js source file that defines it's keys as variables, with JSON encoded values
    """
    with open(os.path.join(out_dir, file_name), "w") as f:
        for k, v in data.items():
            f.write(f"var {k} = ")
            json.dump(v, f)
            f.write(";\n")


def output_proparray(tree, out_dir, prop_name):
    """
    Given an ete4 tree and prop_name, write out 2 packed arrays to out_dir:

        (prop_name)_leaves_(pack format).dat
        (prop_name)_nodes_(pack format).dat

    The ordering will match ordered_leaves/ordered_nodes
    """
    PROP_FORMAT_TO_PACK = dict(
        c8="c",  # 8-bit chars
        i8="b",  # Signed 8-bit ints
        u8="B",  # Unsigned 8-bit ints
        f16="<e",  # LE 16-bit floats
        f32="<f",  # LE 32-bit floats
        f64="<d",  # LE 32-bit floats (doubles)
    )

    # Derive packing format from python type of property
    prop_format = tree.root.props.get("prop_format", {}).get(prop_name)
    if prop_format is None:
        raise ValueError(f"Property {prop_name} has no entry in prop_format. Has it been applied to the tree?")
    pack_format = PROP_FORMAT_TO_PACK.get(prop_format)
    if pack_format is None:
        raise ValueError(f"Unknown property format {prop_format}")

    leaf_path = os.path.join(out_dir, f"{prop_name}_leaves_{prop_format}.dat")
    node_path = os.path.join(out_dir, f"{prop_name}_nodes_{prop_format}.dat")
    with open(leaf_path, "wb") as leaf_f:
        with open(node_path, "wb") as node_f:
            # NB: Traverse behaviour has to match output_mysqlexport
            for node in tree.traverse("preorder"):
                value = node.props[prop_name]
                if node.is_leaf:
                    leaf_f.write(struct.pack(pack_format, value))
                else:
                    node_f.write(struct.pack(pack_format, value))
    return (leaf_path, node_path)
