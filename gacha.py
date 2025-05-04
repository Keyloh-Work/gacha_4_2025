import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
from collections import defaultdict
import db
import logging

logger = logging.getLogger(__name__)
COOLDOWN = 10.0

class PaginatorView(discord.ui.View):
    def __init__(self, data, collected):
        super().__init__(timeout=None)
        self.data = data
        self.collected = collected
        self.page = 0
        self.max = (len(data)-1)//20

    def get_lines(self):
        start = self.page*20
        end = start+20
        lines = []
        for item in self.data[start:end]:
            no = item["no"]
            text = f"🔗 Link"
            if no in self.collected:
                lines.append(f":ballot_box_with_check: **No.{no}** {item['chname']} {item['title']} [{text}]({item['url']})")
            else:
                lines.append(f":blue_square: **No.{no}** {item['chname']} {item['title']}")
        return lines

    async def update(self, inter):
        emb = discord.Embed(
            title=f"{inter.user.name} のリスト (Page {self.page+1}/{self.max+1})",
            description="\n".join(self.get_lines())
        )
        await inter.response.edit_message(embed=emb, view=self)

    @discord.ui.button(label="<<")
    async def first(self, inter, btn):
        self.page = 0
        await self.update(inter)

    @discord.ui.button(label="<")
    async def prev(self, inter, btn):
        if self.page>0: self.page-=1
        await self.update(inter)

    @discord.ui.button(label=">")
    async def nxt(self, inter, btn):
        if self.page<self.max: self.page+=1
        await self.update(inter)

    @discord.ui.button(label=">>")
    async def last(self, inter, btn):
        self.page = self.max
        await self.update(inter)

class GachaButtonView(discord.ui.View):
    def __init__(self, bot, uname, gachatype):
        super().__init__(timeout=None)
        self.bot = bot
        self.uname = uname
        self.gachatype = gachatype

    @discord.ui.button(label="ガチャを回す！", style=discord.ButtonStyle.primary)
    async def callback(self, inter, btn):
        await inter.response.defer()
        pts = await db.get_points(self.bot.db_pool, self.uname)
        if pts<=0:
            return await inter.followup.send("ポイント不足", ephemeral=True)
        await db.set_points(self.bot.db_pool, self.uname, pts-1)
        await inter.edit_original_response(
            content=f"{self.gachatype}ガチャ — 残りポイント: {pts-1} pt"
        )
        info = await db.get_random_item(self.bot.db_pool, self.gachatype)
        is_new = info["no"] not in await db.get_user_cards(self.bot.db_pool, self.uname, self.gachatype)
        if is_new:
            await db.add_card(self.bot.db_pool, self.uname, self.gachatype, info["no"])

        msg = await inter.followup.send("ガチャ中…")
        await asyncio.sleep(1)
        emb = discord.Embed(title=f"{self.gachatype} ガチャ結果")
        emb.add_field(name="キャラ", value=info["chname"], inline=True)
        emb.add_field(name="レア度", value=info["rarity"], inline=True)
        emb.add_field(name="No.", value=info["no"], inline=True)
        if is_new:
            emb.add_field(name="NEW", value="✨NEW✨", inline=True)
        emb.add_field(name="タイトル", value=info["title"], inline=True)
        emb.add_field(name="URL", value=f"[🔗 Link]({info['url']})", inline=False)
        emb.add_field(name="残りポイント", value=f"**{pts-1} pt**", inline=False)
        emb.set_image(url=info["url"])
        await msg.edit(embed=emb)

