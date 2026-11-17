"""Yield model (docs/YIELD_MODEL.md §2, §4): priors, offer odds per job, referral lift.
Priors are defaults overridable in `pipeline.yaml: yield_priors` (no learning yet, §6); grades B-C, so these
numbers order work, they do not predict outcomes."""
from __future__ import annotations

import math
from typing import Any, Iterable

DEFAULTS: dict[str, Any] = {
    "r": {"cold": 0.03, "referral": 0.20, "sourced": 0.03, "hm_dm": 0.03},   # application -> interview
    "o": {"cold": 0.06, "referral": 0.10, "sourced": 0.06, "hm_dm": 0.06},   # interview -> offer
    "q_ask": {"warm": 0.4, "weak": 0.1},                                     # P(contact agrees to refer)
    "s_co": {"weak": 0.3, "normal": 1.0, "strong": 1.5},                     # company referral-program strength
    "m_stale": 0.7,                                                          # posted > 60 days ago
}
_MAX = {"s_co": 5.0}  # every other prior is a probability or multiplier in (0, 1]


def priors(settings: Any = None) -> dict[str, Any]:
    """DEFAULTS with `pipeline.yaml: yield_priors` merged over them (per key), validated."""
    from careeros.config import ConfigError

    over = ((settings.pipeline if settings is not None else {}) or {}).get("yield_priors") or {}
    if not isinstance(over, dict):
        raise ConfigError("config/pipeline.yaml: yield_priors must be a mapping")
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in over.items():
        if k not in DEFAULTS:
            raise ConfigError(f"config/pipeline.yaml: yield_priors.{k} is not a prior ({', '.join(DEFAULTS)})")
        items = v.items() if isinstance(DEFAULTS[k], dict) and isinstance(v, dict) else [(None, v)]
        for sub, x in items:
            name = f"yield_priors.{k}" + (f".{sub}" if sub is not None else "")
            if (sub is not None and sub not in DEFAULTS[k]) or isinstance(DEFAULTS[k], dict) != (sub is not None):
                raise ConfigError(f"config/pipeline.yaml: {name} is not a known prior")
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 < x <= _MAX.get(k, 1.0):
                raise ConfigError(f"config/pipeline.yaml: {name} must be a number in (0, {_MAX.get(k, 1.0):g}], got {x!r}")
            if sub is None:
                out[k] = float(x)
            else:
                out[k][sub] = float(x)
    return out


def p_offer(channel: str, fit: int | float = 70, stale: bool = False, pr: dict[str, Any] | None = None) -> float:
    """p = r_k * o_k * m_fit * m_stale; the referral channel ignores fit (the referrer already filtered it)."""
    pr = pr or DEFAULTS
    m_fit = 1.0 if channel == "referral" else math.exp(0.3 * (float(fit) - 70) / 30)
    return pr["r"][channel] * pr["o"][channel] * m_fit * (pr["m_stale"] if stale else 1.0)


def referral_lift(fit: int | float = 70, stale: bool = False, tie: str = "weak", strength: str = "normal",
                  pr: dict[str, Any] | None = None) -> float:
    """Expected offer odds if you ask a contact for a referral, as a multiple of applying cold:
    1 + q_ask * s_co * (p_ref - p_cold) / p_cold."""
    pr = pr or DEFAULTS
    cold = p_offer("cold", fit, stale, pr)
    return 1 + pr["q_ask"][tie] * pr["s_co"].get(strength, 1.0) * (p_offer("referral", fit, stale, pr) - cold) / cold


def referral_lifts(settings: Any, jobs: Iterable[tuple[str, str, int | float, bool]]) -> dict[str, float]:
    """{job_id: lift} for (job_id, company, fit, stale) at a company where the imported LinkedIn network
    (`careeros network import`) has a 1st-degree connection. Tie strength is unknown there, so weak.
    `companies.yaml: referral_strength: {Company: weak|normal|strong}` scales it (default normal)."""
    from careeros.company_policy import Policy
    from careeros.network import load_network

    conns = load_network(settings)
    if not conns:
        return {}
    pr = priors(settings)
    key = Policy.from_settings(settings).company_key
    have = {key(c["company"]) for c in conns}
    strength = {key(k): str(v) for k, v in (settings.companies.get("referral_strength") or {}).items()}
    return {jid: referral_lift(fit, stale, "weak", strength.get(key(co), "normal"), pr)
            for jid, co, fit, stale in jobs if key(co) in have}
