package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

type Server struct {
	store        *Store
	assistantURL string
	dataDir      string // for optional smtp.json / llm_key.txt
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func readBody(r *http.Request, v any) error {
	defer r.Body.Close()
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

const sessionCookie = "girly_session"

// currentUser resolves the signed-in user from the session cookie.
func (s *Server) currentUser(r *http.Request) (User, bool) {
	c, err := r.Cookie(sessionCookie)
	if err != nil || c.Value == "" {
		return User{}, false
	}
	return s.store.UserForToken(c.Value)
}

func (s *Server) setSession(w http.ResponseWriter, userID string) {
	token := randomToken(24)
	_ = s.store.CreateSession(token, userID)
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookie,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   60 * 60 * 24 * 30,
	})
}

func (s *Server) clearSession(w http.ResponseWriter, r *http.Request) {
	if c, err := r.Cookie(sessionCookie); err == nil {
		if u, ok := s.store.UserForToken(c.Value); ok {
			_ = s.store.RevokeSessionsByToken(c.Value, u.ID)
		}
	}
	http.SetCookie(w, &http.Cookie{Name: sessionCookie, Value: "", Path: "/", MaxAge: -1})
}

// ---- Auth ----

type registerReq struct {
	Name            string `json:"name"`
	Email           string `json:"email"`
	Password        string `json:"password"`
	DOB             string `json:"dob"`
	BioSex          string `json:"bio_sex"`
	PeriodStatus    string `json:"period_status"` // "started" | "not_yet"
	LastPeriodDate  string `json:"last_period_date"`
	PeriodLength    int    `json:"period_length"`
}

func (s *Server) handleRegister(w http.ResponseWriter, r *http.Request) {
	var req registerReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	req.Email = strings.ToLower(strings.TrimSpace(req.Email))
	if req.Name == "" || req.Email == "" || len(req.Password) < 8 {
		writeErr(w, 400, "name, email and a password of at least 8 characters are required")
		return
	}
	if _, exists := s.store.UserByEmail(req.Email); exists {
		writeErr(w, 409, "an account with that email already exists")
		return
	}

	// Validate the date of birth: a real date, age 8–120.
	if dob, ok := parseDate(req.DOB); !ok {
		writeErr(w, 400, "please provide a valid date of birth")
		return
	} else if age := time.Now().Year() - dob.Year(); age < 8 || age > 120 {
		writeErr(w, 400, "date of birth must give an age between 8 and 120")
		return
	}

	u := User{
		Name: req.Name, Email: req.Email,
		Salt:         randomToken(16),
		DOB:          req.DOB,
		BioSex:       req.BioSex,
		Mode:         "learn",
		Role:         "user",
		PeriodLength: req.PeriodLength,
		CreatedAt:    todayStr(),
	}
	if u.PeriodLength <= 0 {
		u.PeriodLength = 5
	}
	if req.PeriodStatus == "started" {
		u.Mode = "tracking"
		if _, ok := parseDate(req.LastPeriodDate); ok {
			u.PeriodStarts = []string{req.LastPeriodDate}
		}
	}
	u.PasswordHash = hashPassword(req.Password, u.Salt)
	if err := s.store.AddUser(&u); err != nil {
		writeErr(w, 500, "could not save account")
		return
	}
	s.store.LogAudit(u.Email, "register", "New account created ("+u.Mode+" mode)")
	s.setSession(w, u.ID)
	writeJSON(w, 201, publicUser(u))
}

type loginReq struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	var req loginReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	u, ok := s.store.UserByEmail(strings.ToLower(strings.TrimSpace(req.Email)))
	if !ok || !verifyPassword(req.Password, u.Salt, u.PasswordHash) {
		writeErr(w, 401, "incorrect email or password")
		return
	}
	s.setSession(w, u.ID)
	s.store.LogAudit(u.Email, "login", "Session opened")
	writeJSON(w, 200, publicUser(u))
}

func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	s.clearSession(w, r)
	writeJSON(w, 200, map[string]bool{"ok": true})
}

func publicUser(u User) map[string]any {
	return map[string]any{
		"id": u.ID, "name": u.Name, "email": u.Email, "mode": u.Mode,
		"role": u.Role, "period_length": u.PeriodLength, "created_at": u.CreatedAt,
	}
}

func (s *Server) handleMe(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	writeJSON(w, 200, map[string]any{"user": publicUser(u), "cycle": ComputeCycle(u)})
}

// ---- Logging ----

type logReq struct {
	Date     string   `json:"date"`
	Flow     string   `json:"flow"`
	Moods    []string `json:"moods"`
	Symptoms []string `json:"symptoms"`
	Note     string   `json:"note"`
}

var validFlow = map[string]bool{"spotting": true, "light": true, "medium": true, "heavy": true}

