#!/usr/bin/env python3
"""
Girly 🌸 — Cycle Companion Service (Python, stdlib only)

A small, dependency-free HTTP service that powers the in-app assistant.
It answers questions about periods, symptoms, cycle phases, general health,
and personal hygiene with a warm, body-positive knowledge base, personalized
with the caller's cycle context supplied by the main backend.

Anything the knowledge base doesn't recognise is sent to an AI service
(Anthropic Messages API) when a key is configured via GIRLY_AI_API_KEY or
ANTHROPIC_API_KEY — without a key the companion stays fully offline and
answers from the built-in topics alone.

Endpoints:
    GET  /health  → liveness probe used by the admin console
    POST /chat    → {"message": str, "context": {...}} → assistant reply
"""

import json
import os
import random
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 3000

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


@topic("fertile", "fertility", "ovulation", "ovulate", "ovulating", "conceive")
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


@topic("irregular", "irregularity", "missed", "late", "skipped", "normal cycle", "cycle length")
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


@topic("tss", "toxic shock", "tampon too long", "tampon in too long", "left in too long", "forgot my tampon", "forgot to change my tampon")
def _(ctx):
    return {
        "reply": (
            "Toxic shock syndrome (TSS) is a rare but serious infection historically linked "
            "to leaving tampons in too long. Warning signs come on fast: sudden high fever, "
            "vomiting, diarrhoea, a sunburn-like rash, dizziness, or muscle aches while using "
            "a tampon. If that happens, remove the tampon and get medical help immediately — "
            "it's an emergency, not a wait-and-see situation."
        ),
        "tips": [
            "Change tampons every 4–8 hours; use the lowest absorbency that works",
            "Alternate tampons with pads, especially overnight",
            "Sudden fever + rash + vomiting while using a tampon = seek care now",
        ],
        "doctor": True,
    }


@topic("pad", "pads", "tampon", "tampons", "cup", "menstrual cup", "hygiene", "wipe", "wipes", "underwear", "period underwear", "reusable pads")
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


@topic("exercise", "workout", "gym", "yoga", "run", "running", "train", "sport", "swim", "swimming", "dance", "dancing")
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


@topic("headache", "migraine", "dizzy", "nausea", "backache", "back pain", "tender")
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


# ---------------------------------------------------------------------------
# Knowledge base — general health, menstrual health & personal hygiene.
# These are checked after the core topics above (so the core topics win
# conflicts); anything that matches nothing here goes to the AI layer.
# ---------------------------------------------------------------------------

# --- wellbeing topics where safety comes first ------------------------------

@topic("eating disorder", "anorexia", "bulimia", "binge", "purge", "making myself throw up", "restricting food")
def _(ctx):
    return {
        "reply": (
            "Thank you for trusting me with this — it takes courage. Struggles with food and "
            "body image are real health concerns, not failures of willpower, and they deserve "
            "kind, professional support. You matter far more than any number on a scale."
        ),
        "tips": [
            "Tell one trusted adult today — a parent, school nurse, counsellor, or doctor",
            "Regular meals steady both mood and energy while you get support",
            "NEDA and local helplines offer free, confidential guidance",
        ],
        "doctor": True,
    }


@topic("depressed", "depression", "hopeless", "self harm", "self-harm", "suicidal", "kill myself", "want to die", "can't go on", "cant go on")
def _(ctx):
    return {
        "reply": (
            "I'm really glad you told me. Feeling this heavy is exhausting, and you shouldn't "
            "have to carry it alone. These feelings can change with the right support — please "
            "reach out to a trusted adult, doctor, or a crisis line in your country right now. "
            "You deserve care and kindness, including from yourself. 💜"
        ),
        "tips": [
            "Contact a crisis line or emergency services if you feel unsafe",
            "Tell one person you trust how you're feeling today",
            "Gentle basics help while you wait for support: daylight, water, rest",
        ],
        "doctor": True,
    }


# --- menstrual health ---------------------------------------------------------

