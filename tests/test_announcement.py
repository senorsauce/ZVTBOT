import unittest
from types import SimpleNamespace

from announcement import AnnouncementCog, AnnouncementRoleSelect


class AnnouncementTests(unittest.TestCase):
    def test_slash_command_uses_correct_name(self):
        self.assertEqual(AnnouncementCog.announcement.name, "announcement")

    def test_role_picker_requires_at_least_one_and_allows_multiple_roles(self):
        selector = AnnouncementRoleSelect(AnnouncementCog(None), "Update")

        self.assertEqual(selector.min_values, 1)
        self.assertEqual(selector.max_values, 25)

    def test_builds_message_with_selected_role_mentions(self):
        role_one = SimpleNamespace(mention="<@&123>")
        role_two = SimpleNamespace(mention="<@&456>")
        cog = AnnouncementCog(None)

        self.assertEqual(
            cog._build_content([role_one, role_two], "Update"),
            "<@&123> <@&456>\nUpdate",
        )


if __name__ == "__main__":
    unittest.main()