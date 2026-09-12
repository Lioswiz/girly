#!/usr/bin/env python3
"""
Girly 🌸 — Cycle Companion Service (Python, stdlib only)

A small, dependency-free HTTP service that powers the in-app assistant.
It answers questions about periods, symptoms, and cycle phases with a
warm, body-positive knowledge base, personalized with the caller's
cycle context supplied by the Go backend.

Endpoints:
    GET  /health  → liveness probe used by the admin console
    POST /chat    → {"message": str, "context": {...}} → assistant reply
"""

import json
import os
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 3000
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

# ---------------------------------------------------------------------------
# Knowledge base: (keyword patterns, response builder)
# Each builder receives the cycle context dict and returns a dict:
#   {"reply": str, "tips": [str], "doctor": bool}
# ---------------------------------------------------------------------------

KB = []


def topic(*words):
    def deco(fn):
        pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)
        KB.append((pattern, fn))
        return fn
    return deco


def phase_intro(ctx):
    """A gentle, phase-aware opening line."""
    phase = ctx.get("phase", "")
    day = ctx.get("cycle_day")
    if phase == "menstrual":
        return "Since you're on your period right now"
    if phase == "ovulatory":
        return f"Around Day {day} (your fertile window)"
    if phase == "follicular":
        return f"In your follicular phase (around Day {day})"
    if phase == "luteal":
        return f"In your late-luteal stretch (around Day {day})"
    return "In Learn Mode, without cycle dates to go on"


@topic("wash", "washing", "shower", "bath", "clean", "cleaning", "douche", "douching")
def _(ctx):
    return {
        "reply": (
            "For everyday menstrual and intimate hygiene, gently wash the vulva (the outside) with "
            "lukewarm water and, if you like, a mild fragrance-free cleanser. The vagina cleans itself, "
            "so douching and scented sprays are not needed and can irritate the natural balance. Pat dry "
            "and change out of damp clothes when you can."
        ),
        "tips": [
            "Wipe front to back after using the toilet",
            "Choose breathable underwear and change it after sweating",
            "Avoid scented pads, washes, sprays, and bath products on the vulva",
        ],
        "doctor": True,
    }


@topic("discharge", "odor", "smell", "itch", "itchy", "burning", "irritation", "irritated")
def _(ctx):
    return {
        "reply": (
            "Clear or white discharge can be a normal part of the cycle, and its amount and texture may "
            "change around ovulation. A new strong or fishy odor, intense itching, burning, pain, sores, "
            "or green, gray, or cottage-cheese-like discharge is worth checking with a clinician because "
            "different causes need different treatment. Avoid douching or using leftover medication."
        ),
        "tips": [
            "Use unscented products and keep the area dry and comfortable",
            "Note when symptoms started and whether they follow a new product or sexual contact",
            "Seek prompt care for pelvic pain, fever, sores, or pregnancy with unusual symptoms",
        ],
        "doctor": True,
    }


@topic("hiv", "aids", "antiretroviral", "viral load", "undetectable", "prep", "pep")
def _(ctx):
    return {
        "reply": (
            "HIV is a virus that can gradually affect the immune system if it is not treated; AIDS is the "
            "most advanced stage of untreated HIV, not a separate way to catch it. HIV can be transmitted "
            "through specific contact with infected blood, semen, vaginal fluids, or breast milk, but not by "
            "hugging, sharing food, toilet seats, or casual contact. Testing is the only way to know your status. "
            "Modern antiretroviral treatment can reduce HIV to an undetectable level, and undetectable HIV is "
            "not sexually transmissible (U=U)."
        ),
        "tips": [
            "Condoms, not sharing needles, and PrEP can reduce the chance of HIV transmission",
            "PEP is emergency medicine that should be started as soon as possible, ideally within 24 hours and no later than 72 hours after a possible exposure",
            "If you may have been exposed, contact a clinic or urgent-care service today for testing and PEP advice",
        ],
        "doctor": True,
    }


