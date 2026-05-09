import asyncio
import os
import re

import discord
from discord import app_commands
from discord.ext import commands


# ----------------------------
# Environment config
# ----------------------------

token = os.getenv("DISCORD_TOKEN")
setupChannelIdRaw = os.getenv("SETUP_CHANNEL_ID")
radioCategoryIdRaw = os.getenv("RADIO_CATEGORY_ID")

if token is None:
    raise RuntimeError("Missing DISCORD_TOKEN Railway variable.")

if setupChannelIdRaw is None:
    raise RuntimeError("Missing SETUP_CHANNEL_ID Railway variable.")

if radioCategoryIdRaw is None:
    raise RuntimeError("Missing RADIO_CATEGORY_ID Railway variable.")

setupChannelId = int(setupChannelIdRaw)
radioCategoryId = int(radioCategoryIdRaw)

deleteDelaySeconds = 30


# ----------------------------
# Bot setup
# ----------------------------

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

hasSyncedCommands = False
deleteTasks: dict[int, asyncio.Task] = {}


# ----------------------------
# Helpers
# ----------------------------

def cleanFrequency(frequency: str) -> str | None:
    frequency = frequency.strip().lower()

    if not re.fullmatch(r"[a-z0-9.-]{1,20}", frequency):
        return None

    return frequency


def getRadioChannelName(frequency: str) -> str:
    return f"Freq: {frequency}"


def isRadioChannel(channel: discord.abc.GuildChannel | None) -> bool:
    return (
        isinstance(channel, discord.VoiceChannel)
        and channel.category_id == radioCategoryId
        and channel.name.startswith("Freq: ")
    )


async def sendPrivate(interaction: discord.Interaction, message: str) -> None:
    await interaction.followup.send(message, ephemeral=True)


async def findRadioChannel(
    radioCategory: discord.CategoryChannel,
    frequency: str
) -> discord.VoiceChannel | None:
    channelName = getRadioChannelName(frequency)

    for channel in radioCategory.voice_channels:
        if channel.name == channelName:
            return channel

    return None


def getLockedOverwrites(
    guild: discord.Guild,
    member: discord.Member
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
            connect=False
        ),
        member: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True
        )
    }

    if guild.me is not None:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            manage_channels=True,
            move_members=True
        )

    return overwrites


def botCanManageChannel(channel: discord.abc.GuildChannel, guild: discord.Guild) -> bool:
    if guild.me is None:
        return False

    permissions = channel.permissions_for(guild.me)
    return permissions.manage_channels


def botCanMoveMembers(channel: discord.abc.GuildChannel, guild: discord.Guild) -> bool:
    if guild.me is None:
        return False

    permissions = channel.permissions_for(guild.me)
    return permissions.move_members


async def allowMemberIntoChannel(
    channel: discord.VoiceChannel,
    member: discord.Member
) -> None:
    await channel.set_permissions(
        member,
        view_channel=True,
        connect=True,
        speak=True
    )


def cancelDeleteTask(channelId: int) -> None:
    task = deleteTasks.pop(channelId, None)

    if task is not None and not task.done():
        task.cancel()
        print(f"Cancelled delete timer for channel ID: {channelId}")


async def deleteChannelAfterDelay(channelId: int, guildId: int) -> None:
    try:
        await asyncio.sleep(deleteDelaySeconds)

        guild = bot.get_guild(guildId)

        if guild is None:
            print(f"Could not find guild while deleting channel ID: {channelId}")
            return

        channel = guild.get_channel(channelId)

        if channel is None:
            return

        if not isinstance(channel, discord.VoiceChannel):
            return

        if not isRadioChannel(channel):
            return

        if len(channel.members) > 0:
            print(f"Skipped delete because channel is no longer empty: {channel.name}")
            return

        await channel.delete(reason=f"Radio frequency empty for {deleteDelaySeconds} seconds")
        print(f"Deleted empty radio channel: {channel.name}")

    except asyncio.CancelledError:
        return

    except discord.NotFound:
        return

    except discord.Forbidden:
        print(f"Missing Manage Channels permission to delete channel ID: {channelId}")

    except Exception as error:
        print(f"Failed to delete channel ID {channelId}: {type(error).__name__}: {error}")

    finally:
        deleteTasks.pop(channelId, None)


