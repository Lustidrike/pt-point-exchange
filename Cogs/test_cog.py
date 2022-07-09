import logging
import discord
import datetime
from discord.ext import commands
from os import linesep
from .base_cog import BaseCog
from conf import config
from dependency_load_error import DependencyLoadError

log = logging.getLogger(__name__)

class Testing(BaseCog):
    """A cog for testing."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.bot = bot
        timed_events_cog = BaseCog.load_dependency(self, 'TimedTasks')
        timed_events_cog.register_timed_event(self.testing_timed_task)

    async def testing_timed_task(self):
        await self.bot.post_message(context, self.bot.bot_channel, 'Testing timed task')

    async def on_season_end(self):
        await self.bot.post_message(context, self.bot.bot_channel, 'Testing season end')
        pass

    def extend_trivia_table(self, trivia_table):
        #raise Exception()
        pass

    @commands.command()
    async def testing(self, context):
        """Testing."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_admin(self, context)
        BaseCog.load_dependency(self, 'Core')
        await self.bot.post_message(context, context.message.channel, 'Success!')


def setup(bot):
    """Testing cog load."""
    bot.add_cog(Testing(bot))
    log.info("Testing cog loaded")