@topic("sex", "sexual", "condom", "contraception", "birth control", "sti", "std", "chlamydia", "gonorrhea")
def _(ctx):
    return {
        "reply": (
            "For sexual health, condoms and internal condoms help reduce STI and pregnancy risk when used "
            "correctly every time, while other birth-control methods mainly prevent pregnancy. STI testing "
            "is the only way to know your status, and many infections have no symptoms. A pharmacist, clinic, "
            "or doctor can help you choose private, age-appropriate care."
        ),
        "tips": [
            "Use a new condom for every act of vaginal, anal, or oral sex",
            "Consider routine STI testing after a new partner or possible exposure",
            "Ask urgently about emergency contraception or post-exposure care when timing matters",
        ],
        "doctor": True,
    }


@topic("pregnant", "pregnancy", "pregnancy test", "test positive", "missed period")
def _(ctx):
    return {
        "reply": (
            "A missed period can have many causes, including stress, illness, travel, medication, or pregnancy. "
            "If pregnancy is possible, a home test is generally most useful after the missed period or about "
            "two weeks after sex; follow its instructions and repeat it or contact a clinician if the result "
            "is unclear. Seek urgent care for a positive test with severe one-sided pain, fainting, or heavy bleeding."
        ),
        "tips": [
            "Use first-morning urine when testing early",
            "Record the test date and result for a clinician if needed",
            "Do not take new medicines or supplements for pregnancy without checking first",
        ],
        "doctor": True,
    }


@topic("fever", "faint", "fainted", "unbearable", "unmanageable", "emergency", "severe bleeding", "soaking")
def _(ctx):
    return {
        "reply": (
            "Please seek urgent medical help for severe or worsening pain, fainting, confusion, trouble breathing, "
            "a high fever, possible pregnancy with pain or bleeding, or bleeding that soaks a pad or tampon every "
            "hour for several hours. If you feel unsafe or seriously unwell, contact local emergency services now."
        ),
        "tips": [
            "Ask someone you trust to stay with you if you feel faint or very unwell",
            "Keep track of bleeding, pain, temperature, medicines, and when symptoms began",
            "Do not drive yourself if you may faint",
        ],
        "doctor": True,
    }


@topic("pmdd", "depression", "depressed", "hopeless", "self harm", "suicidal", "panic")
def _(ctx):
    return {
        "reply": (
            "Severe mood symptoms that reliably appear before a period and interfere with daily life can be "
            "more than ordinary PMS, including PMDD. You deserve support, not blame. A clinician can compare "
            "symptoms across at least two cycles and discuss treatment. If you might hurt yourself, contact local "
            "emergency services or a crisis line now and stay with someone you trust."
        ),
        "tips": [
            "Track mood, sleep, and cycle dates daily for two cycles",
            "Tell a trusted person what support would help today",
            "Reduce pressure and prioritize food, water, rest, and safety",
        ],
        "doctor": True,
    }


@topic("cramp", "cramps", "ache", "aching", "pain", "painful", "hurts")
def _(ctx):
    return {
        "reply": (
            f"{phase_intro(ctx)}, mild cramps are completely normal. Your uterus is gently "
            "contracting to shed its lining, which can feel like a dull ache or fullness low in your belly. "
            "Warmth and rest usually soften it beautifully."
        ),
        "tips": [
            "Apply a heating pad or warm compress to your lower belly",
            "Sip warm peppermint, ginger, or chamomile tea",
            "Try child's pose or gentle hip stretches",
        ],
        "doctor": True,
    }


@topic("bloat", "bloated", "bloating", "puffy", "swollen", "water retention")
def _(ctx):
    return {
        "reply": (
            "Bloating is one of the most common pre-period cues. As progesterone peaks and then eases "
            "in the late luteal phase, your body naturally retains a bit more water. It's temporary and "
            "usually eases within the first day or two of your period."
        ),
        "tips": [
            "Stay hydrated — it actually helps your body release retained water",
            "Choose potassium-rich snacks like banana or avocado",
            "Avoid super-salty foods and carbonated drinks today",
        ],
        "doctor": False,
    }


