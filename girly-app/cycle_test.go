package main

import (
	"testing"
	"time"
)

// mkUser builds a user with period history relative to today, so tests stay
// deterministic regardless of when they run.
func mkUser(periodLen int, startsAgo []int) User {
	u := User{PeriodLength: periodLen}
	now := time.Now()
	for _, ago := range startsAgo {
		u.PeriodStarts = append(u.PeriodStarts, now.AddDate(0, 0, -ago).Format(dateLayout))
	}
	return u
}

func mustDate(t *testing.T, s string) time.Time {
	t.Helper()
	d, ok := parseDate(s)
	if !ok {
		t.Fatalf("bad date %q", s)
	}
	return d
}

// Default: no logged starts → no data, fallback cycle length 28.
func TestDefaultCycleLength(t *testing.T) {
	sum := ComputeCycle(mkUser(5, nil))
	if sum.HasData {
		t.Fatal("expected has_data=false with no period starts")
	}
	if sum.CycleLength != 28 || sum.AvgCycleLength != 28 {
		t.Fatalf("expected default 28-day cycle, got %d/%d", sum.CycleLength, sum.AvgCycleLength)
	}
	if sum.Phase != "learn" {
		t.Fatalf("expected learn phase, got %q", sum.Phase)
	}
}

// Personal cycle length is learned from the average gap between starts.
func TestLearnedAverage(t *testing.T) {
	// gaps of 30 and 30 → learned 30
	sum := ComputeCycle(mkUser(5, []int{50, 20}))
	if sum.AvgCycleLength != 30 {
		t.Fatalf("expected learned 30-day cycle, got %d", sum.AvgCycleLength)
	}
	if sum.CycleLength != 30 {
		t.Fatalf("expected active cycle length 30, got %d", sum.CycleLength)
	}
}

// Outlier gaps (re-logs, flukes outside 15–60 days) are ignored.
func TestOutlierFiltering(t *testing.T) {
	// starts 63, 35, 30, 0 days ago → gaps: 28, 5 (re-log → ignored), 30
	// → average of 28 and 30 = 29
	sum := ComputeCycle(mkUser(5, []int{63, 35, 30, 0}))
	if sum.AvgCycleLength != 29 {
		t.Fatalf("expected outlier-filtered average 29, got %d", sum.AvgCycleLength)
	}
}

// Learned lengths are clamped to a medically plausible 21–45 day range.
func TestClamping(t *testing.T) {
	long := ComputeCycle(mkUser(5, []int{110, 50})) // gap of 60 → clamped to 45
	if long.AvgCycleLength != 45 {
		t.Fatalf("expected clamp to 45, got %d", long.AvgCycleLength)
	}
	// gaps of 18 and 20 → average 19 → clamped up to 21
	short := ComputeCycle(mkUser(5, []int{38, 20, 0}))
	if short.AvgCycleLength != 21 {
		t.Fatalf("expected clamp to 21, got %d", short.AvgCycleLength)
	}
}

// Ovulation anchors 14 days before the projected next period; the fertile
// window spans ovulation −5 … +1, all on the personal (learned) length.
func TestOvulationAnchoring(t *testing.T) {
	sum := ComputeCycle(mkUser(5, []int{50, 20})) // learned 30-day cycle, last start 20 days ago
	if !sum.HasData {
		t.Fatal("expected has_data")
	}
	next := mustDate(t, sum.NextPeriodDate)
	ovu := mustDate(t, sum.OvulationDate)
	fertStart := mustDate(t, sum.FertileStart)
	fertEnd := mustDate(t, sum.FertileEnd)

	if got := next.Sub(ovu).Hours() / 24; got != 14 {
		t.Fatalf("expected ovulation 14 days before next period, got %v days", got)
	}
	if got := ovu.Sub(fertStart).Hours() / 24; got != 5 {
		t.Fatalf("expected fertile window to open 5 days before ovulation, got %v", got)
	}
	if got := fertEnd.Sub(ovu).Hours() / 24; got != 1 {
		t.Fatalf("expected fertile window to close 1 day after ovulation, got %v", got)
	}
}

// Cycle day is 1-based: the start day itself is Day 1.
func TestCycleDayOneBased(t *testing.T) {
	sum := ComputeCycle(mkUser(5, []int{30, 0})) // last start = today
	if sum.CycleDay != 1 {
		t.Fatalf("expected cycle day 1 on the start day, got %d", sum.CycleDay)
	}
	if sum.Phase != "menstrual" {
		t.Fatalf("expected menstrual phase on day 1, got %q", sum.Phase)
	}

	next := ComputeCycle(mkUser(5, []int{1})) // yesterday → day 2 of default 28
	if next.CycleDay != 2 {
		t.Fatalf("expected cycle day 2, got %d", next.CycleDay)
	}
}

