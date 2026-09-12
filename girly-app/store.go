package main

import (
	"encoding/json"
	"os"
	"sort"
	"strconv"
	"sync"
	"time"
)

// ---- Models ----

type DayLog struct {
	Date     string   `json:"date"` // YYYY-MM-DD
	Flow     string   `json:"flow,omitempty"`
	Moods    []string `json:"moods,omitempty"`
	Symptoms []string `json:"symptoms,omitempty"`
	Note     string   `json:"note,omitempty"`
}

type User struct {
	ID           string     `json:"id"`
	Name         string     `json:"name"`
	Email        string     `json:"email"`
	ProfilePicture string   `json:"profile_picture,omitempty"`
	PasswordHash string     `json:"password_hash"`
	Salt         string     `json:"salt"`
	DOB          string     `json:"dob"`
	BioSex       string     `json:"bio_sex"`
	Mode         string     `json:"mode"` // "tracking" | "learn"
	Role         string     `json:"role"` // "user" | "admin"
	PeriodLength int        `json:"period_length"`
	PeriodStarts []string   `json:"period_starts"` // sorted ascending
	Logs         []DayLog   `json:"logs"`
	CreatedAt    string     `json:"created_at"`
}

type Session struct {
	Token     string `json:"token"`
	UserID    string `json:"user_id"`
	CreatedAt string `json:"created_at"`
}

type AuditEntry struct {
	Time   string `json:"time"`
	Actor  string `json:"actor"`
	Action string `json:"action"`
	Detail string `json:"detail"`
}

type ChatMessage struct {
	UserID    string `json:"user_id"`
	Role      string `json:"role"`
	Content   string `json:"content"`
	CreatedAt string `json:"created_at"`
}

type Store struct {
	mu       sync.Mutex
	path     string
	Users    []User       `json:"users"`
	Sessions []Session    `json:"sessions"`
	Audit    []AuditEntry `json:"audit"`
	Chat     []ChatMessage `json:"chat,omitempty"`
	nextID   int
}

func LoadStore(path string) (*Store, error) {
	s := &Store{path: path, nextID: 1}
	data, err := os.ReadFile(path)
	if err == nil {
		if err := json.Unmarshal(data, s); err != nil {
			return nil, err
		}
	}
	// compute next id
	for _, u := range s.Users {
		if n, err := strconv.Atoi(u.ID); err == nil && n >= s.nextID {
			s.nextID = n + 1
		}
	}
	if len(s.Users) == 0 {
		if err := s.save(); err != nil {
			return nil, err
		}
	}
	return s, nil
}

func (s *Store) save() error {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.path, data, 0600)
}

// ---- Mutations (all lock internally) ----

func (s *Store) AddUser(u *User) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	u.ID = strconv.Itoa(s.nextID)
	s.nextID++
	s.Users = append(s.Users, *u)
	return s.save()
}

func (s *Store) UserByEmail(email string) (User, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, u := range s.Users {
		if u.Email == email {
			return u, true
		}
	}
	return User{}, false
}

func (s *Store) UserByID(id string) (User, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, u := range s.Users {
		if u.ID == id {
			return u, true
		}
	}
	return User{}, false
}

func (s *Store) UpdateUser(id string, fn func(*User)) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for i := range s.Users {
		if s.Users[i].ID == id {
			fn(&s.Users[i])
			return s.save()
		}
	}
	return nil
}

func (s *Store) DeleteUser(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for i := range s.Users {
		if s.Users[i].ID == id {
			s.Users = append(s.Users[:i], s.Users[i+1:]...)
			break
		}
	}
	// drop their sessions too
	kept := s.Sessions[:0]
	for _, sess := range s.Sessions {
		if sess.UserID != id {
			kept = append(kept, sess)
		}
	}
	s.Sessions = kept
	chat := s.Chat[:0]
	for _, message := range s.Chat {
		if message.UserID != id {
			chat = append(chat, message)
		}
	}
	s.Chat = chat
	return s.save()
}

