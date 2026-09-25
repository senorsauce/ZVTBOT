import unittest
from types import SimpleNamespace

from announcement import AnnouncementCog


class AnnouncementTests(unittest.TestCase):
    def test_resolves_role_mentions_and_ids(self):
        role_one = SimpleNamespace(id=123, mention="<@&123>")
        role_two = SimpleNamespace(id=456, mention="<@&456>")
        guild = SimpleNamespace(get_role=lambda role_id: {123: role_one, 456: role_two}.get(role_id))
        cog = AnnouncementCog(None)

        roles = cog._resolve_roles(guild, "<@&123>, 456 <@&123>")

        self.assertEqual(roles, [role_one, role_two])

    def test_rejects_unknown_or_malformed_roles(self):
        guild = SimpleNamespace(get_role=lambda role_id: None)
        cog = AnnouncementCog(None)

        self.assertIsNone(cog._resolve_roles(guild, "<@&123>"))
        self.assertIsNone(cog._resolve_roles(guild, "@everyone"))


if __name__ == "__main__":
    unittest.main()