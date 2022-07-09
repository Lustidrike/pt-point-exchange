import logging
import discord
import datetime
import json
from operator import itemgetter
from discord.ext import commands
from os import linesep
from .base_cog import BaseCog
from conf import config
from datetime import date

log = logging.getLogger(__name__)

class Core(BaseCog):
    """A minimal cog for testing."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.main_db = bot.database.table('main_db')
        self.bot = bot

        with open(config.cogs_data_path + '/user_shortcuts.json', 'r') as shortcuts_file:
            self.shortcuts = json.load(shortcuts_file)


    @commands.command()
    async def info(self, context):
        """General information on the bot instance."""

        BaseCog.check_forbidden_characters(self, context)
        await self.bot.send_private_message(context, '```' + self.bot.info_text + '```')


    @commands.command(pass_context=True)
    async def time(self, context):
        """Displays current local time and date for the bot."""

        BaseCog.check_forbidden_characters(self, context)
        await self.bot.send_revertible(context, context.message.channel, 'Current time is ' + datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + ' (' + config.timezone + ').')


    @commands.command()
    async def shortcuts(self, context):
        """Displays registered shortcuts for user nicknames."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)

        indent = max(len(shortcut) for shortcut, name in self.shortcuts.items())

        sorted_shortcuts = sorted(self.shortcuts.items(), key=itemgetter(0), reverse=False)

        result = '```Shortcut    Nickname' + linesep + linesep

        for shortcut, name in sorted_shortcuts:
            result += shortcut.ljust(indent) + '  ' + name + linesep

        result += '```'
        await self.bot.send_private_message(context, result)


    @commands.command()
    async def addshortcut(self, context, shortcut, user):
        """Creates a new shortcut for a particular username."""

        BaseCog.check_not_private(self, context)
        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_admin(self, context)
        BaseCog.check_forbidden_characters(self, context)

        if not self.main_db.contains(self.bot.query.user == user):
            await self.bot.post_error(context, 'User ' + user + ' has not been added yet. They need to type !add to initialize their account before a shortcut can be created.')
            return

        self.shortcuts[shortcut] = user

        with open(config.cogs_data_path + '/user_shortcuts.json', 'w') as shortcuts_file:
            json.dump(self.shortcuts, shortcuts_file)

        await self.bot.post_message(context, self.bot.bot_channel, context.message.author.name + ' has created a new shortcut \'' + shortcut + '\'.')


    @commands.command()
    async def deleteshortcut(self, context, shortcut):
        """Deletes an existing user shortcut."""

        BaseCog.check_not_private(self, context)
        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_admin(self, context)
        BaseCog.check_forbidden_characters(self, context)

        if shortcut in self.shortcuts:
            del self.shortcuts[shortcut]
            with open(config.cogs_data_path + '/user_shortcuts.json', 'w') as shortcuts_file:
                json.dump(self.shortcuts, shortcuts_file)

            await self.bot.post_message(context, self.bot.bot_channel, context.message.author.name + ' has deleted the shortcut \'' + shortcut + '\'.')
        else:
            await self.bot.post_error(context, 'The shortcut \'' + shortcut + '\' does not exist, ' + context.message.author.name + '.')



def setup(bot):
    """Core cog load."""
    bot.add_cog(Core(bot))
    log.info("Core cog loaded")
