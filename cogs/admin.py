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
            return await ctx.send("このコマンドは gacha-dev チャンネル内でのみ使用できます。")
        uname = member.name
        old = await db.get_points(self.bot.db_pool, uname)
        new = min(15, old + pointnumber)
        await db.set_points(self.bot.db_pool, uname, new)
        await ctx.send(f"{member.display_name} に {pointnumber}pt 付与しました。({old} → {new})")
        logger.info(f"Admin {ctx.author.name} used addpointuser: member={uname}, pointnumber={pointnumber}")

    @commands.command(name="addpointall")
    @commands.has_permissions(administrator=True)
    async def addpointall(self, ctx, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            return await ctx.send("このコマンドは gacha-dev チャンネル内でのみ使用できます。")
        cnt = 0
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT username, points FROM user_points")
            for r in rows:
                old = r["points"]
                new = min(15, old + pointnumber)
                await conn.execute(
                    "UPDATE user_points SET points=$1 WHERE username=$2",
                    new, r["username"]
                )
                if new > old:
                    cnt += 1
        await ctx.send(f"全ユーザーに {pointnumber}pt 付与しました (増えたユーザー数: {cnt})")
        logger.info(f"Admin {ctx.author.name} used addpointall: pointnumber={pointnumber}")

    @commands.command(name="addpointauto")
    @commands.has_permissions(administrator=True)
    async def addpointauto(self, ctx, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            return await ctx.send("このコマンドは gacha-dev チャンネル内でのみ使用できます。")
        if pointnumber < 0:
            return await ctx.send("0以上の値を指定してください。")
        old = await db.get_daily_auto_points(self.bot.db_pool)
        await db.set_daily_auto_points(self.bot.db_pool, pointnumber)
        await ctx.send(f"自動付与ポイントを {old} → {pointnumber} に変更しました。")
        logger.info(f"Admin {ctx.author.name} used addpointauto: pointnumber={pointnumber}")

# ここがポイント。必ず await して Cog を登録します
async def setup(bot):
    await bot.add_cog(AdminCog(bot))
