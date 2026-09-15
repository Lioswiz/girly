"""Girly 🌸 — cycle-day / phase / fertile-window prediction math.

Python port of cycle.go. Users are plain dicts (as loaded from the JSON
store); all prediction logic is day-level and timezone-safe.
"""

import calendar
from datetime import date, datetime, timedelta

DATE_FMT = "%Y-%m-%d"


def today_str() -> str:
    return date.today().strftime(DATE_FMT)


def parse_date(s):
    """Parse a YYYY-MM-DD string; returns a date or None."""
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def parse_month(s):
    """Parse a YYYY-MM string; returns a date (first of month) or None."""
    try:
        return datetime.strptime(s, "%Y-%m").date()
    except (TypeError, ValueError):
        return None


def compute_cycle(user):
    """Derive the prediction summary handed to the frontend."""
    starts = user.get("period_starts") or []
    period_length = user.get("period_length") or 0
    summary = {
        "has_data": False,
        "cycle_day": 0,
        "cycle_length": 28,
        "avg_cycle_length": 28,
        "period_length": period_length if period_length > 0 else 5,
        "cycles_logged": len(starts),
        "phase": "",
        "phase_label": "",
        "next_period_date": "",
        "days_until_period": 0,
        "ovulation_date": "",
        "fertile_start": "",
        "fertile_end": "",
        "last_period_start": "",
        "prediction_window": 2,
        "tip": "",
    }

    # Average cycle length from completed cycles (gaps between starts),
    # clamped to a medically plausible 21–45 day range.
    if len(starts) >= 2:
        total = n = 0
        for prev, cur in zip(starts, starts[1:]):
            a, b = parse_date(prev), parse_date(cur)
            if a and b:
                gap = (b - a).days
                if 15 <= gap <= 60:
                    total += gap
                    n += 1
        if n > 0:
            avg = total // n
            avg = max(21, min(45, avg))
            summary["avg_cycle_length"] = avg
            summary["cycle_length"] = avg

    if not starts:
        summary["phase"] = "learn"
        summary["phase_label"] = "Learn Mode"
        summary["tip"] = (
            "Your journey is just beginning — explore the Learn tab for friendly guides."
        )
        return summary

    last = parse_date(starts[-1])
    if last is None:
        return summary
    summary["has_data"] = True
    summary["last_period_start"] = last.strftime(DATE_FMT)

    # "Today" as a clean calendar date, so every comparison below stays
    # day-level and timezone-safe.
    now = parse_date(today_str())
    avg = summary["avg_cycle_length"]
    # Roll the reference start forward so today always falls inside a cycle.
    start = last
    while start + timedelta(days=avg) <= now:
        start = start + timedelta(days=avg)
    cycle_day = (now - start).days + 1
    summary["cycle_day"] = max(1, cycle_day)

    next_start = start + timedelta(days=avg)
    summary["next_period_date"] = next_start.strftime(DATE_FMT)
    summary["days_until_period"] = (next_start - now).days

    # Ovulation ~14 days before the next period; fertile window spans
    # ovulation −5 … ovulation +1.
    ovu = next_start - timedelta(days=14)
    summary["ovulation_date"] = ovu.strftime(DATE_FMT)
    summary["fertile_start"] = (ovu - timedelta(days=5)).strftime(DATE_FMT)
    summary["fertile_end"] = (ovu + timedelta(days=1)).strftime(DATE_FMT)

    summary["phase"], summary["phase_label"] = _phase_for(
        now, cycle_day, summary["period_length"], ovu
    )
    summary["tip"] = _tip_for(summary["phase"], summary["days_until_period"])
    return summary


def _phase_for(now, cycle_day, period_len, ovu):
    fertile_start = ovu - timedelta(days=5)
    fertile_end = ovu + timedelta(days=1)

    if cycle_day <= period_len:
        return "menstrual", "Menstrual Phase"
    if fertile_start <= now <= fertile_end:
        if now == ovu:
            return "ovulatory", "Ovulation Peak"
        return "ovulatory", "Ovulatory Phase (Fertile Window)"
    if now < fertile_start:
        return "follicular", "Follicular Phase (Rising Energy)"
    return "luteal", "Luteal Phase (Free Window)"


