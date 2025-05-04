import os
import sys
import logging
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import asyncpg
import db

# ─── ログ設定 ──────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')

fh = logging.FileHandler('bot.log', encoding='utf-8')
fh.setFormatter(fmt)
logger.addHandler(fh)

sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

# ─── Bot初期化 ─────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot.last_gacha_usage = {}
scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Tokyo'))

# ─── 起動時処理 ─────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}!')
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    bot.db_pool = await asyncpg.create_pool(DATABASE_URL)

    # テーブル初期化 & 設定初期値投入
    await db.init_db(bot.db_pool)

    # CSV→DBロード（初回／更新時）
    await db.load_gacha_data(bot.db_pool, 'data/gacha_data_1.csv', 'spring')
    await db.load_gacha_data(bot.db_pool, 'data/gacha_data_2.csv', 'summer')

    # Cog読み込み
    await bot.load_extension("cogs.gacha")
    await bot.load_extension("cogs.admin")
    await bot.tree.sync()

    # 毎日00:00ジョブ登録
    scheduler.add_job(
        lambda: db.add_daily_points_for_all(
            bot.db_pool,
            # settingsテーブルから現在の付与ポイントを取得
            bot.loop.create_task(db.get_daily_auto_points(bot.db_pool))
        ),
        'cron', hour=0, minute=0
    )
    scheduler.start()
    logger.info("Scheduler started.")

# ─── コマンド利用ログ ―────────────────────────────────
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        cmd = interaction.data.get("name")
        user = interaction.user
        opts = interaction.data.get("options", [])
        parts = []
        for o in opts:
            parts.append(f"{o['name']}={o.get('value')}")
        logger.info(
            f"User {user.name} used /{cmd} with parameters: {', '.join(parts) or 'None'}"
        )

# トークン実行
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set")
    bot.run(TOKEN)
