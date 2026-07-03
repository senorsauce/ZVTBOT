import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands

from config import get_guild_config


class RadioCog(commands.Cog):
    def __init__(self, bot: commands.Bot, delete_delay_seconds: int = 30):
        self.bot = bot
        self.delete_delay_seconds = delete_delay_seconds
        self.delete_tasks: dict[int, asyncio.Task] = {}

    def clean_frequency(self, frequency: str) -> str | None:
        frequency = frequency.strip().lower()

        if not re.fullmatch(r"[a-z0-9.-]{1,20}", frequency):
            return None

        return frequency

    def get_radio_channel_name(self, frequency: str) -> str:
        return f"Freq: {frequency}"

    def get_setup_channel_id(self, guild: discord.Guild | None) -> int:
        setup_channel_id, _ = get_guild_config(guild.id if guild is not None else None)
        return setup_channel_id

    def get_radio_category_id(self, guild: discord.Guild | None) -> int:
        _, radio_category_id = get_guild_config(guild.id if guild is not None else None)
        return radio_category_id

    def is_radio_channel(self, channel: discord.abc.GuildChannel | None) -> bool:
        if not isinstance(channel, discord.VoiceChannel):
            return False

        if channel.guild is None:
            return False

        return (
            channel.category_id == self.get_radio_category_id(channel.guild)
            and channel.name.startswith("Freq: ")
        )

    async def send_private(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.followup.send(message, ephemeral=True)

    async def find_radio_channel(self, radio_category: discord.CategoryChannel, frequency: str) -> discord.VoiceChannel | None:
        channel_name = self.get_radio_channel_name(frequency)

        for channel in radio_category.voice_channels:
            if channel.name == channel_name:
                return channel

        return None

    def get_locked_overwrites(self, guild: discord.Guild, member: discord.Member) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            member: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
        }

        if guild.me is not None:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True,
                move_members=True,
            )

        return overwrites

    def bot_can_manage_channel(self, channel: discord.abc.GuildChannel, guild: discord.Guild) -> bool:
        if guild.me is None:
            return False
        return channel.permissions_for(guild.me).manage_channels

    def bot_can_move_members(self, channel: discord.abc.GuildChannel, guild: discord.Guild) -> bool:
        if guild.me is None:
            return False
        return channel.permissions_for(guild.me).move_members

    async def allow_member_into_channel(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        await channel.set_permissions(member, view_channel=True, connect=True, speak=True)

    def cancel_delete_task(self, channel_id: int) -> None:
        task = self.delete_tasks.pop(channel_id, None)
        if task is not None and not task.done():
            task.cancel()
            print(f"Cancelled delete timer for channel ID: {channel_id}")

    async def delete_channel_after_delay(self, channel_id: int, guild_id: int) -> None:
        try:
            await asyncio.sleep(self.delete_delay_seconds)
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                print(f"Could not find guild while deleting channel ID: {channel_id}")
                return

            channel = guild.get_channel(channel_id)
            if channel is None or not isinstance(channel, discord.VoiceChannel):
                return

            if not self.is_radio_channel(channel):
                return

            if len(channel.members) > 0:
                print(f"Skipped delete because channel is no longer empty: {channel.name}")
                return

            await channel.delete(reason=f"Radio frequency empty for {self.delete_delay_seconds} seconds")
            print(f"Deleted empty radio channel: {channel.name}")

        except asyncio.CancelledError:
            return
        except discord.NotFound:
            return
        except discord.Forbidden:
            print(f"Missing Manage Channels permission to delete channel ID: {channel_id}")
        except Exception as error:
            print(f"Failed to delete channel ID {channel_id}: {type(error).__name__}: {error}")
        finally:
            self.delete_tasks.pop(channel_id, None)

    def schedule_delete_if_empty(self, channel: discord.VoiceChannel) -> None:
        if len(channel.members) > 0 or channel.id in self.delete_tasks:
            return

        print(f"Scheduling delete for empty radio channel: {channel.name}")
        self.delete_tasks[channel.id] = asyncio.create_task(
            self.delete_channel_after_delay(channel.id, channel.guild.id)
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Radio cog ready for {self.bot.user}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if self.is_radio_channel(after.channel):
            self.cancel_delete_task(after.channel.id)

        if self.is_radio_channel(before.channel):
            self.schedule_delete_if_empty(before.channel)

    @app_commands.command(name="freq", description="Create or join a radio frequency")
    @app_commands.describe(action="Create or join a frequency", frequency="The frequency")
    @app_commands.choices(action=[
        app_commands.Choice(name="create", value="create"),
        app_commands.Choice(name="join", value="join"),
    ])
    async def freq(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        frequency: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            guild = interaction.guild
            member = interaction.user

            print(f"freq invoked by member={getattr(member,'id',None)} guild={getattr(guild,'id',None)} action={getattr(action,'value',None)} frequency={frequency}")

            if guild is None:
                await self.send_private(interaction, "Server only.")
                return

            if not isinstance(member, discord.Member):
                await self.send_private(interaction, "Member info unavailable.")
                return

            setup_channel_id = self.get_setup_channel_id(guild)
            radio_category_id = self.get_radio_category_id(guild)
            setup_channel = guild.get_channel(setup_channel_id)
            radio_category = guild.get_channel(radio_category_id)

            if not isinstance(setup_channel, discord.VoiceChannel):
                await self.send_private(interaction, "Setup channel misconfigured.")
                return

            if not isinstance(radio_category, discord.CategoryChannel):
                await self.send_private(interaction, "Radio category misconfigured.")
                return

            if member.voice is None or member.voice.channel is None:
                await self.send_private(interaction, f"Join `{setup_channel.name}` first.")
                return

            if member.voice.channel.id != setup_channel_id:
                await self.send_private(interaction, f"Join `{setup_channel.name}` first.")
                return

            cleaned_frequency = self.clean_frequency(frequency)
            if cleaned_frequency is None:
                await self.send_private(interaction, "Invalid frequency.")
                return

            radio_channel = await self.find_radio_channel(radio_category, cleaned_frequency)

            if action.value == "create":
                if radio_channel is not None:
                    await self.send_private(interaction, "Frequency already exists.")
                    return

                if not self.bot_can_manage_channel(radio_category, guild):
                    await self.send_private(interaction, "Bot needs `Manage Channels` in the radio category.")
                    return

                if not self.bot_can_move_members(setup_channel, guild):
                    await self.send_private(interaction, "Bot needs `Move Members` in the setup channel.")
                    return

                channel_name = self.get_radio_channel_name(cleaned_frequency)
                try:
                    radio_channel = await guild.create_voice_channel(
                        name=channel_name,
                        category=radio_category,
                        overwrites=self.get_locked_overwrites(guild, member),
                        reason=f"Radio frequency created by {member}",
                    )
                    await member.move_to(radio_channel)
                    await self.send_private(interaction, "Created. Moving you.")
                    return
                except discord.Forbidden:
                    await self.send_private(interaction, "Bot lacks permission to create or move.")
                    return
                except Exception as error:
                    print(f"Create failed: {type(error).__name__}: {error}")
                    await self.send_private(interaction, "Create failed.")
                    return

            if action.value == "join":
                if radio_channel is None:
                    await self.send_private(interaction, "Frequency not found.")
                    return

                if not self.bot_can_manage_channel(radio_channel, guild):
                    await self.send_private(interaction, "Bot needs `Manage Channels` for this frequency.")
                    return

                if not self.bot_can_move_members(setup_channel, guild):
                    await self.send_private(interaction, "Bot needs `Move Members` in the setup channel.")
                    return

                try:
                    await self.allow_member_into_channel(radio_channel, member)
                    await member.move_to(radio_channel)
                    await self.send_private(interaction, "Moving you.")
                    return
                except discord.Forbidden:
                    await self.send_private(interaction, "Bot lacks permission to add you or move you.")
                    return
                except Exception as error:
                    print(f"Join failed: {type(error).__name__}: {error}")
                    await self.send_private(interaction, "Join failed.")
                    return

            await self.send_private(interaction, "Unknown action.")

        except Exception as error:
            print(f"Unhandled error in freq: {type(error).__name__}: {error}")
            try:
                await interaction.followup.send("Internal error occurred.", ephemeral=True)
            except Exception:
                pass
            return

    # Command registration is handled by discord.py when the cog is added.