func (s *Server) handleLog(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	var req logReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	if req.Date == "" {
		req.Date = todayStr()
	}
	if _, ok := parseDate(req.Date); !ok {
		writeErr(w, 400, "invalid date")
		return
	}
	if req.Flow != "" && !validFlow[req.Flow] {
		writeErr(w, 400, "flow must be spotting, light, medium or heavy")
		return
	}
	entry := DayLog{Date: req.Date, Flow: req.Flow, Moods: req.Moods, Symptoms: req.Symptoms, Note: req.Note}
	if err := s.store.UpsertLog(u.ID, entry); err != nil {
		writeErr(w, 500, "could not save log")
		return
	}
	writeJSON(w, 201, map[string]any{"ok": true})
}

type periodReq struct {
	Date string `json:"date"`
	Flow string `json:"flow"`
}

func (s *Server) handleLogPeriod(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	var req periodReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	if req.Date == "" {
		req.Date = todayStr()
	}
	if _, ok := parseDate(req.Date); !ok {
		writeErr(w, 400, "invalid date")
		return
	}
	if err := s.store.AddPeriodStart(u.ID, req.Date); err != nil {
		writeErr(w, 500, "could not save period start")
		return
	}
	entry := DayLog{Date: req.Date}
	if req.Flow != "" && validFlow[req.Flow] {
		entry.Flow = req.Flow
	}
	_ = s.store.UpsertLog(u.ID, entry)
	s.store.LogAudit(u.Email, "log_period", "Period start recorded for "+req.Date)
	writeJSON(w, 201, map[string]any{"ok": true})
}

type modeReq struct {
	Mode           string `json:"mode"` // "tracking"
	LastPeriodDate string `json:"last_period_date"`
}

func (s *Server) handleMode(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	var req modeReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	if req.Mode != "tracking" && req.Mode != "learn" {
		writeErr(w, 400, "mode must be tracking or learn")
		return
	}
	if req.Mode == "tracking" {
		date := req.LastPeriodDate
		if date == "" {
			date = todayStr()
		}
		if err := s.store.AddPeriodStart(u.ID, date); err != nil {
			writeErr(w, 500, "could not switch mode")
			return
		}
	} else {
		_ = s.store.UpdateUser(u.ID, func(us *User) { us.Mode = "learn" })
	}
	s.store.LogAudit(u.Email, "mode_switch", "Switched to "+req.Mode+" mode")
	updated, _ := s.store.UserByID(u.ID)
	writeJSON(w, 200, publicUser(updated))
}

// ---- Dashboard / calendar ----

func (s *Server) handleDashboard(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	month := time.Now()
	if m := r.URL.Query().Get("month"); m != "" {
		if t, err := time.Parse("2006-01", m); err == nil {
			month = t
		}
	}
	sum := ComputeCycle(u)
	writeJSON(w, 200, map[string]any{
		"user":     publicUser(u),
		"cycle":    sum,
		"calendar": BuildCalendar(u, sum, month),
		"month":    month.Format("2006-01"),
		"logs":     u.Logs,
	})
}

func (s *Server) handleCalendar(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	month := time.Now()
	if m := r.URL.Query().Get("month"); m != "" {
		if t, err := time.Parse("2006-01", m); err == nil {
			month = t
		}
	}
	writeJSON(w, 200, map[string]any{
		"calendar": BuildCalendar(u, ComputeCycle(u), month),
		"month":    month.Format("2006-01"),
	})
}

// ---- Chat (proxied to the Python assistant service) ----

type chatReq struct {
	Message string `json:"message"`
}

func (s *Server) handleChat(w http.ResponseWriter, r *http.Request) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return
	}
	var req chatReq
	if err := readBody(r, &req); err != nil || strings.TrimSpace(req.Message) == "" {
		writeErr(w, 400, "message is required")
		return
	}

	sum := ComputeCycle(u)
	payload, _ := json.Marshal(map[string]any{
		"message": req.Message,
		"context": map[string]any{
			"name":              u.Name,
			"mode":              u.Mode,
			"cycle_day":         sum.CycleDay,
			"phase":             sum.Phase,
			"phase_label":       sum.PhaseLabel,
			"days_until_period": sum.DaysUntilPeriod,
			"next_period_date":  sum.NextPeriodDate,
		},
	})

	resp, err := http.Post(s.assistantURL+"/chat", "application/json", bytes.NewReader(payload))
	if err != nil {
		writeErr(w, 502, "the companion service is unreachable — is assistant/server.py running?")
		return
	}
	defer resp.Body.Close()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

// ---- Admin ----

