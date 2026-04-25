#!/usr/bin/env python3

import os
import asyncio
import logging
import logging.handlers
import sys

from bot.client import BotClient
from bot.scheduler import Scheduler
from utils.files import FileRepo
from utils.users import UserManager
from utils.birthday_service import BirthdayService
from utils.ollama_client import OllamaClient
from utils.jeff_persona import JeffPersona
from cogs.sound_board import SoundBoard
from cogs.entrances import Entrances
from cogs.google_img import GoogleImages
from cogs.birthdays import Birthdays
from cogs.chat_ollama import ChatOllama
from cogs.conversation_ai import ConversationAI
from cogs.ollama_manager import OllamaManager
from jobs.birthday_checker import BirthdayChecker
from jobs.friday_alert import FridayAlert
from commands.commands import friday, tuesday, xmas, jobs
from discord import Intents


REQUIRED_ENV = ['DISCORD_TOKEN', 'OPENWEBUI_URL', 'OPENWEBUI_API_KEY', 'BUCKET_PATH']

DATA_DIR = os.environ.get('DATA_DIR', './data')
GOOGLE_CREDS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')


def _bucket_path(bucket: str, sub: str) -> str:
    return f'{bucket.rstrip("/")}/{sub}'


async def main():
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        filename='discord.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,
        backupCount=5,
    )
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '[{asctime}] [{levelname:<8}] {name}: {message}',
        '%Y-%m-%d %H:%M:%S',
        style='{',
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.info("Logging system initialized")

    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    discord_token = os.environ['DISCORD_TOKEN']
    bucket_path = os.environ['BUCKET_PATH']
    openwebui_url = os.environ['OPENWEBUI_URL']
    openwebui_api_key = os.environ['OPENWEBUI_API_KEY']
    searxng_url = os.environ.get('SEARXNG_URL')
    project_id = os.environ.get('PROJECT_ID')
    bucket_sub_name = os.environ.get('BUCKET_SUB_NAME')

    if not GOOGLE_CREDS:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set; GCS features will fail.")

    repo_kwargs = dict(
        service_account_json=GOOGLE_CREDS,
        project_id=project_id,
        bucket_sub_name=bucket_sub_name,
    )

    sound_files = FileRepo(
        base_path=os.path.join(DATA_DIR, 'sounds'),
        bucket_path=_bucket_path(bucket_path, 'sounds'),
        **repo_kwargs,
    )
    resource_files = FileRepo(
        base_path=os.path.join(DATA_DIR, 'resources'),
        bucket_path=_bucket_path(bucket_path, 'resources'),
        **repo_kwargs,
    )
    user_manager = UserManager(
        user_repo=FileRepo(
            base_path=os.path.join(DATA_DIR, 'users'),
            bucket_path=_bucket_path(bucket_path, 'users'),
            overwrite=True,
            **repo_kwargs,
        )
    )
    memory_repo = FileRepo(
        base_path=os.path.join(DATA_DIR, 'memory'),
        bucket_path=_bucket_path(bucket_path, 'memory'),
        **repo_kwargs,
    )
    logger.info("File repositories initialized")

    bot = BotClient(user_manager=user_manager, intents=Intents.all())
    ollama_client = OllamaClient(
        base_url=openwebui_url,
        api_key=openwebui_api_key,
        default_model="gpt-4.1",
    )
    jeff_persona = JeffPersona(ollama_client)
    birthday_service = BirthdayService(user_manager)
    scheduler = Scheduler(bot)
    bot.scheduler = scheduler

    async with bot:
        cog_configs = [
            ('SoundBoard', SoundBoard, {'bot': bot, 'sound_files': sound_files}),
            ('Entrances', Entrances, {'bot': bot, 'user_manager': user_manager, 'sound_files': sound_files}),
            ('GoogleImages', GoogleImages, {'bot': bot, 'searxng_url': searxng_url}),
            ('Birthdays', Birthdays, {'bot': bot, 'birthday_service': birthday_service, 'jeff_persona': jeff_persona}),
            ('ChatOllama', ChatOllama, {'bot': bot, 'ollama_client': ollama_client}),
            ('ConversationAI', ConversationAI, {'bot': bot, 'ollama_client': ollama_client, 'memory_repo': memory_repo}),
            ('OllamaManager', OllamaManager, {'bot': bot, 'ollama_client': ollama_client}),
        ]
        for cog_name, cog_class, cog_kwargs in cog_configs:
            try:
                await bot.add_cog(cog_class(**cog_kwargs))
                logger.info(f"Loaded cog: {cog_name}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)

        for command in [friday, tuesday, xmas, jobs]:
            bot.add_command(command)

        scheduler.jobs.append(BirthdayChecker(bot=bot, birthday_service=birthday_service, jeff_persona=jeff_persona))
        scheduler.jobs.append(FridayAlert(bot=bot, jeff_persona=jeff_persona))
        scheduler.start()

        logger.info("Starting Discord bot")
        await bot.start(discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger('discord').info("Bot shutdown requested by user")
