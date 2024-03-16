from discord.ext import commands
from datetime import timedelta
import logging
from .base_cog import BaseCog

log = logging.getLogger(__name__)

class SelfTimeout(BaseCog):
    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.bot = bot
    
    @commands.command(aliases=["selftimeout", "to"])
    async def selfto(self, ctx, duration: str = commands.parameter(description="Length of time out. Examples: 2m = 2 minutes, 5h = 5 hours.")):
        """Times the user out for a specified amount of time which cannot exceed 48 hours. Go do your work!"""
        BaseCog.check_not_private(self, ctx)
        if len(duration) <= 1 or duration[-1].lower() not in ["h", "m"]:
            await self.bot.post_error(ctx, "Must supply a valid time duration.")
            return
        timechar = duration[-1]
        duration = duration[:-1]
        try:
            if timechar == "m":
                time = timedelta(minutes=int(duration))
            else:
                time = timedelta(hours=int(duration))
        except ValueError:
            await self.bot.post_error(ctx, "Must supply a valid time duration.")
            return
        if time.total_seconds() > 172800:
            await self.bot.post_error(ctx, "Total time must not exceed 2 days.")
            return
        try:
            await ctx.author.timeout(time)
            await self.bot.post_message(None, self.bot.bot_channel, "Successfully timed user out for the specified time.")
        except:
            await self.bot.post_error(ctx, "Could not time you out. You may have higher permissions than the bot.")

async def setup(bot):
    """Load self timeout cog."""
    await bot.add_cog(SelfTimeout(bot))
    log.info("Self Timeout cog loaded.")
