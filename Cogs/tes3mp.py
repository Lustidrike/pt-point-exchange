import logging
import discord
import json
from discord.ext import commands
from operator import itemgetter
from os import linesep
from .base_cog import BaseCog
from conf import config

log = logging.getLogger(__name__)


class Tes3Mp(BaseCog):
    """A cog for general tes3mp-related commands."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.tesmp_role = 'TES3MP Player'
        bot.info_text += 'Tes3mp: ' + linesep + '  You may add/remove the \'' + self.tesmp_role + '\' role by using the !subscribemp and !unsubscribemp commands respectively.' + linesep + linesep


    @commands.command()
    async def subscribemp(self, context):
        """Get a notification every time we play tes3mp."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        role = discord.utils.get(context.message.author.guild.roles, name=self.tesmp_role)

        if role in context.message.author.roles:
            await self.bot.post_error(context, 'You are already subscribed, ' + context.message.author.name + '.')

        else:
            await context.message.author.add_roles(role)
            await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** Added ' + context.message.author.name + ' to the tes3mp player list.')


    @commands.command()
    async def unsubscribemp(self, context):
        """Removes tes3mp role so that you don't get a notification every time we play together anymore."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        role = discord.utils.get(context.message.author.guild.roles, name=self.tesmp_role)

        if role not in context.message.author.roles:
            await self.bot.post_error(context, 'You are not subscribed, ' + context.message.author.name + '.')
        else:
            await context.message.author.remove_roles(role)
            await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** Removed ' + context.message.author.name + ' from the tes3mp player list.')



def setup(bot):
    """Tes3Mp cog load."""
    bot.add_cog(Tes3Mp(bot))
    log.info("Tes3Mp cog loaded")
