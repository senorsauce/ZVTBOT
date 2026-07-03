import discord
from discord.ext import commands


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("Moderation cog ready")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if not message.guild:
            return

        # Placeholder for future moderation rules such as spam filtering,
        # profanity filtering, or invite blocking.
        return
