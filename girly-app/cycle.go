package main

import (
	"time"
)

const (
	dateLayout = "2006-01-02"
)

func todayStr() string { return time.Now().Format(dateLayout) }

func parseDate(s string) (time.Time, bool) {
	t, err := time.Parse(dateLayout, s)
	return t, err == nil
}

// CycleSummary is the computed prediction model handed to the frontend.
type CycleSummary struct {
	HasData          bool   `json:"has_data"`
	CycleDay         int    `json:"cycle_day"`
	CycleLength      int    `json:"cycle_length"`
	AvgCycleLength   int    `json:"avg_cycle_length"`
	PeriodLength     int    `json:"period_length"`
	CyclesLogged     int    `json:"cycles_logged"`
	Phase            string `json:"phase"`             // menstrual | follicular | ovulatory | luteal
	PhaseLabel       string `json:"phase_label"`       // human label e.g. "Luteal Phase (Free Window)"
	NextPeriodDate   string `json:"next_period_date"`  // YYYY-MM-DD
	DaysUntilPeriod  int    `json:"days_until_period"` // 0 = today
	OvulationDate    string `json:"ovulation_date"`
	FertileStart     string `json:"fertile_start"`
	FertileEnd       string `json:"fertile_end"`
	LastPeriodStart  string `json:"last_period_start"`
	PredictionWindow int    `json:"prediction_window"` // ± days
	Tip              string `json:"tip"`               // gentle wellness tip for the current phase
}

// ComputeCycle derives predictions from a user's period history.
func ComputeCycle(u User) CycleSummary {
	sum := CycleSummary{
		CycleLength:      28,
		AvgCycleLength:   28,
		PeriodLength:     u.PeriodLength,
		CyclesLogged:     len(u.PeriodStarts),
		PredictionWindow: 2,
	}
	if sum.PeriodLength <= 0 {
		sum.PeriodLength = 5
	}

	// Average cycle length from completed cycles (gaps between starts),
	// clamped to a medically plausible 21–45 day range.
	if len(u.PeriodStarts) >= 2 {
		total := 0
		n := 0
		for i := 1; i < len(u.PeriodStarts); i++ {
			a, ok1 := parseDate(u.PeriodStarts[i-1])
			b, ok2 := parseDate(u.PeriodStarts[i])
			if ok1 && ok2 {
				gap := int(b.Sub(a).Hours() / 24)
				if gap >= 15 && gap <= 60 {
					total += gap
					n++
				}
			}
		}
		if n > 0 {
			avg := total / n
			if avg < 21 {
				avg = 21
			}
			if avg > 45 {
				avg = 45
			}
			sum.AvgCycleLength = avg
			sum.CycleLength = avg
		}
	}

	if len(u.PeriodStarts) == 0 {
		sum.Phase, sum.PhaseLabel = "learn", "Learn Mode"
		sum.Tip = "Your journey is just beginning — explore the Learn tab for friendly guides."
		return sum
	}

	last, ok := parseDate(u.PeriodStarts[len(u.PeriodStarts)-1])
	if !ok {
		return sum
	}
	sum.HasData = true
	sum.LastPeriodStart = last.Format(dateLayout)

	// "Today" as a clean UTC-midnight instant matching the local calendar
	// date, so every comparison below stays day-level and timezone-safe.
	now, _ := parseDate(todayStr())
	// Roll the reference start forward so today always falls inside a cycle.
	start := last
	for start.AddDate(0, 0, sum.AvgCycleLength).Before(now) || start.AddDate(0, 0, sum.AvgCycleLength).Equal(now) {
		start = start.AddDate(0, 0, sum.AvgCycleLength)
	}
	cycleDay := int(now.Sub(start).Hours()/24) + 1
	if cycleDay < 1 {
		cycleDay = 1
	}
	sum.CycleDay = cycleDay

	next := start.AddDate(0, 0, sum.AvgCycleLength)
	sum.NextPeriodDate = next.Format(dateLayout)
	sum.DaysUntilPeriod = int(next.Sub(now).Hours() / 24)

	// Ovulation ~14 days before the next period; fertile window spans
	// ovulation −5 … ovulation +1.
	ovu := next.AddDate(0, 0, -14)
	sum.OvulationDate = ovu.Format(dateLayout)
	sum.FertileStart = ovu.AddDate(0, 0, -5).Format(dateLayout)
	sum.FertileEnd = ovu.AddDate(0, 0, 1).Format(dateLayout)

	sum.Phase, sum.PhaseLabel = phaseFor(now, cycleDay, sum.PeriodLength, ovu)
	sum.Tip = tipFor(sum.Phase, sum.DaysUntilPeriod)
	return sum
}

func phaseFor(now time.Time, cycleDay, periodLen int, ovu time.Time) (string, string) {
	fertileStart := ovu.AddDate(0, 0, -5)
	fertileEnd := ovu.AddDate(0, 0, 1)

	switch {
	case cycleDay <= periodLen:
		return "menstrual", "Menstrual Phase"
	case !now.Before(fertileStart) && !now.After(fertileEnd):
		if now.Equal(ovu) {
			return "ovulatory", "Ovulation Peak"
		}
		return "ovulatory", "Ovulatory Phase (Fertile Window)"
	case now.Before(fertileStart):
		return "follicular", "Follicular Phase (Rising Energy)"
	default:
		return "luteal", "Luteal Phase (Free Window)"
	}
}

