"""careeros.bootstrap: `careeros init` copy / --link logic on a tmp root."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO

from careeros.bootstrap import InitError, copy_examples, examples_dir, link_private
from careeros.config import Settings

pytestmark = pytest.mark.unit


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A fresh clone: examples/ only, no personal dirs."""
    root = tmp_path / "checkout"
    shutil.copytree(EXAMPLE_REPO, root / "examples")
    return root


@pytest.fixture
def private(tmp_path: Path) -> Path:
    d = tmp_path / "private"
    shutil.copytree(EXAMPLE_REPO / "config", d / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", d / "profile")
    (d / "CLAUDE.local.md").write_text("# personal notes\n")
    return d


# --- copy -------------------------------------------------------------------------------------------

def test_copy_creates_both_dirs_from_examples(checkout: Path):
    rep = copy_examples(checkout)
    assert rep.actions == [("config/", "copied"), ("profile/", "copied")]
    for rel in ("config/targets.yaml", "profile/master.yaml", "profile/standard_answers.yaml",
                "profile/confidential_terms.yaml", "profile/voice/style_guide.md"):
        assert (checkout / rel).read_bytes() == (checkout / "examples" / rel).read_bytes(), rel
    assert not (checkout / "config").is_symlink()
    assert Settings.load(checkout).profile["identity"]["name"] == "Alex Example"


def test_copy_never_overwrites(checkout: Path):
    (checkout / "profile").mkdir()
    (checkout / "profile" / "master.yaml").write_text("identity: {name: Me}\n")
    rep = copy_examples(checkout)
    assert rep.actions == [("config/", "copied"), ("profile/", "kept")]
    assert (checkout / "profile" / "master.yaml").read_text() == "identity: {name: Me}\n"
    assert not (checkout / "profile" / "standard_answers.yaml").exists()  # no merging into an existing dir
    again = copy_examples(checkout)
    assert again.actions == [("config/", "kept"), ("profile/", "kept")]
    assert again.lines() == ["kept      config/", "kept      profile/"]


def test_copy_keeps_existing_symlink(checkout: Path, private: Path):
    (checkout / "config").symlink_to(private / "config", target_is_directory=True)
    rep = copy_examples(checkout)
    assert ("config/", "kept") in rep.actions and (checkout / "config").is_symlink()


def test_examples_dir_missing(tmp_path: Path, monkeypatch):
    import careeros.bootstrap as b

    monkeypatch.setattr(b, "PKG_ROOT", tmp_path / "nowhere")
    with pytest.raises(InitError, match="no examples/"):
        examples_dir(tmp_path)


def test_examples_dir_falls_back_to_package_checkout(tmp_path: Path):
    assert examples_dir(tmp_path / "empty-root") == EXAMPLE_REPO.resolve()


# --- link -------------------------------------------------------------------------------------------

def test_link_creates_symlinks_including_local_notes(checkout: Path, private: Path):
    rep = link_private(checkout, private)
    assert [n for n, _ in rep.actions] == ["config", "profile", "CLAUDE.local.md"]
    for name in ("config", "profile", "CLAUDE.local.md"):
        p = checkout / name
        assert p.is_symlink() and p.resolve() == (private / name).resolve()
    assert Settings.load(checkout).profile["identity"]["name"] == "Alex Example"


def test_link_without_local_notes_skips_it(checkout: Path, private: Path):
    (private / "CLAUDE.local.md").unlink()
    link_private(checkout, private)
    assert not (checkout / "CLAUDE.local.md").exists() and not (checkout / "CLAUDE.local.md").is_symlink()


def test_link_is_idempotent_and_repoints_existing_symlinks(checkout: Path, private: Path, tmp_path: Path):
    link_private(checkout, private)
    link_private(checkout, private)
    other = tmp_path / "other"
    shutil.copytree(private, other)
    link_private(checkout, other)
    assert (checkout / "profile").resolve() == (other / "profile").resolve()


@pytest.mark.parametrize("real", ["profile", "config", "CLAUDE.local.md"])
def test_link_refuses_real_path_and_changes_nothing(checkout: Path, private: Path, real: str):
    dest = checkout / real
    if real.endswith(".md"):
        dest.write_text("mine\n")
    else:
        dest.mkdir()
        (dest / "keep.txt").write_text("mine\n")
    with pytest.raises(InitError, match="refusing to replace real"):
        link_private(checkout, private)
    for name in ("config", "profile", "CLAUDE.local.md"):
        assert not (checkout / name).is_symlink(), name
    assert dest.exists()


def test_link_requires_config_and_profile_in_private_dir(checkout: Path, private: Path):
    shutil.rmtree(private / "config")
    with pytest.raises(InitError, match="config"):
        link_private(checkout, private)
    assert not (checkout / "profile").exists()


def test_link_private_dir_missing(checkout: Path, tmp_path: Path):
    with pytest.raises(InitError, match="not a directory"):
        link_private(checkout, tmp_path / "nope")


def test_relink_to_dir_without_local_notes_drops_stale_notes_symlink(checkout: Path, private: Path, tmp_path: Path):
    link_private(checkout, private)
    assert (checkout / "CLAUDE.local.md").is_symlink()
    other = tmp_path / "other"
    shutil.copytree(private, other)
    (other / "CLAUDE.local.md").unlink()
    rep = link_private(checkout, other)
    notes = checkout / "CLAUDE.local.md"
    assert not notes.exists() and not notes.is_symlink()  # no stale context from the previous private dir
    assert ("CLAUDE.local.md", "unlinked") in rep.actions
    assert (checkout / "profile").resolve() == (other / "profile").resolve()


def test_relink_without_local_notes_keeps_a_real_local_notes_file(checkout: Path, private: Path):
    (private / "CLAUDE.local.md").unlink()
    (checkout / "CLAUDE.local.md").write_text("mine\n")
    link_private(checkout, private)
    assert (checkout / "CLAUDE.local.md").read_text() == "mine\n"
