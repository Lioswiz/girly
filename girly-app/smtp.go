package main

import (
	"encoding/json"
	"net/smtp"
	"os"
	"path/filepath"
	"strconv"
)

// SMTPConfig optionally wires up outgoing mail for admin password resets.
// Configured via data/smtp.json (see data/smtp.example.json) or SMTP_* env
// vars. When absent, resets simply return the temp password to the admin.
type SMTPConfig struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	User     string `json:"user"`
	Password string `json:"password"`
	From     string `json:"from"`
}

func LoadSMTPConfig(dataDir string) *SMTPConfig {
	// env vars win
	if os.Getenv("SMTP_HOST") != "" {
		port, _ := strconv.Atoi(os.Getenv("SMTP_PORT"))
		return &SMTPConfig{
			Host:     os.Getenv("SMTP_HOST"),
			Port:     port,
			User:     os.Getenv("SMTP_USER"),
			Password: os.Getenv("SMTP_PASS"),
			From:     os.Getenv("SMTP_FROM"),
		}
	}
	path := filepath.Join(dataDir, "smtp.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var cfg SMTPConfig
	if json.Unmarshal(data, &cfg) != nil || cfg.Host == "" {
		return nil
	}
	return &cfg
}

// SendResetEmail delivers the temporary password. Returns an error only when
// configured but failed; a nil config means "not configured" (caller reports
// emailed=false rather than failing the reset).
func SendResetEmail(cfg *SMTPConfig, to, tempPassword string) error {
	if cfg == nil {
		return nil
	}
	addr := cfg.Host + ":" + strconv.Itoa(cfg.Port)
	auth := smtp.PlainAuth("", cfg.User, cfg.Password, cfg.Host)

	subject := "Subject: Your Girly temporary password"
	body := "Hi,\n\nAn administrator reset your Girly password.\n\n" +
		"Temporary password: " + tempPassword + "\n\n" +
		"Sign in at your Girly app and change it from there.\n\n" +
		"Stay gentle with yourself,\nThe Girly Team \U0001F338"

	msg := []byte("To: " + to + "\r\n" +
		"From: " + cfg.From + "\r\n" +
		subject + "\r\n" +
		"MIME-Version: 1.0\r\n" +
		"Content-Type: text/plain; charset=UTF-8\r\n" +
		"\r\n" +
		body + "\r\n")

	return smtp.SendMail(addr, auth, cfg.From, []string{to}, msg)
}
