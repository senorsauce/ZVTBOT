import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from moderation import ModerationCog


class ModerationLogConfigTests(unittest.TestCase):
    def test_parses_json_log_config(self):
        with patch.dict(
            os.environ,
            {"MODERATION_LOG_CONFIG": '{"1505564505445498930": {"output_channel_id": "1522884803366752347"}}'},
            clear=False,
        ):
            cog = ModerationCog(SimpleNamespace(get_guild=lambda guild_id: None))
            self.assertEqual(
                cog.moderation_log_config,
                {"1505564505445498930": {"output_channel_id": "1522884803366752347"}},
            )


if __name__ == "__main__":
    unittest.main()
