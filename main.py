import os
import discord
from discord import app_commands
from discord.ext import commands

token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
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
    await interaction.response.send_message(
        f"Received request to `{action.value}` frequency `{frequency}`.",
        ephemeral=True
    )


bot.run(token)
