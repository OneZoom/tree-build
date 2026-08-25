"""
Unit tests for the taxonomy-reading parts of taxon_map
"""

from oz_tree_build.taxon_mapping_and_popularity.taxon_map import (
    add_taxon_sources,
    parse_sourceinfo,
    read_extra_source_file,
    read_ot_taxonomy,
)


def write_ot_taxonomy(path, rows):
    """Write rows (dicts) out in OpenTree taxonomy.tsv format, i.e. "\t|\t"-separated"""
    header = ["uid", "parent_uid", "name", "rank", "sourceinfo", "uniqname", "flags"]
    with open(path, "w", encoding="utf-8") as f:
        for r in [{k: k for k in header}, *rows]:
            f.write("".join(f"{r.get(k, '')}\t|\t" for k in header) + "\n")


def write_extra_source_file(path, rows, header=("uid", "name", "sourceinfo", "notes")):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(k, "")) for k in header) + "\n")


class TestParseSourceinfo:
    def test_numeric_ids_become_ints(self):
        assert parse_sourceinfo("ncbi:1274384,gbif:8094325") == {
            "ncbi": 1274384,
            "gbif": 8094325,
        }

    def test_non_numeric_ids_stay_strings(self):
        # e.g. SILVA accessions, and GBIF ids of the form "D11377/#1"
        assert parse_sourceinfo("silva:JX948102,gbif:D11377/#1") == {
            "silva": "JX948102",
            "gbif": "D11377/#1",
        }

    def test_only_first_colon_separates(self):
        assert parse_sourceinfo("silva:AB:CD") == {"silva": "AB:CD"}

    def test_zero_ids_are_kept(self):
        # "life" is silva:0,ncbi:1,gbif:0,irmng:0, so 0 must not be treated as absent
        assert parse_sourceinfo("silva:0,ncbi:1,gbif:0") == {"silva": 0, "ncbi": 1, "gbif": 0}

    def test_empty_sourceinfo(self):
        assert parse_sourceinfo("") == {}

    def test_order_is_preserved(self):
        # add_taxon_sources relies on the order for source priority
        assert list(parse_sourceinfo("silva:0,ncbi:1,gbif:0,irmng:0")) == [
            "silva",
            "ncbi",
            "gbif",
            "irmng",
        ]


class TestReadOtTaxonomy:
    def test_fields_are_split_and_converted(self, tmp_path):
        path = tmp_path / "taxonomy.tsv"
        write_ot_taxonomy(
            path,
            [
                {"uid": 805080, "name": "life", "rank": "no rank", "sourceinfo": "ncbi:1"},
                {
                    "uid": 93302,
                    "parent_uid": 805080,
                    "name": "cellular organisms",
                    "rank": "no rank",
                    "sourceinfo": "ncbi:131567",
                },
            ],
        )
        rows = list(read_ot_taxonomy(path))

        assert [r["uid"] for r in rows] == [805080, 93302]
        assert [r["parent_uid"] for r in rows] == [None, 805080]
        assert [r["name"] for r in rows] == ["life", "cellular organisms"]
        assert [r["rank"] for r in rows] == ["no rank", "no rank"]
        assert [r["sourceinfo"] for r in rows] == [{"ncbi": 1}, {"ncbi": 131567}]

    def test_trailing_separator_is_not_a_field(self, tmp_path):
        # Each line ends with "\t|\t", which must not yield an extra empty column
        path = tmp_path / "taxonomy.tsv"
        write_ot_taxonomy(path, [{"uid": 1, "sourceinfo": "ncbi:1", "flags": "sibling_higher"}])
        (row,) = list(read_ot_taxonomy(path))

        assert set(row) == {"uid", "parent_uid", "name", "rank", "sourceinfo", "uniqname", "flags"}
        assert row["flags"] == "sibling_higher"


