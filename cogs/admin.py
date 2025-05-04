import discord
from discord.ext import commands
import db
import logging

logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addpointuser")
    @commands.has_permissions(administrator=True)
    async def addpointuser(self, ctx, member: discord.Member, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            return await ctx.send("このコマンドは gacha-dev チャンネルのみで実行できます。")
        uname = member.name
        cur = await db.get_points(self.bot.db_pool, uname)
        new = min(15, cur + pointnumber)
        await db.set_points(self.bot.db_pool, uname, new)
        await ctx.send(f"{member.display_name} に {pointnumber}pt付与 ({cur}->{new})")
        logger.info(f"Admin {ctx.author.name} set {uname} pts {cur}->{new}")

    @commands.command(name="addpointall")
    @commands.has_permissions(administrator=True)
    async def addpointall(self, ctx, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            return await ctx.send("このコマンドは gacha-dev チャンネルのみで実行できます。")
        cnt = 0
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT username,points FROM user_points")
            for r in rows:
                cur = r["points"]
                new = min(15, cur + pointnumber)
                await conn.execute(
                    "UPDATE user_points SET points=$1 WHERE username=$2",
                    new, r["username"]
                )
                if new > cur:
                    cnt += 1
        await ctx.send(f"全ユーザーに{pointnumber}pt付与 (増えた数: {cnt})")
        logger.info(f"Admin {ctx.author.name} addpointall +{pointnumber}, affected {cnt}")

    @commands.command(name="addpointauto")
    @commands.has_permissions(administrator=True)
    async def addpointauto(self, ctx, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            return await ctx.send("このコマンドは gacha-dev チャンネルのみで実行できます。")
        if pointnumber < 0:
            return await ctx.send("0以上を指定してください。")
        old = await db.get_daily_auto_points(self.bot.db_pool)
        await db.set_daily_auto_points(self.bot.db_pool, pointnumber)
        await ctx.send(f"自動付与ptを{old}->{pointnumber}に変更しました。")
        logger.info(f"Admin {ctx.author.name} set daily_auto_points {old}->{pointnumber}")

async def setup(bot):
    bot.add_cog(AdminCog(bot))