@topic("pregnan", "am i pregnant", "could i be pregnant", "unprotected", "plan b", "morning after", "emergency contraception")
def _(ctx):
    return {
        "reply": (
            "Pregnancy is possible any time semen reaches the vagina, especially around "
            "ovulation — but the only way to know is a test. Home urine tests are reliable "
            "from about the first day of a missed period, and a doctor or clinic can confirm "
            "earlier. If there's a chance of pregnancy and it wasn't planned, a pharmacist, "
            "doctor, or clinic can talk you through the options confidentially."
        ),
        "tips": [
            "Take a home test from the first day of a missed period (morning urine is best)",
            "Emergency contraception works best within 24 hours and is available at pharmacies",
            "Stress and illness can also delay a period — a late period isn't proof alone",
        ],
        "doctor": True,
    }


@topic("birth control", "contraception", "the pill", "iud", "implant", "condom", "condoms")
def _(ctx):
    return {
        "reply": (
            "There are many contraception options — condoms, the pill, patches, rings, IUDs, "
            "implants, and injections — each with different effectiveness, routines, and side "
            "effects. Condoms are the only ones that also protect against infections. A doctor "
            "or clinic can help you choose what fits your body and life; it's a completely "
            "normal thing to ask about."
        ),
        "tips": [
            "Condoms protect against both pregnancy and STIs",
            "Hormonal methods need consistent use to be effective",
            "Pharmacists and family-planning clinics give confidential advice",
        ],
        "doctor": True,
    }


@topic("what is a period", "what's a period", "whats a period", "what are periods", "why do periods", "why do we have", "periods work", "period happen", "menstruation", "uterus lining", "cycle explained", "get my cycle")
def _(ctx):
    return {
        "reply": (
            "A period is your body's monthly reset. Each cycle, hormones prepare the uterus "
            "with a soft lining in case a pregnancy begins; if it doesn't, the lining sheds "
            "and leaves through the vagina — that's the bleeding you see. A full cycle runs "
            "from the first day of one period to the first day of the next, typically 21–35 "
            "days. Totally natural, and tracking it helps you understand your own rhythm."
        ),
        "tips": [
            "Day 1 of a cycle is the first day of bleeding",
            "Bleeding usually lasts 3–7 days",
            "Log each start date — patterns emerge after a few cycles",
        ],
        "doctor": False,
    }


@topic("pmdd")
def _(ctx):
    return {
        "reply": (
            "PMDD (premenstrual dysphoric disorder) is like a much more intense PMS: in the "
            "one to two weeks before a period, mood can drop sharply — deep sadness, anxiety, "
            "anger, or feeling overwhelmed — often with physical symptoms too, and it eases "
            "soon after bleeding starts. It's a real, treatable condition, not 'just moodiness'."
        ),
        "tips": [
            "Tracking mood and cycle dates together helps a doctor see the pattern",
            "Regular sleep, movement, and limiting caffeine and alcohol soften symptoms",
            "Treatments range from therapy to medication — worth a doctor's visit",
        ],
        "doctor": True,
    }


@topic("pcos", "polycystic")
def _(ctx):
    return {
        "reply": (
            "PCOS (polycystic ovary syndrome) is a common hormonal condition where periods "
            "become irregular or infrequent, and androgen levels rise — often showing up as "
            "acne, extra facial or body hair, or weight changes. Ovaries may carry many small "
            "cysts. It can't be cured, but it's very manageable with lifestyle changes and "
            "medication, and it's a leading reason to check in when cycles stay irregular."
        ),
        "tips": [
            "Irregular or absent periods for months deserves a doctor's assessment",
            "Balanced meals and regular movement improve symptoms for many",
            "Ask about ultrasound and hormone blood tests for diagnosis",
        ],
        "doctor": True,
    }


@topic("endometriosis")
def _(ctx):
    return {
        "reply": (
            "Endometriosis is where tissue similar to the uterine lining grows outside the "
            "uterus — on ovaries, fallopian tubes, or elsewhere. It causes periods that are "
            "seriously painful (painkillers barely help), pain during sex or bowel movements, "
            "and sometimes heavy bleeding. Diagnosis often takes years, so persistent "
            "period pain that disrupts your life is always worth pursuing with a gynecologist."
        ),
        "tips": [
            "Track pain intensity alongside your cycle — it strengthens your case",
            "Pain that stops you attending school or work is not 'normal period pain'",
            "A gynecologist can discuss hormone treatment or laparoscopy",
        ],
        "doctor": True,
    }


