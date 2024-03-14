import logging
import discord
import json
from discord.ext import commands
from operator import itemgetter
from os import linesep
from .base_cog import BaseCog
from conf import config

log = logging.getLogger(__name__)


class Gambling(BaseCog):
    """A cog for general gambling commands and everything global for all minigames."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.lock = True
        bot.info_text += 'Gambling: ' + linesep + '  ' + config.currency_name + 's can be gambled with in various minigames. Participation is optional.' + linesep + linesep

        with open(config.cogs_data_path + '/gambling.json', 'r') as gambling_config:
            self.weapon_emotes = json.load(gambling_config)['weapon_emotes']

        self.lock_max_bet = int(config.get('Gambling', 'lock_max_bet', fallback=15))
        self.unlock_max_points_to_give_per_day = int(config.get('Gambling', 'unlock_max_points_to_give_per_day', fallback=10000))
        self.subscriber_role = config.get('Gambling', 'subscriber_role', fallback='')


    #================ BASECOG INTERFACE ================
    def extend_check_options(self, db_entry):
        result_string = (config.currency_name + ' profit from gambling').ljust(config.check_ljust) + ' ' + str(db_entry['gambling_profit'])
        return result_string


    def extend_season_output(self, number, season_trivia_table, season_main_db, season_tables):
        result = ''

        gambling = max(season_main_db.all(), key=itemgetter('gambling_profit'))

        if gambling['gambling_profit'] > 0:
            result += 'Most profit made from gambling'.ljust(config.season_ljust) + '  ' + str(gambling['gambling_profit']) + ' by ' + gambling['user'] + linesep

        return result


    def get_check_message_for_aspect(self, aspect):
        mes = None

        if aspect == 'gambling_profit':
            mes = config.currency_name + ' profit from gambling'

        return mes


    def get_label_for_command(self, command):
        result = None

        if command == 'gambling_profit':
            result = 'profit from gambling'

        return result
    #==============================================


    @commands.command(hidden=True)
    async def unlock(self, context):
        """Unlocks high-stake gambling."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_owner(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')

        self.lock = False
        economy.max_points_to_give_per_day = self.unlock_max_points_to_give_per_day
        await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** High-stakes gambling is now unlocked.')
        await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** Max points to give per day is ' + str(self.unlock_max_points_to_give_per_day) + '.')

    @commands.command(hidden=True)
    async def lock(self, context):
        """Locks high-stake gambling."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_owner(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')

        self.lock = True
        economy.max_points_to_give_per_day = int(config.get('Economy', 'max_points_to_give_per_day', fallback=30))
        await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** High-stakes gambling is now locked.')

    @commands.command()
    async def subscribe(self, context):
        """Get a notification every time we play minigames."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        role = discord.utils.get(context.message.author.guild.roles, name=self.subscriber_role)

        if role in context.message.author.roles:
            await self.bot.post_error(context, 'You are already subscribed, ' + context.message.author.name + '.')

        else:
            await context.message.author.add_roles(role)
            await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** Added ' + context.message.author.name + ' to the subscriber list.')


    @commands.command()
    async def unsubscribe(self, context):
        """Removes subscriber role so that you don't get a notification every time we play minigames anymore."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        role = discord.utils.get(context.message.author.guild.roles, name=self.subscriber_role)

        if role not in context.message.author.roles:
            await self.bot.post_error(context, 'You are not subscribed, ' + context.message.author.name + '.')
        else:
            await context.message.author.remove_roles(role)
            await self.bot.post_message(context, self.bot.bot_channel, '**[INFO]** Removed ' + context.message.author.name + ' from the subscriber list.')



async def setup(bot):
    """Gambling cog load."""
    await bot.add_cog(Gambling(bot))
    log.info("Gambling cog loaded")