@topic("chocolate", "craving", "cravings", "sugar", "sweet", "hungry", "appetite")
def _(ctx):
    return {
        "reply": (
            "Craving chocolate or sweets before your period is your body being wonderfully honest! "
            "Falling serotonin and shifting energy metabolism in the luteal phase nudge you toward "
            "quick fuel. A square of dark chocolate is genuinely restorative — no guilt needed."
        ),
        "tips": [
            "Pair the treat with magnesium-rich nuts or seeds",
            "A little dark chocolate (70%+) covers the craving with less sugar",
            "Keep meals steady so blood sugar doesn't rollercoaster",
        ],
        "doctor": False,
    }


@topic("mood", "moods", "emotional", "cry", "crying", "irritable", "irritated", "sad", "anxious", "anxiety", "pms")
def _(ctx):
    return {
        "reply": (
            "Mood shifts before a period are real and valid — not imagined. In the late luteal phase, "
            "progesterone and estrogen ebb, which influences serotonin, sleep, and emotional resilience. "
            "Being extra gentle with yourself is the right instinct."
        ),
        "tips": [
            "Protect sleep — even 30 extra minutes helps emotional regulation",
            "A short walk in daylight steadies mood chemistry",
            "Journal one line a day to spot your own patterns",
        ],
        "doctor": True,
    }


@topic("first period", "first time", "started my period", "haven't started", "when will i get", "first one")
def _(ctx):
    return {
        "reply": (
            "Most people get their first period between ages 10 and 15, but everyone's timeline is "
            "unique — and there's no 'right day'. It often starts subtly: a few drops of brown or "
            "rusty-colored spotting in your underwear, not a dramatic movie moment. Your body knows "
            "exactly what to do."
        ),
        "tips": [
            "Keep 2–3 pads in a discreet pouch so you always feel prepared",
            "Brown or dark red blood at the start is completely normal",
            "Marking the date helps you learn your own rhythm",
        ],
        "doctor": False,
    }


@topic("fertile", "fertility", "ovulation", "ovulate", "ovulating", "conceive", "pregnan")
def _(ctx):
    d = ctx.get("next_period_date", "")
    extra = f" Based on your logs, your next period is estimated around {d}." if d else ""
    return {
        "reply": (
            "Your fertile window is the ~6 days when pregnancy is possible: the 5 days before ovulation "
            "plus ovulation day itself. Ovulation usually happens about 14 days before your next period "
            "starts. Cervical mucus often becomes clear and stretchy — like egg white — during this time."
            + extra
        ),
        "tips": [
            "Egg-white cervical mucus is the classic fertile sign",
            "A mild one-sided twinge can mark ovulation (mittelschmerz)",
            "Energy and confidence often peak around ovulation",
        ],
        "doctor": False,
    }


@topic("irregular", "irregularity", "missed", "late", "skipped", "normal cycle", "how long", "cycle length")
def _(ctx):
    return {
        "reply": (
            "Cycles between 21 and 35 days are considered typical, and it's normal for them to vary "
            "by a few days each month — especially in the first few years after your first period, "
            "during stress, big travel, or intense exercise. Girly learns your average over time to "
            "make gentler predictions."
        ),
        "tips": [
            "Log each period start — patterns emerge after 3+ cycles",
            "Big stress or illness can shift a cycle; one off month is okay",
            "Track how you feel, not just the dates",
        ],
        "doctor": True,
    }


@topic("pad", "pads", "tampon", "tampons", "cup", "menstrual cup", "hygiene", "wipe", "wipes", "underwear")
def _(ctx):
    return {
        "reply": (
            "Pads, tampons, and menstrual cups are all valid choices — whatever feels comfortable is "
            "right for you. Pads are the easiest starting point; change them every 3–4 hours. If you "
            "use tampons, use the lowest absorbency you need and change them every 4–8 hours."
        ),
        "tips": [
            "Change pads every 3–4 hours on heavier days",
            "Never wear a tampon longer than 8 hours",
            "Unscented, gentle wipes are best for freshening up",
        ],
        "doctor": False,
    }


@topic("flow", "heavy", "bleeding", "bleed", "spotting", "blood", "brown blood", "color")
def _(ctx):
    return {
        "reply": (
            "Period blood ranges from bright red to dark brown — brown just means the blood took "
            "longer to leave your body and oxidized, which is completely harmless. A typical period "
            "loses about 2–3 tablespoons total across 3–7 days."
        ),
        "tips": [
            "Spotting at the very start or end is normal",
            "Small clots (smaller than a grape) are common on heavy days",
            "Soaking through a pad an hour for several hours is a doctor flag",
        ],
        "doctor": True,
    }


