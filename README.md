# jeff-bot

A Discord bot with a soundboard, member entrance sounds, AI chat (via OpenWebUI / Ollama), birthday reminders, a Friday alert, and Google image search. Assets are cached locally and synced from a Google Cloud Storage bucket on startup.

## Features

- **Soundboard** (`cogs/sound_board.py`) — play short audio clips in voice channels
- **Entrances** (`cogs/entrances.py`) — assign each member a personal entry sound
- **AI chat** (`cogs/chat_ollama.py`, `cogs/conversation_ai.py`) — Jeff's persona, with per-channel memory
- **Birthdays** (`cogs/birthdays.py`, `jobs/birthday_checker.py`) — remembers and announces user birthdays
- **Friday alert** (`jobs/friday_alert.py`) — scheduled Friday reminder
- **Google image search** (`cogs/google_img.py`) — `!image <query>` via Custom Search

## Requirements

- Python 3.8+
- `ffmpeg` on PATH (for voice playback)
- A Discord bot token
- A Google Cloud Storage bucket + service-account JSON (for assets)
- An OpenWebUI / Ollama endpoint with an API key (for AI features)
- *Optional:* a Google Custom Search Image API key + engine CX (for `!image`)

## Local development

```sh
cp .env.example .env
# fill in DISCORD_TOKEN, OPENWEBUI_*, BUCKET_PATH, GOOGLE_APPLICATION_CREDENTIALS, ...
pip install -r requirements.txt
python run.py
```

## Tests

```sh
pip install pytest pytest-asyncio
python -m pytest tests/
```

## Docker

```sh
docker build -t jeff-bot .
docker run --rm --env-file .env -v "$PWD/gcp-credentials.json:/etc/gcp/credentials.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/etc/gcp/credentials.json jeff-bot
```

## Deployment

Kubernetes manifests + 1Password-backed secrets live in the homelab repo, not here. See `serves/jeff-bot/` for the deploy script and manifests.

## License

MIT — see [LICENSE](LICENSE).