def _tip_for(phase, days_until):
    if phase == "menstrual":
        return (
            "Rest is productive today. A warm compress, iron-rich foods, and extra "
            "hydration help your body replenish."
        )
    if phase == "follicular":
        return (
            "Energy is on the rise — a lovely window for movement, projects, and "
            "trying something new."
        )
    if phase == "ovulatory":
        return "You may feel outgoing and confident. Great days for social plans and energizing workouts."
    if days_until <= 4:
        return (
            "Your body is naturally winding down. Drink warm chamomile tea, hydrate, "
            "and prioritize rest today."
        )
    return (
        "Steady self-care now softens the week ahead: magnesium-rich snacks and "
        "gentle stretching go a long way."
    )


def _blank_day():
    return {
        "date": "",
        "day": 0,
        "kind": "",
        "is_today": False,
        "has_log": False,
        "is_window": False,
    }


def build_calendar(user, summary, month):
    """Produce the day grid (with leading blanks as empty-date entries) for a
    given month, colored by logs and predictions."""
    first = month.replace(day=1)
    days_in_month = calendar.monthrange(month.year, month.month)[1]

    logs_by_date = {log["date"]: log for log in (user.get("logs") or [])}
    period_days = set()
    period_len = user.get("period_length") or 0
    if period_len <= 0:
        period_len = 5
    for start in user.get("period_starts") or []:
        t = parse_date(start)
        if t:
            for i in range(period_len):
                period_days.add((t + timedelta(days=i)).strftime(DATE_FMT))

    # Projected period starts: project the average cycle from the last known
    # start, forward and backward, covering the requested month. The bound
    # extends past month end by the prediction window so a start early next
    # month still colors its ±2d window days that spill into this month.
    month_end = (first + timedelta(days=32)).replace(day=1) + timedelta(
        days=summary["prediction_window"] + 7
    )

    avg = summary["avg_cycle_length"]
    starts = user.get("period_starts") or []
    predicted, window = set(), set()
    fertile, ovu_days = set(), set()
    if summary["has_data"] and starts:
        last = parse_date(starts[-1])
        if last:
            base = last - timedelta(days=avg * 4)
            while base <= month_end:
                for i in range(summary["period_length"]):
                    d = (base + timedelta(days=i)).strftime(DATE_FMT)
                    if d not in period_days:
                        predicted.add(d)
                for w in range(-summary["prediction_window"], summary["prediction_window"] + 1):
                    wd = (base + timedelta(days=w)).strftime(DATE_FMT)
                    if wd not in period_days:
                        window.add(wd)
                # Fertile / ovulation days across projected cycles.
                ovu = base + timedelta(days=avg - 14)
                for i in range(-5, 2):
                    fertile.add((ovu + timedelta(days=i)).strftime(DATE_FMT))
                ovu_days.add(ovu.strftime(DATE_FMT))
                base = base + timedelta(days=avg)

    today = today_str()
    out = []
    # weekday offset — calendar starts on Monday (Python: Monday == 0)
    for _ in range(first.weekday()):
        out.append(_blank_day())
    for d in range(1, days_in_month + 1):
        ds = first.replace(day=d).strftime(DATE_FMT)
        status = _blank_day()
        status.update(
            {"date": ds, "day": d, "is_today": ds == today, "has_log": ds in logs_by_date}
        )

        if ds in period_days:
            status["kind"] = "logged_period"
            status["phase"] = "menstrual"
        elif ds in ovu_days:
            status["kind"] = "ovulation"
            status["phase"] = "ovulatory"
        elif ds in fertile:
            status["kind"] = "fertile"
            status["phase"] = "ovulatory"
        elif ds in predicted or ds in window:
            status["kind"] = "predicted"
            status["phase"] = "menstrual"
            status["is_window"] = ds in window
        elif summary["has_data"]:
            status["kind"] = "plain"
        out.append(status)
    return out
