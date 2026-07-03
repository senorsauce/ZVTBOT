import discord
from discord.ext import commands
from discord import app_commands


class DayzCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("DAYZ cog ready")

    @app_commands.command(name="dayz-status", description="Check a DAYZ server status")
    async def dayz_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "DAYZ API integration is scaffolded and ready for the real endpoint.",
            ephemeral=True,
        )
