"""Outreach email finding: company domain, pattern guesses, optional Hunter.io domain search (user's own key),
and which jobs are high-yield enough for outreach. Never probes or sends to an address."""
from __future__ import annotations

import json

import pytest

from careeros.email_guess import (
    apply_to_contacts,
    company_domain,
    email_candidates,
    hunter_domain_search,
    outreach_targets,
)

pytestmark = pytest.mark.unit


def test_candidates_default_order_and_name_cleanup():
    assert email_candidates("José van der Berg", "acme.com")[:4] == [
        "jose.berg@acme.com", "jberg@acme.com", "jose@acme.com", "joseb@acme.com"]


def test_candidates_put_known_pattern_first_without_dupes():
    out = email_candidates("Ada Lovelace", "acme.com", pattern="{first}{l}")
    assert out[0] == "adal@acme.com" and len(out) == len(set(out))


def test_candidates_single_name_only_first():
    assert email_candidates("Cher", "acme.com") == ["cher@acme.com"]


def test_company_domain_prefers_config_then_posting_url(settings):
    settings.companies["company_domains"] = {"Acme Robotics": "acmerobotics.ai"}
    assert company_domain(settings, "Acme Robotics", "https://boards.greenhouse.io/acme/1") == ("acmerobotics.ai", "high")
    assert company_domain(settings, "Quillstone", "https://careers.quillstone.com/jobs/1") == ("quillstone.com", "high")
    assert company_domain(settings, "Quill Stone", "https://jobs.lever.co/x/1") == ("quillstone.com", "low")


HUNTER = {"data": {"domain": "acme.com", "pattern": "{f}{last}", "emails": [
    {"value": "rjones@acme.com", "first_name": "Rita", "last_name": "Jones", "position": "Technical Recruiter",
     "confidence": 94},
    {"value": "bob@acme.com", "first_name": "Bob", "last_name": "Smith", "position": "Sales", "confidence": 60},
]}}


def test_hunter_domain_search_builds_query_and_parses():
    seen = {}

    def fetch(url, key):
        seen["url"], seen["key"] = url, key
        return json.dumps(HUNTER)

    r = hunter_domain_search("KEY", domain="acme.com", fetch=fetch)
    assert "domain=acme.com" in seen["url"] and "KEY" not in seen["url"] and seen["key"] == "KEY"
    assert r["pattern"] == "{f}{last}" and r["emails"][0]["value"] == "rjones@acme.com"


def test_hunter_error_is_none():
    def boom(url, key):
        raise OSError("429")
    assert hunter_domain_search("KEY", domain="acme.com", fetch=boom) is None


def test_apply_to_contacts_uses_pattern_exact_hits_and_adds_recruiters():
    data = {"company": "Acme", "contacts": [
        {"name": "Rita Jones", "role": "recruiter", "email": None, "email_confidence": "low"},
        {"name": "Sam Lee", "role": "hiring_manager", "email": None, "email_confidence": "low"}]}
    out = apply_to_contacts(data, "acme.com", "high", HUNTER["data"])
    rita, sam = out["contacts"][:2]
    assert rita["email"] == "rjones@acme.com" and rita["email_confidence"] == "medium"
    assert rita["email_source"] == "hunter.io"
    assert sam["email"] is None and sam["email_candidates"][0] == "slee@acme.com"
    assert sam["email_confidence"] == "medium"                       # pattern known from Hunter
    assert out["email_pattern"] == "{f}{last}" and out["domain"] == "acme.com"
    assert "compose" in out["verify_tip"]                            # manual Gmail tip, never automated
    assert [c["name"] for c in out["contacts"]] == ["Rita Jones", "Sam Lee"]  # Rita not added twice; Bob not a recruiter


def test_apply_to_contacts_adds_new_hunter_recruiter():
    out = apply_to_contacts({"contacts": []}, "acme.com", "high", HUNTER["data"])
    assert [(c["name"], c["role"], c["source"]) for c in out["contacts"]] == [("Rita Jones", "recruiter", "hunter.io")]


