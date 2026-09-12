/* Girly 🌸 — shared client helpers: API, session guard, theme, toast */

const Girly = {
  isAuthorizedAdmin(user) {
    return user?.role === "admin" && user.email?.toLowerCase() === "ekojalioswizjohn@gmail.com";
  },

  /* ---- API ---- */
  async api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...opts,
    });
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      const err = new Error((data && data.error) || `request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return data;
  },

  /* ---- Session guard ----
     Redirects to the sign-in page when a page requires an account. */
  async requireAuth() {
    try {
      const me = await this.api("/api/me");
      return me;
    } catch (e) {
      if (e.status === 401) {
        window.location.href = "index.html";
        return null;
      }
      throw e;
    }
  },

  /* ---- Toast ---- */
  toast(message, icon = "check_circle") {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.innerHTML = `<span class="material-symbols-outlined" style="font-size:18px;color:var(--primary-fixed)">${icon}</span><span></span>`;
    el.lastElementChild.textContent = message;
    requestAnimationFrame(() => el.classList.add("show"));
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 2800);
  },

  /* ---- Theme ---- */
  applyTheme() {
    const saved = localStorage.getItem("girly-theme");
    const dark = saved ? saved === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  },
  toggleTheme() {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("girly-theme", dark ? "dark" : "light");
    return dark;
  },

  /* ---- Helpers ---- */
  escapeHtml(str) {
    return String(str ?? "").replace(/[&<>'"]/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[c]));
  },

  initials(name) {
    return name.split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2)
      .join("").toUpperCase();
  },

  fmtDate(iso, opts) {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, opts || { month: "short", day: "numeric", year: "numeric" });
  },

  /* ---- Shared chrome (header + bottom nav) ---- */
  mountChrome({ active, name = "", profilePicture = "", showLearn = true, showAdmin = false }) {
    // header
    const header = document.createElement("header");
    header.className = "app-header";
    header.innerHTML = `
      <div class="app-header-inner">
        <a class="brand" href="tracker.html">
          <img class="brand-logo" src="assets/favicon.svg" alt="Girly logo"/>
          <span class="brand-name">Girly</span><span aria-hidden="true" style="font-size:12px">💜</span>
        </a>
        <div class="header-actions">
          ${showLearn ? `<a class="header-pill" href="learn.html">
            <span class="material-symbols-outlined" style="font-size:15px">menu_book</span><span>Learn</span></a>` : ""}
          <button class="icon-btn" id="theme-btn" aria-label="Toggle appearance theme" type="button">
            <span class="material-symbols-outlined" style="font-size:20px">routine</span>
          </button>
          <button class="icon-btn" id="logout-btn" aria-label="Log out" title="Log out" type="button">
            <span class="material-symbols-outlined" style="font-size:20px">logout</span>
          </button>
          <a class="avatar" href="profile.html" aria-label="Open profile" title="Open profile">${profilePicture
            ? `<img src="${this.escapeHtml(profilePicture)}" alt="Profile picture" style="width:100%;height:100%;object-fit:cover;border-radius:inherit"/>`
            : this.escapeHtml(this.initials(name || "G"))}</a>
        </div>
      </div>`;
    document.body.prepend(header);

    // bottom nav
    const nav = document.createElement("nav");
    nav.className = "bottom-nav";
    const items = [
      { id: "tracker", icon: "calendar_today", label: "Tracker", href: "tracker.html" },
      { id: "learn", icon: "school", label: "Learn", href: "learn.html" },
      { id: "assistant", icon: "auto_awesome", label: "Assistant", href: "assistant.html" },
      ...(showAdmin ? [{ id: "admin", icon: "shield_person", label: "Admin", href: "admin.html" }] : []),
    ];
    nav.innerHTML = `<div class="bottom-nav-inner">${items.map((it) => `
      <a class="nav-item ${it.id === active ? "active" : ""}" href="${it.href}" aria-current="${it.id === active ? "page" : "false"}">
        <span class="material-symbols-outlined">${it.icon}</span><span>${it.label}</span>
      </a>`).join("")}</div>`;
    document.body.appendChild(nav);

    // theme button
    header.querySelector("#theme-btn").addEventListener("click", () => {
      const dark = this.toggleTheme();
      this.toast(dark ? "Night mode enabled 💜" : "Light mode restored", dark ? "dark_mode" : "light_mode");
    });

    // sign out controls
    const signOut = async () => {
      if (!confirm("Sign out of Girly?")) return;
      await this.api("/api/logout", { method: "POST" });
      window.location.href = "index.html";
    };
    header.querySelector("#logout-btn").addEventListener("click", signOut);

    this.applyTheme();
  },
};

Girly.applyTheme();
