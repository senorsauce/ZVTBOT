import asyncio

import discord

from bot import bot, main as bot_main


@bot.tree.command(name="help", description="Show all available Discord commands")
async def help_command(interaction: discord.Interaction) -> None:
    command_lines = [
        "/help — Show this help message.",
        "/freq <action> <frequency> — Create or join a radio frequency voice channel.",
        "/radio-diagnostics — Show radio configuration and permission details for this server.",
        "/warnings <member> — Show a member's warning points (moderators only).",
        "/clear-warnings <member> — Clear a member's warning points (moderators only).",
    ]
    help_text = "Available commands:\n" + "\n".join(command_lines)
    await interaction.response.send_message(help_text, ephemeral=True)


if __name__ == "__main__":
    asyncio.run(bot_main())
