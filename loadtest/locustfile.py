"""OVID load-test harness (INFRA-03 / D-11) — p95 gate against the honest stack.

Proves API **p95 ≤ 500ms** against the real Redis-backed, multi-worker
``gunicorn -w 4`` + Postgres configuration (Plans 03-01..03-03), NOT the
retiring single-worker ``memory://`` config (D-14). The gate is native: an
``events.quitting`` listener reads the aggregate 0.95 response-time percentile
and sets ``environment.process_exit_code`` — no custom CSV parser (03-RESEARCH
"Don't Hand-Roll").

Workload mix (D-13):
  * ~70%  GET  /v1/disc/{fp}   — lookups against seeded ``dvd1-seed-{i}`` rows
  * ~20%  GET  /v1/search?q=Seed — search on the shared seed title token
  * ~10%  POST /v1/disc         — authenticated novel-fingerprint submissions

Read-limit handling (CR-01): ~90% of this workload is unauthenticated/
authenticated GET reads generated from one load-generator host, which would
trip the default read-tier limits (``UNAUTH_LIMIT`` 100/min, ``AUTH_LIMIT``
500/min) long before p95 could be measured. The load-test CI stack raises
those tiers via ``OVID_UNAUTH_LIMIT``/``OVID_AUTH_LIMIT`` (see
``.github/workflows/loadtest.yml``) so read traffic isn't throttled and p95
reflects real handler latency — only the write ceiling (``AUTH_WRITE_LIMIT``,
see below) remains active, by design.

Dataset coupling: ``api/scripts/seed.py --count N`` seeds discs with
fingerprints ``dvd1-seed-{0..N-1}`` and titles ``Seed Movie {i}``. This file
reproduces that scheme via ``BULK_FINGERPRINT_PREFIX`` / ``SEARCH_TOKEN`` so
lookups hit real rows and search returns real results. Set
``OVID_LOADTEST_SEED_COUNT`` to the seeded N so lookups stay in-range.

Write-cap handling (Plan 02 ``AUTH_WRITE_LIMIT`` = 20/min per account,
T-03-10 / D-11): under sustained load a single shared submit token WILL trip
the per-account write ceiling. Those 429s are an *expected throttle*, not a
service failure, so the submit task uses ``catch_response`` to mark a 429 as a
success — it is never counted in ``fail_ratio``. Each POST uses a novel unique
fingerprint (``dvd1-load-{uuid}``) so it is a genuine new-disc write, never a
duplicate no-op. (Alternative approaches — spreading across multiple seeded
tokens, or keeping submit volume under the cap — are equally valid; the 429-as-
non-failure marking is the simplest and is what is implemented here.)

Auth: the submit token is minted at runtime by the CI job (the app's JWT
issuer, ``api/app/auth/jwt.create_access_token``, for a seeded contributor) and
passed in via ``OVID_LOADTEST_TOKEN`` — never committed. This mirrors
``ovid-client``'s ``Authorization: Bearer <token>`` scheme (client.py). If the
env var is unset the submit task is skipped (so a token is never required just
to smoke the read paths locally).

Headless run (its exit code gates the run; results_stats.csv is the artifact):

    locust -f loadtest/locustfile.py --headless -u 100 -r 10 -t 3m \
        --host http://localhost:8000 --csv loadtest/results
"""

import logging
import os
import random
import uuid

from locust import HttpUser, between, events, task

# --- Budgets (INFRA-03) ---------------------------------------------------
P95_BUDGET_MS = 500
ERROR_RATIO_BUDGET = 0.01  # 1%
# Minimum request count for the run to be considered meaningful (WR-03). Below
# this, p95/fail_ratio are statistically meaningless (or undefined on zero
# requests) and must not be allowed to report a silent PASS.
MIN_EXPECTED_REQUESTS = int(os.environ.get("OVID_LOADTEST_MIN_REQUESTS", "100"))

# --- Dataset coupling (must match api/scripts/seed.py) --------------------
BULK_FINGERPRINT_PREFIX = "dvd1-seed-"
SEARCH_TOKEN = "Seed"

