/* Girly 🌸 — assistant chat logic */

const TIP_ICONS = ["local_cafe", "heat", "water_drop", "self_improvement", "hotel", "bed", "directions_walk", "restaurant"];

let ctxInfo = { name: "there", cycle_day: null, phase_label: "" };

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;
  Girly.mountChrome({ active: "assistant", name: me.user.name });

  ctxInfo.name = me.user.name.split(" ")[0];
  const c = me.cycle;
  document.getElementById("ctx-label").textContent = c.has_data
    ? `Day ${c.cycle_day} · ${c.phase_label}`
    : `${ctxInfo.name} · ${c.phase_label}`;
  document.getElementById("suggest-label").textContent = c.has_data
    ? `Suggested questions for Day ${c.cycle_day}`
    : "Suggested questions";

  renderPromptChips();
  greet(c);

  document.getElementById("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(document.getElementById("chat-input").value.trim());
  });

  // arriving from the Learn page "Ask" bar?
  const prefill = new URLSearchParams(window.location.search).get("q");
  if (prefill) sendMessage(prefill);
});

function renderPromptChips() {
  const chips = [
    ["🍫", "Why am I craving chocolate?"],
    ["🎒", "What should I pack in my bag?"],
    ["🌿", "Explain my fertile window"],
    ["🔮", "How does Girly predict my cycle?"],
    ["🔥", "How do I soothe cramps?"],
    ["🌙", "Why is my mood shifting?"],
  ];
  document.getElementById("prompt-chips").innerHTML = chips
    .map(([emoji, text]) =>
      `<button class="prompt-chip" type="button"><span>${emoji}</span><span>${text}</span></button>`
    ).join("");
  document.querySelectorAll(".prompt-chip").forEach((btn) =>
    btn.addEventListener("click", () => sendMessage(btn.textContent.trim()))
  );
}

function greet(c) {
  let opening = `Hi ${ctxInfo.name}! 💜 I'm your Girly companion.`;
  if (c.has_data) {
    opening += ` Since you're around <b style="color:var(--primary)">Day ${c.cycle_day}</b> of your cycle (${c.phase_label.toLowerCase()}), `;
    opening += c.phase === "menstrual"
      ? "extra rest and warmth are exactly what your body is asking for."
      : c.phase === "luteal"
        ? "you might be noticing progesterone shifts or gentle pre-period cues."
        : c.phase === "ovulatory"
          ? "you may be feeling energetic and glowing."
          : "your energy is likely on the rise.";
  } else {
    opening += " Ask me anything about periods, symptoms, or cycle basics — no question is too small.";
  }
  opening += " How are you feeling today?";
  appendBot(`<p class="t-body-md" style="margin:0">${opening}</p>`);
}

function userBubble(text) {
  const row = document.createElement("div");
  row.className = "bubble-row user fade-in";
  row.innerHTML = `
    <div class="bubble-col user">
      <div class="bubble user-bubble"><p class="t-body-md" style="margin:0">${Girly.escapeHtml(text)}</p></div>
      <span class="bubble-time">${nowTime()}</span>
    </div>`;
  document.getElementById("chat-stream").appendChild(row);
  scrollStream();
}

function appendBot(html, feedback = true) {
  const row = document.createElement("div");
  row.className = "bubble-row fade-in";
  row.innerHTML = `
    <div class="bot-avatar"><span class="material-symbols-outlined" style="font-size:18px">auto_awesome</span></div>
    <div class="bubble-col">
      <div class="bubble bot">${html}</div>
      ${feedback ? `<div class="row" style="justify-content:space-between; padding-inline:4px">
        <span class="bubble-time">${nowTime()}</span>
        <div class="row" style="gap:var(--sp-xs)">
          <button class="icon-btn" style="width:28px;height:28px;background:var(--surface-container)" aria-label="Helpful response" type="button"><span class="material-symbols-outlined" style="font-size:15px">thumb_up</span></button>
          <button class="icon-btn" style="width:28px;height:28px;background:var(--surface-container)" aria-label="Save tip" type="button"><span class="material-symbols-outlined" style="font-size:15px">bookmark_border</span></button>
        </div>
      </div>` : ""}
    </div>`;
  row.querySelectorAll(".icon-btn").forEach((btn) =>
    btn.addEventListener("click", () => Girly.toast("Thanks for the feedback 💜", "favorite"))
  );
  document.getElementById("chat-stream").appendChild(row);
  scrollStream();
}

function thinkingBubble() {
  const row = document.createElement("div");
  row.className = "bubble-row";
  row.id = "bot-thinking";
  row.innerHTML = `
    <div class="bot-avatar" style="animation:pulse 1.2s infinite"><span class="material-symbols-outlined" style="font-size:18px">auto_awesome</span></div>
    <div class="bubble bot typing-dots"><span></span><span></span><span></span></div>`;
  document.getElementById("chat-stream").appendChild(row);
  scrollStream();
}

async function sendMessage(query) {
  const input = document.getElementById("chat-input");
  if (!query) return;
  input.value = "";
  userBubble(query);
  thinkingBubble();

  try {
    const res = await Girly.api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: query }),
    });
    document.getElementById("bot-thinking")?.remove();

    let html = `<p class="t-body-md" style="margin:0">${Girly.escapeHtml(res.reply)}</p>`;
    if (res.tips?.length) {
      html += `<div class="stack" style="gap:var(--sp-xs); padding-top:var(--sp-sm)">` +
        res.tips.map((tip, i) =>
          `<div class="care-tip"><span class="material-symbols-outlined" style="color:var(--primary); font-size:18px">${TIP_ICONS[i % TIP_ICONS.length]}</span><span>${Girly.escapeHtml(tip)}</span></div>`
        ).join("") + `</div>`;
    }
    if (res.doctor) {
      html += `<div class="doctor-note" style="margin-top:var(--sp-sm)">
        <span class="material-symbols-outlined filled" style="color:var(--primary); font-size:18px; flex-shrink:0">info</span>
        <span><b style="color:var(--primary)">Friendly reminder:</b> if symptoms ever become sharp, unmanageable, or disrupt your movement, please reach out to your doctor or gynecologist.</span>
      </div>`;
    }
    appendBot(html);
  } catch (e) {
    document.getElementById("bot-thinking")?.remove();
    appendBot(`<p class="t-body-md" style="margin:0; color:var(--error)">${Girly.escapeHtml(e.message)}</p>`, false);
  }
}

function nowTime() {
  return new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function scrollStream() {
  requestAnimationFrame(() =>
    document.getElementById("chat-stream").lastElementChild
      ?.scrollIntoView({ behavior: "smooth", block: "end" })
  );
}
