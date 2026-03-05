import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from fetch_node import BASE_URL, fetch_node, fetch_node_block_number, parse_rsc_response

load_dotenv()

HEARTBEAT_STALE_MINUTES = 1
HEARTBEAT_CHECK_INTERVAL_SECONDS = 30

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


def load_all_registered_nodes() -> list[str]:
    """Return unique node (wallet) addresses from all registrations."""
    if not REGISTRATIONS_FILE.exists():
        return []
    data = json.loads(REGISTRATIONS_FILE.read_text())
    nodes = set()
    for wallet_list in data.values():
        nodes.update(wallet_list)
    return sorted(nodes)


def get_user_ids_for_node(node_address: str) -> list[int]:
    """Return Discord user IDs of everyone who registered this node."""
    if not REGISTRATIONS_FILE.exists():
        return []
    data = json.loads(REGISTRATIONS_FILE.read_text())
    return [int(uid) for uid, wallets in data.items() if node_address in wallets]


def parse_block_timestamp(ts: str) -> datetime | None:
    """Parse Blacklight block_timestamp e.g. '2026-03-05 7:21:37.0 +00:00:00' to UTC datetime."""
    if not ts:
        return None
    ts = ts.strip()
    # Strip timezone suffix (API uses " +00:00:00" or "+00:00:00"); treat as UTC
    for suffix in (" +00:00:00", "+00:00:00", " +00:00", "+00:00"):
        if ts.endswith(suffix):
            ts = ts[: -len(suffix)].strip()
            break
    try:
        # Parse "2026-03-05 7:43:05.0" (optional fractional seconds)
        if "." in ts:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


async def get_latest_heartbeat(node_address: str) -> dict | None:
    """Fetch node data (limit 1) and return the first/latest heartbeat record, or None."""
    url = f"{BASE_URL}/nodes/{node_address}"
    try:
        block = await asyncio.to_thread(fetch_node_block_number, node_address)
        if block is None:
            print(f"[Heartbeat]   No block number from [address] payload; skipping heartbeat fetch for {node_address}")
            return None
        print(f"[Heartbeat]   Block number for node: {block}")
        text = await asyncio.to_thread(fetch_node, node_address, block, 1)
        data = parse_rsc_response(text)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        # No exception but no data: API returned something that didn't contain a non-empty data array
        print(f"[Heartbeat]   URL: {url}")
        print(f"[Heartbeat]   Response length: {len(text)} chars")
        if isinstance(data, list):
            print(f"[Heartbeat]   Parse ok but data list is empty (node may have no heartbeats for this round)")
        else:
            print(f"[Heartbeat]   Could not find 'data' array in RSC response (first 300 chars): {text[:300]!r}")
        return None
    except Exception as e:
        print(f"[Heartbeat]   URL: {url}")
        print(f"[Heartbeat] Error fetching node {node_address}: {e}")
        return None


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
        self.loop.create_task(self.heartbeat_check_cron())

    async def _sync_commands_to_guilds(self):
        """Sync slash commands to every guild the bot is in so they appear immediately."""
        await self.wait_until_ready()
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            except discord.HTTPException:
                pass

    async def heartbeat_check_cron(self):
        """Every 30s: for each registered node, check latest heartbeat; DM users if > 1 min old."""
        await self.wait_until_ready()
        stale_threshold_seconds = HEARTBEAT_STALE_MINUTES * 60
        def dm_message(node: str) -> str:
            return (
                f"Hey. The node you registered ({node}) has not responded to heartbeat transaction "
                f"for {HEARTBEAT_STALE_MINUTES} minute{'s' if HEARTBEAT_STALE_MINUTES != 1 else ''} - you may want to check up on it."
            )
        while not self.is_closed():
            nodes = load_all_registered_nodes()
            if not nodes:
                print("[Heartbeat] No registered nodes; skipping check.")
            for node_address in nodes:
                url = f"{BASE_URL}/nodes/{node_address}"
                print(f"[Heartbeat] Calling endpoint for node {node_address}")
                print(f"[Heartbeat]   URL: {url}")
                latest = await get_latest_heartbeat(node_address)
                if not latest:
                    print(f"[Heartbeat]   No heartbeat data returned for {node_address}")
                    continue
                ts_str = latest.get("block_timestamp")
                if not ts_str:
                    print(f"[Heartbeat]   No block_timestamp in response for {node_address}")
                    continue
                dt = parse_block_timestamp(ts_str)
                if not dt:
                    print(f"[Heartbeat]   Could not parse block_timestamp {ts_str!r} for {node_address}")
                    continue
                now = datetime.now(timezone.utc)
                age_seconds = (now - dt).total_seconds()
                print(f"[Heartbeat]   Last transaction: {ts_str} (age {age_seconds:.0f}s)")
                if age_seconds > stale_threshold_seconds:
                    user_ids = get_user_ids_for_node(node_address)
                    for uid in user_ids:
                        try:
                            user = self.get_user(uid) or await self.fetch_user(uid)
                            if user:
                                await user.send(dm_message(node_address))
                                print(f"[Heartbeat]   DM sent to user {uid} for {node_address}")
                        except discord.HTTPException as e:
                            print(f"[Heartbeat]   Failed to DM user {uid}: {e}")
                else:
                    print(f"[Heartbeat]   No message (heartbeat under {HEARTBEAT_STALE_MINUTES} min)")
            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL_SECONDS)


bot = BlacklightBot()


@bot.tree.command(name="register", description="Register a wallet address")
@app_commands.describe(wallet_address="The wallet address to register")
async def register(interaction: discord.Interaction, wallet_address: str):
    if not await require_channel(interaction):
        return
    user_id = str(interaction.user.id)
    registrations = load_registrations()
    user_wallets = registrations.get(user_id, [])

    if wallet_address in user_wallets:
        await interaction.response.send_message(
            f"You have already registered `{wallet_address}`.", ephemeral=True
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
