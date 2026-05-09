import os
import discord
from discord import app_commands
from discord.ext import commands

token = os.getenv("DISCORD_TOKEN")
setupChannelId = int(os.getenv("SETUP_CHANNEL_ID"))
radioCategoryId = int(os.getenv("RADIO_CATEGORY_ID"))

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash command(s) to {guild.name} ({guild.id})")
    except Exception as error:
        print(f"Failed to sync slash commands: {type(error).__name__}: {error}")


@bot.tree.command(name="freq", description="Create or join a radio frequency")
@app_commands.describe(
    action="Choose whether to create or join a frequency",
    frequency="The radio frequency to create or join"
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
    guild = interaction.guild

    setupChannel = guild.get_channel(setupChannelId)
    radioCategory = guild.get_channel(radioCategoryId)

    if setupChannel is None:
        await interaction.response.send_message(
            "Setup channel could not be found. Check SETUP_CHANNEL_ID in Railway.",
            ephemeral=True
        )
        return

    if radioCategory is None:
        await interaction.response.send_message(
            "Radio category could not be found. Check RADIO_CATEGORY_ID in Railway.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Config check passed.\n"
        f"Setup channel: `{setupChannel.name}`\n"
        f"Radio category: `{radioCategory.name}`\n"
        f"Action: `{action.value}`\n"
        f"Frequency: `{frequency}`",
        ephemeral=True
    )

bot.run(token)
