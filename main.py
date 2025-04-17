import os
import sys
import logging
import discord
from discord.ext import commands
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncpg
import db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ファイルおよびターミナルへのログ出力の設定
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# CSV データファイルのパス
bot.gacha_data_path = 'data/gacha_data.csv'

# Railway の PostgreSQL 用：環境変数から DATABASE_URL を取得
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable not set")

# タイムゾーンは日本標準時 (JST)
scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Tokyo'))

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}!")
    # DB接続プールを作成
    bot.db_pool = await asyncpg.create_pool(DATABASE_URL)
    # DBテーブルの初期化
    await db.init_db(bot.db_pool)
    # CSVからガチャデータを読み込み DB にロード（初回のみ）
    await db.load_gacha_data(bot.db_pool, bot.gacha_data_path)
    # Cog の読み込み
    await bot.load_extension("cogs.gacha")
    await bot.load_extension("cogs.admin")
    await bot.tree.sync()
    scheduler.start()
    logger.info("Scheduler started.")

# 毎日00:00に自動付与するポイントの上限は 15pt です。
@scheduler.scheduled_job('cron', hour=0, minute=0)
async def daily_points_job():
    await db.add_daily_points(bot.db_pool, bot.daily_auto_points)

# コマンド実行時のパラメータ詳細ログ（アプリケーションコマンド）
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        command_name = interaction.data.get("name", "Unknown")
        user = interaction.user
        options = interaction.data.get("options", [])
        param_list = []
        for opt in options:
            if "resolved" in opt:
                resolved = opt["resolved"]
                param_value = None
                if isinstance(resolved, dict):
                    if "username" in resolved and "discriminator" in resolved:
                        param_value = f"{resolved['username']}#{resolved['discriminator']}"
                    else:
                        param_value = opt.get("value")
                else:
                    param_value = opt.get("value")
            else:
                param_value = opt.get("value")
            param_list.append(f"{opt['name']}={param_value}")
        params_str = ", ".join(param_list) if param_list else "None"
        logger.info(f"User {user.name} (ID: {user.id}) used command /{command_name} with parameters: {params_str}")

# 初期値: 自動付与ポイントのデフォルトを3に設定
bot.daily_auto_points = 3

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")

bot.run(TOKEN)
