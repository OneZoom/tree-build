from oz_tree_build.utilities.apply_mask_to_object_graph import apply_mask_to_object_graph
from oz_tree_build.utilities.filter_wikidata import WIKIDATA_MASK
from oz_tree_build.vernaculars import get_wiki_vernaculars as vernaculars


def statement(language, text, rank="normal"):
    return {"rank": rank, "mainsnak": {"datavalue": {"value": {"language": language, "text": text}}}}


def label(language, value):
    return {"language": language, "value": value}


def test_priorities_deduplication_and_languages():
    item = {
        "labels": {
            "en": label("en", "Owls"),
            "fr": label("fr", "Chouettes"),
            "de": label("de", "Eulen"),
            "es": label("es", "Strigidae"),
            "mul": label("mul", "Strigidae"),
            "sr-Cyrl": label("sr-Cyrl", "Сове"),
            "nl": label("nl", "Uilen"),
        },
        "claims": {
            "P225": [{"mainsnak": {"datavalue": {"value": "Strigidae"}}}],
            "P1843": [
                statement("en", "OWLS"),
                statement("en", "Owls!", "preferred"),
                statement("en", "Old owls", "deprecated"),
                statement("fr", "Hiboux"),
                statement("fr", "chouettes"),
                statement("de", "Käuze"),
                statement("it", "Zeta"),
                statement("it", "Alfa"),
                statement("sr-cyrl", "Сове"),
                statement("nl", "Andere uilen", "preferred"),
                {"rank": "normal", "mainsnak": {"snaktype": "somevalue"}},
            ],
        },
    }
    assert vernaculars.get_vernaculars_by_language_from_json_item(item) == {
        "en": [{"name": "Owls!", "preferred": 1}],
        "fr": [{"name": "chouettes", "preferred": 1}, {"name": "Hiboux", "preferred": 0}],
        "de": [{"name": "Eulen", "preferred": 1}, {"name": "Käuze", "preferred": 0}],
        "it": [{"name": "Alfa", "preferred": 1}, {"name": "Zeta", "preferred": 0}],
        "sr-cyrl": [{"name": "Сове", "preferred": 1}],
        "nl": [{"name": "Andere uilen", "preferred": 1}, {"name": "Uilen", "preferred": 0}],
    }


def test_label_only_and_deprecated_statements():
    item = {
        "labels": {"en": label("en", "true owls"), "fr": label("fr", "Strigidés")},
        "claims": {"P1843": [statement("en", "old name", "deprecated")]},
    }
    assert vernaculars.get_vernaculars_by_language_from_json_item(item) == {
        "en": [{"name": "true owls", "preferred": 1}],
        "fr": [{"name": "Strigidés", "preferred": 1}],
    }
    assert vernaculars.get_vernaculars_by_language_from_json_item({"claims": {}}) == {}


def test_dump_mask_retains_all_labels_and_scientific_names():
    item = {
        "labels": {"en": label("en", "true owls"), "fr": label("fr", "Strigidés")},
        "claims": {"P225": [{"mainsnak": {"datavalue": {"value": "Strigidae"}}, "rank": "normal"}]},
    }
    apply_mask_to_object_graph(item, WIKIDATA_MASK)
    assert item == {
        "labels": {"en": {"value": "true owls"}, "fr": {"value": "Strigidés"}},
        "claims": {"P225": [{"mainsnak": {"datavalue": {"value": "Strigidae"}}}]},
    }
