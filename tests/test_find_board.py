from careeros.scout import find_board as fb
from careeros.scout.base import BoardNotFound


def test_slug_candidates_drop_suffixes_and_punctuation():
    assert fb.slug_candidates("Snap Inc.") == ["snap", "snapinc", "snap-inc"]
    assert fb.slug_candidates("Wealth.com") == ["wealthcom", "wealth-com", "wealth"]
    assert fb.slug_candidates("Brain Co.") == ["brain", "brainco", "brain-co"]
    assert fb.slug_candidates("Plaid") == ["plaid"]
    # never a first-word-only guess for multi-word names
    assert "clear" not in fb.slug_candidates("Clear Street")


def test_find_board_first_nonempty_hit(monkeypatch):
    def fake(url, params=None, retries=1):
        if "greenhouse" in url:
            raise BoardNotFound(url)
        if "ashbyhq" in url and url.endswith("/ramp"):
            return {"jobs": [{"id": 1}]}
        if "lever" in url:
            return []
        raise BoardNotFound(url)

    monkeypatch.setattr(fb, "get_json", fake)
    assert fb.find_board("Ramp") == {"company": "Ramp", "ats": "ashby", "slug": "ramp", "jobs": 1}


def test_find_board_none_when_empty_or_missing(monkeypatch):
    monkeypatch.setattr(fb, "get_json", lambda url, params=None, retries=1: {"jobs": []} if "greenhouse" in url else [])
    assert fb.find_board("Nobody") is None


def test_find_board_skips_fetch_errors(monkeypatch):
    from careeros.scout.base import FetchError

    def fake(url, params=None, retries=1):
        if "lever" in url:
            return [{"id": "x"}, {"id": "y"}]
        raise FetchError(url)

    monkeypatch.setattr(fb, "get_json", fake)
    assert fb.find_board("Plaid") == {"company": "Plaid", "ats": "lever", "slug": "plaid", "jobs": 2}