@topic("tired", "fatigue", "exhausted", "energy", "sleep", "sleepy", "insomnia")
def _(ctx):
    return {
        "reply": (
            "Feeling more tired before or during your period is your body asking for gentler pacing. "
            "Hormonal shifts can dip energy and disturb sleep quality. Rest isn't laziness — it's "
            "recovery."
        ),
        "tips": [
            "Aim for a consistent bedtime this week",
            "Iron-rich foods (lentils, spinach, eggs) replenish what period blood loses",
            "A 20-minute afternoon nap beats fighting through it",
        ],
        "doctor": False,
    }


@topic("exercise", "workout", "gym", "yoga", "run", "running", "train", "sport")
def _(ctx):
    phase = ctx.get("phase", "")
    if phase == "menstrual":
        reply = "Movement is still welcome during your period if it feels good — just downshift. Gentle walking, stretching, or restorative yoga often ease cramps better than total stillness."
    elif phase == "follicular":
        reply = "Your follicular phase is a lovely window for building strength and trying harder workouts — energy and recovery tend to be on your side."
    elif phase == "ovulatory":
        reply = "Around ovulation many people feel strongest and most energized — a great time for higher-intensity sessions or social sports."
    else:
        reply = "In the luteal phase, perceived effort can feel higher and recovery is slower. Swapping one intense session for gentle movement is smart training, not weakness."
    return {
        "reply": reply,
        "tips": [
            "Listen to energy first, the plan second",
            "Warm up longer during your period and luteal phase",
            "Hydrate well around any workout",
        ],
        "doctor": False,
    }


@topic("predict", "prediction", "how does girly", "algorithm", "estimate", "accurate")
def _(ctx):
    return {
        "reply": (
            "Girly learns your rhythm from the period start dates you log. It averages the gaps "
            "between your recent cycles, projects your next start from your latest one, and marks a "
            "±2 day window around it — because bodies aren't clocks. Ovulation is estimated at 14 "
            "days before the projected next period, and your fertile window spans the 5 days before "
            "that plus ovulation day. Estimates get cozier with every cycle you log."
        ),
        "tips": [
            "Log every period start to sharpen predictions",
            "Predictions are estimates, not medical advice",
        ],
        "doctor": False,
    }


@topic("headache", "migraine", "dizzy", "nausea", "acne", "skin", "backache", "back pain", "breast", "tender")
def _(ctx):
    return {
        "reply": (
            "Headaches, queasiness, breakouts, tender breasts, and backaches are all common "
            "cycle companions — hormonal shifts touch many systems, not just the uterus. They "
            "usually cluster in the days just before a period."
        ),
        "tips": [
            "Hydration and steady meals soften hormone headaches",
            "A warm compress helps both backache and cramping",
            "Gentle skincare (no harsh scrubs) during breakouts",
        ],
        "doctor": True,
    }


@topic("pack", "bag", "school", "kit", "emergency", "prepare", "prepared")
def _(ctx):
    return {
        "reply": (
            "A cute little zipper pouch in your bag means you're ready anywhere: "
            "it's the single best calm-your-mind move. Here's the classic discreet kit."
        ),
        "tips": [
            "2–3 regular pads with wings",
            "Spare comfy underwear in a zip bag",
            "Gentle unscented wipes",
            "An adhesive heat patch for stealth cramp relief",
        ],
        "doctor": False,
    }


@topic("doctor", "gynecologist", "see a doctor", "medical", "worry", "worried", "concerned")
def _(ctx):
    return {
        "reply": (
            "Reaching out to a doctor, school nurse, or trusted adult is always a smart, "
            "self-advocating move — you don't need to wait for a crisis. Definitely check in if: "
            "pain regularly stops your daily life, flow soaks a pad an hour for hours, cycles are "
            "consistently shorter than 21 or longer than 35 days, or you simply feel uneasy."
        ),
        "tips": [
            "Write down what you noticed and when — it makes visits easier",
            "No question is too small or embarrassing to ask",
        ],
        "doctor": False,
    }


