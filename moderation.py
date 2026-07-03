import json
import logging
import os
import re
from datetime import timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("ZVTBOT.moderation")


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_path = Path(__file__).parent / "data" / "warning_points.json"
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.banned_words = self._parse_words(os.getenv("BANNED_WORDS", ""))
        self.warning_words = self._parse_words(os.getenv("WARNING_WORDS", ""))
        self.timeout_minutes = int(os.getenv("MODERATION_TIMEOUT_MINUTES", "10"))
        self.log_channel_id = os.getenv("MODERATION_LOG_CHANNEL_ID", "").strip()
        self.warning_points = self._load_warning_points()

    def _parse_words(self, raw_value: str) -> list[str]:
        if not raw_value.strip():
            return []

        if raw_value.strip().startswith("["):
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, list):
                return [str(word).strip().lower() for word in parsed if str(word).strip()]

        return [word.strip().lower() for word in raw_value.replace("\n", ",").split(",") if word.strip()]

    def _load_warning_points(self) -> dict[str, dict[str, int]]:
        if not self.data_path.exists():
            return {}

        try:
            with self.data_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load warning points from %s", self.data_path)
            return {}

        if not isinstance(payload, dict):
            return {}

        return payload

    def _save_warning_points(self) -> None:
        try:
            with self.data_path.open("w", encoding="utf-8") as handle:
                json.dump(self.warning_points, handle, indent=2)
        except OSError:
            logger.exception("Failed to save warning points to %s", self.data_path)

    def _get_warning_points(self, guild_id: int, member_id: int) -> int:
        guild_key = str(guild_id)
        member_key = str(member_id)
        guild_data = self.warning_points.get(guild_key, {})
        if not isinstance(guild_data, dict):
            return 0
        value = guild_data.get(member_key, 0)
        return int(value) if isinstance(value, int) else 0

    def _increment_warning_points(self, guild_id: int, member_id: int) -> int:
        guild_key = str(guild_id)
        member_key = str(member_id)
        guild_data = self.warning_points.setdefault(guild_key, {})
        if not isinstance(guild_data, dict):
            guild_data = {}
            self.warning_points[guild_key] = guild_data

        current_points = int(guild_data.get(member_key, 0))
        new_points = current_points + 1
        guild_data[member_key] = new_points
        self._save_warning_points()
        return new_points

    def _get_member_warning_points(self, guild_id: int, member_id: int) -> int:
        return self._get_warning_points(guild_id, member_id)

    def _clear_member_warning_points(self, guild_id: int, member_id: int) -> int:
        guild_key = str(guild_id)
        member_key = str(member_id)
        guild_data = self.warning_points.get(guild_key, {})
        if not isinstance(guild_data, dict):
            return 0

        if member_key not in guild_data:
            return 0

        old_value = int(guild_data.pop(member_key, 0))
        if not guild_data:
            self.warning_points.pop(guild_key, None)
        self._save_warning_points()
        return old_value

    def _contains_keyword(self, content: str, keyword: str) -> bool:
        normalized_content = content.lower()
        return bool(re.search(rf"\b{re.escape(keyword)}\b", normalized_content))

    async def _send_log(self, guild: discord.Guild, member: discord.Member, keyword: str, total_points: int) -> None:
        if not self.log_channel_id:
            return

        try:
            channel = guild.get_channel(int(self.log_channel_id))
        except ValueError:
            logger.warning("MODERATION_LOG_CHANNEL_ID is not a valid snowflake: %s", self.log_channel_id)
            return

        if not isinstance(channel, discord.TextChannel):
            logger.warning("Moderation log channel %s is not a text channel", self.log_channel_id)
            return

        await channel.send(
            f"User {member.mention} said `{keyword}`. Timeout and warning point issued.\n"
            f"Total warning points: {total_points}."
        )

    async def _warn_and_timeout(self, guild: discord.Guild, member: discord.Member, keyword: str) -> None:
        total_points = self._increment_warning_points(guild.id, member.id)

        try:
            timeout_until = discord.utils.utcnow() + timedelta(minutes=self.timeout_minutes)
            await member.timeout(until=timeout_until, reason=f"Used banned word: {keyword}")
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Could not timeout %s in %s: %s", member, guild, exc)

        try:
            await member.send(
                f"Your message contained a banned word (`{keyword}`), so it was removed and you received a warning point."
                f"\nCurrent total warning points: {total_points}."
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.info("Could not send moderation DM to %s", member)

        await self._send_log(guild, member, keyword, total_points)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("Moderation cog ready")

    @app_commands.command(name="warnings", description="Show a user's warning points")
    @app_commands.describe(member="The member to inspect")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        points = self._get_member_warning_points(interaction.guild.id, member.id)
        await interaction.response.send_message(
            f"{member.mention} has {points} warning point(s).",
            ephemeral=True,
        )

    @app_commands.command(name="clear-warnings", description="Clear a user's warning points")
    @app_commands.describe(member="The member whose warnings should be cleared")
    async def clear_warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        removed = self._clear_member_warning_points(interaction.guild.id, member.id)
        await interaction.response.send_message(
            f"Cleared {removed} warning point(s) for {member.mention}.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        if not message.content:
            return

        content = message.content.strip()
        if not content:
            return

        if not isinstance(message.author, discord.Member):
            return

        for keyword in self.warning_words:
            if self._contains_keyword(content, keyword):
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    logger.info("Could not delete message from %s for warning keyword %s", message.author, keyword)

                await self._warn_and_timeout(message.guild, message.author, keyword)
                return

        for keyword in self.banned_words:
            if self._contains_keyword(content, keyword):
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    logger.info("Could not delete message from %s for banned keyword %s", message.author, keyword)

                try:
                    await message.author.send(
                        f"Your message contained a banned word (`{keyword}`), so it was removed."
                    )
                except (discord.Forbidden, discord.HTTPException):
                    logger.info("Could not send banned-word DM to %s", message.author)

                return
