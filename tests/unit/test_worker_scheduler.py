import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.update(APP_DB=":memory:", MEMORY_DB=":memory:", MODEL_PROFILE="offline", GIGSIM_INPROCESS="1", GIGSIM_ERROR_RATE="0")

from apps.api import db  # noqa: E402
from apps.api.auth import users  # noqa: E402
from worker import scheduler  # noqa: E402


class FakeRunner:
    def __init__(self):
        self.scans = []

    async def scan(self, u):
        self.scans.append(u["id"])
        return ["t1", "t2"]


async def test_scheduler_respects_interval_and_never_scans_more_often_than_hourly():
    db.reset_for_tests()
    u = users.create_user("w@example.com", "password-123", "data_analyst")
    s = dict(users.DEFAULT_SETTINGS, saved_searches=[dict(name="x", query="", interval_minutes=5)])   # user asks for 5 min
    users.save_settings(u["id"], s)
    r, last = FakeRunner(), {}
    assert await scheduler.scan_due(r, last, now=1_000_000.0) == 2          # first tick scans
    assert await scheduler.scan_due(r, last, now=1_000_000.0 + 600) == 0    # 10 min later: still too soon (floor is 60 min)
    assert await scheduler.scan_due(r, last, now=1_000_000.0 + 3700) == 2   # > 60 min: scans again
    assert r.scans == [u["id"], u["id"]]