func tipFor(phase string, daysUntil int) string {
	switch phase {
	case "menstrual":
		return "Rest is productive today. A warm compress, iron-rich foods, and extra hydration help your body replenish."
	case "follicular":
		return "Energy is on the rise — a lovely window for movement, projects, and trying something new."
	case "ovulatory":
		return "You may feel outgoing and confident. Great days for social plans and energizing workouts."
	default:
		if daysUntil <= 4 {
			return "Your body is naturally winding down. Drink warm chamomile tea, hydrate, and prioritize rest today."
		}
		return "Steady self-care now softens the week ahead: magnesium-rich snacks and gentle stretching go a long way."
	}
}

// DayStatus describes one calendar day for the tracker calendar UI.
type DayStatus struct {
	Date        string `json:"date"`
	Day         int    `json:"day"`
	Phase       string `json:"phase,omitempty"`       // menstrual|follicular|ovulatory|luteal (inferred/predicted)
	Kind        string `json:"kind"`                  // logged_period|predicted|fertile|ovulation|plain
	IsToday     bool   `json:"is_today"`
	HasLog      bool   `json:"has_log"`
	IsWindow    bool   `json:"is_window"` // inside ±2d prediction window
}

// BuildCalendar produces the day grid (with leading blanks as empty Date strings)
// for a given month, colored by logs and predictions.
func BuildCalendar(u User, sum CycleSummary, month time.Time) []DayStatus {
	first := time.Date(month.Year(), month.Month(), 1, 0, 0, 0, 0, time.UTC)
	daysInMonth := time.Date(month.Year(), month.Month()+1, 0, 0, 0, 0, 0, time.UTC).Day()

	logsByDate := map[string]DayLog{}
	for _, l := range u.Logs {
		logsByDate[l.Date] = l
	}
	periodDays := map[string]bool{}
	for _, start := range u.PeriodStarts {
		if t, ok := parseDate(start); ok {
			pl := u.PeriodLength
			if pl <= 0 {
				pl = 5
			}
			for i := 0; i < pl; i++ {
				periodDays[t.AddDate(0, 0, i).Format(dateLayout)] = true
			}
		}
	}

	// Projected period starts: project the average cycle from the last known
	// start, forward and backward, covering the requested month. The bound
	// extends past month end by the prediction window so a start early next
	// month still colors its ±2d window days that spill into this month.
	monthEnd := first.AddDate(0, 1, 0).AddDate(0, 0, sum.PredictionWindow+7)

	predicted := map[string]bool{}
	window := map[string]bool{}
	if sum.HasData {
		if last, ok := parseDate(u.PeriodStarts[len(u.PeriodStarts)-1]); ok {
			for base := last.AddDate(0, 0, -sum.AvgCycleLength*4); !base.After(monthEnd); base = base.AddDate(0, 0, sum.AvgCycleLength) {
				for i := 0; i < sum.PeriodLength; i++ {
					d := base.AddDate(0, 0, i)
					if !periodDays[d.Format(dateLayout)] {
						predicted[d.Format(dateLayout)] = true
					}
				}
				for w := -sum.PredictionWindow; w <= sum.PredictionWindow; w++ {
					wd := base.AddDate(0, 0, w)
					if !periodDays[wd.Format(dateLayout)] {
						window[wd.Format(dateLayout)] = true
					}
				}
			}
		}
	}

	// Fertile / ovulation days across projected cycles.
	fertile := map[string]bool{}
	ovuDays := map[string]bool{}
	if sum.HasData {
		if last, ok := parseDate(u.PeriodStarts[len(u.PeriodStarts)-1]); ok {
			for base := last.AddDate(0, 0, -sum.AvgCycleLength*4); !base.After(monthEnd); base = base.AddDate(0, 0, sum.AvgCycleLength) {
				ovu := base.AddDate(0, 0, sum.AvgCycleLength-14)
				for i := -5; i <= 1; i++ {
					fertile[ovu.AddDate(0, 0, i).Format(dateLayout)] = true
				}
				ovuDays[ovu.Format(dateLayout)] = true
			}
		}
	}

	today := todayStr()
	var out []DayStatus
	// weekday offset — calendar starts on Monday
	offset := (int(first.Weekday()) + 6) % 7
	for i := 0; i < offset; i++ {
		out = append(out, DayStatus{})
	}
	for d := 1; d <= daysInMonth; d++ {
		date := time.Date(month.Year(), month.Month(), d, 0, 0, 0, 0, time.UTC)
		ds := date.Format(dateLayout)
		status := DayStatus{Date: ds, Day: d, IsToday: ds == today, HasLog: logsByDate[ds].Date != ""}

		switch {
		case periodDays[ds]:
			status.Kind = "logged_period"
			status.Phase = "menstrual"
		case ovuDays[ds]:
			status.Kind = "ovulation"
			status.Phase = "ovulatory"
		case fertile[ds]:
			status.Kind = "fertile"
			status.Phase = "ovulatory"
		case predicted[ds] || window[ds]:
			status.Kind = "predicted"
			status.Phase = "menstrual"
			status.IsWindow = window[ds]
		case sum.HasData:
			status.Kind = "plain"
		}
		out = append(out, status)
	}
	return out
}