// The prediction window spans ±2 days around the projected start.
func TestPredictionWindow(t *testing.T) {
	sum := ComputeCycle(mkUser(5, []int{28}))
	if sum.PredictionWindow != 2 {
		t.Fatalf("expected ±2 day window, got %d", sum.PredictionWindow)
	}
}

// Calendar classification must stay correct across month boundaries with a
// learned (non-28) cycle length — the case the original progress log had
// pending verification.
//
// Setup (relative to today): starts 40 and 10 days ago → learned 30-day
// cycle, last start 10 days ago. Next period lands 20 days out; depending on
// today's date it may fall in this month or the next, so every assertion is
// computed from the projected dates rather than hardcoded.
func TestCalendarAcrossMonthsWithLearnedLength(t *testing.T) {
	u := mkUser(5, []int{40, 10}) // learned 30-day cycle
	sum := ComputeCycle(u)
	if sum.AvgCycleLength != 30 {
		t.Fatalf("expected learned 30-day cycle, got %d", sum.AvgCycleLength)
	}

	lastStart := mustDate(t, u.PeriodStarts[len(u.PeriodStarts)-1])
	next := mustDate(t, sum.NextPeriodDate)
	ovu := mustDate(t, sum.OvulationDate)

	calendarFor := func(month time.Time) map[string]DayStatus {
		byDate := map[string]DayStatus{}
		for _, d := range BuildCalendar(u, sum, month) {
			if d.Date != "" {
				byDate[d.Date] = d
			}
		}
		return byDate
	}

	thisMonth := calendarFor(time.Now())
	nextMonth := calendarFor(time.Now().AddDate(0, 1, 0))

	// The logged start is always logged_period, never overwritten by a
	// prediction.
	if st, ok := thisMonth[lastStart.Format(dateLayout)]; !ok || st.Kind != "logged_period" {
		t.Fatalf("expected logged start %s to be logged_period in this month, got %+v", lastStart.Format(dateLayout), st)
	}

	// Ovulation day must be classified as such.
	if st, ok := thisMonth[ovu.Format(dateLayout)]; !ok || st.Kind != "ovulation" {
		t.Fatalf("expected ovulation %s to be ovulation, got %+v", ovu.Format(dateLayout), st)
	}

	// The projected next start (and its ±2 window) must be predicted,
	// whichever month it lands in.
	checkPredicted := func(date time.Time, label string) {
		key := date.Format(dateLayout)
		st, inThis := thisMonth[key]
		if !inThis {
			st = nextMonth[key]
		}
		if st.Date == "" {
			t.Fatalf("%s %s missing from both months' calendars", label, key)
		}
		if st.Kind != "predicted" {
			t.Fatalf("expected %s %s to be predicted, got %q", label, key, st.Kind)
		}
	}
	checkPredicted(next, "projected start")
	for _, off := range []int{-2, -1, 1, 2} {
		checkPredicted(next.AddDate(0, 0, off), "window day")
	}

	// The following cycle's projected start (last start + 60) must be
	// predicted in the month it lands in.
	checkPredicted(lastStart.AddDate(0, 0, 60), "following projected start")
}

// Logged days keep their own flow history; predictions never overwrite them.
func TestUpsertLogMerge(t *testing.T) {
	s, err := LoadStore(t.TempDir() + "/girly.json")
	if err != nil {
		t.Fatal(err)
	}
	salt := randomToken(16)
	u := User{Name: "T", Email: "t@t.io", Salt: salt, PasswordHash: hashPassword("pw", salt), PeriodLength: 5}
	if err := s.AddUser(&u); err != nil {
		t.Fatal(err)
	}

	_ = s.UpsertLog(u.ID, DayLog{Date: "2026-01-05", Flow: "medium", Moods: []string{"Tired"}})
	_ = s.UpsertLog(u.ID, DayLog{Date: "2026-01-05", Symptoms: []string{"Cramps"}})

	got, ok := s.UserByID(u.ID)
	if !ok {
		t.Fatal("user vanished")
	}
	log := got.Logs[0]
	if log.Flow != "medium" || len(log.Moods) != 1 || len(log.Symptoms) != 1 {
		t.Fatalf("merge failed: %+v", log)
	}
	if len(got.Logs) != 1 {
		t.Fatalf("expected a single merged log, got %d", len(got.Logs))
	}
}
