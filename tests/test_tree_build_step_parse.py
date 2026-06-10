import ete4
import pytest

from oz_tree_build.tree_build import step_parse
from oz_tree_build.tree_build.step_parse import (
    decypher_inclusion_syntax,
    parse_bespoke_trees,
    parse_ot_orphans,
    remove_exclusions,
)


class TestDecypherInclusionSyntax:
    def test_returns_none_for_falsy_input(self):
        assert decypher_inclusion_syntax(None) is None
        assert decypher_inclusion_syntax("") is None

    def test_returns_none_without_trailing_at(self):
        assert decypher_inclusion_syntax("Foo_ott1") is None
        assert decypher_inclusion_syntax("BASE") is None

    def test_bespoke_token_no_ott(self):
        # Bespoke tokens lack the _ottN suffix; they fall through to the
        # "@-but-no-ott-syntax" branch.
        assert decypher_inclusion_syntax("BASE@") == {
            "orig_name": "BASE@",
            "node_name": "BASE",
        }
        assert decypher_inclusion_syntax("AMORPHEA@") == {
            "orig_name": "AMORPHEA@",
            "node_name": "AMORPHEA",
        }

    def test_simple_ott(self):
        # node_name preserves the "ottN" suffix (space-separated) when no
        # rebase via ~ occurred.
        assert decypher_inclusion_syntax("Foo_ott1@") == {
            "orig_name": "Foo_ott1@",
            "excluded_otts": [],
            "base_ott": "1",
            "node_name": "Foo ott1",
        }

    def test_ott_with_rebase(self):
        # `~N` rebases the subtree extraction onto ott N; the parent's ott
        # number is dropped from node_name.
        assert decypher_inclusion_syntax("Foo_ott1~2@") == {
            "orig_name": "Foo_ott1~2@",
            "excluded_otts": [],
            "base_ott": "2",
            "node_name": "Foo",
        }

    def test_ott_with_exclusions(self):
        assert decypher_inclusion_syntax("Foo_ott1~-2-3@") == {
            "orig_name": "Foo_ott1~-2-3@",
            "excluded_otts": ["2", "3"],
            "base_ott": "1",
            "node_name": "Foo ott1",
        }

    def test_ott_with_rebase_and_exclusions(self):
        assert decypher_inclusion_syntax("Foo_ott~4-2-3@") == {
            "orig_name": "Foo_ott~4-2-3@",
            "excluded_otts": ["2", "3"],
            "base_ott": "4",
            "node_name": "Foo",
        }


class TestRemoveExclusions:
    def test_empty_exclusion_list_is_noop(self):
        t = ete4.Tree("(A_ott1,B_ott2)R_ott3;", parser=1)
        orphans = remove_exclusions(t, [])
        assert orphans == []
        assert t.write() == "(A_ott1,B_ott2);"

    def test_removes_matching_otts(self):
        t = ete4.Tree(
            "((A_ott1,B_ott2)Sub_ott3,(C_ott4,D_ott5)Other_ott6)Root_ott7;",
            parser=1,
        )
        orphans = remove_exclusions(t, ["2", "4"])
        assert t.write() == "((A_ott1),(D_ott5));"
        orphan_names = sorted(o.root.name for o in orphans)
        assert orphan_names == ["B_ott2", "C_ott4"]

    def test_accepts_int_exclusions(self):
        # Values are stringified before matching, so int input is fine.
        t = ete4.Tree("(A_ott1,B_ott2)R_ott3;", parser=1)
        orphans = remove_exclusions(t, [2])
        assert t.write() == "(A_ott1);"
        assert [o.root.name for o in orphans] == ["B_ott2"]

    def test_non_matching_otts_left_alone(self):
        t = ete4.Tree("(A_ott1,B_ott2)R_ott3;", parser=1)
        orphans = remove_exclusions(t, ["99"])
        assert orphans == []
        assert t.write() == "(A_ott1,B_ott2);"


