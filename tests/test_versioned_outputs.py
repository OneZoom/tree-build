"""
Unit tests for versioned_outputs.process
"""

import gzip

from oz_tree_build.versioned_outputs.versioned_outputs import process


def _write(path, content):
    with open(path, "w") as f:
        f.write(content)


def test_copies_with_version_appended(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    src = in_dir / "data.csv"
    _write(src, "hello,world\n")

    process([str(src)], str(out_dir), 42)

    out_file = out_dir / "data_42.csv"
    assert out_file.read_text() == "hello,world\n"


def test_replaces_existing_version_in_filename(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    src = in_dir / "data_99.csv"
    _write(src, "row\n")

    process([str(src)], str(out_dir), 7)

    assert (out_dir / "data_7.csv").exists()
    assert not (out_dir / "data_99_7.csv").exists()


def test_produces_gzip_alongside_plain_file(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    src = in_dir / "data.csv"
    _write(src, "the quick brown fox\n")

    process([str(src)], str(out_dir), 3)

    gz_path = out_dir / "data_3.csv.gz"
    assert gz_path.exists()
    with gzip.open(gz_path, "rt") as f:
        assert f.read() == "the quick brown fox\n"


def test_multiple_files_each_versioned(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    a = in_dir / "a.csv"
    b = in_dir / "b.json"
    _write(a, "A\n")
    _write(b, "B\n")

    process([str(a), str(b)], str(out_dir), 11)

    assert (out_dir / "a_11.csv").read_text() == "A\n"
    assert (out_dir / "b_11.json").read_text() == "B\n"


def test_import_sql_rewrites_filename_references(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    nodes = in_dir / "ordered_nodes.csv"
    leaves = in_dir / "ordered_leaves.csv"
    sql = in_dir / "import.sql"
    _write(nodes, "n\n")
    _write(leaves, "l\n")
    _write(
        sql,
        "LOAD DATA INFILE 'ordered_nodes.csv' INTO TABLE ordered_nodes;\n"
        "LOAD DATA INFILE 'ordered_leaves.csv' INTO TABLE ordered_leaves;\n",
    )

    process([str(nodes), str(leaves), str(sql)], str(out_dir), 55)

    out_sql = (out_dir / "import_55.sql").read_text()
    assert "'ordered_nodes_55.csv'" in out_sql
    assert "'ordered_leaves_55.csv'" in out_sql
    assert "'ordered_nodes.csv'" not in out_sql
    assert "'ordered_leaves.csv'" not in out_sql


def test_import_sql_appends_root_parent_update(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    sql = in_dir / "import.sql"
    _write(sql, "-- nothing to rewrite\n")

    process([str(sql)], str(out_dir), 123)

    out_sql = (out_dir / "import_123.sql").read_text()
    assert out_sql.endswith("UPDATE ordered_nodes SET parent = -123 WHERE id = 1;\n")
    assert "-- nothing to rewrite\n" in out_sql


def test_import_sql_only_replaces_quoted_names(tmp_path):
    """Filename substring inside other identifiers (no quotes) should not be touched."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    nodes = in_dir / "ordered_nodes.csv"
    sql = in_dir / "import.sql"
    _write(nodes, "n\n")
    # Mention the bare filename (no quotes) in a comment; it must NOT be rewritten.
    _write(
        sql,
        "-- see ordered_nodes.csv for schema\n" "LOAD DATA INFILE 'ordered_nodes.csv' INTO TABLE ordered_nodes;\n",
    )

    process([str(nodes), str(sql)], str(out_dir), 9)

    out_sql = (out_dir / "import_9.sql").read_text()
    assert "-- see ordered_nodes.csv for schema\n" in out_sql
    assert "'ordered_nodes_9.csv'" in out_sql


def test_input_file_outside_in_dir_uses_basename(tmp_path):
    """Output is named from basename, regardless of input path."""
    nested = tmp_path / "deep" / "nested" / "dir"
    nested.mkdir(parents=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    src = nested / "thing.txt"
    _write(src, "x\n")

    process([str(src)], str(out_dir), 1)

    assert (out_dir / "thing_1.txt").exists()
    assert (out_dir / "thing_1.txt.gz").exists()


def test_overwrites_existing_output(tmp_path):
    """gzip -f and shutil.copyfile both clobber prior outputs without error."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    src = in_dir / "data.csv"
    _write(src, "fresh\n")

    # Pre-existing stale outputs from an earlier run.
    _write(out_dir / "data_5.csv", "stale\n")
    _write(out_dir / "data_5.csv.gz", "not a real gzip")

    process([str(src)], str(out_dir), 5)

    assert (out_dir / "data_5.csv").read_text() == "fresh\n"
    with gzip.open(out_dir / "data_5.csv.gz", "rt") as f:
        assert f.read() == "fresh\n"
