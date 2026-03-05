# Blacklight Discord Bot

A Discord bot for registering and tracking wallet addresses.

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**

   Copy `.env.example` to `.env`, then set:

   - `DISCORD_BOT_TOKEN` — your Discord bot token
   - `DISCORD_CHANNEL_ID` — the single channel where commands run and the bot sends messages (e.g. `1465635325870211155`)
   - `DISCORD_GUILD_ID` (optional) — your server’s ID so slash commands appear right away (Developer Mode → right‑click server → Copy Server ID). If unset, commands sync globally and can take up to an hour to show.
   - `HEARTBEAT_CHECK_INTERVAL_SECONDS` (optional, default `300`) — how often to run the node heartbeat check, in seconds.
   - `HEARTBEAT_STALE_THRESHOLD_SECONDS` (optional, default `1800`) — send a DM if the node's last heartbeat is older than this many seconds.

3. **Run the bot**

   ```bash
   python bot.py
   ```

## Docker

Build and run with Docker (pass env from your `.env` file; use a volume if you want to persist registrations):

```bash
docker build -t blacklight-bot .
docker run --env-file .env --rm blacklight-bot
```

To persist registrations across restarts:

```bash
docker run --env-file .env -v $(pwd)/data:/app/data --rm blacklight-bot
```

Or use Docker Compose (builds, loads `.env`, and mounts a `data` directory so `registrations.json` is stored as a file inside it):

```bash
docker compose up -d
```

## Commands

| Command | Description |
|---|---|
| `/register <wallet_address>` | Register a wallet address to your Discord account |
| `/unregister <wallet_address>` | Unregister a wallet you previously registered |

## Notes

- Wallet registrations are persisted in `data/registrations.json`.
- `/register` and `/unregister` only work in the channel set by `DISCORD_CHANNEL_ID`; in other channels the bot replies that the command must be used in the designated bot channel.
- The bot runs a heartbeat check every `HEARTBEAT_CHECK_INTERVAL_SECONDS` (default 300). For each registered node it calls the Blacklight API; if the latest heartbeat is older than `HEARTBEAT_STALE_THRESHOLD_SECONDS` (default 1800), it DMs that message to every user who registered that node.