func (s *Server) requireAdmin(w http.ResponseWriter, r *http.Request) (User, bool) {
	u, ok := s.currentUser(r)
	if !ok {
		writeErr(w, 401, "not signed in")
		return User{}, false
	}
	if u.Role != "admin" {
		writeErr(w, 403, "admin access required")
		return User{}, false
	}
	return u, true
}

func (s *Server) handleAdminStats(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdmin(w, r); !ok {
		return
	}
	s.store.mu.Lock()
	registered := len(s.store.Users)
	sessions := len(s.store.Sessions)
	learn, tracking := 0, 0
	for _, u := range s.store.Users {
		if u.Mode == "learn" {
			learn++
		} else {
			tracking++
		}
	}
	s.store.mu.Unlock()

	// Ask the Python companion for its health, mirroring the admin
	// "System Health" panel.
	pythonUp := false
	if resp, err := http.Get(s.assistantURL + "/health"); err == nil {
		pythonUp = resp.StatusCode == 200
		resp.Body.Close()
	}

	writeJSON(w, 200, map[string]any{
		"registered":        registered,
		"active_sessions":   sessions,
		"learn_mode":        learn,
		"tracking_mode":     tracking,
		"registered_today":  0,
		"services": []map[string]any{
			{"name": "Go API Gateway", "detail": "girly/stdlib net/http · port 8080", "status": "running"},
			{"name": "Python Companion Service", "detail": "assistant/server.py · port 3000", "status": map[bool]string{true: "running", false: "offline"}[pythonUp]},
			{"name": "JSON Persistent Store", "detail": "data/girly.json · PBKDF2 credentials", "status": "running"},
		},
		"python_up": pythonUp,
	})
}

func (s *Server) handleAdminUsers(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdmin(w, r); !ok {
		return
	}
	s.store.mu.Lock()
	users := append([]User{}, s.store.Users...)
	sessions := append([]Session{}, s.store.Sessions...)
	s.store.mu.Unlock()

	sessionCount := map[string]int{}
	for _, sess := range sessions {
		sessionCount[sess.UserID]++
	}

	type adminUser struct {
		ID        string `json:"id"`
		Name      string `json:"name"`
		Email     string `json:"email"`
		Mode      string `json:"mode"`
		Role      string `json:"role"`
		Active    bool   `json:"active"`
		Sessions  int    `json:"sessions"`
		CreatedAt string `json:"created_at"`
	}
	var out []adminUser
	for _, u := range users {
		out = append(out, adminUser{
			ID: u.ID, Name: u.Name, Email: u.Email, Mode: u.Mode, Role: u.Role,
			Active: sessionCount[u.ID] > 0, Sessions: sessionCount[u.ID], CreatedAt: u.CreatedAt,
		})
	}
	writeJSON(w, 200, map[string]any{"users": out})
}

type emailReq struct {
	Email string `json:"email"`
}

func (s *Server) handleAdminReset(w http.ResponseWriter, r *http.Request) {
	admin, ok := s.requireAdmin(w, r)
	if !ok {
		return
	}
	var req emailReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	target, ok := s.store.UserByEmail(strings.ToLower(strings.TrimSpace(req.Email)))
	if !ok {
		writeErr(w, 404, "no account with that email")
		return
	}
	temp := "girly_" + randomToken(4)
	salt := randomToken(16)
	hash := hashPassword(temp, salt)
	_ = s.store.UpdateUser(target.ID, func(u *User) { u.Salt = salt; u.PasswordHash = hash })
	_ = s.store.RevokeSessions(target.ID)

	// Email the temp password when SMTP is configured; the admin always
	// gets it in the response as a fallback channel.
	emailed := false
	if cfg := LoadSMTPConfig(s.dataDir); cfg != nil {
		if err := SendResetEmail(cfg, target.Email, temp); err == nil {
			emailed = true
		} else {
			fmt.Printf("[girly] reset email to %s failed: %v\n", target.Email, err)
		}
	}

	s.store.LogAudit(admin.Email, "password_reset", "Temporary password dispatched for "+target.Email+
		map[bool]string{true: " (emailed)", false: " (shown to admin)"}[emailed])
	writeJSON(w, 200, map[string]any{"ok": true, "temp_password": temp, "emailed": emailed})
}

func (s *Server) handleAdminRevoke(w http.ResponseWriter, r *http.Request) {
	admin, ok := s.requireAdmin(w, r)
	if !ok {
		return
	}
	var req emailReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	target, ok := s.store.UserByEmail(strings.ToLower(strings.TrimSpace(req.Email)))
	if !ok {
		writeErr(w, 404, "no account with that email")
		return
	}
	_ = s.store.RevokeSessions(target.ID)
	s.store.LogAudit(admin.Email, "revoke_sessions", "All sessions revoked for "+target.Email)
	writeJSON(w, 200, map[string]any{"ok": true})
}

