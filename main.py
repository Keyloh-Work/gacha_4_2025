import os
import sys
import logging
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import asyncpg
import db

# ─── ログ設定 ─────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
fh = logging.FileHandler('bot.log', encoding='utf-8')
fh.setFormatter(fmt)
logger.addHandler(fh)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

# ─── Bot初期化 ─────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot.last_gacha_usage = {}  # クールダウン管理用
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Tokyo"))

# ─── 起動時処理 ─────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}!')

    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL が設定されていません")

    # PostgreSQL プール作成
    bot.db_pool = await asyncpg.create_pool(DATABASE_URL)

    # テーブル初期化 & 初期設定投入
    await db.init_db(bot.db_pool)

    # CSV→DBロード（spring / summer）
    await db.load_gacha_data(bot.db_pool, 'data/gacha_data_1.csv', 'summer_2025')
    await db.load_gacha_data(bot.db_pool, 'data/gacha_data_2.csv', 'halloween')

    # Cog の読み込み
    await bot.load_extension("cogs.gacha")
    await bot.load_extension("cogs.admin")
    await bot.tree.sync()

    # 毎日00:00にポイント自動付与ジョブを登録
    async def daily_job():
        pt = await db.get_daily_auto_points(bot.db_pool)
        await db.add_daily_points_for_all(bot.db_pool, pt)
    scheduler.add_job(daily_job, 'cron', hour=0, minute=0)
    scheduler.start()

    logger.info("Scheduler started.")

# ─── 使用コマンドログ ────────────────────────────────────
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        cmd = interaction.data.get("name")
        user = interaction.user
        opts = interaction.data.get("options", [])
        parts = [f"{o['name']}={o.get('value')}" for o in opts]
        logger.info(
            f"User {user.name} used /{cmd} with parameters: "
            f"{', '.join(parts) if parts else 'None'}"
        )

# ─── 実行 ─────────────────────────────────────────────
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN が設定されていません")
    bot.run(TOKEN)