FALLBACK_REPLIES = [
    (
        "I'm here for you! 🌸 Hormones shift across your cycle, so how you feel day-to-day is often "
        "your body narrating its own rhythm. Could you tell me a little more — is it about cramps, "
        "mood, flow, or timing?"
    ),
    (
        "That's a thoughtful question! While I keep learning, the classic gentle advice holds: "
        "hydrate, rest kindly, and track what you notice. Ask me about cramps, cravings, your "
        "fertile window, or first-period prep anytime."
    ),
]


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "GirlyCompanion/1.0"

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/health", "/"):
            self._send_json(200, {
                "status": "ok",
                "service": "girly-companion",
                "version": "1.0",
                "port": PORT,
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/chat":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 1 << 20)
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid JSON"})
            return

        message = str(data.get("message", "")).strip()
        ctx = data.get("context") or {}
        if not message:
            self._send_json(400, {"error": "message is required"})
            return

        reply = respond(message, ctx)
        self._send_json(200, reply)

    def log_message(self, fmt, *args):
        print(f"[companion] {self.command} {self.path}")


def respond(message, ctx):
    if GEMINI_API_KEY:
        result = ask_gemini(message, ctx)
        if result is not None:
            return decorate(result, ctx)

    generic_terms = {"ache", "aching", "pain", "painful", "hurts", "symptom", "symptoms"}
    best = None
    for order, (pattern, builder) in enumerate(KB):
        match = pattern.search(message)
        if not match:
            continue
        matched_text = match.group(0)
        specific = matched_text.lower() not in generic_terms
        score = (specific, len(matched_text.split()), len(matched_text), -order)
        if best is None or score > best[0]:
            best = (score, builder)

    if best is not None:
        result = best[1](ctx)
        return decorate(result, ctx)

    result = {"reply": random.choice(FALLBACK_REPLIES), "tips": [], "doctor": False}
    return decorate(result, ctx)


def ask_gemini(message, ctx):
    """Ask Gemini a general question while keeping the local fallback available."""
    prompt = (
        "You are Girly, a warm and concise health education assistant. Answer the user's question "
        "directly and accurately. Cover general health, menstrual health, sexual health, hygiene, "
        "and everyday wellness. Do not diagnose, prescribe, or claim certainty. For urgent symptoms "
        "or possible pregnancy, STI, HIV, self-harm, or abuse concerns, recommend prompt professional "
        "help and mention emergency services when appropriate. Use plain language and avoid judgment. "
        "Return only the answer text, without markdown headings or a disclaimer.\n\n"
        f"Cycle context (use only when relevant): {json.dumps(ctx, ensure_ascii=False)}\n"
        f"User question: {message}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 700},
    }).encode("utf-8")
    query = urllib.parse.urlencode({"key": GEMINI_API_KEY})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL)}:generateContent?{query}"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text:
            return None
        return {"reply": text, "tips": [], "doctor": False}
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError):
        return None


def decorate(result, ctx):
    """Attach a phase-aware footer and suggested follow-up chips."""
    phase = ctx.get("phase", "")
    footer = ""
    if phase == "luteal":
        d = ctx.get("days_until_period")
        if isinstance(d, int) and 0 <= d <= 6:
            footer = f" Your next period is estimated in about {d} day{'s' if d != 1 else ''} — extra gentleness is perfect timing."
    elif phase == "menstrual":
        footer = " Cozy rest and hydration are exactly what your body is asking for today."
    elif phase == "ovulatory":
        footer = " You're in your fertile window right now — energy and glow often peak here."

    reply = result["reply"]
    if footer and footer not in reply:
        reply += footer

    return {
        "reply": reply,
        "tips": result.get("tips", []),
        "doctor": result.get("doctor", False),
        "disclaimer": "Girly provides educational insights and is not a medical diagnosis.",
    }


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"🌸 Girly companion service listening on http://{HOST}:{PORT}")
    print("   endpoints: GET /health · POST /chat")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[companion] shutting down — bye 💜")


if __name__ == "__main__":
    main()