# (toxic shock syndrome is defined above, before the period-products topic,
# so "my tampon was in too long" reaches it before the products answer)


@topic("discharge", "leaking", "wet down there", "everyday discharge")
def _(ctx):
    return {
        "reply": (
            "Everyday vaginal discharge is completely normal — it's how the vagina cleans and "
            "protects itself. Healthy discharge shifts through your cycle: milky white or "
            "cloudy after your period, clear and stretchy like egg white around ovulation, "
            "then thicker and white before your period. What's not normal: a strong fishy "
            "smell, grey/green/frothy colour, or itching and burning alongside a change."
        ),
        "tips": [
            "Clear, white, or slightly yellow discharge is healthy",
            "Egg-white stretchy discharge marks your fertile window",
            "Sudden change in smell, colour, or texture with itching → get checked",
        ],
        "doctor": True,
    }


@topic("yeast", "thrush", "candida")
def _(ctx):
    return {
        "reply": (
            "A yeast infection happens when naturally-present Candida overgrows — classic "
            "signs are thick white 'cottage cheese' discharge, intense itching, and soreness. "
            "They're common after antibiotics, in tight synthetic clothing, or around your "
            "period. Pharmacy treatments (antifungal creams and pessaries) usually clear them "
            "up quickly; recurring infections are worth a doctor's visit."
        ),
        "tips": [
            "Cotton underwear and loose clothes let the area breathe",
            "Avoid scented soaps and sprays down there",
            "See a doctor if it keeps coming back or doesn't clear in a week",
        ],
        "doctor": True,
    }


@topic("uti", "urinary tract", "burning when i pee", "burns when i pee", "burning pee", "peeing hurts", "pee burns", "stings when i pee", "wee stings")
def _(ctx):
    return {
        "reply": (
            "A burning, stinging feeling when you pee — often with a constant urge to go and "
            "sometimes cloudy or strong-smelling urine — usually means a urinary tract "
            "infection (UTI). They're very common and need antibiotic treatment from a doctor "
            "or pharmacist; untreated UTIs can travel up to the kidneys. Drink plenty of water "
            "and get seen promptly."
        ),
        "tips": [
            "Always wipe front to back after using the toilet",
            "Pee after sex and whenever you feel the urge — don't hold it",
            "Fever, back pain, or blood in urine means see a doctor urgently",
        ],
        "doctor": True,
    }


@topic("bacterial vaginosis", "bv")
def _(ctx):
    return {
        "reply": (
            "Bacterial vaginosis (BV) is a common imbalance where the vagina's usual bacteria "
            "are disrupted — the tell-tale sign is thin greyish discharge with a fishy smell, "
            "especially after sex or a period. It's not an STI and not a hygiene failure; in "
            "fact, washing too much or douching makes it more likely. A doctor or pharmacist "
            "can confirm and treat it with a short course of antibiotics."
        ),
        "tips": [
            "Wash the vulva with warm water only — no douching, no scented products",
            "BV needs treatment; it doesn't usually clear on its own",
            "It can recur — mention repeat episodes to your doctor",
        ],
        "doctor": True,
    }


@topic("itch", "itchy", "itching")
def _(ctx):
    return {
        "reply": (
            "An itchy vulva or vagina usually has a simple cause — irritation from a new soap, "
            "detergent, tight clothing, or a yeast infection. Cool water, cotton underwear, "
            "and avoiding the irritant often settle it. If itching comes with unusual "
            "discharge, odour, pain when peeing, or doesn't ease in a few days, get it "
            "checked — yeast, BV, and some skin conditions all need specific treatment."
        ),
        "tips": [
            "Switch to unscented, gentle washes for your body and laundry",
            "Don't scratch — a cool compress soothes better",
            "Persistent itching plus discharge changes deserves a check-up",
        ],
        "doctor": True,
    }