_SEED_COUNT = int(os.environ.get("OVID_LOADTEST_SEED_COUNT", "3000"))
_TOKEN = os.environ.get("OVID_LOADTEST_TOKEN")


def _submit_payload() -> dict:
    """A schema-valid POST /v1/disc body with a novel unique fingerprint.

    A fresh ``dvd1-load-{uuid}`` fingerprint makes every submission a genuine
    new-disc write (never a duplicate no-op), exercising the real write path.
    """
    token = uuid.uuid4().hex[:12]
    fp = f"dvd1-load-{token}"
    return {
        "fingerprint": fp,
        "format": "DVD",
        "region_code": "1",
        "release": {
            "title": f"Load Test {token}",
            "year": 2024,
            "content_type": "movie",
            "original_language": "en",
        },
        "titles": [
            {
                "title_index": 1,
                "title_type": "main_feature",
                "duration_secs": 6000,
                "chapter_count": 12,
                "is_main_feature": True,
                "display_name": "Load Test Main Feature",
                "audio_tracks": [
                    {
                        "track_index": 0,
                        "language_code": "en",
                        "codec": "ac3",
                        "channels": 6,
                        "is_default": True,
                    }
                ],
                "subtitle_tracks": [
                    {
                        "track_index": 0,
                        "language_code": "en",
                        "codec": "vobsub",
                        "is_default": False,
                    }
                ],
            }
        ],
    }


class OvidUser(HttpUser):
    """Simulated OVID API consumer running the D-13 70/20/10 workload mix."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self._auth = {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}
        if not _TOKEN:
            logging.warning(
                "OVID_LOADTEST_TOKEN unset — POST /v1/disc submit task will be "
                "skipped (read paths still exercised)."
            )

    @task(70)
    def lookup(self) -> None:
        i = random.randrange(_SEED_COUNT)
        # Stable aggregation name so per-fingerprint URLs collapse into one row.
        self.client.get(
            f"/v1/disc/{BULK_FINGERPRINT_PREFIX}{i}", name="/v1/disc/[fp]"
        )

    @task(20)
    def search(self) -> None:
        self.client.get(f"/v1/search?q={SEARCH_TOKEN}", name="/v1/search")

    @task(10)
    def submit(self) -> None:
        if not _TOKEN:
            return
        with self.client.post(
            "/v1/disc",
            json=_submit_payload(),
            headers=self._auth,
            name="/v1/disc[POST]",
            catch_response=True,
        ) as resp:
            # Plan 02 write cap → 429 is an expected throttle, not a failure.
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code in (200, 201):
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code}")


@events.quitting.add_listener
def _p95_gate(environment, **_kwargs) -> None:
    """Native exit-code gate: fail the run on too little traffic, p95 > 500ms,
    or error ratio > 1%."""
    stats = environment.stats.total

    if stats.num_requests < MIN_EXPECTED_REQUESTS:
        logging.error(
            "LOAD TEST FAIL: only %d requests recorded (< %d expected) — harness generated no meaningful load",
            stats.num_requests, MIN_EXPECTED_REQUESTS,
        )
        environment.process_exit_code = 1
        return

    p95 = stats.get_response_time_percentile(0.95)
    fail_pct = stats.fail_ratio * 100

    if stats.fail_ratio > ERROR_RATIO_BUDGET:
        logging.error(
            "LOAD TEST FAIL: error ratio %.2f%% > %.2f%% budget",
            fail_pct,
            ERROR_RATIO_BUDGET * 100,
        )
        environment.process_exit_code = 1
    elif p95 > P95_BUDGET_MS:
        logging.error("LOAD TEST FAIL: p95 %dms > %dms budget", p95, P95_BUDGET_MS)
        environment.process_exit_code = 1
    else:
        logging.info(
            "LOAD TEST PASS: p95 %dms <= %dms budget, error ratio %.2f%%",
            p95,
            P95_BUDGET_MS,
            fail_pct,
        )
        environment.process_exit_code = 0