class TestReadExtraSourceFile:
    def test_row_is_parsed_like_a_taxonomy_row(self, tmp_path):
        path = tmp_path / "SupplementaryTaxonomy.tsv"
        write_extra_source_file(
            path,
            [
                {
                    "uid": 809432,
                    "name": "Strigops habroptilus",
                    "sourceinfo": "ncbi:2489341,irmng:11435975",
                    "notes": "Add in missing kakapo",
                }
            ],
        )
        (row,) = list(read_extra_source_file(path))

        assert row["uid"] == 809432
        assert row["sourceinfo"] == {"ncbi": 2489341, "irmng": 11435975}
        assert row["name"] == "Strigops habroptilus"
        assert row["notes"] == "Add in missing kakapo"

    def test_non_numeric_uid_stays_a_string(self, tmp_path):
        path = tmp_path / "extra.tsv"
        write_extra_source_file(path, [{"uid": "mrcaott409215ott616649", "sourceinfo": "ncbi:1"}])
        (row,) = list(read_extra_source_file(path))

        assert row["uid"] == "mrcaott409215ott616649"

    def test_only_uid_and_sourceinfo_are_required(self, tmp_path):
        path = tmp_path / "extra.tsv"
        write_extra_source_file(path, [{"uid": 1, "sourceinfo": "gbif:2"}], header=("uid", "sourceinfo"))
        (row,) = list(read_extra_source_file(path))

        assert row == {"uid": 1, "sourceinfo": {"gbif": 2}}

    def test_missing_file_is_ignored_with_a_warning(self, tmp_path, caplog):
        path = tmp_path / "nonexistent.tsv"

        assert list(read_extra_source_file(path)) == []
        assert "not found" in caplog.text


class TestAddTaxonSources:
    def test_adds_a_new_ott_with_its_sources(self):
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 770315, {"ncbi": 9999, "gbif": 1234}, "species")

        assert OTT_ptrs == {
            770315: {
                "ott": 770315,
                "rank": "species",
                "sources": {"ncbi": {"id": 9999}, "gbif": {"id": 1234}},
            }
        }
        assert source_ptrs == {"ncbi": {9999: {"id": 9999}}, "gbif": {1234: {"id": 1234}}}

    def test_ott_and_source_entries_are_the_same_object(self):
        # Wikidata data is added via source_ptrs, and read back out via OTT_ptrs,
        # so the two must point at one shared dict
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 5})

        assert OTT_ptrs[1]["sources"]["ncbi"] is source_ptrs["ncbi"][5]

    def test_otts_sharing_a_source_id_share_its_entry(self):
        # Otherwise the first OTT is left pointing at an orphaned dict, which never
        # gets the wikidata item that is added via source_ptrs
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 5})
        add_taxon_sources(OTT_ptrs, source_ptrs, 2, {"ncbi": 5})

        source_ptrs["ncbi"][5]["wd"] = "Q123"
        assert OTT_ptrs[1]["sources"]["ncbi"] is OTT_ptrs[2]["sources"]["ncbi"]
        assert OTT_ptrs[1]["sources"]["ncbi"]["wd"] == "Q123"

    def test_reading_a_source_keeps_data_added_to_its_entry(self):
        # An extra_source_file row re-stating an id must not wipe out its wikidata item
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 5})
        source_ptrs["ncbi"][5]["wd"] = "Q123"
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 5})

        assert OTT_ptrs[1]["sources"]["ncbi"] == {"id": 5, "wd": "Q123"}

    def test_non_numeric_source_ids_are_usable(self):
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"silva": "JX948102"})

        assert source_ptrs["silva"]["JX948102"] == {"id": "JX948102"}

    def test_a_second_call_overrides_only_the_sources_given(self):
        # i.e. how an extra_source_file supplements the OpenTree taxonomy
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 9999, "gbif": 1234}, "species")
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 2489341, "irmng": 11435975})

        assert OTT_ptrs[1]["sources"] == {
            "ncbi": {"id": 2489341},
            "gbif": {"id": 1234},
            "irmng": {"id": 11435975},
        }

    def test_rank_is_kept_when_not_given(self):
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 1}, "species")
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"gbif": 2})

        assert OTT_ptrs[1]["rank"] == "species"

    def test_rank_is_absent_if_never_given(self):
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"ncbi": 1})

        assert "rank" not in OTT_ptrs[1]

    def test_a_silva_derived_ncbi_id_is_used_like_any_other(self):
        # NCBI ids from SILVA-sourced rows used to be singled out as "ncbi_silva"
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {"silva": "JX948102", "ncbi": 1274384})

        assert OTT_ptrs[1]["sources"]["ncbi"] == {"id": 1274384}

    def test_empty_sourceinfo_still_adds_the_ott(self):
        OTT_ptrs, source_ptrs = {}, {}
        add_taxon_sources(OTT_ptrs, source_ptrs, 1, {}, "species")

        assert OTT_ptrs == {1: {"ott": 1, "rank": "species", "sources": {}}}
        assert source_ptrs == {}