@topic("odor down there", "smell down there", "vaginal odor", "vaginal smell", "fishy", "smells fishy")
def _(ctx):
    return {
        "reply": (
            "Every vagina has a natural, mild scent — that's normal and healthy. But a strong "
            "fishy or unpleasant smell signals something's off, most often bacterial vaginosis "
            "(grey, thin discharge) or a forgotten tampon. The fix isn't washing more or using "
            "scented products — those make it worse — it's getting the actual cause treated."
        ),
        "tips": [
            "Warm water and gentle cleansing outside only — never douche",
            "Change pads and tampons regularly during your period",
            "A fishy smell with unusual discharge → pharmacy or doctor",
        ],
        "doctor": True,
    }


@topic("menopause", "perimenopause")
def _(ctx):
    return {
        "reply": (
            "Menopause is when periods stop for good, confirmed after 12 months without one — "
            "typically in the late 40s to early 50s. Perimenopause is the years-long run-up, "
            "when cycles become irregular, and hot flushes, sleep changes, and mood shifts can "
            "appear. It's a natural transition, and a doctor can offer real help — from "
            "lifestyle adjustments to hormone therapy — if symptoms disrupt daily life."
        ),
        "tips": [
            "Cycle tracking makes the irregular stage much easier to read",
            "Cool bedrooms, layered clothing, and strength training ease symptoms",
            "Bleeding after menopause should always be checked promptly",
        ],
        "doctor": True,
    }


@topic("period poop", "poop", "diarrhea", "diarrhoea", "constipation", "bowel", "digestion", "gassy", "gut")
def _(ctx):
    return {
        "reply": (
            "Yes — 'period poop' is real! Prostaglandins, the same hormone-like chemicals that "
            "trigger cramps, also speed up your bowel, so looser stools and more frequent "
            "poos are common in the first days of a period. Others get constipated before it "
            "starts. It's normal and settles as the period eases."
        ),
        "tips": [
            "Hydrate and choose gentle, fibre-rich foods around your period",
            "Warm drinks help both cramps and sluggish digestion",
            "Blood in stool or severe gut pain is separate — get that checked",
        ],
        "doctor": False,
    }


# --- general health ------------------------------------------------------------

@topic("fever", "sick", "flu", "a cold", "cold symptoms", "runny nose", "cough", "coughing", "sore throat", "temperature", "illness")
def _(ctx):
    return {
        "reply": (
            "When you're run down with a cold or flu — especially during or before your "
            "period, when immunity dips a little — rest really is the treatment. Your body is "
            "busy fighting something off; give it sleep, fluids, and simple food. Most bugs "
            "ease within a week."
        ),
        "tips": [
            "Fluids and sleep do more than any supplement",
            "Eat what appeals — soup, fruit, toast all count",
            "High fever over 3 days, trouble breathing, or severe pain → see a doctor",
        ],
        "doctor": True,
    }


@topic("weight", "lose weight", "gain weight", "dieting", "overweight", "underweight")
def _(ctx):
    return {
        "reply": (
            "A healthy weight is about how you feel and function, not a number alone — and "
            "weight naturally shifts a little across your cycle thanks to water retention. "
            "If you want to change your weight, do it kindly: steady meals, movement you "
            "enjoy, and patience. Dramatic diets almost always backfire."
        ),
        "tips": [
            "Aim for steady changes you could keep up for years, not weeks",
            "Period-week 'gain' is usually water — ignore the scale then",
            "Talk to a doctor or dietitian before restricting anything",
        ],
        "doctor": False,
    }


@topic("diet", "food", "foods", "eat", "nutrition", "eating healthy", "meals", "vegetarian", "vegan", "protein", "breakfast", "snacks")
def _(ctx):
    return {
        "reply": (
            "Eating well across your cycle genuinely helps how you feel: iron-rich foods "
            "replenish what period blood loses, steady meals keep blood sugar (and mood) "
            "even, and magnesium-rich foods may soften cramps and cravings. You don't need a "
            "perfect diet — just steady, colourful, balanced most of the time."
        ),
        "tips": [
            "Iron + vitamin C together (lentils with peppers) absorbs best",
            "Magnesium sources: dark chocolate, nuts, seeds, leafy greens",
            "Don't skip breakfast — it steadies the whole day's energy",
        ],
        "doctor": False,
    }