func (s *Store) AddChatMessage(userID, role, content string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Chat = append(s.Chat, ChatMessage{UserID: userID, Role: role, Content: content, CreatedAt: time.Now().Format(time.RFC3339)})
	count := 0
	for i := len(s.Chat) - 1; i >= 0; i-- {
		if s.Chat[i].UserID == userID {
			count++
			if count > 100 {
				s.Chat = append(s.Chat[:i], s.Chat[i+1:]...)
				break
			}
		}
	}
	return s.save()
}

func (s *Store) ChatForUser(userID string) []ChatMessage {
	s.mu.Lock()
	defer s.mu.Unlock()
	var messages []ChatMessage
	for _, message := range s.Chat {
		if message.UserID == userID {
			messages = append(messages, message)
		}
	}
	return messages
}

func (s *Store) ClearChat(userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	kept := s.Chat[:0]
	for _, message := range s.Chat {
		if message.UserID != userID {
			kept = append(kept, message)
		}
	}
	s.Chat = kept
	return s.save()
}

func (s *Store) CreateSession(token, userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Sessions = append(s.Sessions, Session{Token: token, UserID: userID, CreatedAt: todayStr()})
	return s.save()
}

func (s *Store) UserForToken(token string) (User, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, sess := range s.Sessions {
		if sess.Token == token {
			for _, u := range s.Users {
				if u.ID == sess.UserID {
					return u, true
				}
			}
		}
	}
	return User{}, false
}

func (s *Store) RevokeSessions(userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	kept := s.Sessions[:0]
	for _, sess := range s.Sessions {
		if sess.UserID != userID {
			kept = append(kept, sess)
		}
	}
	s.Sessions = kept
	return s.save()
}

// RevokeSessionsByToken removes a single session (used at logout).
func (s *Store) RevokeSessionsByToken(token, userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	kept := s.Sessions[:0]
	for _, sess := range s.Sessions {
		if sess.Token != token {
			kept = append(kept, sess)
		}
	}
	s.Sessions = kept
	return s.save()
}

func (s *Store) CountSessions(userID string) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	n := 0
	for _, sess := range s.Sessions {
		if sess.UserID == userID {
			n++
		}
	}
	return n
}

func (s *Store) LogAudit(actor, action, detail string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.Audit = append(s.Audit, AuditEntry{
		Time: time.Now().Format(time.RFC3339), Actor: actor, Action: action, Detail: detail,
	})
	// keep the most recent 100 entries
	if len(s.Audit) > 100 {
		s.Audit = s.Audit[len(s.Audit)-100:]
	}
	_ = s.save()
}

// ---- Cycle log helpers ----

// AddPeriodStart records a period start date, deduplicating and keeping order.
func (s *Store) AddPeriodStart(userID, date string) error {
	return s.UpdateUser(userID, func(u *User) {
		for _, d := range u.PeriodStarts {
			if d == date {
				return
			}
		}
		u.PeriodStarts = append(u.PeriodStarts, date)
		sort.Strings(u.PeriodStarts)
		// new period start implies tracking mode
		u.Mode = "tracking"
	})
}

// UpsertLog merges a daily log entry with anything already stored for that date.
func (s *Store) UpsertLog(userID string, log DayLog) error {
	return s.UpdateUser(userID, func(u *User) {
		for i := range u.Logs {
			if u.Logs[i].Date == log.Date {
				if log.Flow != "" {
					u.Logs[i].Flow = log.Flow
				}
				u.Logs[i].Moods = mergeUnique(u.Logs[i].Moods, log.Moods)
				u.Logs[i].Symptoms = mergeUnique(u.Logs[i].Symptoms, log.Symptoms)
				if log.Note != "" {
					u.Logs[i].Note = log.Note
				}
				return
			}
		}
		u.Logs = append(u.Logs, log)
		sort.Slice(u.Logs, func(a, b int) bool { return u.Logs[a].Date < u.Logs[b].Date })
	})
}

func mergeUnique(a, b []string) []string {
	out := append([]string{}, a...)
	for _, v := range b {
		found := false
		for _, existing := range out {
			if existing == v {
				found = true
				break
			}
		}
		if !found {
			out = append(out, v)
		}
	}
	return out
}

