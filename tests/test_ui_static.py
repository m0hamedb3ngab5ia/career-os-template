"""The committed web UI bundle (ui/ -> npm run build -> src/careeros/ui/static) is complete and packaged."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "careeros" / "ui" / "static"


@pytest.mark.integration
def test_index_references_only_files_that_exist():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="/(assets/[^"]+)"', html)
    assert refs, "index.html should load the built JS and CSS from /assets/"
    for ref in refs:
        assert (STATIC / ref).is_file(), f"index.html points at missing {ref}; rebuild ui/ and commit"


@pytest.mark.integration
def test_bundle_has_no_source_maps_or_dev_leftovers():
    names = [p.name for p in STATIC.rglob("*") if p.is_file()]
    assert not [n for n in names if n.endswith(".map")]
    assert "main.tsx" not in (STATIC / "index.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_static_bundle_is_package_data():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "ui/static/**/*" in cfg["tool"]["setuptools"]["package-data"]["careeros"]
