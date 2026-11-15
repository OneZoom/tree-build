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


@pytest.mark.parametrize("command", ["taxon", "leaf"])
def test_database_commands_use_config(site_config, monkeypatch, command):
    calls = []
    monkeypatch.setattr(get_wiki_vernaculars, "connect_to_database", lambda uri: calls.append(uri))
    monkeypatch.setattr(get_wiki_vernaculars, "process_taxon", lambda *args: calls.append(args[1]))
    monkeypatch.setattr("sys.argv", ["get_wiki_vernaculars", command, "123"])
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
                subcommand="leaf",
            )
        )


@pytest.mark.parametrize("module", [get_wiki_images, get_wiki_vernaculars])
def test_clade_dump_config_and_override(site_config, tmp_path, monkeypatch, module):
    _, _, root = site_config
    configured_dump = root / "dump.json"
    configured_dump.write_text("[]")
    override_dump = tmp_path / "override.json"
    override_dump.write_text("[]")
    with (root / "config.ini").open("a") as file:
        file.write("wd_json_dump = dump.json\n")
    calls = []
    monkeypatch.setattr(module, "connect_to_database", lambda uri: None)
    monkeypatch.setattr(module, "process_clade", lambda db, name, dump, *args: calls.append((name, dump)))
    if module is get_wiki_images:
        monkeypatch.setattr(module, "AzureImageCropper", lambda config: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["harvest", "clade", "123", "456"])
    module.main()
    monkeypatch.setattr("sys.argv", ["harvest", "clade", "123", "--wd-dump", str(override_dump)])
    module.main()
    assert calls == [
        ("123", str(configured_dump)),
        ("456", str(configured_dump)),
        ("123", str(override_dump)),
    ]


@pytest.mark.parametrize("module", [get_wiki_images, get_wiki_vernaculars])
def test_clade_dump_required_before_database_connection(site_config, tmp_path, monkeypatch, module):
    monkeypatch.setattr(module, "connect_to_database", lambda *args: pytest.fail("connected to database"))
    monkeypatch.setattr("sys.argv", ["harvest", "clade", "123"])
    with pytest.raises(ValueError, match=r"wd_json_dump.*--wd-dump"):
        module.main()
    monkeypatch.setattr("sys.argv", ["harvest", "clade", "123", "--wd-dump", str(tmp_path / "missing.json")])
    with pytest.raises(ValueError, match="does not exist or is not a file"):
        module.main()
