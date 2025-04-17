import os
import asyncpg
import logging
import csv
import chardet
import random

logger = logging.getLogger(__name__)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                user_id BIGINT PRIMARY KEY,
                points INTEGER NOT NULL
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                user_id BIGINT,
                card_no TEXT,
                PRIMARY KEY(user_id, card_no)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gacha_items (
                no TEXT PRIMARY KEY,
                url TEXT,
                chname TEXT,
                rarity TEXT,
                rate REAL,
                title TEXT
            );
        """)
    logger.info("Database initialized.")

async def get_points(pool, user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT points FROM user_points WHERE user_id=$1", user_id)
        if row is None:
            # 初期値15ptでユーザー登録
            await conn.execute("INSERT INTO user_points(user_id, points) VALUES($1, $2)", user_id, 15)
            return 15
        return row['points']

async def set_points(pool, user_id: int, points: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_points(user_id, points) VALUES($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET points=EXCLUDED.points
        """, user_id, points)

async def add_card(pool, user_id: int, card_no: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_cards(user_id, card_no) VALUES($1, $2)
            ON CONFLICT DO NOTHING
        """, user_id, card_no)

async def get_user_cards(pool, user_id: int) -> list:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT card_no FROM user_cards WHERE user_id=$1", user_id)
        return [r['card_no'] for r in rows]

async def add_daily_points(pool, daily_auto_points: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, points FROM user_points")
        for row in rows:
            current = row['points']
            new_pt = current if current >= 15 else min(15, current + daily_auto_points)
            await conn.execute("UPDATE user_points SET points=$1 WHERE user_id=$2", new_pt, row['user_id'])
    logger.info("Daily points added to all users.")

async def load_gacha_data(pool, csv_path):
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        return

    with open(csv_path, 'rb') as f:
        result = chardet.detect(f.read())
    encoding = result['encoding']

    async with pool.acquire() as conn:
        with open(csv_path, newline='', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                no = row["No."]
                url = row["url"]
                chname = row["chname"]
                rarity = row["rarity"]
                value = row["rate"].strip()
                try:
                    rate = float(value) if value else 0.0
                except ValueError:
                    logger.warning(f"Invalid rate, using 0.0: {row}")
                    rate = 0.0
                title = row["title"]
                exists = await conn.fetchval("SELECT no FROM gacha_items WHERE no=$1", no)
                if exists:
                    continue
                await conn.execute("""
                    INSERT INTO gacha_items (no, url, chname, rarity, rate, title)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, no, url, chname, rarity, rate, title)
    logger.info("Gacha data loaded into DB.")

async def get_random_item_from_db(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT no, url, chname, rarity, rate, title FROM gacha_items")
        if not rows:
            return None
        total_rate = sum(row['rate'] for row in rows)
        r = random.uniform(0, total_rate)
        current = 0
        for row in rows:
            current += row['rate']
            if r <= current:
                return dict(row)
        return dict(rows[-1])
