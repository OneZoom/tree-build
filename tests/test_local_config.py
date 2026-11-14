from types import SimpleNamespace

import pytest

from oz_tree_build.images import get_wiki_images, process_image_bits
from oz_tree_build.utilities import db_helper, local_config, make_js_treefiles
from oz_tree_build.vernaculars import get_wiki_vernaculars


@pytest.fixture()
def local_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("TREE_BUILD_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / "tree-build"
    config_dir.mkdir(parents=True)
    monkeypatch.chdir(config_dir)
    appconfig = tmp_path / "appconfig.ini"
    appconfig.write_text("[db]\nuri = sqlite://example.sqlite\n", encoding="utf-8")
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (config_dir / "config.ini").write_text(
        "[onezoom]\nappconfig = ~/appconfig.ini\nimage_output_dir = ~/images\n",
        encoding="utf-8",
    )
    return appconfig, image_dir, config_dir


def test_config_resolution_and_explicit_overrides(local_paths):
    appconfig, image_dir, config_dir = local_paths
    assert db_helper.read_config().get("db", "uri") == "sqlite://example.sqlite"
    assert local_config.resolve_path(None, "image_output_dir", "--output-dir") == str(image_dir)
    (config_dir / "config.ini").write_text("[onezoom]\nappconfig = ../appconfig.ini\n", encoding="utf-8")
    assert db_helper.read_config().get("db", "uri") == "sqlite://example.sqlite"
    (config_dir / "config.ini").write_text("invalid ini", encoding="utf-8")
    assert db_helper.read_config(str(appconfig)).get("db", "uri") == "sqlite://example.sqlite"
    assert local_config.resolve_path(str(image_dir), "image_output_dir", "--output-dir") == str(image_dir)


def test_missing_and_invalid_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("TREE_BUILD_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=r"--conf-file.*appconfig"):
        db_helper.read_config()
    with pytest.raises(ValueError, match=r"--output-dir.*image_output_dir"):
        local_config.resolve_path(None, "image_output_dir", "--output-dir")
    with pytest.raises(ValueError, match="must not be empty"):
        local_config.resolve_path("", "appconfig", "--conf-file")
    with pytest.raises(ValueError, match="cannot be found"):
        db_helper.read_config(str(tmp_path / "missing.ini"))


def test_config_location_override(local_paths, tmp_path, monkeypatch):
    _, image_dir, config_dir = local_paths
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TREE_BUILD_CONFIG", str(config_dir / "config.ini"))
    assert local_config.resolve_path(None, "image_output_dir", "--output-dir") == str(image_dir)
    monkeypatch.setenv("TREE_BUILD_CONFIG", "relative.ini")
    with pytest.raises(ValueError, match="absolute path"):
        local_config.resolve_path(None, "appconfig", "--conf-file")
    monkeypatch.setenv("TREE_BUILD_CONFIG", str(tmp_path / "missing.ini"))
    with pytest.raises(FileNotFoundError):
        local_config.resolve_path(None, "appconfig", "--conf-file")


def test_update_commands_use_machine_paths(local_paths, monkeypatch):
    _, image_dir, _ = local_paths
    calls = []
    monkeypatch.setattr(get_wiki_images, "connect_to_database", lambda uri: calls.append(("image_db", uri)))
    monkeypatch.setattr(get_wiki_images, "process_leaf", lambda *args: calls.append(("image", args[5])))
    monkeypatch.setattr(get_wiki_vernaculars, "connect_to_database", lambda uri: calls.append(("vern_db", uri)))
    monkeypatch.setattr(get_wiki_vernaculars, "process_leaf", lambda *args: calls.append(("vern", args[1])))
    monkeypatch.setattr(process_image_bits, "connect_to_database", lambda uri: calls.append(("bits_db", uri)))
    monkeypatch.setattr(process_image_bits, "resolve", lambda db, ott: calls.append(("bits", ott)))
    get_wiki_images.process_args(
        SimpleNamespace(
            wikimedia_client_id=None,
            wikimedia_client_secret=None,
            output_dir=None,
            conf_file=None,
            no_azure_crop=True,
            taxa_data_file=None,
            subcommand="leaf",
            ott_or_taxa=["123"],
            image=None,
            rating=None,
        )
    )
    get_wiki_vernaculars.process_args(
        SimpleNamespace(
            conf_file=None,
            taxa_data_file=None,
            subcommand="leaf",
            ott_or_taxa=["123"],
        )
    )
    process_image_bits.process_args(SimpleNamespace(conf_file=None, subcommand="leaf", ott=123))
    assert calls == [
        ("image_db", "sqlite://example.sqlite"),
        ("image", str(image_dir)),
        ("vern_db", "sqlite://example.sqlite"),
        ("vern", "123"),
        ("bits_db", "sqlite://example.sqlite"),
        ("bits", 123),
    ]


def test_image_missing_directory_fails_before_connecting(local_paths, monkeypatch):
    appconfig, _, _ = local_paths
    monkeypatch.setattr(get_wiki_images, "connect_to_database", lambda *args: pytest.fail("connected to database"))
    with pytest.raises(ValueError, match="not a directory"):
        get_wiki_images.process_args(
            SimpleNamespace(
                wikimedia_client_id=None,
                wikimedia_client_secret=None,
                output_dir=str(appconfig),
                conf_file=None,
            )
        )


def test_image_command_explicit_paths_override_config(local_paths, tmp_path, monkeypatch):
    _, _, config_dir = local_paths
    override_config = tmp_path / "override.ini"
    override_config.write_text("[db]\nuri = sqlite://override.sqlite\n", encoding="utf-8")
    override_dir = tmp_path / "override_images"
    override_dir.mkdir()
    (config_dir / "config.ini").write_text("invalid ini", encoding="utf-8")
    calls = []
    monkeypatch.setattr(get_wiki_images, "connect_to_database", lambda uri: calls.append(uri))
    monkeypatch.setattr(get_wiki_images, "process_leaf", lambda *args: calls.append(args[5]))
    monkeypatch.setattr(
        "sys.argv",
        [
            "get_wiki_images",
            "leaf",
            "123",
            "--conf-file",
            str(override_config),
            "--output-dir",
            str(override_dir),
            "--no-azure-crop",
        ],
    )
    get_wiki_images.main()
    assert calls == ["sqlite://override.sqlite", str(override_dir)]


def test_make_js_requires_output_dir(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["make_js_treefiles", "ordered_tree_123.poly"])
    with pytest.raises(SystemExit) as exc:
        make_js_treefiles.main()
    assert exc.value.code == 2
    assert "--outdir" in capsys.readouterr().err
