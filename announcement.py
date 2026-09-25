import os
import re

import discord
from discord import app_commands
from discord.ext import commands


class AnnouncementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        try:
            self.channel_id = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "0"))
        except ValueError:
            self.channel_id = 0

    def _resolve_roles(self, guild: discord.Guild, raw_roles: str) -> list[discord.Role] | None:
        role_mentions = re.findall(r"<@&(\d+)>", raw_roles)
        remainder = re.sub(r"<@&\d+>", " ", raw_roles)
        role_ids = role_mentions + re.findall(r"\d+", remainder)

        if re.sub(r"<@&\d+>|\d+|[\s,]+", "", raw_roles):
            return None

        roles: list[discord.Role] = []
        seen_ids: set[int] = set()
        for role_id in role_ids:
            parsed_id = int(role_id)
            if parsed_id in seen_ids:
                continue
            role = guild.get_role(parsed_id)
            if role is None:
                return None
            roles.append(role)
            seen_ids.add(parsed_id)

        return roles

    @app_commands.command(name="annoucement", description="Post an announcement and ping selected roles")
    @app_commands.describe(roles="Role mentions or IDs, separated by spaces or commas", text="Announcement message")
    @app_commands.checks.has_any_role("Management", "Owner")
    async def announcement(self, interaction: discord.Interaction, roles: str, text: str) -> None:
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

        selected_roles = self._resolve_roles(guild, roles)
        if selected_roles is None:
            await interaction.response.send_message(
                "One or more roles are invalid. Use role mentions or role IDs from this server.",
                ephemeral=True,
            )
            return

        content = " ".join(role.mention for role in selected_roles)
        if content:
            content += "\n"
        content += text
        if len(content) > 2000:
            await interaction.response.send_message("The announcement is too long (maximum 2000 characters).", ephemeral=True)
            return

        allowed_mentions = discord.AllowedMentions(
            everyone=False,
            users=False,
            roles=selected_roles,
            replied_user=False,
        )
        await channel.send(content, allowed_mentions=allowed_mentions)
        await interaction.response.send_message(f"Announcement posted in {channel.mention}.", ephemeral=True)