def test_apply_to_contacts_without_hunter_is_low():
    out = apply_to_contacts({"contacts": [{"name": "Sam Lee"}]}, "acme.com", "low", None)
    c = out["contacts"][0]
    assert c["email_candidates"][0] == "sam.lee@acme.com" and c["email_confidence"] == "low"


JOBS = [
    {"job_id": "a", "status": "applied", "fit": 90, "tier": "B", "company": "A", "title": "t"},
    {"job_id": "b", "status": "queued", "fit": 75, "tier": "B", "company": "B", "title": "t"},
    {"job_id": "c", "status": "applied", "fit": 60, "tier": "A", "company": "C", "title": "t"},
    {"job_id": "d", "status": "applied", "fit": 99, "tier": "C", "company": "D", "title": "t"},
    {"job_id": "e", "status": "scored", "fit": 95, "tier": "B", "company": "E", "title": "t"},
]
TIERS = {"A": {"outreach": "always"}, "B": {"outreach": "if_contact_found"}, "C": {"outreach": "never"}}


def test_outreach_targets_bar():
    out = outreach_targets(JOBS, TIERS, min_fit=80, statuses=["applied", "queued"], done=set())
    assert [j["job_id"] for j in out] == ["a", "c"]       # b below bar, d tier never, e wrong status; A ignores min_fit


def test_outreach_targets_skips_done():
    assert [j["job_id"] for j in outreach_targets(JOBS, TIERS, 80, ["applied"], done={"a"})] == ["c"]


def _root(tmp_path, jobs):
    from conftest import make_temp_root
    root = make_temp_root(tmp_path / "repo")
    for jid, company, status, fit, tier, url in jobs:
        d = root / "data" / "jobs" / jid
        d.mkdir(parents=True)
        (d / "posting.json").write_text(json.dumps({
            "job_id": jid, "company": company, "title": "SWE", "location": "NYC", "description_text": "x",
            "raw": {}, "ats": "greenhouse", "url": url}))
        (d / "status.json").write_text(json.dumps({"status": status}))
        (d / "score.json").write_text(json.dumps({"job_id": jid, "category": "swe", "fit": fit, "tier": tier,
                                                  "decision": "prepare"}))
    return root


def test_min_fit_policy_default_and_validation(example_settings):
    from careeros.config import ConfigError
    from careeros.outreach import OutreachPolicy
    assert OutreachPolicy.from_settings(example_settings).min_fit == 80
    example_settings.pipeline["outreach"] = {"min_fit": 101}
    with pytest.raises(ConfigError, match="min_fit"):
        OutreachPolicy.from_settings(example_settings)


def test_cli_targets_top_json(tmp_path, capsys):
    from careeros.cli import main
    root = _root(tmp_path, [("j1", "Acme", "applied", 90, "B", "https://x.test/1"),
                            ("j2", "Beta", "applied", 85, "B", "https://x.test/2"),
                            ("j3", "Gamma", "applied", 50, "B", "https://x.test/3")])
    (root / "data" / "jobs" / "j2" / "outreach.json").write_text("{}")
    assert main(["--root", str(root), "outreach", "targets", "--top", "3", "--json"]) == 0
    assert [j["job_id"] for j in json.loads(capsys.readouterr().out)] == ["j1"]


def test_cli_emails_fills_contacts_without_hunter_key(tmp_path, capsys):
    from careeros.cli import main
    root = _root(tmp_path, [("j1", "Quillstone", "applied", 90, "B", "https://careers.quillstone.com/1")])
    f = root / "data" / "jobs" / "j1" / "contacts.json"
    f.write_text(json.dumps({"job_id": "j1", "company": "Quillstone", "contacts": [{"name": "Sam Lee"}]}))
    assert main(["--root", str(root), "outreach", "emails", "j1"]) == 0
    out = json.loads(f.read_text())
    assert out["domain"] == "quillstone.com" and out["contacts"][0]["email_candidates"][0] == "sam.lee@quillstone.com"
    assert "no hunter key" in capsys.readouterr().out


