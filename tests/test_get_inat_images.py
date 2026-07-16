from types import SimpleNamespace
from unittest import mock

import duckdb
import pytest

from oz_tree_build.images_and_vernaculars import get_inat_images


class MockResponse:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.content = content
        self.text = ""

    def json(self):
        return self._json_data

    def iter_content(self, chunk_size):
        return [self.content]


def test_get_inat_taxon_id_from_json_item_prefers_preferred_claim():
    json_item = {
        "id": "Q2355832",
        "claims": {
            "P3151": [
                {"rank": "normal", "mainsnak": {"datavalue": {"value": "111"}}},
                {"rank": "preferred", "mainsnak": {"datavalue": {"value": "319598"}}},
            ]
        },
    }
    assert get_inat_images.get_inat_taxon_id_from_json_item(json_item) == 319598


@pytest.mark.parametrize(
    "licence,expected",
    [
        ("CC0", True),
        ("cc-by", True),
        ("CC-BY-SA", True),
        ("cc-by-nc", False),
        ("cc-by-nd", False),
        ("all-rights-reserved", False),
        (None, False),
    ],
)
def test_license_filter_is_strict(licence, expected):
    assert get_inat_images.is_allowed_inat_license(licence) is expected


def test_inat_open_data_url_uses_medium_not_square():
    url = get_inat_images.inat_photo_url_from_open_data(12345, "jpg")
    assert url == "https://inaturalist-open-data.s3.amazonaws.com/photos/12345/medium.jpg"


def test_api_selection_rejects_non_allowed_licences():
    api_response = {
        "results": [
            {
                "uuid": "obs-1",
                "quality_grade": "research",
                "cached_votes_total": 999,
                "user": {"login": "badlicence"},
                "photos": [
                    {
                        "id": 1,
                        "url": "https://static.inaturalist.org/photos/1/square.jpg",
                        "license_code": "cc-by-nc",
                    }
                ],
            },
            {
                "uuid": "obs-2",
                "quality_grade": "research",
                "cached_votes_total": 10,
                "user": {"login": "goodlicence"},
                "photos": [
                    {
                        "id": 2,
                        "url": "https://static.inaturalist.org/photos/2/square.jpg",
                        "license_code": "cc-by",
                        "original_dimensions": {"width": 1000, "height": 800},
                    }
                ],
            },
        ]
    }

    def fake_get(url, params=None, headers=None, stream=False):
        assert params["photo_license"] == "cc-by,cc-by-sa,cc0"
        assert params["order_by"] == "votes"
        return MockResponse(json_data=api_response)

    with mock.patch("requests.get", side_effect=fake_get):
        candidate = get_inat_images.get_best_photo_from_inat_api(319598)

    assert candidate["photo_id"] == 2
    assert candidate["license"] == "cc-by"
    assert candidate["image_url"].endswith("/medium.jpg")


def create_test_inat_duckdb(tmp_path):
    db_path = tmp_path / "inat.duckdb"
    inat_db = duckdb.connect(str(db_path))
    inat_db.execute(
        """CREATE TABLE observations (
        observation_uuid TEXT NOT NULL,
        observer_id INTEGER,
        taxon_id INTEGER,
        quality_grade TEXT,
        observed_on TEXT
        );"""
    )
    inat_db.execute(
        """CREATE TABLE photos (
        photo_id INTEGER NOT NULL,
        observation_uuid TEXT NOT NULL,
        observer_id INTEGER,
        extension TEXT,
        license TEXT,
        width INTEGER,
        height INTEGER,
        position INTEGER
        );"""
    )
    inat_db.execute(
        """CREATE TABLE observers (
        observer_id INTEGER NOT NULL,
        login TEXT,
        name TEXT
        );"""
    )
    inat_db.execute(
        """CREATE TABLE taxa (
        taxon_id INTEGER NOT NULL,
        rank TEXT
        );"""
    )
    inat_db.execute("INSERT INTO observers VALUES (1, 'observer_login', 'Observer Name');")
    inat_db.execute("INSERT INTO taxa VALUES (319598, 'species'), (999, 'species'), (111, 'genus');")
    inat_db.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?);",
        ("obs-bad", 1, 319598, "research", "2024-01-01"),
    )
    inat_db.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?);",
        ("obs-good", 1, 319598, "research", "2024-01-02"),
    )
    inat_db.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?);",
        ("obs-nonresearch", 1, 999, "casual", "2024-01-03"),
    )
    inat_db.execute(
        "INSERT INTO photos VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        (1, "obs-bad", 1, "jpg", "cc-by-nc", 4000, 4000, 0),
    )
    inat_db.execute(
        "INSERT INTO photos VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        (2, "obs-good", 1, "jpeg", "CC-BY-SA", 2000, 1000, 0),
    )
    inat_db.execute(
        "INSERT INTO photos VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        (3, "obs-nonresearch", 1, "jpg", "CC0", 1000, 1000, 0),
    )
    return inat_db


def test_metadata_selection_filters_to_allowed_license_and_research_grade(tmp_path):
    inat_db = create_test_inat_duckdb(tmp_path)
    
    candidate = get_inat_images.get_best_photo_from_metadata_db(inat_db, 319598)
    assert candidate["photo_id"] == 2
    assert candidate["license"] == "cc-by-sa"
    assert candidate["license_string"] == "CC-BY-SA"
    assert candidate["rights"] == "© Observer Name, some rights reserved (CC-BY-SA)"
    assert candidate["image_url"].endswith("/2/medium.jpeg")
    inat_db.close()


def test_usable_photo_species_stats(tmp_path):
    inat_db = create_test_inat_duckdb(tmp_path)

    stats = get_inat_images.get_usable_photo_species_stats(inat_db)
    assert stats["inat_species"] == 2
    assert stats["inat_species_with_usable_photos"] == 2
    assert stats["inat_species_with_research_grade_usable_photos"] == 1
    inat_db.close()
