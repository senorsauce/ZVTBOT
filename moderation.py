import json
import os

import discord
from discord.ext import commands
import random
import asyncio
from typing import Any


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


class TicketingCog(commands.Cog):
    """Cog providing a persistent ticket panel and ticket channel creation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ticket_config = self._load_ticket_config()
        # persistent state (counters etc.)
        self.state_path = os.getenv("TICKET_STATE_PATH", "ticket_state.json")
        self.state = self._load_state()
        # optional global archive category id
        self.global_archive_category = os.getenv("TICKET_ARCHIVE_CATEGORY_ID")
        # optional panel channel id (post the persistent panel there on_ready)
        self.panel_channel_id = os.getenv("TICKET_PANEL_CHANNEL_ID")

    def _load_ticket_config(self) -> dict[str, Any]:
        raw = os.getenv("TICKET_CONFIG", "").strip()
        if not raw:
            # Example default config — users should override with JSON in env or a configuration file.
            return {
                "bug_report": {
                    "label": "Bug Report",
                    "description": "Report bugs to developers.",
                    "emoji": "🪲",
                    "prefix": "BR",
                    "category_id": None,
                    "role_ids": []
                },
                "whitelist": {
                    "label": "Whitelist",
                    "description": "Request whitelist access.",
                    "emoji": "✅",
                    "prefix": "WL",
                    "category_id": None,
                    "role_ids": []
                }
            }

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        return parsed

    def _load_state(self) -> dict[str, Any]:
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        # default structure
        return {"counters": {}}

    def _save_state(self) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(self.state, fh)
        except Exception:
            pass

    @commands.command(name="post_ticket_panel")
    @commands.has_permissions(manage_guild=True)
    async def post_ticket_panel(self, ctx: commands.Context) -> None:
        """Posts a persistent ticket panel with a select menu for ticket types."""
        options = []
        for key, cfg in self.ticket_config.items():
            label = cfg.get("label") or key
            desc = cfg.get("description", "")
            emoji = cfg.get("emoji")
            options.append(discord.SelectOption(label=label, description=desc, emoji=emoji, value=key))

        if not options:
            await ctx.send("No ticket types are configured.")
            return

        class TicketSelect(discord.ui.Select):
            def __init__(self, parent: "TicketingCog"):
                super().__init__(placeholder="Select a topic", min_values=1, max_values=1, options=options)
                self.parent = parent

            async def callback(self, interaction: discord.Interaction) -> None:
                key = self.values[0]
                await self.parent._handle_ticket_request(interaction, key)

        class TicketView(discord.ui.View):
            def __init__(self, parent: "TicketingCog"):
                super().__init__(timeout=None)
                self.add_item(TicketSelect(parent))

        embed = discord.Embed(title="Ticket Center", description="If you require support, create a ticket by selecting a topic below.")
        await ctx.send(embed=embed, view=TicketView(self))

    async def _handle_ticket_request(self, interaction: discord.Interaction, key: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if guild is None:
            await interaction.followup.send("This command must be used in a server.")
            return

        cfg = self.ticket_config.get(key)
        if not cfg:
            await interaction.followup.send("Unknown ticket type selected.")
            return

        prefix = cfg.get("prefix", "T")
        # optional name format, supports {key} and {counter}
        name_format = cfg.get("name_format") or os.getenv("TICKET_NAME_FORMAT") or "{key}-ticket-{counter:02d}"
        category_id = cfg.get("category_id")
        role_ids = cfg.get("role_ids", []) or []

        # Resolve category
        category = None
        if category_id:
            try:
                category = guild.get_channel(int(category_id))
            except Exception:
                category = None

        # Increment and persist counter for this ticket type
        counters = self.state.setdefault("counters", {})
        cur = int(counters.get(key, 0)) + 1
        counters[key] = cur
        self._save_state()

        # Format channel name
        try:
            channel_name = name_format.format(key=key, prefix=prefix, counter=cur)
        except Exception:
            channel_name = f"{key}-ticket-{cur:02d}"

        # Prepare overwrites: hide from @everyone, show to requester and allowed roles
        overwrites: dict = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        for rid in role_ids:
            try:
                role = guild.get_role(int(rid))
            except Exception:
                role = None
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        # Bot perms
        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)

        # Create channel
        try:
            channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, reason="Ticket created via ticket panel")
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create channels in this server.")
            return
        except Exception as exc:
            await interaction.followup.send(f"Failed to create ticket channel: {exc}")
            return

        # Send initial message with a close button
        view = discord.ui.View()

        async def close_callback(interact: discord.Interaction) -> None:
            # Only allow the ticket creator, members with manage_guild, or configured roles to close
            requester = member
            actor = interact.user
            allowed = False
            if actor.id == requester.id:
                allowed = True
            if interact.user.guild_permissions.manage_guild:
                allowed = True
            for rid in role_ids:
                role = guild.get_role(int(rid)) if rid else None
                if role and role in getattr(actor, "roles", []):
                    allowed = True
                    break

            if not allowed:
                await interact.response.send_message("You don't have permission to close this ticket.", ephemeral=True)
                return

            # Try to archive the ticket: move to archive category and lock the requester
            archive_cat_id = cfg.get("archive_category_id") or self.global_archive_category
            archived = False
            if archive_cat_id:
                try:
                    archive_category = guild.get_channel(int(archive_cat_id))
                except Exception:
                    archive_category = None
                try:
                    if archive_category is not None:
                        await channel.edit(category=archive_category)
                        # remove view for requester
                        await channel.set_permissions(requester, overwrite=discord.PermissionOverwrite(view_channel=False))
                        archived = True
                except Exception:
                    archived = False

            if not archived:
                # fallback: try to delete
                try:
                    await channel.delete(reason="Ticket closed")
                    try:
                        await interact.response.send_message("Ticket closed and channel deleted.", ephemeral=True)
                    except Exception:
                        pass
                except Exception:
                    # last resort: lock channel for requester
                    try:
                        await channel.set_permissions(requester, overwrite=discord.PermissionOverwrite(view_channel=False))
                        await interact.response.send_message("Ticket locked.", ephemeral=True)
                    except Exception:
                        await interact.response.send_message("Failed to archive or delete ticket.", ephemeral=True)

        close_button = discord.ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger)
        close_button.callback = close_callback
        view.add_item(close_button)

        try:
            await channel.send(f"Ticket created for {member.mention}. A staff member will be with you shortly.", view=view)
        except Exception:
            pass

        await interaction.followup.send(f"Created ticket: {channel.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Post the ticket panel into the configured channel (if provided)
        if not self.panel_channel_id:
            return

        try:
            chan_id = int(self.panel_channel_id)
        except Exception:
            return

        # Try to find the channel in any guild
        channel = None
        for g in self.bot.guilds:
            channel = g.get_channel(chan_id)
            if channel is not None:
                break

        if channel is None:
            return

        # Check recent messages for our panel (embed title match)
        try:
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    for e in msg.embeds:
                        if e.title == "Ticket Center":
                            return
        except Exception:
            pass

        # Post a new panel
        options = []
        for key, cfg in self.ticket_config.items():
            label = cfg.get("label") or key
            desc = cfg.get("description", "")
            emoji = cfg.get("emoji")
            options.append(discord.SelectOption(label=label, description=desc, emoji=emoji, value=key))

        if not options:
            return

        class TicketSelect(discord.ui.Select):
            def __init__(self, parent: "TicketingCog"):
                super().__init__(placeholder="Select a topic", min_values=1, max_values=1, options=options)
                self.parent = parent

            async def callback(self, interaction: discord.Interaction) -> None:
                key = self.values[0]
                await self.parent._handle_ticket_request(interaction, key)

        class TicketView(discord.ui.View):
            def __init__(self, parent: "TicketingCog"):
                super().__init__(timeout=None)
                self.add_item(TicketSelect(parent))

        embed = discord.Embed(title="Ticket Center", description="If you require support, create a ticket by selecting a topic below.")
        try:
            await channel.send(embed=embed, view=TicketView(self))
        except Exception:
            pass


def setup(bot: commands.Bot) -> None:
    bot.add_cog(TicketingCog(bot))