def test_cli_emails_uses_hunter_key(tmp_path, capsys, monkeypatch):
    from careeros import email_guess
    from careeros.cli import main
    root = _root(tmp_path, [("j1", "Acme", "applied", 90, "B", "https://boards.greenhouse.io/acme/1")])
    monkeypatch.setattr("careeros.credentials.get_credential", lambda s, site: {"password": "K"})
    monkeypatch.setattr(email_guess, "_fetch", lambda url, key: json.dumps(HUNTER))
    assert main(["--root", str(root), "outreach", "emails", "j1"]) == 0   # no contacts.json yet: created
    out = json.loads((root / "data" / "jobs" / "j1" / "contacts.json").read_text())
    assert out["contacts"][0]["email"] == "rjones@acme.com" and out["email_pattern"] == "{f}{last}"
    assert "K" not in capsys.readouterr().out


def test_outreach_targets_one_per_company():
    jobs = [{"job_id": "x1", "status": "applied", "fit": 95, "tier": "B", "company": "Acme"},
            {"job_id": "x2", "status": "applied", "fit": 92, "tier": "B", "company": "Acme, Inc."},
            {"job_id": "y", "status": "applied", "fit": 90, "tier": "B", "company": "Zenith Co."}]
    assert [j["job_id"] for j in outreach_targets(jobs, TIERS, 80, ["applied"], done=set())] == ["x1", "y"]


# --- Apollo.io (optional): search finds who (0 credits), enrich gets the email (1 credit each) ---------------

APOLLO_SEARCH = {"people": [
    {"id": "p1", "first_name": "Ann", "last_name_obfuscated": "Ki***r", "title": "Engineering Manager", "has_email": True},
    {"id": "p2", "first_name": "Rita", "last_name_obfuscated": "Jo***s", "title": "Technical Recruiter", "has_email": True},
    {"id": "p3", "first_name": "Zed", "last_name_obfuscated": "Q***", "title": "Recruiter", "has_email": False},
]}
APOLLO_MATCH = {"p2": {"name": "Rita Jones", "first_name": "Rita", "last_name": "Jones", "title": "Technical Recruiter",
                       "email": "rita.jones@acme.com", "email_status": "verified",
                       "linkedin_url": "http://www.linkedin.com/in/rita", "organization": {"primary_domain": "acme.com"}},
                "p1": {"name": "Ann Kiper", "first_name": "Ann", "last_name": "Kiper", "title": "Engineering Manager",
                       "email": "ann.kiper@acme.com", "email_status": "verified", "linkedin_url": None,
                       "organization": {"website_url": "http://www.acme.com"}}}


def _apollo_fetch(calls):
    def fetch(url, headers, body):
        calls.append((url, headers, body))
        if url.endswith("/mixed_people/api_search"):
            return json.dumps(APOLLO_SEARCH)
        return json.dumps({"person": APOLLO_MATCH[json.loads(body)["id"]]})
    return fetch


def test_apollo_search_and_enrich_recruiters_first_with_email_only():
    from careeros.email_guess import apollo_contacts
    calls = []
    people = apollo_contacts("AK", "acme.com", enrich=2, fetch=_apollo_fetch(calls))
    assert [p["name"] for p in people] == ["Rita Jones", "Ann Kiper"]   # recruiter first; p3 has no email: skipped
    assert all(h == {"x-api-key": "AK", "Content-Type": "application/json"} for _, h, _ in calls)
    assert all("AK" not in u for u, _, _ in calls)
    assert len(calls) == 3                                              # 1 search (0 credits) + 2 enrich


def test_apollo_enrich_zero_is_search_only_names_partial():
    from careeros.email_guess import apollo_contacts
    calls = []
    assert apollo_contacts("AK", "acme.com", enrich=0, fetch=_apollo_fetch(calls)) == []
    assert len(calls) == 1