class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /gacha spring|summer
    @app_commands.command(name="gacha", description="ガチャを回します")
    @app_commands.describe(gachatype="spring または summer")
    async def gacha(self, inter: discord.Interaction, gachatype: str):
        user = inter.user.name
        now = time.time()
        last = self.bot.last_gacha_usage.get(user, 0)
        if now-last<COOLDOWN:
            return await inter.response.send_message(
                f"クールダウン中：あと{int(COOLDOWN-(now-last))}秒", ephemeral=True
            )
        self.bot.last_gacha_usage[user]=now
        pts = await db.get_points(self.bot.db_pool, user)
        if not (isinstance(inter.channel, discord.Thread)
                and inter.channel.name.startswith("gacha-thread-")):
            return await inter.response.send_message(
                "ガチャスレッド内で実行してください", ephemeral=True
            )
        view = GachaButtonView(self.bot, user, gachatype)
        await inter.response.send_message(
            f"{gachatype}ガチャ — 残りポイント: {pts} pt",
            view=view, ephemeral=True
        )

    # /creategachathread
    @app_commands.command(name="creategachathread", description="専用スレッド作成")
    async def creategacha(self, inter: discord.Interaction):
        if inter.channel.name!="gacha-channel":
            return await inter.response.send_message(
                "gacha-channel内でのみ実行可能", ephemeral=True
            )
        exist = discord.utils.get(
            inter.channel.threads,
            name=f"gacha-thread-{inter.user.name}"
        )
        if exist:
            return await inter.response.send_message(
                "既存スレッドがあります", ephemeral=True
            )
        await inter.response.defer(ephemeral=True)
        th = await inter.channel.create_thread(
            name=f"gacha-thread-{inter.user.name}",
            type=discord.ChannelType.private_thread,
            auto_archive_duration=10080,
            invitable=False
        )
        await th.add_user(inter.user)
        await th.edit(slowmode_delay=10)
        await th.send(f"{inter.user.mention} の専用ガチャスレッドです。\n`/gacha spring` または `/gacha summer` で回せます。")
        await inter.followup.send("スレッドを作成しました", ephemeral=True)

    # /artlistnum spring|summer
    @app_commands.command(name="artlistnum", description="一覧(No順)")
    @app_commands.describe(gachatype="spring または summer")
    async def artlistnum(self, inter: discord.Interaction, gachatype: str):
        user = inter.user.name
        if not (isinstance(inter.channel, discord.Thread)
                and inter.channel.name.startswith("gacha-thread-")):
            return await inter.response.send_message(
                "スレッド内で実行してください", ephemeral=True
            )
        cards = await db.get_user_cards(self.bot.db_pool, user, gachatype)
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT no,url,chname,title FROM gacha_items_{gachatype}
                ORDER BY CAST(no AS INT)
            """)
        data = [dict(r) for r in rows]
        view = PaginatorView(data, cards)
        emb = discord.Embed(
            title=f"{user} の一覧(No順)",
            description="\n".join(view.get_lines())
        )
        await inter.response.send_message(embed=emb, view=view)

    # /artlistch spring|summer
    @app_commands.command(name="artlistch", description="一覧(キャラ順)")
    @app_commands.describe(gachatype="spring または summer")
    async def artlistch(self, inter: discord.Interaction, gachatype: str):
        user = inter.user.name
        if not (isinstance(inter.channel, discord.Thread)
                and inter.channel.name.startswith("gacha-thread-")):
            return await inter.response.send_message(
                "スレッド内で実行してください", ephemeral=True
            )
        cards = await db.get_user_cards(self.bot.db_pool, user, gachatype)
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT no,url,chname,title FROM gacha_items_{gachatype}
            """)
        grouped = defaultdict(list)
        for r in rows:
            grouped[r["chname"]].append(dict(r))
        grp = sorted(grouped.items(), key=lambda x: x[0])
        view = PaginatorView([], cards)  # Dummy, reuse view logic
        # We’ll override get_lines / update for char groups if needed…
        # For brevity just send first char page:
        ch, items = grp[0]
        lines = []
        for it in items:
            no = it["no"]
            if no in cards:
                lines.append(f":ballot_box_with_check: **No.{no}** {it['title']} [🔗 Link]({it['url']})")
            else:
                lines.append(f":blue_square: **No.{no}** {it['title']}")
        emb = discord.Embed(
            title=f"{user} の一覧({gachatype}・{ch})",
            description="\n".join(lines)
        )
        await inter.response.send_message(embed=emb)

async def setup(bot):
    await bot.add_cog(GachaCog(bot))
