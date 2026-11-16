import json

from oz_tree_build.utilities.filter_wikidata import filter_wikidata


def test_filter_preserves_multilingual_labels_and_scientific_names(tmp_path):
    item = {
        "type": "item",
        "id": "Q26012",
        "labels": {
            "en": {"language": "en", "value": "true owls"},
            "fr": {"language": "fr", "value": "Strigidés"},
            "mul": {"language": "mul", "value": "Strigidae"},
        },
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"numeric-id": 16521}}}}],
            "P225": [
                {"mainsnak": {"datavalue": {"value": "Strigidae"}}, "rank": "normal"},
                {"mainsnak": {"datavalue": {"value": "Striges"}}, "rank": "deprecated"},
            ],
            "P1843": [
                {
                    "mainsnak": {"datavalue": {"value": {"language": "nb", "text": "uglefamilien"}}},
                    "rank": "normal",
                }
            ],
        },
        "sitelinks": {},
    }
    output = tmp_path / "filtered.json"
    filter_wikidata([json.dumps(item, separators=(",", ":"))], str(output))
    lines = output.read_text().splitlines()
    assert lines[0] == "["
    assert lines[-1] == "]"
    result = json.loads(lines[1].rstrip(","))
    assert result["labels"] == {
        "en": {"value": "true owls"},
        "fr": {"value": "Strigidés"},
        "mul": {"value": "Strigidae"},
    }
    assert result["claims"]["P225"] == [
        {"mainsnak": {"datavalue": {"value": "Strigidae"}}},
        {"mainsnak": {"datavalue": {"value": "Striges"}}},
    ]
    assert result["claims"]["P1843"] == item["claims"]["P1843"]
