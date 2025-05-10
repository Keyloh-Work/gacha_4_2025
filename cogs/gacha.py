import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
from collections import defaultdict
import db
import logging

logger = logging.getLogger(__name__)
COOLDOWN = 10.0  # 秒

class PaginatorView(discord.ui.View):
    def __init__(self, data, collected):
        super().__init__(timeout=None)
        self.data = data
        self.collected = collected
        self.page = 0
        self.max_page = (len(data) - 1) // 20

    def get_lines(self):
        start = self.page * 20
        end = start + 20
        lines = []
        for item in self.data[start:end]:
            no = item["no"]
            chname = item["chname"]
            title = item["title"]
            url = item["url"]
            if no in self.collected:
                lines.append(
                    f":ballot_box_with_check: **No.{no}** {chname} {title} [🔗 Link]({url})"
                )
            else:
                lines.append(
                    f":blue_square: **No.{no}** {chname} {title}"
                )
        return lines

    async def update(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{interaction.user.name} の一覧 (Page {self.page+1}/{self.max_page+1})",
            description="\n".join(self.get_lines())
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="<<")
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        await self.update(interaction)

    @discord.ui.button(label="<")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await self.update(interaction)

    @discord.ui.button(label=">")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
        await self.update(interaction)

    @discord.ui.button(label=">>")
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        await self.update(interaction)


class ChnamePaginatorView(discord.ui.View):
    def __init__(self, grouped_data, collected):
        super().__init__(timeout=None)
        self.grouped = grouped_data
        self.collected = collected
        self.index = 0
        self.total_pages = len(grouped_data)   # ← 追加
        self.max_page = self.total_pages - 1

    def build_page_content(self):
        chname, items = self.grouped[self.index]
        lines = []
        for it in items:
            no = it["no"]
            title = it["title"]
            url = it["url"]
            if no in self.collected:
                lines.append(
                    f":ballot_box_with_check: **No.{no}** {title} [🔗 Link]({url})"
                )
            else:
                lines.append(
                    f":blue_square: **No.{no}** {title}"
                )
        return chname, lines

    async def update(self, interaction: discord.Interaction):
        chname, lines = self.build_page_content()
        embed = discord.Embed(
            title=f"{chname} の一覧 (Page {self.index+1}/{self.total_pages})",
            description="\n".join(lines)
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="<<")
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = 0
        await self.update(interaction)

    @discord.ui.button(label="<")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
        await self.update(interaction)

    @discord.ui.button(label=">")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < self.max_page:
            self.index += 1
        await self.update(interaction)

    @discord.ui.button(label=">>")
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = self.max_page
        await self.update(interaction)