@topic("vitamin", "vitamins", "iron", "supplement", "supplements", "magnesium", "zinc", "calcium")
def _(ctx):
    return {
        "reply": (
            "Supplements can help when you have a real gap — iron is genuinely useful if your "
            "periods are heavy, and many people benefit from vitamin D in winter. But food "
            "first: supplements can't out-supplement a poor diet, and more isn't better "
            "(excess iron especially isn't harmless). If you suspect a deficiency, a simple "
            "blood test tells you exactly what you need."
        ),
        "tips": [
            "Heavy periods + fatigue = ask about a ferritin blood test",
            "Take iron with orange juice, not tea or coffee",
            "Never mega-dose supplements without a confirmed deficiency",
        ],
        "doctor": True,
    }


@topic("water", "hydrated", "hydration", "dehydrated", "drink enough")
def _(ctx):
    return {
        "reply": (
            "Hydration quietly improves almost everything cycle-related: it eases bloating, "
            "can soften headaches and cramps, and keeps energy steadier. Around 6–8 glasses "
            "spread through the day is a good target, more in heat or after exercise. If your "
            "urine is pale straw colour, you're doing it right."
        ),
        "tips": [
            "Carry a water bottle — you'll drink far more without thinking",
            "Herbal teas and water-rich fruit count too",
            "Headache + dark urine = drink up before reaching for painkillers",
        ],
        "doctor": False,
    }


@topic("stress", "stressed", "overwhelmed", "burnout", "burnt out", "exam", "exams", "pressure")
def _(ctx):
    return {
        "reply": (
            "Stress and cycles talk to each other: high stress can delay or change a period, "
            "and hormonal shifts can lower your stress buffer. It's not in your head, and "
            "it's not a character flaw. Small, repeated resets — breathing, walks, saying no "
            "to one thing — work better than waiting for a holiday that never comes."
        ),
        "tips": [
            "Try 4-7-8 breathing: inhale 4s, hold 7s, exhale 8s — three rounds",
            "Protect sleep first; everything else is easier rested",
            "Big stress for a long time is worth talking through with someone",
        ],
        "doctor": False,
    }


@topic("immune", "immunity", "boost my immune")
def _(ctx):
    return {
        "reply": (
            "Your immune system isn't boosted by any single trick — it's supported by the "
            "boring-but-powerful basics: consistent sleep, varied food, movement, and keeping "
            "stress in check. Around your period, immunity dips slightly, which is why you "
            "might feel more run down then — extra rest that week genuinely helps."
        ),
        "tips": [
            "Sleep is the single biggest immune lever you control",
            "Eat the rainbow — variety feeds your gut, where immunity lives",
            "Wash hands before eating; it's simple and it works",
        ],
        "doctor": False,
    }


@topic("acne", "pimple", "pimples", "breakout", "breakouts", "skincare", "face wash", "oily skin", "dry skin", "razor bump")
def _(ctx):
    return {
        "reply": (
            "Cycle acne is classic — hormonal shifts before a period boost oil production, so "
            "breakouts cluster on the chin and jaw. Keep it simple: a gentle cleanser morning "
            "and night, oil-free moisturiser, and hands off. Picking and scrubbing hard make "
            "spots last longer and scar. Consistency beats any miracle product."
        ),
        "tips": [
            "Cleanse gently twice a day — over-washing backfires",
            "Change pillowcases weekly and clean your phone screen",
            "Painful, cystic, or scarring acne is very treatable — see a doctor",
        ],
        "doctor": True,
    }


@topic("puberty", "developing", "breast", "breasts", "bra", "bras", "growing up", "body is changing", "when will i develop")
def _(ctx):
    return {
        "reply": (
            "Puberty unfolds on its own timeline, and every bit of variation is normal — "
            "breast buds can start anywhere from about 8 to 13, often one side before the "
            "other, and body shape, height, and hair all change in their own order. It's your "
            "body doing exactly what it's built to do, at its own pace."
        ),
        "tips": [
            "One breast growing faster than the other is common and usually evens out",
            "Get fitted for a bra when comfort asks for one — no deadline otherwise",
            "Questions are welcome here; a school nurse is great for the rest",
        ],
        "doctor": False,
    }


