from types import SimpleNamespace

import pytest

from oz_tree_build.images import get_wiki_images, process_image_bits
from oz_tree_build.utilities import db_helper
from oz_tree_build.vernaculars import get_wiki_vernaculars


@pytest.fixture()
def site_config(tmp_path, monkeypatch):
    root = tmp_path / "tree-build"
    root.mkdir()
    monkeypatch.setattr(db_helper, "TREE_BUILD_CONFIG", root / "config.ini")
    appconfig = tmp_path / "appconfig.ini"
    appconfig.write_text("[db]\nuri = sqlite://example.sqlite\n")
    images = root / "images"
    images.mkdir()
    (root / "config.ini").write_text("[onezoom]\nappconfig = ../appconfig.ini\nimage_output_dir = images\n")
    return appconfig, images, root


def test_configured_paths_and_overrides(site_config, tmp_path, monkeypatch):
    appconfig, images, root = site_config
    monkeypatch.chdir(tmp_path)
    assert db_helper.read_config(None).get("db", "uri") == "sqlite://example.sqlite"
    assert db_helper.configured_path(None, "image_output_dir", "--output-dir") == str(images)
    monkeypatch.setenv("HOME", str(tmp_path))
    (root / "config.ini").write_text("[onezoom]\nappconfig = ~/appconfig.ini\nimage_output_dir = images\n")
    assert db_helper.read_config(None).get("db", "uri") == "sqlite://example.sqlite"
    (root / "config.ini").write_text("invalid ini")
    assert db_helper.read_config(str(appconfig)).get("db", "uri") == "sqlite://example.sqlite"
    assert db_helper.configured_path(str(images), "image_output_dir", "--output-dir") == str(images)


def test_missing_config_and_setting(site_config):
    _, _, root = site_config
    (root / "config.ini").unlink()
    with pytest.raises(ValueError, match=r"--conf-file.*config.ini"):
        db_helper.read_config(None)
    (root / "config.ini").write_text("[onezoom]\nappconfig = ../appconfig.ini\n")
    with pytest.raises(ValueError, match=r"image_output_dir.*--output-dir"):
        db_helper.configured_path(None, "image_output_dir", "--output-dir")


def test_image_command_uses_config(site_config, monkeypatch):
    _, images, _ = site_config
    calls = []
    monkeypatch.setattr(get_wiki_images, "connect_to_database", lambda uri: calls.append(uri))
    monkeypatch.setattr(get_wiki_images, "process_leaf", lambda *args: calls.append(args[5]))
    monkeypatch.setattr("sys.argv", ["get_wiki_images", "leaf", "123", "--no-azure-crop"])
    get_wiki_images.main()
    assert calls == ["sqlite://example.sqlite", str(images)]


def test_database_commands_use_config(site_config, monkeypatch):
    calls = []
    monkeypatch.setattr(get_wiki_vernaculars, "connect_to_database", lambda uri: calls.append(uri))
    monkeypatch.setattr(get_wiki_vernaculars, "process_leaf", lambda *args: calls.append(args[1]))
    monkeypatch.setattr("sys.argv", ["get_wiki_vernaculars", "leaf", "123"])
    get_wiki_vernaculars.main()
    monkeypatch.setattr(process_image_bits, "connect_to_database", lambda uri: calls.append(uri))
    monkeypatch.setattr(process_image_bits, "resolve", lambda db, ott: calls.append(ott))
    monkeypatch.setattr("sys.argv", ["process_image_bits", "leaf", "123"])
    process_image_bits.main()
    assert calls == ["sqlite://example.sqlite", "123", "sqlite://example.sqlite", 123]


def test_bad_image_directory_does_not_connect(site_config, monkeypatch):
    _, _, root = site_config
    monkeypatch.setattr(get_wiki_images, "connect_to_database", lambda *args: pytest.fail("connected to database"))
    with pytest.raises(ValueError, match="not a directory"):
        get_wiki_images.process_args(
            SimpleNamespace(
                wikimedia_client_id=None,
                wikimedia_client_secret=None,
                output_dir=str(root / "missing"),
                conf_file=None,
            )
        )