class GachaButtonView(discord.ui.View):
    def __init__(self, bot, username, gachatype, display_name):
        super().__init__(timeout=None)
        self.bot = bot
        self.username = username
        self.gachatype = gachatype            # "spring" or "summer"
        self.display_name = display_name      # Choice.name ("春ガチャ"/"夏ガチャ")

    @discord.ui.button(label="ガチャを回す！", style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1) 残りポイント更新
        pts = await db.get_points(self.bot.db_pool, self.username)
        if pts <= 0:
            return await interaction.response.send_message(
                "ポイントが不足しています。", ephemeral=True
            )
        await db.set_points(self.bot.db_pool, self.username, pts - 1)
        remaining = pts - 1

        # ここで元のエフェメラルメッセージを更新
        await interaction.response.edit_message(
            content=f"{self.display_name} — 残りポイント: {remaining} pt"
        )

        # 2) ガチャ演出
        url_info = await db.get_random_item(self.bot.db_pool, self.gachatype)
        if url_info is None:
            return await interaction.followup.send(
                "ガチャデータの読み込みに失敗しました。", ephemeral=True
            )

        # ログに抽選履歴
        logger.info(
            f"User {self.username} drew [{self.gachatype}] No.{url_info['no']} / {url_info['title']}"
        )

        # 新規判定
        user_cards = await db.get_user_cards(
            self.bot.db_pool, self.username, self.gachatype
        )
        is_new = url_info["no"] not in user_cards
        if is_new:
            await db.add_card(
                self.bot.db_pool, self.username, self.gachatype, url_info["no"]
            )

        # 3) アニメーション表示
        await self.animate_embed(interaction, url_info, remaining, is_new)

    def add_emoji_to_rarity(self, rarity: str) -> str:
        if rarity == "N":
            return "🌈 N"
        elif rarity == "R":
            return "💫 R 💫"
        elif rarity == "SR":
            return "✨ 🌟 SR 🌟 ✨"
        elif rarity == "SSR":
            return "🎉✨✨👑 SSR 👑✨✨🎉"
        elif rarity == "UR":
            return "🎇✨✨🌟💎 UR 💎🌟✨✨🎇"
        return rarity

    async def animate_embed(self, interaction, url_info, remaining, is_new):
        # 「ガチャ中…」フォロワップ
        msg = await interaction.followup.send("ガチャ中…", ephemeral=False)
        await asyncio.sleep(1)

        # タイトル
        embed = discord.Embed(
            title=self.display_name
        )
        await msg.edit(content=None, embed=embed)
        await asyncio.sleep(1)

        # キャラ
        embed.add_field(name="キャラ", value=url_info['chname'], inline=True)
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

        # レア度 → 装飾付きに差し替え
        embed.add_field(name="レア度", value="...", inline=True)
        await msg.edit(embed=embed)
        await asyncio.sleep(1)
        decorated = self.add_emoji_to_rarity(url_info['rarity'])
        embed.set_field_at(1, name="レア度", value=decorated, inline=True)
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

        # No. & NEW
        embed.add_field(name="イラストNo.", value=f"No.{url_info['no']}", inline=True)
        if is_new:
            embed.add_field(name="\u200b", value="✨NEW✨", inline=True)
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

        # タイトル文
        embed.add_field(name="タイトル", value=url_info['title'], inline=True)
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

        # URL と画像
        embed.add_field(name="URL", value=f"[🔗 Link]({url_info['url']})", inline=False)
        embed.set_image(url=url_info['url'])
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

        # 残りポイント
        embed.add_field(name="残りポイント", value=f"**{remaining} pt**", inline=False)
        await msg.edit(embed=embed)