# --- personal hygiene ----------------------------------------------------------

@topic("douche", "douching", "intimate wash", "feminine wash", "wash down there", "vulva", "ph balance", "ph imbalance", "feminine hygiene")
def _(ctx):
    return {
        "reply": (
            "The vagina is self-cleaning — it really is. The vulva (outside) just needs warm "
            "water and gentle cleansing; the vagina (inside) needs nothing at all. Douches, "
            "intimate washes, and scented sprays upset the healthy bacteria and make "
            "infections like BV more likely, not less. Plain water and cotton underwear are "
            "the whole routine."
        ),
        "tips": [
            "Warm water outside only — never wash inside the vagina",
            "Skip scented soaps, sprays, and douches entirely",
            "If odour or discharge changes, treat the cause — don't mask it",
        ],
        "doctor": True,
    }


@topic("wash my hands", "handwashing", "hand washing", "germs", "sanitizer", "sanitiser")
def _(ctx):
    return {
        "reply": (
            "Handwashing is the most underrated health habit there is — it prevents colds, "
            "stomach bugs, and infections far better than most things. Twenty seconds with "
            "soap, covering fronts, backs, between fingers, and nails, before eating and "
            "after the bathroom, does the job."
        ),
        "tips": [
            "20 seconds of soap — hum a short song and you're there",
            "Wash before eating and after the bathroom, always",
            "Sanitiser works when soap isn't around, but soap wins when available",
        ],
        "doctor": False,
    }


@topic("feet", "foot", "smelly feet", "stinky feet", "shoes smell")
def _(ctx):
    return {
        "reply": (
            "Smelly feet happen when sweat meets bacteria inside shoes — some feet just "
            "sweat more, and teenagers' feet famously do. It's very fixable: air your shoes "
            "between wears, let feet breathe at home, and wash and fully dry them daily, "
            "especially between the toes."
        ),
        "tips": [
            "Rotate shoes — never wear the same pair two days running",
            "Cotton or wool socks beat synthetics; change them daily",
            "Itching, peeling skin, or white between toes could be athlete's foot — treatable at a pharmacy",
        ],
        "doctor": False,
    }


@topic("teeth", "tooth", "dentist", "floss", "bad breath", "brush", "brushing", "mouthwash")
def _(ctx):
    return {
        "reply": (
            "Dental care matters cycle-wise too — hormonal shifts can make gums more "
            "sensitive and prone to bleeding around your period. The essentials: brush twice "
            "a day for two minutes, floss daily, and keep sugary drinks to mealtimes. If your "
            "breath is despite-good-brushing bad, it can signal dehydration or a gut/tonsil "
            "issue worth mentioning to a dentist."
        ),
        "tips": [
            "Two minutes, twice a day, gentle circles at the gumline",
            "Floss before brushing so fluoride reaches between teeth",
            "Gums that bleed every time you brush deserve a dental check",
        ],
        "doctor": False,
    }


@topic("body odor", "bo", "sweat", "sweaty", "deodorant", "antiperspirant", "armpit", "armpits", "smelly")
def _(ctx):
    return {
        "reply": (
            "Body odour is completely normal — sweat itself is odourless until skin bacteria "
            "break it down, and puberty amps up both sweating and scent. A daily shower, "
            "deodorant (masks odour) or antiperspirant (blocks sweat), and breathable fabrics "
            "handle it easily. Smelling stronger around your period is common too."
        ),
        "tips": [
            "Apply antiperspirant at night — it works best on dry skin",
            "Shower after sweating heavily and dry fully before dressing",
            "Sudden strong odour changes can be hormonal — worth noting, rarely serious",
        ],
        "doctor": False,
    }


