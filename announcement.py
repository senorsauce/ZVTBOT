import os

import discord
from discord import app_commands
from discord.ext import commands


class AnnouncementRoleSelect(discord.ui.RoleSelect):
    def __init__(self, cog: "AnnouncementCog", text: str):
        super().__init__(
            placeholder="Choose roles to ping",
            min_values=1,
            max_values=25,
        )
        self.cog = cog
        self.text = text

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog._post_announcement(interaction, self.values, self.text)


class AnnouncementRoleView(discord.ui.View):
    def __init__(self, cog: "AnnouncementCog", text: str):
        super().__init__(timeout=300)
        self.add_item(AnnouncementRoleSelect(cog, text))


class AnnouncementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        try:
            self.channel_id = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "0"))
        except ValueError:
            self.channel_id = 0

    def _build_content(self, roles: list[discord.Role], text: str) -> str:
        role_mentions = " ".join(role.mention for role in roles)
        return f"{role_mentions}\n{text}" if role_mentions else text

    async def _post_announcement(
        self,
        interaction: discord.Interaction,
        roles: list[discord.Role],
        text: str,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not self.channel_id:
            await interaction.response.send_message(
                "Announcements are not configured. Set ANNOUNCEMENTS_CHANNEL_ID in Railway.",
                ephemeral=True,
            )
            return

        channel = guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "The configured announcements channel was not found. Check ANNOUNCEMENTS_CHANNEL_ID in Railway.",
                ephemeral=True,
            )
            return

        content = self._build_content(roles, text)
        if len(content) > 2000:
            await interaction.response.send_message("The announcement is too long (maximum 2000 characters).", ephemeral=True)
            return

        allowed_mentions = discord.AllowedMentions(
            everyone=False,
            users=False,
            roles=roles,
            replied_user=False,
        )
        await channel.send(content, allowed_mentions=allowed_mentions)
        await interaction.response.send_message(f"Announcement posted in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="annoucement", description="Post an announcement and ping selected roles")
    @app_commands.describe(text="Announcement message")
    @app_commands.checks.has_any_role("Management", "Owner")
    async def announcement(self, interaction: discord.Interaction, text: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not self.channel_id:
            await interaction.response.send_message(
                "Announcements are not configured. Set ANNOUNCEMENTS_CHANNEL_ID in Railway.",
                ephemeral=True,
            )
            return

        channel = guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "The configured announcements channel was not found. Check ANNOUNCEMENTS_CHANNEL_ID in Railway.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Choose one or more roles to ping:",
            view=AnnouncementRoleView(self, text),
            ephemeral=True,
        )