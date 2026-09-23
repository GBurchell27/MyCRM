"""The settings registry: coercion, clamping, and the features that read it."""

import unittest

from support import TempDbTestCase

from config.ai_models import (
    CHAT,
    SUMMARY,
    TRANSCRIPTION,
    chat_completion_kwargs,
    combine_chat_model,
    resolve_chat_model,
    supports_reasoning_effort,
    transcription_model,
)
from config.app_settings import (
    CATCHUP_LOOKBACK_DAYS,
    CATCHUP_MEETING_CHARS,
    DICTATION_MAX_MINUTES,
    HOVER_PREVIEWS,
    RECURRING_HORIZON_DAYS,
    STARTUP_TAB,
    TAB_TASKS,
)
from config.setting_types import BoolSetting, ChoiceSetting, IntSetting
from db import set_setting


class SettingCoercionTests(TempDbTestCase):
    def test_unset_setting_returns_its_default(self):
        self.assertEqual(CATCHUP_LOOKBACK_DAYS.get(), 14)
        self.assertTrue(HOVER_PREVIEWS.get())

    def test_saved_value_round_trips(self):
        CATCHUP_LOOKBACK_DAYS.save(30)
        self.assertEqual(CATCHUP_LOOKBACK_DAYS.get(), 30)

    def test_bool_round_trips_both_ways(self):
        HOVER_PREVIEWS.save(False)
        self.assertFalse(HOVER_PREVIEWS.get())
        HOVER_PREVIEWS.save(True)
        self.assertTrue(HOVER_PREVIEWS.get())

    def test_out_of_range_number_is_clamped_not_rejected(self):
        DICTATION_MAX_MINUTES.save(600)
        self.assertEqual(DICTATION_MAX_MINUTES.get(), DICTATION_MAX_MINUTES.maximum)

    def test_unreadable_value_falls_back_to_the_default(self):
        set_setting(CATCHUP_MEETING_CHARS.key, "not a number")
        self.assertEqual(CATCHUP_MEETING_CHARS.get(), CATCHUP_MEETING_CHARS.default)

    def test_blank_value_falls_back_to_the_default(self):
        set_setting(STARTUP_TAB.key, "   ")
        self.assertEqual(STARTUP_TAB.get(), STARTUP_TAB.default)

    def test_choice_outside_the_options_falls_back(self):
        set_setting(STARTUP_TAB.key, "nowhere")
        self.assertEqual(STARTUP_TAB.get(), STARTUP_TAB.default)

    def test_choice_maps_between_value_and_label(self):
        STARTUP_TAB.save(TAB_TASKS)
        self.assertEqual(STARTUP_TAB.get(), TAB_TASKS)
        self.assertEqual(STARTUP_TAB.label_for(TAB_TASKS), "Tasks")
        self.assertEqual(STARTUP_TAB.value_for("Tasks"), TAB_TASKS)


class SettingTypeTests(unittest.TestCase):
    """The type behaviour that doesn't need a database."""

    def test_bool_reads_the_shapes_a_hand_edited_db_might_hold(self):
        setting = BoolSetting("k", "Label", default=False)
        for raw in ("1", "true", "TRUE", "yes", "on"):
            self.assertTrue(setting.coerce(raw), raw)
        for raw in ("0", "false", "no", "off", "anything else"):
            self.assertFalse(setting.coerce(raw), raw)

    def test_int_clamps_to_its_range(self):
        setting = IntSetting("k", "Label", default=5, minimum=1, maximum=10)
        self.assertEqual(setting.coerce("99"), 10)
        self.assertEqual(setting.coerce("-4"), 1)
        self.assertEqual(setting.coerce("7"), 7)

    def test_choice_reports_its_values_and_labels(self):
        setting = ChoiceSetting(
            "k", "Label", default="a", options=[("a", "Apple"), ("b", "Pear")]
        )
        self.assertEqual(setting.values, ["a", "b"])
        self.assertEqual(setting.labels, ["Apple", "Pear"])
        self.assertEqual(setting.value_for("unknown label"), "a")


class ModelSettingTests(TempDbTestCase):
    def test_model_and_effort_split_and_rejoin(self):
        self.assertEqual(resolve_chat_model("gpt-5.6-terra:max"), ("gpt-5.6-terra", "max"))
        self.assertEqual(resolve_chat_model("gpt-5.6-luna"), ("gpt-5.6-luna", ""))
        self.assertEqual(combine_chat_model("gpt-5.6-terra", "max"), "gpt-5.6-terra:max")
        self.assertEqual(combine_chat_model("gpt-5.6-terra", ""), "gpt-5.6-terra")

    def test_effort_is_dropped_for_a_model_that_cannot_use_it(self):
        self.assertFalse(supports_reasoning_effort("gpt-4o"))
        self.assertEqual(combine_chat_model("gpt-4o", "max"), "gpt-4o")

    def test_configured_effort_reaches_the_api_kwargs(self):
        set_setting(SUMMARY["key"], "gpt-5.6-terra:high")
        self.assertEqual(
            chat_completion_kwargs(SUMMARY),
            {"model": "gpt-5.6-terra", "reasoning_effort": "high"},
        )

    def test_no_effort_means_no_reasoning_kwarg(self):
        set_setting(SUMMARY["key"], "gpt-5.6-luna")
        self.assertEqual(chat_completion_kwargs(SUMMARY), {"model": "gpt-5.6-luna"})

    def test_effort_never_reaches_a_model_that_would_reject_it(self):
        set_setting(SUMMARY["key"], "gpt-4o:max")
        self.assertEqual(chat_completion_kwargs(SUMMARY), {"model": "gpt-4o"})

    def test_transcription_model_is_a_bare_name(self):
        self.assertEqual(TRANSCRIPTION["kind"], "transcription")
        self.assertNotEqual(SUMMARY["kind"], TRANSCRIPTION["kind"])
        self.assertEqual(SUMMARY["kind"], CHAT)
        set_setting(TRANSCRIPTION["key"], "gpt-4o-transcribe:max")
        self.assertEqual(transcription_model(), "gpt-4o-transcribe")


class SettingsDriveBehaviourTests(TempDbTestCase):
    """The settings are wired to something, not just stored."""

    def test_lookback_setting_moves_the_catchup_window(self):
        from meeting_window import load_window

        self.add_meeting("2026-08-01", "Morgan", notes="last time")
        self.add_meeting("2026-08-03", "Sam", notes="something since")

        CATCHUP_LOOKBACK_DAYS.save(2)
        window = load_window("Morgan", "2026-08-10")
        self.assertTrue(window.capped)
        self.assertEqual(window.lookback_days, 2)
        self.assertEqual(window.interim, [])

        CATCHUP_LOOKBACK_DAYS.save(30)
        window = load_window("Morgan", "2026-08-10")
        self.assertFalse(window.capped)
        self.assertEqual([row["person"] for row in window.interim], ["Sam"])

    def test_character_budget_trims_what_the_ai_is_given(self):
        from catchup_pack import clamp

        CATCHUP_MEETING_CHARS.save(500)
        trimmed = clamp("x" * 900)
        self.assertLess(len(trimmed), 900)
        self.assertTrue(trimmed.endswith("[…trimmed]"))

    def test_horizon_setting_controls_how_far_ahead_notes_are_created(self):
        from recurring_meetings import RecurringMeetingManager

        RECURRING_HORIZON_DAYS.save(3)
        # Every day of the week, so the horizon is the only thing limiting the count.
        RecurringMeetingManager.create("Morgan", list(range(7)))
        self.assertEqual(len(self.all_meetings()), 4)  # today plus three days


if __name__ == "__main__":
    unittest.main()