@topic("shave", "shaving", "razor", "waxing", "hair removal", "body hair", "pubic hair", "unwanted hair", "ingrown hair")
def _(ctx):
    return {
        "reply": (
            "Body hair — including pubic hair — is completely normal, and removing any of it "
            "is purely your choice; there's no hygiene requirement either way. If you do "
            "shave: sharp razor, warm water, shave with hair growth to protect skin, and "
            "moisturise after. Ingrown hairs ease with exfoliation and never squeezing."
        ),
        "tips": [
            "Never share razors, and replace blades after 5–8 shaves",
            "Shave in the direction hair grows to avoid ingrown hairs",
            "Cuts that won't heal or painful ingrown bumps — let them be and ask a pharmacist",
        ],
        "doctor": False,
    }


@topic("shampoo", "greasy hair", "oily hair", "dandruff", "wash my hair", "hair care", "split ends", "scalp")
def _(ctx):
    return {
        "reply": (
            "How often you wash your hair is genuinely personal — daily for oily scalps, "
            "every few days for dry or curly hair; neither is wrong. Androgens around your "
            "period can make hair oilier, so needing an extra wash then is normal. Dandruff "
            "flakes that persist usually need an anti-dandruff shampoo rather than more "
            "washing."
        ),
        "tips": [
            "Wash your scalp, not your lengths — let suds rinse down",
            "Condition mid-lengths to ends, skip the scalp if it's oily",
            "Itchy, flaky, persistent scalp → anti-dandruff shampoo; no change in 2 weeks → mention it",
        ],
        "doctor": False,
    }


@topic("nails", "nail care", "manicure", "cuticles", "bite my nails")
def _(ctx):
    return {
        "reply": (
            "Nails tell on your habits — biting them transfers germs and can reshape the "
            "nail bed over time. Keep them trimmed straight across, moisturise cuticles "
            "instead of cutting them, and keep them short if you struggle with biting; that's "
            "the single best quitting strategy."
        ),
        "tips": [
            "Trim after a shower when nails are soft",
            "Push cuticles back gently — cutting them invites infection",
            "Nail biting often fades with a bitter polish + stress awareness",
        ],
        "doctor": False,
    }


@topic("shower", "bath", "bathing", "how often should i wash")
def _(ctx):
    return {
        "reply": (
            "A daily shower or bath is great for most people, especially after sweating, "
            "though skipping a day isn't a hygiene crime if your skin is dry. During your "
            "period, a warm shower or bath is also genuinely soothing for cramps — fully "
            "safe, water doesn't travel inward. Warm water and gentle cleanser beat hot "
            "water and harsh soaps every time."
        ),
        "tips": [
            "Warm, not hot — hot water strips skin's natural oils",
            "Wash sweaty areas daily: armpits, feet, groin, and folds",
            "A warm bath during your period eases cramps beautifully",
        ],
        "doctor": False,
    }


# --- greetings (last on purpose: a greeting mixed with a real question —
# "hey, I have cramps" — should still reach the topic above, not this) ------

@topic("hi", "hello", "hey", "heya", "hiya", "good morning", "good afternoon", "good evening", "how are you", "how's it going", "hows it going", "what's up", "whats up")
def _(ctx):
    name = (ctx.get("name") or "").split(" ")[0]
    who = f" {name}" if name else ""
    return {
        "reply": f"Hi{who}! 💜 I'm your Girly companion — ask me anything about your cycle, health, or personal hygiene.",
        "tips": [],
        "doctor": False,
        "greeting": True,
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
    (
        "I can help with periods and cycle tracking, general health, and personal hygiene — "
        "things like cramps, discharge, skincare, sleep, or showering. Could you tell me a "
        "little more about what you're noticing?"
    ),
]


# ---------------------------------------------------------------------------
# Optional AI layer — answers anything the knowledge base above doesn't cover.
# Enabled by setting GIRLY_AI_API_KEY (or ANTHROPIC_API_KEY). Without a key,
# the companion stays fully offline and uses the built-in answers only.
# Note: when enabled, the user's question and minimal cycle context (day and
# phase, never names or logs) are sent to the configured AI service.
# ---------------------------------------------------------------------------

AI_API_URL = os.environ.get("GIRLY_AI_API_URL", "https://api.anthropic.com/v1/messages")
AI_MODEL = os.environ.get("GIRLY_AI_MODEL", "claude-sonnet-5")
AI_MAX_TOKENS = 700
AI_TIMEOUT = 20.0

