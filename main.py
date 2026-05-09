import asyncio
import hashlib
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
    hashedFrequency = hashlib.sha256(frequency.encode()).hexdigest()

    partOne = hashedFrequency[0:4]
    partTwo = hashedFrequency[4:8]
    partThree = hashedFrequency[8:12]

    return f"cipher-{partOne}-{partTwo}-{partThree}"


def isRadioChannel(channel: discord.abc.GuildChannel | None) -> bool:
    if not isinstance(channel, discord.VoiceChannel):
        return False

    if channel.category_id != radioCategoryId:
        return False

    if not channel.name.startswith("cipher-"):
        return False

    return True


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

    botMember = guild.me

    if botMember is not None:
        overwrites[botMember] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            manage_channels=True,
            move_members=True
        )

    return overwrites


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


async def deleteChannelAfterDelay(channel: discord.VoiceChannel) -> None:
    try:
        await asyncio.sleep(10)

        # Re-check after 10 seconds.
        if len(channel.members) > 0:
            return

        await channel.delete(reason="Radio frequency empty for 10 seconds")
        print(f"Deleted empty radio channel: {channel.name}")

    except asyncio.CancelledError:
        return

    except discord.NotFound:
        return

    except discord.Forbidden:
        print(f"Missing permissions to delete channel: {channel.name}")

    except Exception as error:
        print(f"Failed to delete channel {channel.name}: {type(error).__name__}: {error}")

    finally:
        deleteTasks.pop(channel.id, None)


def scheduleDeleteIfEmpty(channel: discord.VoiceChannel) -> None:
    if len(channel.members) > 0:
        return

    if channel.id in deleteTasks:
        return

    deleteTasks[channel.id] = asyncio.create_task(deleteChannelAfterDelay(channel))


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
    # Someone joined or moved into a radio channel.
    # Cancel pending deletion.
    if isRadioChannel(after.channel):
        cancelDeleteTask(after.channel.id)

    # Someone left or moved out of a radio channel.
    # If it is now empty, start the 10-second delete timer.
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
        await interaction.followup.send("Server only.", ephemeral=True)
        return

    if not isinstance(member, discord.Member):
        await interaction.followup.send("Member info unavailable.", ephemeral=True)
        return

    setupChannel = guild.get_channel(setupChannelId)
    radioCategory = guild.get_channel(radioCategoryId)

    if not isinstance(setupChannel, discord.VoiceChannel):
        await interaction.followup.send("Setup channel misconfigured.", ephemeral=True)
        return

    if not isinstance(radioCategory, discord.CategoryChannel):
        await interaction.followup.send("Radio category misconfigured.", ephemeral=True)
        return

    if member.voice is None or member.voice.channel is None:
        await interaction.followup.send(f"Join `{setupChannel.name}` first.", ephemeral=True)
        return

    if member.voice.channel.id != setupChannelId:
        await interaction.followup.send(f"Join `{setupChannel.name}` first.", ephemeral=True)
        return

    cleanedFrequency = cleanFrequency(frequency)

    if cleanedFrequency is None:
        await interaction.followup.send("Invalid frequency.", ephemeral=True)
        return

    radioChannel = await findRadioChannel(radioCategory, cleanedFrequency)

    if action.value == "create":
        if radioChannel is not None:
            await interaction.followup.send("Frequency already exists.", ephemeral=True)
            return

        channelName = getRadioChannelName(cleanedFrequency)

        radioChannel = await guild.create_voice_channel(
            name=channelName,
            category=radioCategory,
            overwrites=getLockedOverwrites(guild, member),
            reason=f"Radio frequency created by {member}"
        )

        await member.move_to(radioChannel)
        await interaction.followup.send("Created. Moving you.", ephemeral=True)
        return

    if action.value == "join":
        if radioChannel is None:
            await interaction.followup.send("Frequency not found.", ephemeral=True)
            return

        await allowMemberIntoChannel(radioChannel, member)
        await member.move_to(radioChannel)
        await interaction.followup.send("Moving you.", ephemeral=True)
        return

    await interaction.followup.send("Unknown action.", ephemeral=True)


bot.run(token)
