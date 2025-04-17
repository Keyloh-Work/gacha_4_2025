import discord
from discord.ext import commands
import logging
import db

logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addpointuser")
    @commands.has_permissions(administrator=True)
    async def addpointuser(self, ctx, member: discord.Member, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            await ctx.send("このコマンドは gacha-dev チャンネルでのみ使用できます。")
            return
        current_points = await db.get_points(self.bot.db_pool, member.id)
        new_points = min(15, current_points + pointnumber)
        await db.set_points(self.bot.db_pool, member.id, new_points)
        await ctx.send(f"{member.display_name} に {pointnumber} ポイント付与しました。({current_points} -> {new_points})")

    @commands.command(name="addpointall")
    @commands.has_permissions(administrator=True)
    async def addpointall(self, ctx, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            await ctx.send("このコマンドは gacha-dev チャンネルでのみ使用できます。")
            return
        count = 0
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, points FROM user_points")
            for row in rows:
                current_points = row['points']
                new_points = min(15, current_points + pointnumber)
                await conn.execute("UPDATE user_points SET points=$1 WHERE user_id=$2", new_points, row['user_id'])
                if new_points > current_points:
                    count += 1
        await ctx.send(f"全てのユーザーに {pointnumber} ポイント付与しました。(上限15まで)\nポイントが増えたユーザー数: {count}")

    @commands.command(name="addpointauto")
    @commands.has_permissions(administrator=True)
    async def addpointauto(self, ctx, pointnumber: int):
        if ctx.channel.name != "gacha-dev":
            await ctx.send("このコマンドは gacha-dev チャンネルでのみ使用できます。")
            return
        if pointnumber < 0:
            await ctx.send("0以上の値を指定してください。")
            return
        old_value = self.bot.daily_auto_points
        self.bot.daily_auto_points = pointnumber
        await ctx.send(f"毎日00:00時に自動付与されるポイントを {old_value} から {pointnumber} に変更しました。\n次に迎える00:00から {pointnumber} ポイントが付与されます。")
        logger.info(f"Admin changed daily auto points from {old_value} to {pointnumber}")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
