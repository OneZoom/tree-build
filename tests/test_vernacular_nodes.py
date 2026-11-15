import json
import sqlite3

import pytest
from pydal import DAL

from oz_tree_build._OZglobals import src_flags
from oz_tree_build.utilities.db_helper import connect_to_database
from oz_tree_build.vernaculars import get_wiki_vernaculars as vernaculars


def test_existing_sqlite_database_gains_node_table(tmp_path):
    database_path = tmp_path / "existing.sqlite"
    with sqlite3.connect(database_path) as db:
        db.execute("CREATE TABLE existing_data (value INTEGER)")
        db.execute("INSERT INTO existing_data VALUES (42)")
    db = connect_to_database(f"sqlite://{database_path}")
    assert db.executesql("SELECT value FROM existing_data") == [(42,)]
    assert db.executesql("SELECT COUNT(*) FROM ordered_nodes") == [(0,)]
    db.close()


@pytest.fixture()
def tree_db():
    db = DAL("sqlite:memory")
    db.executesql(
        "CREATE TABLE ordered_nodes (id INTEGER, node_rgt INTEGER, leaf_lft INTEGER, leaf_rgt INTEGER, "
        "ott INTEGER, wikidata INTEGER, name TEXT)"
    )
    db.executesql("CREATE TABLE ordered_leaves (id INTEGER, ott INTEGER, wikidata INTEGER, name TEXT)")
    db.executesql(
        "CREATE TABLE vernacular_by_ott (ott INTEGER, vernacular TEXT, lang_primary TEXT, "
        "lang_full TEXT, preferred INTEGER, src INTEGER, src_id INTEGER, updated TEXT)"
    )
    db.executesql(
        "INSERT INTO ordered_nodes VALUES "
        "(1, 4, 1, 4, 10, 100, 'Root'), "
        "(2, 3, 1, 3, 20, 200, 'Clade'), "
        "(3, 3, 1, 2, 30, 300, 'Nested'), "
        "(4, 4, 4, 4, 40, 400, 'Outside'), "
        "(5, 5, 5, 5, NULL, 500, 'No OTT')"
    )
    db.executesql(
        "INSERT INTO ordered_leaves VALUES "
        "(1, 11, 100, 'Shared QID'), (2, 12, 120, 'Leaf'), "
        "(3, 13, 130, 'Existing'), (4, 14, 140, 'Outside leaf')"
    )
    db.commit()
    yield db
    db.close()


@pytest.mark.parametrize("query", ["20", "Clade"])
def test_single_node_by_ott_or_name(tree_db, monkeypatch, query):
    seen = []
    monkeypatch.setattr(
        vernaculars,
        "get_wikidata_json_for_qid",
        lambda qid, headers: (
            seen.append(qid)
            or {
                "claims": {
                    "P1843": [
                        {"rank": "normal", "mainsnak": {"datavalue": {"value": {"language": "en", "text": "cats"}}}}
                    ]
                }
            }
        ),
    )
    vernaculars.process_taxon(tree_db, query)
    assert seen == [200]
    assert tree_db.executesql("SELECT ott,vernacular,src_id FROM vernacular_by_ott") == [(20, "cats", 200)]


def test_single_taxon_ambiguous_and_missing_qid(tree_db, monkeypatch, caplog):
    tree_db.executesql("INSERT INTO ordered_leaves VALUES (5, 20, 201, 'Other')")
    monkeypatch.setattr(vernaculars, "get_wikidata_json_for_qid", lambda *args, **kwargs: pytest.fail("API called"))
    vernaculars.process_taxon(tree_db, "20")
    assert "Multiple results" in caplog.text
    vernaculars.process_taxon(tree_db, "No OTT")
    assert "has no OTT" in caplog.text
    tree_db.executesql("INSERT INTO ordered_nodes VALUES (6, 6, 6, 6, 60, NULL, 'No QID')")
    vernaculars.process_taxon(tree_db, "60")
    assert "No Wikidata QID" in caplog.text


def test_clade_includes_nodes_and_leaves_only_within_bounds(tree_db, tmp_path):
    tree_db.executesql(
        "INSERT INTO vernacular_by_ott (ott, vernacular, src) VALUES (?, ?, ?)",
        (13, "Existing", src_flags["wiki"]),
    )
    dump = tmp_path / "dump.json"
    records = [
        {
            "type": "item",
            "id": f"Q{qid}",
            "claims": {
                "P1843": [
                    {"rank": "normal", "mainsnak": {"datavalue": {"value": {"language": "en", "text": f"name {qid}"}}}}
                ]
            },
        }
        for qid in [100, 120, 130, 140, 200, 300, 400]
    ]
    dump.write_text("\n".join(json.dumps(record) for record in records))
    vernaculars.process_clade(tree_db, "20", str(dump), {})
    rows = tree_db.executesql("SELECT ott, vernacular FROM vernacular_by_ott ORDER BY ott")
    assert rows == [(11, "name 100"), (12, "name 120"), (13, "Existing"), (20, "name 200"), (30, "name 300")]
    vernaculars.process_clade(tree_db, "10", str(dump), {})
    rows = tree_db.executesql("SELECT ott, vernacular FROM vernacular_by_ott ORDER BY ott")
    assert rows == [
        (10, "name 100"),
        (11, "name 100"),
        (12, "name 120"),
        (13, "Existing"),
        (14, "name 140"),
        (20, "name 200"),
        (30, "name 300"),
        (40, "name 400"),
    ]


def test_clade_saves_shared_qid_for_each_ott(tree_db, monkeypatch):
    calls = []
    monkeypatch.setattr(vernaculars, "enumerate_wiki_dump_items", lambda *args: [(100, {"en": []})])
    monkeypatch.setattr(vernaculars, "save_wiki_vernaculars_for_qid", lambda db, ott, qid, names: calls.append(ott))
    vernaculars.process_clade(tree_db, "10", "unused.json", {})
    assert sorted(calls) == [10, 11]


def test_single_node_uses_taxa_data_for_missing_qid(tree_db, monkeypatch):
    tree_db.executesql("INSERT INTO ordered_nodes VALUES (6, 6, 6, 6, 60, NULL, 'Fallback')")
    seen = []
    monkeypatch.setattr(vernaculars, "get_wikidata_json_for_qid", lambda qid, headers: seen.append(qid) or {})
    monkeypatch.setattr(vernaculars, "get_vernaculars_by_language_from_json_item", lambda item: {})
    monkeypatch.setattr(vernaculars, "save_wiki_vernaculars_for_qid", lambda *args: None)
    vernaculars.process_taxon(tree_db, "60", {"Fallback": {"qid": 600}})
    assert seen == [600]


@pytest.mark.parametrize("command", ["taxon", "leaf"])
def test_single_taxon_cli_alias(command, monkeypatch):
    seen = []
    monkeypatch.setattr(vernaculars, "process_args", lambda args: seen.append((args.subcommand, args.ott_or_taxa)))
    monkeypatch.setattr("sys.argv", ["get_wiki_vernaculars", command, "123", "--conf-file", "appconfig.ini"])
    vernaculars.main()
    assert seen == [(command, ["123"])]
