import pytest

from oz_tree_build.images import get_wiki_images
from oz_tree_build.vernaculars import get_wiki_vernaculars


@pytest.mark.parametrize("module", [get_wiki_images, get_wiki_vernaculars])
def test_clade_dump_option(module, tmp_path, monkeypatch, capsys):
    dump = tmp_path / "dump.json"
    dump.write_text("[]")
    args = ["harvest", "clade", "123", "456", "--conf-file", "appconfig.ini"]
    if module is get_wiki_images:
        args += ["--output-dir", str(tmp_path)]
    calls = []
    monkeypatch.setattr(module, "process_args", lambda parsed: calls.append((parsed.ott_or_taxa, parsed.wd_dump)))
    monkeypatch.setattr("sys.argv", [*args, "--wd-dump", str(dump)])
    module.main()
    assert calls == [(["123", "456"], str(dump))]
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    assert "--wd-dump" in capsys.readouterr().err


@pytest.mark.parametrize("module", [get_wiki_images, get_wiki_vernaculars])
def test_clade_missing_dump_fails_before_connecting(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "connect_to_database", lambda *args: pytest.fail("connected to database"))
    args = ["harvest", "clade", "123", "--conf-file", "appconfig.ini", "--wd-dump", str(tmp_path / "missing.json")]
    if module is get_wiki_images:
        args += ["--output-dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(ValueError, match="does not exist or is not a file"):
        module.main()
