import os
import json
import asyncio
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

REGISTRATIONS_FILE = Path("registrations.json")
_channel_id = (os.getenv("DISCORD_CHANNEL_ID") or "0").strip()
ALLOWED_CHANNEL_ID = int(_channel_id) if _channel_id.isdigit() else 0
_guild_id = (os.getenv("DISCORD_GUILD_ID") or "").strip()
GUILD_ID = int(_guild_id) if _guild_id.isdigit() else None


def load_registrations() -> dict[str, list[str]]:
    if REGISTRATIONS_FILE.exists():
        return json.loads(REGISTRATIONS_FILE.read_text())
    return {}


def save_registrations(data: dict[str, list[str]]) -> None:
    REGISTRATIONS_FILE.write_text(json.dumps(data, indent=2))


async def require_channel(interaction: discord.Interaction) -> bool:
    """Return True if interaction is in the allowed channel, else respond and return False."""
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message(
            "This command can only be used in the designated bot channel.",
            ephemeral=True,
        )
        return False
    return True


class BlacklightBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.allowed_channel_id = ALLOWED_CHANNEL_ID

    async def setup_hook(self):
        if GUILD_ID:
            self.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            self.loop.create_task(self._sync_commands_to_guilds())
        self.loop.create_task(self.placeholder_cron())

    async def _sync_commands_to_guilds(self):
        """Sync slash commands to every guild the bot is in so they appear immediately."""
        await self.wait_until_ready()
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            except discord.HTTPException:
                pass

    async def placeholder_cron(self):
        """Placeholder cron job — replace with real wallet-check logic later."""
        await self.wait_until_ready()
        channel = self.get_channel(self.allowed_channel_id)
        while not self.is_closed():
            if channel:
                await channel.send("test message")
            await asyncio.sleep(300)


bot = BlacklightBot()


@bot.tree.command(name="register", description="Register a wallet address")
@app_commands.describe(wallet_address="The wallet address to register")
async def register(interaction: discord.Interaction, wallet_address: str):
    if not await require_channel(interaction):
        return
    user_id = str(interaction.user.id)
    registrations = load_registrations()

    for uid, wallets in registrations.items():
        if wallet_address in wallets:
            if uid == user_id:
                await interaction.response.send_message(
                    f"You have already registered `{wallet_address}`.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"`{wallet_address}` is already registered by another user.",
                    ephemeral=True,
                )
            return

    registrations.setdefault(user_id, []).append(wallet_address)
    save_registrations(registrations)

    await interaction.response.send_message(
        f"Wallet `{wallet_address}` registered successfully!", ephemeral=True
    )


@bot.tree.command(name="unregister", description="Unregister a wallet address")
@app_commands.describe(wallet_address="The wallet address to unregister")
async def unregister(interaction: discord.Interaction, wallet_address: str):
    if not await require_channel(interaction):
        return
    user_id = str(interaction.user.id)
    registrations = load_registrations()
    user_wallets = registrations.get(user_id, [])

    if wallet_address not in user_wallets:
        await interaction.response.send_message(
            f"You have not registered `{wallet_address}`.", ephemeral=True
        )
        return

    user_wallets.remove(wallet_address)
    if not user_wallets:
        del registrations[user_id]
    save_registrations(registrations)

    await interaction.response.send_message(
        f"Wallet `{wallet_address}` has been unregistered.", ephemeral=True
    )


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