class TestParseOtOrphans:
    def test_picks_up_matching_files(self, tmp_path):
        for ott in ["1", "2", "3"]:
            (tmp_path / f"{ott}.nwk").write_text(f"(A_ott{ott}0,B_ott{ott}1);")
        result = parse_ot_orphans(str(tmp_path), ["Sub1_ott1@", "Sub3_ott3@"])
        assert set(result.keys()) == {"Sub1_ott1@", "Sub3_ott3@"}
        assert result["Sub1_ott1@"].write() == "(A_ott10,B_ott11);"
        assert result["Sub3_ott3@"].write() == "(A_ott30,B_ott31);"

    def test_no_matches_returns_empty(self, tmp_path):
        (tmp_path / "5.nwk").write_text("(A,B);")
        result = parse_ot_orphans(str(tmp_path), ["Sub_ott99@"])
        assert result == {}

    def test_empty_directory(self, tmp_path):
        assert parse_ot_orphans(str(tmp_path), ["Sub_ott1@"]) == {}

    def test_applies_exclusions(self, tmp_path):
        # Exclusion otts named in the inclusion syntax are pruned from the
        # loaded orphan tree.
        (tmp_path / "1.nwk").write_text("((A_ott11,B_ott12)Inner_ott13,(C_ott14,D_ott15)Other_ott16)R_ott1;")
        result = parse_ot_orphans(str(tmp_path), ["Sub_ott1~-12-14@"])
        assert set(result.keys()) == {"Sub_ott1~-12-14@"}
        assert result["Sub_ott1~-12-14@"].write() == "((A_ott11),(D_ott15));"

    def test_non_nwk_files_ignored(self, tmp_path):
        (tmp_path / "1.txt").write_text("(A,B);")
        assert parse_ot_orphans(str(tmp_path), ["Sub_ott1@"]) == {}


class TestParseBespokeTrees:
    def test_reads_base_and_listed_files(self, tmp_path, monkeypatch):
        # Restrict the token map so we only have to provide a few files.
        monkeypatch.setattr(
            step_parse,
            "token_to_file_map",
            {
                "AMORPHEA": {"file": "Amorphea.PHY", "edge_length": 50, "taxon": None},
                "AMBULACRARIA": {
                    "file": "Ambulacraria.PHY",
                    "edge_length": 20,
                    "taxon": "AmbulacrariaOverride",
                },
            },
        )
        (tmp_path / "Base.PHY").write_text("(AMORPHEA@,AMBULACRARIA@)Root;")
        (tmp_path / "Amorphea.PHY").write_text("(A_ott1,B_ott2)Amorphea;")
        (tmp_path / "Ambulacraria.PHY").write_text("(C_ott3,D_ott4)OriginalName;")

        base_t, bespoke_t = parse_bespoke_trees(str(tmp_path))

        assert base_t.write() == "(AMORPHEA@,AMBULACRARIA@);"
        assert set(bespoke_t.keys()) == {"AMORPHEA@", "AMBULACRARIA@"}

        # edge_length from token_to_file_map is applied to the subtree root.
        assert bespoke_t["AMORPHEA@"].root.dist == 50
        # AMORPHEA has no taxon override, so its root name is the file's own.
        assert bespoke_t["AMORPHEA@"].root.name == "Amorphea"

        # AMBULACRARIA has a taxon override, which replaces the root name.
        assert bespoke_t["AMBULACRARIA@"].root.dist == 20
        assert bespoke_t["AMBULACRARIA@"].root.name == "AmbulacrariaOverride"

    def test_missing_file_logged_and_skipped(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(
            step_parse,
            "token_to_file_map",
            {
                "AMORPHEA": {"file": "Amorphea.PHY", "edge_length": 50, "taxon": None},
                "MISSING": {"file": "DoesNotExist.PHY", "edge_length": 1, "taxon": None},
            },
        )
        (tmp_path / "Base.PHY").write_text("(AMORPHEA@,MISSING@)Root;")
        (tmp_path / "Amorphea.PHY").write_text("(A_ott1,B_ott2)Amorphea;")

        with caplog.at_level("ERROR", logger=step_parse.__name__):
            _, bespoke_t = parse_bespoke_trees(str(tmp_path))

        assert "AMORPHEA@" in bespoke_t
        assert "MISSING@" not in bespoke_t
        assert any("DoesNotExist.PHY" in r.message for r in caplog.records)

    def test_no_edge_length_leaves_dist_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            step_parse,
            "token_to_file_map",
            {
                "CRUMS": {"file": "CRuMs.PHY", "edge_length": None, "taxon": None},
            },
        )
        (tmp_path / "Base.PHY").write_text("(CRUMS@)Root;")
        (tmp_path / "CRuMs.PHY").write_text("(A_ott1,B_ott2)CRuMs;")

        _, bespoke_t = parse_bespoke_trees(str(tmp_path))
        assert bespoke_t["CRUMS@"].root.dist is None

    def test_alternate_base_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(step_parse, "token_to_file_map", {})
        (tmp_path / "OtherBase.PHY").write_text("(A_ott1,B_ott2)R;")
        base_t, bespoke_t = parse_bespoke_trees(str(tmp_path), base_name="OtherBase.PHY")
        assert base_t.write() == "(A_ott1,B_ott2);"
        assert bespoke_t == {}

    def test_missing_base_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(step_parse, "token_to_file_map", {})
        with pytest.raises(FileNotFoundError):
            parse_bespoke_trees(str(tmp_path))
