# Blacklight Discord Bot

A Discord bot for registering and tracking wallet addresses.

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**

   In `.env` set:

   - `DISCORD_BOT_TOKEN` — your Discord bot token
   - `DISCORD_CHANNEL_ID` — the single channel where commands run and the bot sends messages (e.g. `1465635325870211155`)
   - `DISCORD_GUILD_ID` (optional) — your server’s ID so slash commands appear right away (Developer Mode → right‑click server → Copy Server ID). If unset, commands sync globally and can take up to an hour to show.

3. **Run the bot**

   ```bash
   python bot.py
   ```

## Commands

| Command | Description |
|---|---|
| `/register <wallet_address>` | Register a wallet address to your Discord account |
| `/unregister <wallet_address>` | Unregister a wallet you previously registered |

## Notes

- Wallet registrations are persisted in `registrations.json`.
- `/register` and `/unregister` only work in the channel set by `DISCORD_CHANNEL_ID`; in other channels the bot replies that the command must be used in the designated bot channel.
- Every 30 seconds the bot checks each registered node via the Blacklight API. If the latest heartbeat has a `block_timestamp` more than 1 minute old, it posts: *"Node \<address\> has not responded to heartbeat transaction for 1 minute(s)."* to the designated channel.