class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
    name="creategachathread",
    description="専用ガチャスレッドを作成します"
    )
    async def creategachathread(self, interaction: discord.Interaction):
        # 実行可能チャンネルチェック
        if interaction.channel.name != "gacha-channel":
            return await interaction.response.send_message(
                "このコマンドは gacha-channel 内でのみ実行できます。",
                ephemeral=True
            )
        # すでにスレッドがあるか確認
        existing = discord.utils.get(
            interaction.channel.threads,
            name=f"gacha-thread-{interaction.user.name}"
        )
        if existing:
            return await interaction.response.send_message(
                "あなた専用のガチャスレッドは既に存在します。",
                ephemeral=True
            )
        # Interaction を defer してからスレッド作成
        await interaction.response.defer(ephemeral=True)
        thread = await interaction.channel.create_thread(
            name=f"gacha-thread-{interaction.user.name}",
            type=discord.ChannelType.private_thread,
            auto_archive_duration=10080,  # 1週間
            invitable=False               # 招待不可
        )
        await thread.add_user(interaction.user)
        await thread.edit(slowmode_delay=10)
        await thread.send(
            f"{interaction.user.mention} さんの専用ガチャスレッドです。\n"
            "`/gacha spring` または `/gacha summer` を実行すると\n"
            "ガチャボタンが表示されます。\n"
            "**このスレッドから退出しないでください。**"
        )

        # 完了メッセージ（フォローアップ）
        await interaction.followup.send(
            "専用ガチャスレッドを作成しました！",
            ephemeral=True
        )

    
    @app_commands.command(name="gacha", description="ガチャを回します")
    @app_commands.choices(
        gachatype=[
            app_commands.Choice(name="春ガチャ", value="spring"),
            app_commands.Choice(name="夏ガチャ", value="summer"),
        ]
    )
    @app_commands.describe(gachatype="回すガチャを選択してください")
    async def gacha(
        self,
        interaction: discord.Interaction,
        gachatype: app_commands.Choice[str],
    ):
        user = interaction.user.name
        now = time.time()
        last = self.bot.last_gacha_usage.get(user, 0)
        if now - last < COOLDOWN:
            return await interaction.response.send_message(
                f"クールダウン中です：あと{int(COOLDOWN - (now-last))}秒",
                ephemeral=True
            )
            return
        self.bot.last_gacha_usage[user_id] = now

        display = gachatype.name       # e.g. "春ガチャ"
        gtype = gachatype.value        # "spring" or "summer"
        pts = await db.get_points(self.bot.db_pool, user)

        if not (
            isinstance(interaction.channel, discord.Thread)
            and interaction.channel.name.startswith("gacha-thread-")
        ):
            return await interaction.response.send_message(
                "専用スレッド内で実行してください", ephemeral=True
            )

        view = GachaButtonView(self.bot, user, gtype, display)
        await interaction.response.send_message(
            f"{display} — 残りポイント: {pts} pt",
            view=view, ephemeral=True
        )

    @app_commands.command(name="artlistnum", description="取得カード一覧 (No順)")
    @app_commands.choices(
        gachatype=[
            app_commands.Choice(name="春ガチャ", value="spring"),
            app_commands.Choice(name="夏ガチャ", value="summer"),
        ]
    )
    @app_commands.describe(gachatype="表示するガチャを選択してください")
    async def artlistnum(
        self,
        interaction: discord.Interaction,
        gachatype: app_commands.Choice[str],
    ):
        user = interaction.user.name
        if not (
            isinstance(interaction.channel, discord.Thread)
            and interaction.channel.name.startswith("gacha-thread-")
        ):
            return await interaction.response.send_message(
                "専用スレッド内で実行してください", ephemeral=True
            )

        gtype = gachatype.value
        cards = await db.get_user_cards(self.bot.db_pool, user, gtype)
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT no,url,chname,title FROM gacha_items_{gtype} ORDER BY CAST(no AS INT)"
            )
        data = [dict(r) for r in rows]
        view = PaginatorView(data, cards)
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"{user} の一覧 (No順／{gachatype.name})",
                description="\n".join(view.get_lines())
            ),
            view=view
        )

    @app_commands.command(name="artlistch", description="取得カード一覧 (キャラ順)")
    @app_commands.choices(
        gachatype=[
            app_commands.Choice(name="春ガチャ", value="spring"),
            app_commands.Choice(name="夏ガチャ", value="summer"),
        ]
    )
    @app_commands.describe(gachatype="表示するガチャを選択してください")
    async def artlistch(
        self,
        interaction: discord.Interaction,
        gachatype: app_commands.Choice[str],
    ):
        user = interaction.user.name
        if not (
            isinstance(interaction.channel, discord.Thread)
            and interaction.channel.name.startswith("gacha-thread-")
        ):
            return await interaction.response.send_message(
                "専用スレッド内で実行してください", ephemeral=True
            )

        gtype = gachatype.value
        cards = await db.get_user_cards(self.bot.db_pool, user, gtype)
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT no,url,chname,title FROM gacha_items_{gtype}"
            )
        grouped = defaultdict(list)
        for r in rows:
            grouped[r["chname"]].append(dict(r))
        grouped_data = sorted(grouped.items(), key=lambda x: x[0])
        view = ChnamePaginatorView(grouped_data, cards)
        chname, lines = view.build_page_content()
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"{user} の一覧 ({gachatype.name}・{chname})\nPage 1/{view.total_pages}",
                description="\n".join(lines)
            ),
            view=view
        )

async def setup(bot):
    await bot.add_cog(GachaCog(bot))