func (s *Server) handleAdminDelete(w http.ResponseWriter, r *http.Request) {
	admin, ok := s.requireAdmin(w, r)
	if !ok {
		return
	}
	var req emailReq
	if err := readBody(r, &req); err != nil {
		writeErr(w, 400, "invalid request body")
		return
	}
	target, ok := s.store.UserByEmail(strings.ToLower(strings.TrimSpace(req.Email)))
	if !ok {
		writeErr(w, 404, "no account with that email")
		return
	}
	if target.ID == admin.ID {
		writeErr(w, 400, "you cannot delete your own admin account")
		return
	}
	_ = s.store.DeleteUser(target.ID)
	s.store.LogAudit(admin.Email, "delete_account", "Identity record purged for "+target.Email)
	writeJSON(w, 200, map[string]any{"ok": true})
}

func (s *Server) handleAdminAudit(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdmin(w, r); !ok {
		return
	}
	s.store.mu.Lock()
	entries := append([]AuditEntry{}, s.store.Audit...)
	s.store.mu.Unlock()
	// newest first
	for i, j := 0, len(entries)-1; i < j; i, j = i+1, j-1 {
		entries[i], entries[j] = entries[j], entries[i]
	}
	writeJSON(w, 200, map[string]any{"audit": entries})
}

// handleAdminTelemetry exports aggregate counts only — no health data, ever.
func (s *Server) handleAdminTelemetry(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdmin(w, r); !ok {
		return
	}
	s.store.mu.Lock()
	registered := len(s.store.Users)
	sessions := len(s.store.Sessions)
	learn, tracking := 0, 0
	for _, u := range s.store.Users {
		if u.Mode == "learn" {
			learn++
		} else {
			tracking++
		}
	}
	s.store.mu.Unlock()
	writeJSON(w, 200, map[string]any{
		"timestamp":         time.Now().Format(time.RFC3339),
		"registered":        registered,
		"active_sessions":   sessions,
		"tracking_mode":     tracking,
		"learn_mode":        learn,
		"privacy_audit":     "Counts only. No cycle, symptom, or chat data included.",
	})
}

// ---- Static files ----

func (s *Server) handleSpa(w http.ResponseWriter, r *http.Request, root string) {
	path := r.URL.Path
	if path == "/" {
		path = "/index.html"
	}
	full := root + path
	if _, err := os.Stat(full); err != nil {
		// fall back to index for unknown routes
		full = root + "/index.html"
	}
	http.ServeFile(w, r, full)
}

func (s *Server) routes(webRoot string) http.Handler {
	mux := http.NewServeMux()

	// auth
	mux.HandleFunc("POST /api/register", s.handleRegister)
	mux.HandleFunc("POST /api/login", s.handleLogin)
	mux.HandleFunc("POST /api/logout", s.handleLogout)
	mux.HandleFunc("GET /api/me", s.handleMe)

	// cycle data
	mux.HandleFunc("GET /api/dashboard", s.handleDashboard)
	mux.HandleFunc("GET /api/calendar", s.handleCalendar)
	mux.HandleFunc("POST /api/logs", s.handleLog)
	mux.HandleFunc("POST /api/period", s.handleLogPeriod)
	mux.HandleFunc("POST /api/mode", s.handleMode)

	// assistant
	mux.HandleFunc("POST /api/chat", s.handleChat)

	// admin
	mux.HandleFunc("GET /api/admin/stats", s.handleAdminStats)
	mux.HandleFunc("GET /api/admin/users", s.handleAdminUsers)
	mux.HandleFunc("GET /api/admin/audit", s.handleAdminAudit)
	mux.HandleFunc("GET /api/admin/telemetry", s.handleAdminTelemetry)
	mux.HandleFunc("POST /api/admin/users/reset", s.handleAdminReset)
	mux.HandleFunc("POST /api/admin/users/revoke", s.handleAdminRevoke)
	mux.HandleFunc("POST /api/admin/users/delete", s.handleAdminDelete)

	// static frontend
	fs := http.FileServer(http.Dir(webRoot))
	mux.Handle("GET /css/", fs)
	mux.Handle("GET /js/", fs)
	mux.Handle("GET /assets/", fs)
	mux.HandleFunc("GET /", func(w http.ResponseWriter, r *http.Request) {
		s.handleSpa(w, r, webRoot)
	})

	// Static files (and API responses) are never cached, so UI and data
	// changes always show on refresh.
	return noStore(logRequests(mux))
}

func noStore(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r)
	})
}

func logRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		if strings.HasPrefix(r.URL.Path, "/api/") {
			fmt.Printf("[girly] %s %s (%s)\n", r.Method, r.URL.Path, time.Since(start).Round(time.Millisecond))
		}
	})
}
