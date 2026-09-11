// Girly 🌸 — a private, reassuring menstrual cycle tracker.
//
// Go powers the core: it serves the web frontend, owns accounts & sessions,
// computes cycle predictions, and exposes the admin console API. The AI
// companion lives in the Python service (assistant/server.py).
package main

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
)

const (
	defaultAddr        = ":8080"
	defaultAssistant   = "http://127.0.0.1:3000"
)

func main() {
	// Defaults are relative to the working directory so `go run .` and the
	// built binary behave identically; override with env vars if needed.
	dataPath := envOr("GIRLY_DATA", "data/girly.json")
	if err := os.MkdirAll(filepath.Dir(dataPath), 0755); err != nil {
		fmt.Println("[girly] could not create data dir:", err)
		os.Exit(1)
	}

	store, err := LoadStore(dataPath)
	if err != nil {
		fmt.Println("[girly] could not load store:", err)
		os.Exit(1)
	}

	webRoot := envOr("GIRLY_WEB", "web")
	if _, err := os.Stat(webRoot); err != nil {
		exe, _ := os.Executable()
		alt := filepath.Join(filepath.Dir(exe), "web")
		if _, err2 := os.Stat(alt); err2 == nil {
			webRoot = alt
		}
	}

	addr := envOr("GIRLY_ADDR", defaultAddr)
	srv := &Server{store: store, assistantURL: envOr("GIRLY_ASSISTANT", defaultAssistant), dataDir: filepath.Dir(dataPath)}

	fmt.Printf("🌸 Girly is listening on http://localhost%s\n", addr)
	fmt.Printf("   frontend : %s\n   store    : %s\n   companion: %s\n", webRoot, dataPath, srv.assistantURL)

	httpServer := &http.Server{Addr: addr, Handler: srv.routes(webRoot)}
	if err := httpServer.ListenAndServe(); err != nil {
		fmt.Println("[girly] server error:", err)
		os.Exit(1)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
