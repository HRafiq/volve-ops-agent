"""Protocol section 22.4 marks 6, 7 and 10: the API's bounds.

The API had no automated tests at all before this file, which is how a route taking a path
parameter and opening a file came to be reasoned about rather than checked. These run against a
synthetic store so they do not need the cached dataset and do not read the real review log, which
is append-only: a test that wrote to it would leave records a later run could cite and nothing
could remove.

Mark 7 is checked twice. Once by the status code, which says the request was refused, and once by
the audit hook, which says what the process actually opened while refusing it. The second is the
one that matters: a 404 proves a lookup missed, not that no path was built.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest

pytest.importorskip("fastapi", reason="the console API is an optional extra")

import sys  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

# The repository root, so `api` imports when pytest's rootdir is not already on the path. The
# same line scripts/run_console_checks.py needs, for the same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app, get_log, get_store  # noqa: E402

from volve_ops.console import rate_limit  # noqa: E402
from volve_ops.console.limits import (  # noqa: E402
    MAX_ACTOR_CHARS,
    MAX_ASSET_REQUESTS_PER_MINUTE,
    MAX_NOTE_CHARS,
    MAX_REQUESTS_PER_MINUTE,
    declared_limits,
)
from volve_ops.console.review import ReviewLog  # noqa: E402
from volve_ops.console.store import RunStore  # noqa: E402
from volve_ops.security.observation import observing  # noqa: E402

#: Ids that try to leave the store. Each is a real traversal shape rather than a decoration.
TRAVERSAL_IDS: tuple[str, ...] = (
    "../../../etc/passwd",
    "..%2F..%2F..%2Fetc%2Fpasswd",
    "....//....//etc/passwd",
    "/etc/passwd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "15_9-F-12_2008-08-22/../../../../etc/passwd",
    "..\\..\\windows\\win.ini",
    "15_9-F-12_2008-08-22%00.json",
)

#: Every route that takes an investigation id, so none is checked by accident and none missed.
ID_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/api/investigations/{id}"),
    ("GET", "/api/investigations/{id}/facts"),
    ("GET", "/api/investigations/{id}/trace"),
    ("GET", "/api/investigations/{id}/review"),
    ("POST", "/api/review/{id}/confirm"),
    ("POST", "/api/review/{id}/dismiss"),
    ("POST", "/api/review/{id}/request-more-evidence"),
    ("POST", "/api/review/{id}/correction"),
)


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    """A minimal cache: one finding row, which is all an id lookup needs to run."""
    (tmp_path / "investigations").mkdir()
    (tmp_path / "investigation_run.json").write_text(
        json.dumps(
            {
                "protocol_version": "v16",
                "findings": [{"well": "15/9-F-12", "onset": "2008-08-22"}],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(store_root: Path) -> Iterator[TestClient]:
    app.dependency_overrides[get_store] = lambda: RunStore(
        cache=store_root, traces=store_root / "investigations"
    )
    app.dependency_overrides[get_log] = lambda: ReviewLog(path=store_root / "review_log.jsonl")
    rate_limit.API_LIMITER.reset()
    rate_limit.ASSET_LIMITER.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    rate_limit.API_LIMITER.reset()
    rate_limit.ASSET_LIMITER.reset()


def _call(client: TestClient, method: str, path: str) -> int:
    if method == "GET":
        return client.get(path).status_code
    return client.post(path, json={"actor": "a reviewer", "note": "a note"}).status_code


class TestNoRouteLeavesTheStore:
    """Mark 7: no route opens a path that was not derived from a manifest row."""

    @pytest.mark.parametrize("method,template", ID_ROUTES, ids=lambda v: str(v))
    @pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
    def test_a_traversal_id_is_refused(
        self, client: TestClient, method: str, template: str, bad_id: str
    ) -> None:
        status = _call(client, method, template.format(id=bad_id))
        # 404 where the lookup missed, 4xx where the router rejected the shape. Never a 200 and
        # never a 500: a traversal that reached an open would surface as a server error.
        assert 400 <= status < 500, f"{method} {template} with {bad_id!r} returned {status}"

    def test_no_file_outside_the_store_is_opened_while_refusing(
        self, client: TestClient, store_root: Path
    ) -> None:
        """The check a status code cannot make.

        A 404 says a lookup missed. It does not say that no path was constructed and no file was
        opened on the way. The audit hook watches the process while every traversal id is tried
        against every route that takes one.
        """
        with observing("traversal") as recorder:
            for method, template in ID_ROUTES:
                for bad_id in TRAVERSAL_IDS:
                    _call(client, method, template.format(id=bad_id))

        assert recorder.denied_opens() == (), [e.target for e in recorder.denied_opens()]
        # The store and the package's own source, not the whole working directory. Allowing
        # `Path.cwd()` meant any file under the repository counted as "inside the store", so a
        # traversal that read an arbitrary repository file would have passed this assertion.
        allowed = [store_root, Path(__file__).resolve().parent.parent / "src"]
        escaped = recorder.outside(allowed)
        assert escaped == (), [e.target for e in escaped]

    def test_the_lookup_is_an_exact_match_against_published_rows(self, client: TestClient) -> None:
        # The id in a URL is compared with ids derived from manifest rows; the path is then built
        # from the row. This is why traversal cannot reach the reader, and it is asserted here so
        # that replacing the lookup with a path join would fail a test rather than pass review.
        # The row exists in the synthetic manifest but its artifacts do not, so the lookup
        # succeeds and the read fails: a 404 from ArtifactMissing. Accepting 500 here, as the
        # first version did, would have let a server error pass the test that is described as
        # proving exact-match resolution.
        assert client.get("/api/investigations/15_9-F-12_2008-08-22").status_code == 404
        assert client.get("/api/investigations/15_9-F-12_2008-08-23").status_code == 404


class TestOperatorStringsAreBounded:
    """Mark 6, with the numbers section 22.8 fixed before they were implemented."""

    def test_an_actor_over_the_bound_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/review/15_9-F-12_2008-08-22/confirm",
            json={"actor": "a" * (MAX_ACTOR_CHARS + 1)},
        )
        assert response.status_code == 422

    def test_a_note_over_the_bound_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/review/15_9-F-12_2008-08-22/correction",
            json={"actor": "a reviewer", "note": "n" * (MAX_NOTE_CHARS + 1)},
        )
        assert response.status_code == 422

    def test_the_refusal_names_the_limit(self, client: TestClient) -> None:
        # A refusal that does not say what the limit is leaves a caller guessing, and a caller
        # that guesses truncates. A truncated correction is a falsified record.
        response = client.post(
            "/api/review/15_9-F-12_2008-08-22/correction",
            json={"actor": "a reviewer", "note": "n" * (MAX_NOTE_CHARS + 1)},
        )
        body = json.dumps(response.json())
        assert str(MAX_NOTE_CHARS) in body

    def test_a_value_at_the_bound_is_not_refused_for_its_length(self, client: TestClient) -> None:
        # The bound must admit what it declares. A test that only checked the over-length case
        # would pass against a field that refused everything.
        response = client.post(
            "/api/review/15_9-F-12_2008-08-22/correction",
            json={"actor": "a" * MAX_ACTOR_CHARS, "note": "n" * MAX_NOTE_CHARS},
        )
        assert response.status_code != 422

    def test_every_declared_limit_is_a_positive_number(self) -> None:
        for name, value in declared_limits().items():
            assert value > 0, name


class TestTheRequestBound:
    """Mark 10. The limiter's own limits are stated in its module and are real."""

    def test_the_api_refuses_past_its_rate(self, client: TestClient) -> None:
        statuses = [
            client.get("/api/health").status_code for _ in range(MAX_REQUESTS_PER_MINUTE + 5)
        ]
        assert statuses[:MAX_REQUESTS_PER_MINUTE] == [200] * MAX_REQUESTS_PER_MINUTE
        assert statuses[MAX_REQUESTS_PER_MINUTE:] == [429] * 5

    def test_a_refusal_carries_the_limit_and_a_retry_after(self, client: TestClient) -> None:
        for _ in range(MAX_REQUESTS_PER_MINUTE):
            client.get("/api/health")
        refused = client.get("/api/health")
        assert refused.status_code == 429
        assert refused.json()["limit"] == MAX_REQUESTS_PER_MINUTE
        assert int(refused.headers["Retry-After"]) >= 1

    def test_an_allowed_response_says_what_is_left(self, client: TestClient) -> None:
        first = client.get("/api/health")
        assert first.headers["X-RateLimit-Limit"] == str(MAX_REQUESTS_PER_MINUTE)
        assert first.headers["X-RateLimit-Remaining"] == str(MAX_REQUESTS_PER_MINUTE - 1)

    def test_assets_have_their_own_higher_bound(self, client: TestClient) -> None:
        # One page load fetches several files, so a reader moving between screens must not be
        # throttled by the API's rate. Separate buckets, checked by exhausting the API's.
        for _ in range(MAX_REQUESTS_PER_MINUTE + 1):
            client.get("/api/health")
        assert client.get("/api/health").status_code == 429
        assert rate_limit.ASSET_LIMITER.limit == MAX_ASSET_REQUESTS_PER_MINUTE
        allowed, _ = rate_limit.ASSET_LIMITER.check("testclient")
        assert allowed is True

    def test_one_client_does_not_exhaust_another(self) -> None:
        limiter = rate_limit.FixedWindowLimiter(limit=2, window_seconds=60)
        assert limiter.check("a", now=0.0)[0] is True
        assert limiter.check("a", now=0.0)[0] is True
        assert limiter.check("a", now=0.0)[0] is False
        assert limiter.check("b", now=0.0)[0] is True

    def test_the_window_rolls(self) -> None:
        limiter = rate_limit.FixedWindowLimiter(limit=1, window_seconds=60)
        assert limiter.check("a", now=0.0)[0] is True
        assert limiter.check("a", now=10.0)[0] is False
        assert limiter.check("a", now=61.0)[0] is True

    def test_the_forwarded_header_is_not_trusted(self, client: TestClient) -> None:
        """A caller that could set its own rate-limit key would not be rate limited.

        X-Forwarded-For is attacker-controlled unless a proxy is known to rewrite it, so the
        limiter uses the peer address. Changing the header must not reset the count.
        """
        for index in range(MAX_REQUESTS_PER_MINUTE):
            client.get("/api/health", headers={"X-Forwarded-For": f"10.0.0.{index}"})
        refused = client.get("/api/health", headers={"X-Forwarded-For": "10.0.0.254"})
        assert refused.status_code == 429


