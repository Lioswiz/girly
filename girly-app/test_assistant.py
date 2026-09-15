"""Tests for the companion service's knowledge base and AI layer."""

import json
import unittest
from unittest import mock

import assistant.server as companion


class KnowledgeBaseTests(unittest.TestCase):
    def test_core_topics_still_match(self):
        r = companion.respond("how do I soothe cramps?", {})
        self.assertIn("cramps", r["reply"].lower())

    def test_new_menstrual_topics(self):
        cases = [
            ("what exactly is a period and why do we have them?", "uterus"),
            ("I think I have a yeast infection", "yeast"),
            ("it burns when I pee", "urinary"),
            ("what is PCOS?", "pcos"),
        ]
        for question, needle in cases:
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertIn(needle, r["reply"].lower())

    def test_new_health_topics(self):
        cases = [
            ("how much water should I drink every day?", "hydrat"),
            ("what foods should I eat more of?", "iron"),
            ("I feel so stressed about exams", "stress"),
            ("how do I deal with acne on my chin?", "acne"),
        ]
        for question, needle in cases:
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertIn(needle, r["reply"].lower())

    def test_new_hygiene_topics(self):
        cases = [
            ("how often should I shower?", "shower"),
            ("should I use an intimate wash down there?", "self-cleaning"),
            ("why do my feet smell so much?", "feet"),
            ("is it better to shave my legs with or against the hair?", "razor"),
            ("my armpits sweat a lot, what deodorant works?", "deodorant"),
        ]
        for question, needle in cases:
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertIn(needle, r["reply"].lower())

    def test_safety_topics_flag_doctor(self):
        for question in (
            "I think my friend has an eating disorder",
            "a tampon was left in too long, could it be toxic shock?",
            "could I be pregnant?",
        ):
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertTrue(r["doctor"])

    def test_pregnancy_question_gets_pregnancy_answer(self):
        r = companion.respond("could I be pregnant?", {})
        self.assertIn("pregnancy is possible", r["reply"].lower())

    def test_fallback_when_nothing_matches_and_no_ai(self):
        with mock.patch.object(companion, "ai_api_key", return_value=""):
            r = companion.respond("what is the airspeed velocity of an unladen swallow?", {})
        self.assertIn(r["reply"], companion.FALLBACK_REPLIES)


class GreetingTests(unittest.TestCase):
    def test_greeting_gets_simple_hello(self):
        for hello in ("hi", "hello there", "hey!", "good morning"):
            with self.subTest(hello=hello):
                r = companion.respond(hello, {"name": "Maya Lin", "phase": "menstrual"})
                self.assertIn("Maya", r["reply"])
                self.assertEqual(r["tips"], [])
                self.assertFalse(r["doctor"])

    def test_greeting_has_no_extra_information(self):
        # phase footers must not be attached to a plain greeting
        r = companion.respond("hello", {"name": "Maya", "phase": "menstrual"})
        self.assertNotIn("Cozy rest", r["reply"])
        r = companion.respond("hi", {"name": "Maya", "phase": "luteal", "days_until_period": 3})
        self.assertNotIn("next period is estimated", r["reply"])

    def test_greeting_mixed_with_question_still_answers_the_question(self):
        r = companion.respond("hey, how do I soothe cramps?", {"name": "Maya"})
        self.assertIn("cramps", r["reply"].lower())

    def test_greeting_does_not_call_the_ai(self):
        calls = []
        with mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 side_effect=lambda *a, **k: calls.append(1) or FakeResponse({}),
             ):
            companion.respond("hello", {"name": "Maya"})
        self.assertEqual(calls, [])


class ParseAiReplyTests(unittest.TestCase):
    def test_plain_json(self):
        out = companion.parse_ai_reply(
            json.dumps({"reply": "Drink water", "tips": ["sip often"], "doctor": False})
        )
        self.assertEqual(out["reply"], "Drink water")
        self.assertEqual(out["tips"], ["sip often"])
        self.assertFalse(out["doctor"])

    def test_json_wrapped_in_prose(self):
        out = companion.parse_ai_reply(
            'Here you go: {"reply": "Rest up", "tips": ["sleep"], "doctor": true} — hope that helps!'
        )
        self.assertEqual(out["reply"], "Rest up")
        self.assertTrue(out["doctor"])

    def test_plain_prose(self):
        out = companion.parse_ai_reply("Just a plain, warm answer.")
        self.assertEqual(out["reply"], "Just a plain, warm answer.")
        self.assertEqual(out["tips"], [])

    def test_empty(self):
        self.assertIsNone(companion.parse_ai_reply("   "))

    def test_tips_capped_at_three(self):
        out = companion.parse_ai_reply(
            json.dumps({"reply": "r", "tips": ["a", "b", "c", "d", "e"], "doctor": False})
        )
        self.assertEqual(len(out["tips"]), 3)


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AiLayerTests(unittest.TestCase):
    def test_ask_ai_returns_none_without_key(self):
        with mock.patch.object(companion, "ai_api_key", return_value=""):
            self.assertIsNone(companion.ask_ai("anything", {}))

    def test_ask_ai_sends_request_and_parses_response(self):
        ai_json = json.dumps({"reply": "AI answer", "tips": ["tip 1"], "doctor": True})
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = req.headers
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse({"content": [{"type": "text", "text": ai_json}]})

        with mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(companion.urllib.request, "urlopen", side_effect=fake_urlopen):
            out = companion.ask_ai("why is the sky blue?", {"cycle_day": 14, "phase": "ovulatory"})

        self.assertEqual(out["reply"], "AI answer")
        self.assertTrue(out["doctor"])
        self.assertEqual(captured["url"], companion.AI_API_URL)
        self.assertEqual(captured["headers"]["X-api-key"], "test-key")
        self.assertIn("Day 14", captured["body"]["messages"][0]["content"])
        self.assertIn("why is the sky blue?", captured["body"]["messages"][0]["content"])

    def test_ask_ai_returns_none_on_network_error(self):
        def boom(req, timeout=None):
            raise OSError("no network")

        with mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(companion.urllib.request, "urlopen", side_effect=boom):
            self.assertIsNone(companion.ask_ai("anything", {}))

    def test_respond_uses_ai_for_unmatched_questions(self):
        ai_json = json.dumps({"reply": "Here's your answer", "tips": [], "doctor": False})

        with mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 return_value=FakeResponse({"content": [{"type": "text", "text": ai_json}]}),
             ):
            r = companion.respond("what is the airspeed velocity of an unladen swallow?", {})

        self.assertIn("Here's your answer", r["reply"])
        self.assertIn("educational insights", r["disclaimer"])

    def test_respond_prefers_knowledge_base_over_ai(self):
        calls = []
        with mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 side_effect=lambda *a, **k: calls.append(1) or FakeResponse({}),
             ):
            r = companion.respond("how do I soothe cramps?", {})
        self.assertEqual(calls, [])  # KB matched, AI never called
        self.assertIn("cramps", r["reply"].lower())


if __name__ == "__main__":
    unittest.main()
