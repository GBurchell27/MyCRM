"""Where the OpenAI key comes from, and which one wins."""

import os
import unittest
from unittest.mock import patch

from support import TempDbTestCase

import ai_client
from ai_client import (
    ENV_VAR,
    FROM_ENVIRONMENT,
    FROM_SETTINGS,
    SETTINGS_KEY,
    has_api_key,
    resolve_key,
)
from db import set_setting


class KeyResolutionTests(TempDbTestCase):
    """Each case pins the environment, so a real key in the shell can't sway it."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(ENV_VAR, None)

    def test_no_key_anywhere_reports_no_source(self):
        self.assertEqual(resolve_key(), ("", None))
        self.assertFalse(has_api_key())

    def test_environment_key_is_used_when_nothing_is_stored(self):
        os.environ[ENV_VAR] = "sk-from-env"
        self.assertEqual(resolve_key(), ("sk-from-env", FROM_ENVIRONMENT))
        self.assertTrue(has_api_key())

    def test_stored_key_is_used_when_the_environment_has_none(self):
        set_setting(SETTINGS_KEY, "sk-from-settings")
        self.assertEqual(resolve_key(), ("sk-from-settings", FROM_SETTINGS))

    def test_stored_key_takes_priority_over_the_environment(self):
        os.environ[ENV_VAR] = "sk-from-env"
        set_setting(SETTINGS_KEY, "sk-from-settings")
        self.assertEqual(resolve_key(), ("sk-from-settings", FROM_SETTINGS))

    def test_clearing_the_stored_key_falls_back_to_the_environment(self):
        os.environ[ENV_VAR] = "sk-from-env"
        set_setting(SETTINGS_KEY, "sk-from-settings")
        set_setting(SETTINGS_KEY, "")
        self.assertEqual(resolve_key(), ("sk-from-env", FROM_ENVIRONMENT))

    def test_whitespace_counts_as_no_key_on_either_side(self):
        os.environ[ENV_VAR] = "   "
        set_setting(SETTINGS_KEY, "  \n ")
        self.assertEqual(resolve_key(), ("", None))

    def test_keys_are_returned_stripped(self):
        os.environ[ENV_VAR] = "  sk-padded  "
        self.assertEqual(resolve_key()[0], "sk-padded")

    def test_missing_key_names_the_env_var_it_would_accept(self):
        with self.assertRaises(RuntimeError) as raised:
            ai_client.client()
        self.assertIn(ENV_VAR, str(raised.exception))


class MaskTests(unittest.TestCase):
    def test_mask_shows_only_the_tail(self):
        from dialogs.settings.api_key_field import mask

        self.assertEqual(mask("sk-proj-abcdefgh1234"), "…1234")
        self.assertNotIn("abcdefgh", mask("sk-proj-abcdefgh1234"))

    def test_mask_of_a_short_or_empty_key_leaks_nothing(self):
        from dialogs.settings.api_key_field import mask

        self.assertEqual(mask(""), "…")
        self.assertEqual(mask("abc"), "…")


if __name__ == "__main__":
    unittest.main()
