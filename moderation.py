import json
import os

import discord
from discord.ext import commands


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.moderation_log_config = self._load_moderation_log_config()
        self.banned_words = self._load_banned_words()

    def _load_moderation_log_config(self) -> dict[str, dict[str, str]]:
        raw = os.getenv("MODERATION_LOG_CONFIG", "").strip()
        if not raw:
            return {}

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        return parsed

    def _load_banned_words(self) -> list[str]:
        raw = os.getenv("BANNED_WORDS", "").strip()
        if not raw:
            return []

        return [word.strip().lower() for word in raw.split(",") if word.strip()]

    def _contains_keyword(self, content: str) -> bool:
        if not self.banned_words:
            return False

        lowered = content.lower()
        return any(word in lowered for word in self.banned_words)

    def _get_output_channel(self, guild) -> discord.abc.GuildChannel | None:
        if guild is None:
            return None

        guild_config = self.moderation_log_config.get(str(getattr(guild, "id", "")))
        if not isinstance(guild_config, dict):
            return None

        channel_id = guild_config.get("output_channel_id")
        if channel_id is None:
            return None

        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return None

        return guild.get_channel(channel_id)

    async def _send_log(self, guild, member, word: str, timeout_seconds: int, message: str) -> None:
        channel = self._get_output_channel(guild)
        if channel is None:
            return

        if not isinstance(channel, discord.TextChannel):
            return

        display_name = getattr(member, "display_name", None) or getattr(member, "name", "unknown")
        await channel.send(
            f"[moderation] {display_name} triggered '{word}' (timeout {timeout_seconds}s): {message}"
        )

    async def _warn_and_timeout(self, member, reason: str, timeout_seconds: int) -> None:
        return None

    @commands.Cog.listener()
    async def on_message(self, message) -> None:
        if getattr(message.author, "bot", False):
            return

        if not getattr(message, "guild", None):
            return

        content = getattr(message, "content", "")
        if not content:
            return

        if self._contains_keyword(content):
            await message.delete()
            await message.channel.send("Removed message containing a banned word.")
            await self._send_log(message.guild, message.author, "badword", 1, content)
            await self._warn_and_timeout(message.author, "banned word", 1)
