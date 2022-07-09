import logging
import discord
from discord.ext import commands
from conf import config
from dependency_load_error import DependencyLoadError

log = logging.getLogger(__name__)

class BaseCog(commands.Cog):
    """Base class for all cogs."""


    def __init__(self, bot):
        self.bot = bot


    def load_dependency(self, dependency):
        result = self.bot.get_cog(dependency)

        if result is None:
            raise DependencyLoadError()

        return result


    #================ BASECOG INTERFACE ================
    def extend_check_options(self, db_entry):
        return None


    def extend_trivia_table(self, trivia_table):
        pass


    def extend_trivia_output(self, trivia_table):
        return None


    def extend_season_output(self, number, season_trivia_table, season_main_db, season_tables):
        return None


    def get_check_message_for_aspect(self, aspect):
        return None


    def get_label_for_command(self, command):
        return None


    async def on_season_end(self):
        pass
    #==============================================


    def map_user(self, user):
        """Map user shortcuts to actual usernames as they appear in the database."""

        user_lower = user.lower()
        found = False

        try:
            economy_cog = BaseCog.load_dependency(self, 'Economy')
            core_cog = BaseCog.load_dependency(self, 'Core')
        except DependencyLoadError:
            return user

        for item in economy_cog.main_db:
            if user_lower == item['user'].lower():
                user = item['user']
                found = True
                break

        if not found:
            for s, u in core_cog.shortcuts.items():
                if user_lower == s.lower():
                    user = u
                    break

        return user

    #========= COMMON CHECKS =========

    def check_bot_channel(self, ctx):
        if not ctx.message.channel == self.bot.bot_channel and ctx.message.guild is not None:
            raise commands.CheckFailure(message='')


    def check_not_private(self, ctx):
        if ctx.message.guild is None:
            raise commands.CheckFailure(message='This command may not be issued in a private context, sorry.')


    def check_admin(self, ctx):
        roles = [role.id for role in ctx.message.author.roles]
        if ctx.message.author.name != config.owner and not (set(roles) & set(self.bot.admin_roles)):
            raise commands.CheckFailure(message='Permission denied. Your roles are insufficient to use this specific command.')


    def check_owner(self, ctx):
        if ctx.message.author.name != config.owner:
            raise commands.CheckFailure(message='Permission denied. Your roles are insufficient to use this specific command.')


    def check_forbidden_characters(self, ctx):
        if any(char in ctx.message.content for char in config.forbidden_characters):
            raise commands.CheckFailure(message='Your message includes a forbidden character, ' + ctx.message.author.name + '. Sorry.')


    def check_main_server(self, ctx):
        if ctx.message.guild is not None and not ctx.message.guild.id == config.main_server:
            raise commands.CheckFailure(message='')


    async def dynamic_user_add(self, ctx):
        try:
            economy_cog = BaseCog.load_dependency(self, 'Economy')
        except DependencyLoadError:
            await self.bot.post_error(ctx, 'Oh no, something went wrong (DNL). ' + config.additional_error_message)
            return

        if not economy_cog.main_db.contains(self.bot.query.user == ctx.message.author.name):
            await economy_cog.add_internal(ctx.message.author.name)

    #==================================