def scheduleDeleteIfEmpty(channel: discord.VoiceChannel) -> None:
    if len(channel.members) > 0:
        return

    if channel.id in deleteTasks:
        return

    print(f"Scheduling delete for empty radio channel: {channel.name}")

    deleteTasks[channel.id] = asyncio.create_task(
        deleteChannelAfterDelay(channel.id, channel.guild.id)
    )


# ----------------------------
# Events
# ----------------------------

@bot.event
async def on_ready():
    global hasSyncedCommands

    print(f"Logged in as {bot.user}")

    if hasSyncedCommands:
        return

    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash command(s) to {guild.name} ({guild.id})")

        hasSyncedCommands = True

    except Exception as error:
        print(f"Failed to sync slash commands: {type(error).__name__}: {error}")


@bot.event
async def on_voice_state_update(member, before, after):
    if isRadioChannel(after.channel):
        cancelDeleteTask(after.channel.id)

    if isRadioChannel(before.channel):
        scheduleDeleteIfEmpty(before.channel)


# ----------------------------
# Slash command
# ----------------------------

@bot.tree.command(name="freq", description="Create or join a radio frequency")
@app_commands.describe(
    action="Create or join a frequency",
    frequency="The frequency"
)
@app_commands.choices(action=[
    app_commands.Choice(name="create", value="create"),
    app_commands.Choice(name="join", value="join"),
])
async def freq(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    frequency: str
):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    member = interaction.user

    if guild is None:
        await sendPrivate(interaction, "Server only.")
        return

    if not isinstance(member, discord.Member):
        await sendPrivate(interaction, "Member info unavailable.")
        return

    setupChannel = guild.get_channel(setupChannelId)
    radioCategory = guild.get_channel(radioCategoryId)

    if not isinstance(setupChannel, discord.VoiceChannel):
        await sendPrivate(interaction, "Setup channel misconfigured.")
        return

    if not isinstance(radioCategory, discord.CategoryChannel):
        await sendPrivate(interaction, "Radio category misconfigured.")
        return

    if member.voice is None or member.voice.channel is None:
        await sendPrivate(interaction, f"Join `{setupChannel.name}` first.")
        return

    if member.voice.channel.id != setupChannelId:
        await sendPrivate(interaction, f"Join `{setupChannel.name}` first.")
        return

    cleanedFrequency = cleanFrequency(frequency)

    if cleanedFrequency is None:
        await sendPrivate(interaction, "Invalid frequency.")
        return

    radioChannel = await findRadioChannel(radioCategory, cleanedFrequency)

    if action.value == "create":
        if radioChannel is not None:
            await sendPrivate(interaction, "Frequency already exists.")
            return

        if not botCanManageChannel(radioCategory, guild):
            await sendPrivate(interaction, "Bot needs `Manage Channels` in the radio category.")
            return

        if not botCanMoveMembers(setupChannel, guild):
            await sendPrivate(interaction, "Bot needs `Move Members` in the setup channel.")
            return

        channelName = getRadioChannelName(cleanedFrequency)

        try:
            radioChannel = await guild.create_voice_channel(
                name=channelName,
                category=radioCategory,
                overwrites=getLockedOverwrites(guild, member),
                reason=f"Radio frequency created by {member}"
            )

            await member.move_to(radioChannel)
            await sendPrivate(interaction, "Created. Moving you.")
            return

        except discord.Forbidden:
            await sendPrivate(interaction, "Bot lacks permission to create or move.")
            return

        except Exception as error:
            print(f"Create failed: {type(error).__name__}: {error}")
            await sendPrivate(interaction, "Create failed.")
            return

    if action.value == "join":
        if radioChannel is None:
            await sendPrivate(interaction, "Frequency not found.")
            return

        if not botCanManageChannel(radioChannel, guild):
            await sendPrivate(interaction, "Bot needs `Manage Channels` for this frequency.")
            return

        if not botCanMoveMembers(setupChannel, guild):
            await sendPrivate(interaction, "Bot needs `Move Members` in the setup channel.")
            return

        try:
            await allowMemberIntoChannel(radioChannel, member)
            await member.move_to(radioChannel)
            await sendPrivate(interaction, "Moving you.")
            return

        except discord.Forbidden:
            await sendPrivate(interaction, "Bot lacks permission to add you or move you.")
            return

        except Exception as error:
            print(f"Join failed: {type(error).__name__}: {error}")
            await sendPrivate(interaction, "Join failed.")
            return

    await sendPrivate(interaction, "Unknown action.")


bot.run(token)
