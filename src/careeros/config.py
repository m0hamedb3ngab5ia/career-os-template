from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILES = ("targets", "categories", "companies", "qa", "pipeline")
# Nested keys the code reads as mappings; a list or scalar there is a config typo -> ConfigError.
MAPPING_KEYS = {
    "pipeline": ("paths",),
    "targets": ("candidate", "location", "seniority", "categories"),
    "companies": ("blocklist", "prestige_scoring", "prestige_tiers"),
}

_SUFFIX_RE = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|plc|lp|l\.p\.|limited|holdings|group|technologies)\b\.?",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


# Package checkout root (src/careeros/config.py -> repo). Holds examples/ for `careeros init`.
PKG_ROOT = Path(__file__).resolve().parents[2]
PERSONAL_DIRS = ("config", "profile")


class ConfigError(ValueError):
    """A config/ or profile/ YAML file is malformed or unusable. Fail closed: never run on an empty config."""


class SetupError(FileNotFoundError):
    """config/ or profile/ is missing: the candidate has not run `careeros init` yet."""


def _is_root(p: Path) -> bool:
    return (p / "config" / "pipeline.yaml").exists() or (p / "examples" / "config" / "pipeline.yaml").exists()


def find_repo_root(start: Path | None = None) -> Path:
    """CAREEROS_ROOT, else the nearest ancestor with config/ (or examples/config/ before init), else the checkout."""
    env = os.environ.get("CAREEROS_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for p in (here, *here.parents):
        if _is_root(p):
            return p
    if _is_root(PKG_ROOT):
        return PKG_ROOT
    raise FileNotFoundError("repo root not found (no config/pipeline.yaml or examples/config/pipeline.yaml upwards)")


def require_setup(root: Path) -> None:
    """Raise SetupError naming what is missing when config/ or profile/ does not exist under `root`."""
    missing = [d for d in PERSONAL_DIRS if not (root / d).is_dir()]
    if missing:
        raise SetupError(
            f"{' and '.join(d + '/' for d in missing)} missing under {root}. "
            "Run `careeros init` (copies examples/) or `careeros init --link <your-private-dir>`."
        )


def normalize_company(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = _SUFFIX_RE.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    return " ".join(s.split())


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"could not parse {path}: {str(e).splitlines()[0]}; fix the YAML and re-run") from None
    return data if isinstance(data, dict) else {"_items": data} if data else {}


@dataclass
class Settings:
    root: Path
    targets: dict[str, Any] = field(default_factory=dict)
    categories: dict[str, Any] = field(default_factory=dict)
    companies: dict[str, Any] = field(default_factory=dict)
    qa: dict[str, Any] = field(default_factory=dict)
    pipeline: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)
    standard_answers: dict[str, Any] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "Settings":
        root = (root or find_repo_root()).resolve()
        require_setup(root)
        cfg = {name: _load_yaml(root / "config" / f"{name}.yaml") for name in CONFIG_FILES}
        _check_shapes(cfg)
        s = cls(root=root, **cfg)
        raw_paths = s.pipeline.get("paths", {}) or {}
        for key, val in raw_paths.items():
            if isinstance(val, str):
                p = Path(val).expanduser()
                s.paths[key] = p if p.is_absolute() else (root / p).resolve()
        s.paths.setdefault("jobs_dir", root / "data" / "jobs")
        s.paths.setdefault("seen_file", root / "data" / "seen.json")
        s.paths.setdefault("tracker_xlsx", root / "data" / "JobTracker.xlsx")
        s.paths.setdefault("profile", root / "profile" / "master.yaml")
        s.paths.setdefault("standard_answers", root / "profile" / "standard_answers.yaml")
        s.profile = _load_yaml(s.paths["profile"])
        s.standard_answers = _load_yaml(s.paths["standard_answers"])
        return s

    # --- companies helpers -------------------------------------------------

    @property
    def boards(self) -> list[dict[str, Any]]:
        return list(self.companies.get("boards") or [])

    @property
    def prestige_tiers(self) -> dict[str, list[str]]:
        return {k: list(v or []) for k, v in (self.companies.get("prestige_tiers") or {}).items()}

    def merged_dream_list(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            key = normalize_company(name)
            if key and key not in seen:
                seen.add(key)
                out.append(name)

        for n in self.companies.get("dream_list") or []:
            add(str(n))
        auto = (self.companies.get("prestige_scoring") or {}).get("auto_dream") or []
        tiers = self.prestige_tiers
        for tier in auto:
            for n in tiers.get(tier, []):
                add(str(n))
        return out

    def is_dream(self, company: str) -> bool:
        key = normalize_company(company)
        return any(_fuzzy_eq(key, normalize_company(d)) for d in self.merged_dream_list())

    def prestige_tier(self, company: str) -> str | None:
        key = normalize_company(company)
        if not key:
            return None
        for tier, names in self.prestige_tiers.items():
            for n in names:
                if _fuzzy_eq(key, normalize_company(str(n))):
                    return tier
        return None

    def prestige_bonus(self, company: str) -> int:
        tier = self.prestige_tier(company)
        if tier is None:
            return 0
        bonus = (self.companies.get("prestige_scoring") or {}).get("bonus") or {}
        return int(bonus.get(tier, 0))

    def is_blocklisted(self, company: str) -> bool:
        key = normalize_company(company)
        if not key:
            return False
        bl = self.companies.get("blocklist") or {}
        for n in bl.get("companies") or []:
            if _fuzzy_eq(key, normalize_company(str(n))):
                return True
        for pat in bl.get("name_patterns") or []:
            p = normalize_company(str(pat))
            if p and p in key:
                return True
        return False

    # --- categories / targets helpers ------------------------------------

    def active_categories(self) -> dict[str, dict[str, Any]]:
        excluded = set((self.targets.get("categories") or {}).get("excluded") or [])
        return {
            k: v
            for k, v in self.categories.items()
            if isinstance(v, dict) and not v.get("excluded") and k not in excluded
        }

    def title_keywords(self) -> dict[str, list[str]]:
        return {k: [str(w).lower() for w in v.get("title_keywords") or []] for k, v in self.active_categories().items()}

    def excluded_title_keywords(self) -> list[str]:
        out: list[str] = []
        for k, v in self.categories.items():
            if isinstance(v, dict) and v.get("excluded"):
                out.extend(str(w).lower() for w in v.get("title_keywords") or [])
        return out

    def seniority_exclude_keywords(self) -> list[str]:
        return [str(w).lower() for w in (self.targets.get("seniority") or {}).get("exclude_title_keywords") or []]

    def blocked_countries(self) -> list[str]:
        return [str(c).upper() for c in (self.targets.get("location") or {}).get("blocked_countries") or []]

    def country_aliases(self) -> dict[str, list[str]]:
        """`targets.yaml: location.country_aliases` ({CODE: [words]}), codes upper-cased, words lower-cased."""
        raw = (self.targets.get("location") or {}).get("country_aliases") or {}
        if not isinstance(raw, dict):
            return {}
        return {str(k).upper(): [str(w).lower() for w in (v or [])] for k, v in raw.items()}

    @property
    def lifecycle_statuses(self) -> list[str]:
        from careeros.models import STATUSES

        return list(STATUSES)


def _check_shapes(cfg: dict[str, dict[str, Any]]) -> None:
    for name, data in cfg.items():
        if "_items" in data:
            raise ConfigError(f"config/{name}.yaml: top level must be a mapping (key: value), got a list")
        for key in MAPPING_KEYS.get(name, ()):
            if data.get(key) is not None and not isinstance(data[key], dict):
                raise ConfigError(f"config/{name}.yaml: {key} must be a mapping, got {type(data[key]).__name__}")
    boards = cfg.get("companies", {}).get("boards")
    if boards is not None:
        if not isinstance(boards, list):
            raise ConfigError(f"config/companies.yaml: boards must be a list of {{company, ats, slug}}, got {type(boards).__name__}")
        for i, b in enumerate(boards):
            if not isinstance(b, dict):
                raise ConfigError(f"config/companies.yaml: boards[{i}] must be a mapping, got {type(b).__name__}")
            if not b.get("company") or not b.get("ats"):
                raise ConfigError(f"config/companies.yaml: boards[{i}] needs company and ats")


def _fuzzy_eq(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    at, bt = a.split(), b.split()
    if len(at) >= 2 and len(bt) >= 2 and (a.startswith(b + " ") or b.startswith(a + " ")):
        return True
    return False


_settings: Settings | None = None


def get_settings(root: Path | None = None) -> Settings:
    global _settings
    if _settings is None or root is not None:
        _settings = Settings.load(root)
    return _settings