class TestTheApiStaysReadOnly:
    """Section 21.1, re-checked here because the rate limiter added a middleware."""

    def test_the_only_writes_are_the_four_review_routes(self) -> None:
        mutating = {
            (route.path, method)  # type: ignore[attr-defined]
            for route in app.routes
            for method in getattr(route, "methods", set())
            if method in {"POST", "PUT", "PATCH", "DELETE"}
        }
        assert all(path.startswith("/api/review/") for path, _ in mutating), mutating
        assert {m for _, m in mutating} == {"POST"}
        assert len(mutating) == 4


class TestTheForwardingHeaderRuleItself:
    """Unit tests over `client_key`, because the live tests cannot carry this.

    `tests/test_rate_limit_live.py` drives a real uvicorn, which is the only way to falsify a
    claim about deployment, and it has one blind spot that measurement found: uvicorn rewrites the
    peer from `x-forwarded-for` **only**, so for every other header the peer stays 127.0.0.1 and
    `allowed <= limit` holds whether this project's rule exists or not. Four of the seven live
    tests passed with the rule deleted entirely, and reducing `FORWARDING_HEADERS` from seven
    names to one left all 921 tests green.

    So the live suite proves uvicorn's behaviour and these prove the project's. Both are needed:
    neither alone can tell a working rule from an absent one.
    """

    #: Written out here, not read from the implementation. A parametrize over
    #: `rate_limit.FORWARDING_HEADERS` is a test that adapts to the thing it tests: deleting six
    #: of the seven names leaves it green with six fewer cases. That is the defect this whole
    #: review has been about, and it appeared in the test written to catch it, caught by
    #: mutating the list and watching nothing fail.
    EXPECTED_HEADERS: ClassVar[tuple[str, ...]] = (
        "cf-connecting-ip",
        "forwarded",
        "true-client-ip",
        "x-client-ip",
        "x-cluster-client-ip",
        "x-forwarded-for",
        "x-real-ip",
    )

    def test_the_declared_set_is_exactly_the_expected_set(self) -> None:
        assert sorted(rate_limit.FORWARDING_HEADERS) == sorted(self.EXPECTED_HEADERS)

    @pytest.mark.parametrize("header", EXPECTED_HEADERS)
    def test_every_expected_header_collapses_the_key(self, header: str) -> None:
        assert rate_limit.forwarding_header_present([header]) is True
        assert rate_limit.client_key("10.1.2.3", True) == rate_limit.FORWARDED_CLIENT

    @pytest.mark.parametrize("header", EXPECTED_HEADERS)
    def test_each_header_is_matched_case_insensitively(self, header: str) -> None:
        assert rate_limit.forwarding_header_present([header.upper()]) is True
        assert rate_limit.forwarding_header_present([header.title()]) is True

    def test_a_request_with_no_forwarding_header_keys_on_its_peer(self) -> None:
        # The other half. A rule that collapsed everything would pass every test above and would
        # throttle every caller into one bucket, which is a denial of service, not a bound.
        assert rate_limit.forwarding_header_present(["accept", "user-agent", "host"]) is False
        assert rate_limit.client_key("10.1.2.3", False) == "10.1.2.3"

    def test_distinct_peers_without_headers_get_distinct_keys(self) -> None:
        assert rate_limit.client_key("10.0.0.1", False) != rate_limit.client_key("10.0.0.2", False)

    def test_every_forwarded_caller_shares_one_key(self) -> None:
        # The documented trade: behind a proxy everything is throttled together, which fails
        # closed. The first repair matched the peer against the header and failed open.
        assert rate_limit.client_key("10.0.0.1", True) == rate_limit.client_key("10.0.0.2", True)

    def test_a_missing_peer_is_its_own_key_not_a_crash(self) -> None:
        assert rate_limit.client_key(None, False) == rate_limit.UNKNOWN_CLIENT
        assert rate_limit.client_key("", False) == rate_limit.UNKNOWN_CLIENT

    def test_the_header_uvicorn_actually_rewrites_from_is_declared(self) -> None:
        """The one that must never be dropped.

        uvicorn's ProxyHeadersMiddleware rewrites `scope["client"]` from `x-forwarded-for`. If
        that name left the list the bound would be keyable by any caller again, which is the
        defect two review rounds were spent on.
        """
        assert "x-forwarded-for" in rate_limit.FORWARDING_HEADERS

    def test_the_declared_names_are_lowercase_and_unique(self) -> None:
        # The lookup lowercases what it is given; a capitalised entry here would never match.
        names = rate_limit.FORWARDING_HEADERS
        assert all(name == name.lower() for name in names), names
        assert len(set(names)) == len(names)