AI_SYSTEM_PROMPT = (
    "You are the in-app companion for Girly, a friendly menstrual cycle tracker used mainly "
    "by teens and young women. Answer questions about general health, menstruation, and "
    "personal hygiene with warm, body-positive, age-appropriate, educational information. "
    "Never diagnose or prescribe medication. Encourage seeing a doctor, gynecologist, school "
    "nurse, or trusted adult for severe, persistent, or worrying symptoms, and set "
    '"doctor": true whenever professional care should be considered. Keep the reply under '
    "120 words, in simple, friendly language. Respond ONLY with a JSON object: "
    '{"reply": string, "tips": [up to 3 short practical tips], "doctor": boolean}.'
)


def ai_api_key():
    return os.environ.get("GIRLY_AI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""


def ai_enabled():
    return bool(ai_api_key())


def parse_ai_reply(text):
    """The model is asked for JSON; stay tolerant when it isn't."""
    text = (text or "").strip()
    if not text:
        return None
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None
    if isinstance(data, dict) and str(data.get("reply", "")).strip():
        tips = data.get("tips")
        if not isinstance(tips, list):
            tips = []
        return {
            "reply": str(data["reply"]).strip(),
            "tips": [str(t) for t in tips if str(t).strip()][:3],
            "doctor": bool(data.get("doctor")),
        }
    # plain prose is still a usable answer
    return {"reply": text, "tips": [], "doctor": False}


def ask_ai(message, ctx):
    """Ask the configured AI service, or return None if disabled/unreachable."""
    key = ai_api_key()
    if not key:
        return None

    context_bits = []
    if isinstance(ctx.get("cycle_day"), int) and ctx.get("phase"):
        context_bits.append(
            f"Cycle context: Day {ctx['cycle_day']} of the cycle, {ctx['phase']} phase."
        )
    elif ctx.get("mode") == "learn":
        context_bits.append("Cycle context: the user has not logged any periods (Learn Mode).")
    prompt = (" ".join(context_bits) + "\n\nQuestion: " + message).strip()

    payload = json.dumps(
        {
            "model": AI_MODEL,
            "max_tokens": AI_MAX_TOKENS,
            "system": AI_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        AI_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None

    text = "".join(
        block.get("text", "") for block in data.get("content", []) if isinstance(block, dict)
    )
    return parse_ai_reply(text)


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
                "version": "1.1",
                "port": PORT,
                "ai_enabled": ai_enabled(),
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
    for pattern, builder in KB:
        if pattern.search(message):
            result = builder(ctx)
            return decorate(result, ctx)

    # anything the knowledge base doesn't cover goes to the AI layer
    # (only when a key is configured), then to the friendly fallbacks
    ai = ask_ai(message, ctx)
    if ai:
        return decorate(ai, ctx)

    result = {"reply": random.choice(FALLBACK_REPLIES), "tips": [], "doctor": False}
    return decorate(result, ctx)


def decorate(result, ctx):
    """Attach a phase-aware footer and suggested follow-up chips."""
    phase = ctx.get("phase", "")
    parts = []

    # acknowledge uploaded photos/documents
    files = ctx.get("attachments") or []
    if files:
        names = " and ".join(f"'{a.get('name', 'your file')}'" for a in files[:3])
        parts.append(
            f"📎 I've received {names} — I can't open attachments just yet, "
            "but tell me what's in them and I'll help from there."
        )

    # greetings stay light: just the hello, no phase footers
    if not result.get("greeting"):
        if phase == "luteal":
            d = ctx.get("days_until_period")
            if isinstance(d, int) and 0 <= d <= 6:
                parts.append(f"Your next period is estimated in about {d} day{'s' if d != 1 else ''} — extra gentleness is perfect timing.")
        elif phase == "menstrual":
            parts.append("Cozy rest and hydration are exactly what your body is asking for today.")
        elif phase == "ovulatory":
            parts.append("You're in your fertile window right now — energy and glow often peak here.")

    footer = (" " + " ".join(parts)) if parts else ""
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