def test_apply_to_contacts_adds_apollo_people_before_hunter():
    apollo = [{"name": "Rita Jones", "title": "Technical Recruiter", "email": "rita.jones@acme.com",
               "linkedin_url": "http://www.linkedin.com/in/rita"},
              {"name": "Ann Kiper", "title": "Engineering Manager", "email": "ann.kiper@acme.com", "linkedin_url": None}]
    out = apply_to_contacts({"contacts": []}, "acme.com", "high", HUNTER["data"], apollo=apollo)
    rita, ann = out["contacts"]
    assert (rita["role"], rita["email"], rita["email_source"], rita["email_confidence"]) == (
        "recruiter", "rita.jones@acme.com", "apollo.io", "medium")      # Apollo email beats Hunter's rjones@ hit
    assert ann["role"] == "hiring_manager" and ann["email"] == "ann.kiper@acme.com"


def test_apollo_manual_search_url():
    from careeros.email_guess import apollo_search_url
    u = apollo_search_url("Acme Robotics", "recruiter")
    assert u.startswith("https://app.apollo.io/#/people?") and "Acme%20Robotics" in u


def test_cli_emails_apollo_refused_falls_back_to_manual_link(tmp_path, capsys, monkeypatch):
    import urllib.error

    from careeros import email_guess
    from careeros.cli import main
    root = _root(tmp_path, [("j1", "Acme", "applied", 90, "B", "https://careers.acme.com/1")])
    monkeypatch.setattr("careeros.credentials.get_credential",
                        lambda s, site: {"password": "AK"} if site == "apollo" else (_ for _ in ()).throw(KeyError(site)))

    def refuse(url, headers, body):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(email_guess, "_http", refuse)
    assert main(["--root", str(root), "outreach", "emails", "j1"]) == 0
    out = json.loads((root / "data" / "jobs" / "j1" / "contacts.json").read_text())
    assert out["search_urls"]["apollo_recruiter"].startswith("https://app.apollo.io/")
    printed = capsys.readouterr().out
    assert "apollo.io: refused (403)" in printed and "AK" not in printed
    assert "apollo search" in (root / "data" / "jobs" / "j1" / "log.md").read_text()   # credits logged


def test_verified_email_is_never_replaced_by_a_provider_hit():
    data = {"contacts": [{"name": "Rita Jones", "email": "rita@acme.com", "email_confidence": "verified"}]}
    c = apply_to_contacts(data, "acme.com", "high", HUNTER["data"])["contacts"][0]
    assert (c["email"], c["email_confidence"]) == ("rita@acme.com", "verified")


def test_rerun_without_provider_keeps_paid_emails():
    first = apply_to_contacts({"contacts": [{"name": "Rita Jones"}]}, "acme.com", "high", HUNTER["data"])
    again = apply_to_contacts(first, "acme.com", "high", None)        # quota gone / --no-hunter
    c = again["contacts"][0]
    assert (c["email"], c["email_source"], c["email_confidence"]) == ("rjones@acme.com", "hunter.io", "medium")
    assert again["email_pattern"] == "{f}{last}"


def test_cli_emails_skips_apollo_on_guessed_domain(tmp_path, capsys, monkeypatch):
    from careeros import email_guess
    from careeros.cli import main
    root = _root(tmp_path, [("j1", "Acme", "applied", 90, "B", "https://boards.greenhouse.io/acme/1")])
    monkeypatch.setattr("careeros.credentials.get_credential",
                        lambda s, site: {"password": "AK"} if site == "apollo" else (_ for _ in ()).throw(KeyError(site)))
    monkeypatch.setattr(email_guess, "_http", lambda *a: pytest.fail("Apollo called on a guessed domain"))
    assert main(["--root", str(root), "outreach", "emails", "j1"]) == 0
    assert "--domain" in capsys.readouterr().out


