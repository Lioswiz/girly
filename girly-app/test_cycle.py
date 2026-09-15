"""Python port of cycle_test.go — run with `python -m unittest test_cycle.py`."""

import tempfile
import unittest
from datetime import date, timedelta

from auth import hash_password, random_token
from cycle import DATE_FMT, build_calendar, compute_cycle, parse_date
from store import Store, day_log


def mk_user(period_len, starts_ago):
    """A user with period history relative to today, so tests stay
    deterministic regardless of when they run."""
    now = date.today()
    return {
        "period_length": period_len,
        "period_starts": [
            (now - timedelta(days=ago)).strftime(DATE_FMT) for ago in starts_ago
        ],
        "logs": [],
    }


class ComputeCycleTests(unittest.TestCase):
    # Default: no logged starts → no data, fallback cycle length 28.
    def test_default_cycle_length(self):
        summary = compute_cycle(mk_user(5, []))
        self.assertFalse(summary["has_data"])
        self.assertEqual(summary["cycle_length"], 28)
        self.assertEqual(summary["avg_cycle_length"], 28)
        self.assertEqual(summary["phase"], "learn")

    # Personal cycle length is learned from the average gap between starts.
    def test_learned_average(self):
        # gaps of 30 and 30 → learned 30
        summary = compute_cycle(mk_user(5, [50, 20]))
        self.assertEqual(summary["avg_cycle_length"], 30)
        self.assertEqual(summary["cycle_length"], 30)

    # Outlier gaps (re-logs, flukes outside 15–60 days) are ignored.
    def test_outlier_filtering(self):
        # starts 63, 35, 30, 0 days ago → gaps: 28, 5 (re-log → ignored), 30
        # → average of 28 and 30 = 29
        summary = compute_cycle(mk_user(5, [63, 35, 30, 0]))
        self.assertEqual(summary["avg_cycle_length"], 29)

    # Learned lengths are clamped to a medically plausible 21–45 day range.
    def test_clamping(self):
        long = compute_cycle(mk_user(5, [110, 50]))  # gap of 60 → clamped to 45
        self.assertEqual(long["avg_cycle_length"], 45)
        # gaps of 18 and 20 → average 19 → clamped up to 21
        short = compute_cycle(mk_user(5, [38, 20, 0]))
        self.assertEqual(short["avg_cycle_length"], 21)

    # Ovulation anchors 14 days before the projected next period; the fertile
    # window spans ovulation −5 … +1, all on the personal (learned) length.
    def test_ovulation_anchoring(self):
        summary = compute_cycle(mk_user(5, [50, 20]))  # learned 30-day cycle
        self.assertTrue(summary["has_data"])
        next_start = parse_date(summary["next_period_date"])
        ovu = parse_date(summary["ovulation_date"])
        fert_start = parse_date(summary["fertile_start"])
        fert_end = parse_date(summary["fertile_end"])

        self.assertEqual((next_start - ovu).days, 14)
        self.assertEqual((ovu - fert_start).days, 5)
        self.assertEqual((fert_end - ovu).days, 1)

    # Cycle day is 1-based: the start day itself is Day 1.
    def test_cycle_day_one_based(self):
        summary = compute_cycle(mk_user(5, [30, 0]))  # last start = today
        self.assertEqual(summary["cycle_day"], 1)
        self.assertEqual(summary["phase"], "menstrual")

        nxt = compute_cycle(mk_user(5, [1]))  # yesterday → day 2 of default 28
        self.assertEqual(nxt["cycle_day"], 2)

    # The prediction window spans ±2 days around the projected start.
    def test_prediction_window(self):
        summary = compute_cycle(mk_user(5, [28]))
        self.assertEqual(summary["prediction_window"], 2)


class CalendarTests(unittest.TestCase):
    # Calendar classification must stay correct across month boundaries with a
    # learned (non-28) cycle length — the case the original progress log had
    # pending verification.
    #
    # Setup (relative to today): starts 40 and 10 days ago → learned 30-day
    # cycle, last start 10 days ago. Next period lands 20 days out; depending
    # on today's date it may fall in this month or the next, so every
    # assertion is computed from the projected dates rather than hardcoded.
    def test_calendar_across_months_with_learned_length(self):
        user = mk_user(5, [40, 10])  # learned 30-day cycle
        summary = compute_cycle(user)
        self.assertEqual(summary["avg_cycle_length"], 30)

        last_start = parse_date(user["period_starts"][-1])
        next_start = parse_date(summary["next_period_date"])
        ovu = parse_date(summary["ovulation_date"])

        def calendar_for(month):
            by_date = {}
            for d in build_calendar(user, summary, month):
                if d["date"]:
                    by_date[d["date"]] = d
            return by_date

        this_month = calendar_for(date.today())
        next_month = calendar_for(
            (date.today().replace(day=28) + timedelta(days=4)).replace(day=1)
        )

        # The logged start is always logged_period, never overwritten by a
        # prediction.
        st = this_month.get(last_start.strftime(DATE_FMT))
        self.assertIsNotNone(st)
        self.assertEqual(st["kind"], "logged_period")

        # Ovulation day must be classified as such.
        st = this_month.get(ovu.strftime(DATE_FMT))
        self.assertIsNotNone(st)
        self.assertEqual(st["kind"], "ovulation")

        # The projected next start (and its ±2 window) must be predicted,
        # whichever month it lands in.
        def check_predicted(day, label):
            key = day.strftime(DATE_FMT)
            st = this_month.get(key) or next_month.get(key)
            if st is None:
                # further out — build the calendar of the month it lands in
                st = calendar_for(day.replace(day=1)).get(key)
            self.assertIsNotNone(st, f"{label} {key} missing from the calendars")
            self.assertEqual(st["kind"], "predicted", f"{label} {key}")

        check_predicted(next_start, "projected start")
        for off in (-2, -1, 1, 2):
            check_predicted(next_start + timedelta(days=off), "window day")

        # The following cycle's projected start (last start + 60) must be
        # predicted in the month it lands in.
        check_predicted(last_start + timedelta(days=60), "following projected start")


class StoreTests(unittest.TestCase):
    # Logged days keep their own flow history; predictions never overwrite them.
    def test_upsert_log_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.load(tmp + "/girly.json")
            salt = random_token(16)
            user = {
                "name": "T",
                "email": "t@t.io",
                "salt": salt,
                "password_hash": hash_password("pw", salt),
                "period_length": 5,
            }
            store.add_user(user)

            store.upsert_log(user["id"], day_log("2026-01-05", "medium", moods=["Tired"]))
            store.upsert_log(user["id"], day_log("2026-01-05", symptoms=["Cramps"]))

            got = store.user_by_id(user["id"])
            self.assertIsNotNone(got, "user vanished")
            log = got["logs"][0]
            self.assertEqual(log.get("flow"), "medium")
            self.assertEqual(len(log.get("moods", [])), 1)
            self.assertEqual(len(log.get("symptoms", [])), 1)
            self.assertEqual(len(got["logs"]), 1)


if __name__ == "__main__":
    unittest.main()
