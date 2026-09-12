/* Girly 🌸 — learn mode logic */

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;
  Girly.mountChrome({ active: "learn", name: me.user.name, profilePicture: me.user.profile_picture, showAdmin: Girly.isAuthorizedAdmin(me.user) });

  const phases = {
    menstrual: {
      title: "1. Menstrual phase · Days 1–5",
      color: "var(--primary)",
      body: "Your period begins here. Hormone levels are relatively low, and the uterine lining leaves the body as menstrual bleeding. Bleeding commonly lasts 3–7 days, but your normal may be shorter or longer.",
      tips: ["You may notice cramps, backache, fatigue, headaches, or mood changes.", "Warmth, hydration, gentle movement, rest, and comfortable period products can help.", "Log the first day of real flow as Day 1 so your cycle predictions have a useful starting point."],
    },
    follicular: {
      title: "2. Follicular phase · Days 6–13",
      color: "var(--secondary)",
      body: "After bleeding eases, follicles in the ovaries develop and estrogen gradually rises. One follicle usually becomes dominant and prepares an egg for release. This phase can vary in length, especially when cycles are irregular.",
      tips: ["You may notice improving energy, focus, mood, and interest in activity.", "Cervical mucus may become wetter or clearer as ovulation approaches.", "This can be a comfortable time to return to routines, exercise, and activities that need extra energy."],
    },
    ovulatory: {
      title: "3. Ovulatory phase · Around day 14",
      color: "var(--secondary-container)",
      body: "Ovulation is when an ovary releases an egg. The fertile window includes the five days before ovulation and the day of ovulation because sperm can survive for several days. Ovulation timing is an estimate and can shift from cycle to cycle.",
      tips: ["You may notice clear, slippery, stretchy cervical mucus or a mild one-sided twinge.", "Some people notice higher energy, confidence, or sex drive, while others notice no clear signs.", "If avoiding pregnancy, use reliable contraception rather than relying on an app prediction alone."],
    },
    luteal: {
      title: "4. Luteal phase · Days 15–28",
      color: "var(--tertiary)",
      body: "After ovulation, progesterone rises and the body prepares for a possible pregnancy. If pregnancy does not occur, hormone levels fall near the end of this phase and the next period begins. The luteal phase is often around two weeks, though people vary.",
      tips: ["You may notice breast tenderness, bloating, cravings, acne, lower energy, or mood changes.", "Regular meals, sleep, hydration, gentle movement, and planned rest can support you.", "Track symptoms across several cycles; symptoms that severely disrupt daily life deserve medical support."],
    },
  };

  const phaseSheet = document.getElementById("phase-detail-sheet");
  const phaseContent = document.getElementById("phase-detail-content");
  const openPhaseDetails = (selected) => {
    const phase = phases[selected];
    phaseContent.innerHTML = `
      <article class="card-flat stack" style="gap:8px; border-left:4px solid ${phase.color}; background:var(--surface-container-high)">
        <span class="t-label-md" style="font-weight:700;color:${phase.color}">${phase.title}</span>
        <p class="t-body-md" style="margin:0">${phase.body}</p>
        <div class="stack" style="gap:6px; padding-top:4px">
          ${phase.tips.map((tip) => `<div class="row" style="align-items:flex-start; gap:6px"><span class="material-symbols-outlined" style="font-size:17px;color:${phase.color}">check_circle</span><span class="t-body-sm muted">${tip}</span></div>`).join("")}
        </div>
      </article>`;
    document.getElementById("phase-detail-title").textContent = phase.title;
    phaseSheet.classList.add("open");
  };
  document.querySelectorAll(".phase-card").forEach((card) => {
    card.addEventListener("click", () => openPhaseDetails(card.dataset.phase));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPhaseDetails(card.dataset.phase);
      }
    });
  });
  phaseSheet.querySelector("[data-close]").addEventListener("click", () => phaseSheet.classList.remove("open"));
  phaseSheet.addEventListener("click", (event) => {
    if (event.target === phaseSheet) phaseSheet.classList.remove("open");
  });

  // "My period has started" → switch to tracking mode
  document.getElementById("btn-period-arrived").addEventListener("click", async () => {
    const feedback = document.getElementById("celebration-feedback");
    feedback.classList.remove("hidden");
    try {
      await Girly.api("/api/mode", {
        method: "POST",
        body: JSON.stringify({ mode: "tracking", last_period_date: new Date().toISOString().slice(0, 10) }),
      });
      setTimeout(() => (window.location.href = "tracker.html"), 1200);
    } catch (e) {
      feedback.classList.add("hidden");
      Girly.toast(e.message, "error");
    }
  });

  // Ask bar → jump to the assistant with the question prefilled
  const ask = () => {
    const q = document.getElementById("learn-ask").value.trim();
    if (!q) {
      Girly.toast("Type a question first 💜", "info");
      return;
    }
    window.location.href = "assistant.html?q=" + encodeURIComponent(q);
  };
  document.getElementById("learn-ask-btn").addEventListener("click", ask);
  document.getElementById("learn-ask").addEventListener("keydown", (e) => {
    if (e.key === "Enter") ask();
  });

  // checklist persistence (localStorage — tiny & private)
  document.querySelectorAll(".kit-item").forEach((cb, i) => {
    const key = "girly-kit-" + i;
    cb.checked = localStorage.getItem(key) === "1";
    cb.addEventListener("change", () => localStorage.setItem(key, cb.checked ? "1" : "0"));
  });
});