def test_rerun_keeps_manually_pasted_email():
    data = {"contacts": [{"name": "Rita Jones", "email": "rita.j@acme.com", "email_confidence": "medium",
                          "source": "apollo.io (manual)"}]}
    c = apply_to_contacts(data, "acme.com", "high", None)["contacts"][0]
    assert (c["email"], c["email_confidence"]) == ("rita.j@acme.com", "medium")
    assert c["email_candidates"][0] == "rita.j@acme.com"


def test_apollo_drops_people_now_at_another_company():
    from careeros.email_guess import apollo_contacts
    moved = dict(APOLLO_MATCH)
    moved["p2"] = {**APOLLO_MATCH["p2"], "organization": {"primary_domain": "othercorp.com"}}
    moved["p1"] = {**APOLLO_MATCH["p1"], "organization": {"primary_domain": "acme.com"}}

    def fetch(url, headers, body):
        if url.endswith("/mixed_people/api_search"):
            return json.dumps(APOLLO_SEARCH)
        return json.dumps({"person": moved[json.loads(body)["id"]]})
    assert [p["name"] for p in apollo_contacts("AK", "acme.com", enrich=2, fetch=fetch)] == ["Ann Kiper"]


def test_cli_emails_asks_hunter_by_researched_domain(tmp_path, monkeypatch):
    """A researched medium domain is sent to Hunter as `domain=`, never a company-name search that can return a
    namesake's domain (Hammock -> hammock.com)."""
    from careeros import email_guess
    from careeros.cli import main
    root = _root(tmp_path, [("j1", "Hammock", "applied", 90, "B", "https://jobs.ashbyhq.com/hammock/1")])
    (root / "data" / "jobs" / "j1" / "contacts.json").write_text(json.dumps(
        {"job_id": "j1", "company": "Hammock", "domain": "shophammock.com", "domain_confidence": "medium",
         "contacts": []}))
    urls = []
    monkeypatch.setattr("careeros.credentials.get_credential", lambda s, site: {"password": "K"})
    monkeypatch.setattr(email_guess, "_fetch", lambda url, key: urls.append(url) or json.dumps({"data": None}))
    assert main(["--root", str(root), "outreach", "emails", "j1", "--no-apollo"]) == 0
    assert len(urls) == 1 and "domain=shophammock.com" in urls[0] and "company=" not in urls[0]


def test_learned_patterns_order_guesses_and_drop_failed_ones(tmp_path):
    """User 2026-11-19: learn from every bounce and delivery; reuse the format that worked for the next person."""
    from careeros.email_guess import learned_pattern, pattern_of, record_email_result
    f = tmp_path / "email_patterns.json"
    assert pattern_of("jane.doe@acme.com", "Jane Doe") == "{first}.{last}"
    assert pattern_of("founders@acme.com", "Founders") is None
    assert pattern_of("recruiting@acme.com", "Acme recruiting") is None  # a team inbox teaches nothing about people
    assert pattern_of("chris.hartley@acme.com", "Chris Hartley") == "{first}.{last}"
    record_email_result(f, "jane.doe@acme.com", "Jane Doe", ok=False)
    record_email_result(f, "jdoe@acme.com", "Jane Doe", ok=True)
    assert learned_pattern(f, "acme.com") == {"works": "{f}{last}", "failed": ["{first}.{last}"]}
    out = apply_to_contacts({"contacts": [{"name": "Sam Lee"}]}, "acme.com", "high", None,
                            learned=learned_pattern(f, "acme.com"))
    cands = out["contacts"][0]["email_candidates"]
    assert cands[0] == "slee@acme.com" and "sam.lee@acme.com" not in cands
    # a bounce can land minutes after a send was recorded as delivered: the bounce wins
    record_email_result(f, "jdoe@acme.com", "Jane Doe", ok=False)
    assert learned_pattern(f, "acme.com") == {"works": None, "failed": ["{first}.{last}", "{f}{last}"]}
