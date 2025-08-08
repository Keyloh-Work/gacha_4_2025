import os
import asyncpg
import logging
import csv
import chardet
import random

logger = logging.getLogger(__name__)

async def init_db(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        # ユーザーPT
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_points (
          username TEXT PRIMARY KEY,
          points INTEGER NOT NULL
        );
        """)
        # 取得カード
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_cards (
          username TEXT,
          gachatype TEXT,
          card_no TEXT,
          PRIMARY KEY(username, gachatype, card_no)
        );
        """)
        # ガチャアイテム(spring & summer)
        for gt in ("halloween","summer_2025"):
            await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS gacha_items_{gt} (
              no     TEXT PRIMARY KEY,
              url    TEXT,
              chname TEXT,
              rarity TEXT,
              rate   REAL,
              title  TEXT
            );
            """)
        # 設定テーブル
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
          key   TEXT PRIMARY KEY,
          value INTEGER
        );
        """)
        # 初回だけdaily_auto_pointsを3にセット
        v = await conn.fetchval(
            "SELECT value FROM settings WHERE key='daily_auto_points'"
        )
        if v is None:
            await conn.execute(
                "INSERT INTO settings(key,value) VALUES('daily_auto_points', $1)",
                3
            )
    logger.info("DB initialized")

async def get_daily_auto_points(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT value FROM settings WHERE key='daily_auto_points'"
        )

async def set_daily_auto_points(pool: asyncpg.Pool, pt: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE settings SET value=$1 WHERE key='daily_auto_points'",
            pt
        )

async def add_daily_points_for_all(pool: asyncpg.Pool, daily_pt: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT username, points FROM user_points")
        for r in rows:
            new = min(15, r["points"] + daily_pt)
            await conn.execute(
                "UPDATE user_points SET points=$1 WHERE username=$2",
                new, r["username"]
            )
    logger.info(f"Added {daily_pt} daily pts to all users")

async def get_points(pool: asyncpg.Pool, username: str) -> int:
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT points FROM user_points WHERE username=$1",
            username
        )
        if v is None:
            await conn.execute(
                "INSERT INTO user_points(username, points) VALUES($1, $2)",
                username, 15
            )
            return 15
        return v

async def set_points(pool: asyncpg.Pool, username: str, pts: int):
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO user_points(username, points) VALUES($1,$2)
        ON CONFLICT(username) DO UPDATE SET points=excluded.points
        """, username, pts)

async def add_card(pool: asyncpg.Pool, username: str, gachatype: str, card_no: str):
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO user_cards(username, gachatype, card_no)
        VALUES($1,$2,$3)
        ON CONFLICT DO NOTHING
        """, username, gachatype, card_no)

async def get_user_cards(pool: asyncpg.Pool, username: str, gachatype: str) -> list:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT card_no FROM user_cards WHERE username=$1 AND gachatype=$2",
            username, gachatype
        )
        return [r["card_no"] for r in rows]

async def load_gacha_data(pool: asyncpg.Pool, csv_path: str, gachatype: str):
    table = f"gacha_items_{gachatype}"
    if not os.path.exists(csv_path):
        logger.error(f"CSV not found: {csv_path}")
        return
    with open(csv_path, 'rb') as f:
        enc = chardet.detect(f.read())['encoding']
    async with pool.acquire() as conn:
        with open(csv_path, newline='', encoding=enc) as cf:
            reader = csv.DictReader(cf)
            for r in reader:
                no, url, chname, rarity = r["No."], r["url"], r["chname"], r["rarity"]
                rate = 0.0
                try:
                    rate = float(r["rate"] or 0.0)
                except:
                    pass
                title = r["title"]
                exists = await conn.fetchval(
                    f"SELECT no FROM {table} WHERE no=$1", no
                )
                if exists:
                    continue
                await conn.execute(f"""
                    INSERT INTO {table}(no,url,chname,rarity,rate,title)
                    VALUES($1,$2,$3,$4,$5,$6)
                """, no, url, chname, rarity, rate, title)
    logger.info(f"Loaded {gachatype} data")

async def get_random_item(pool: asyncpg.Pool, gachatype: str):
    table = f"gacha_items_{gachatype}"
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT no,url,chname,rarity,rate,title FROM {table}")
        if not rows:
            return None
        total = sum(r["rate"] for r in rows)
        rnd = random.uniform(0, total)
        cum = 0.0
        for r in rows:
            cum += r["rate"]
            if rnd <= cum:
                return dict(r)
        return dict(rows[-1])
