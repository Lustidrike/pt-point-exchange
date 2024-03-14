import logging
import discord
from discord.ext import commands
from operator import itemgetter
from os import linesep, listdir
import os
from .base_cog import BaseCog
from tinydb import TinyDB
from conf import config

log = logging.getLogger(__name__)

class Stats(BaseCog):
    """A cog for displaying various user- or server-related stats."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.trivia_table = bot.database.table('trivia_table')
        self.seasons_path = config.get('Private', 'seasons_path', fallback='seasons')

        # Past seasons, if available
        self.season_tables = []

        try:
            if len(self.trivia_table) < 1:
                self.reset_trivia()
        except Exception as e:
            print('Stats::__init__: Error while resetting trivia table!')
            log.exception(e)

        for i in range(1, 20):
            filename = self.seasons_path + '/' + 'season' + str(i) + '.json'
            if os.path.isfile(filename):
                season_db = TinyDB(filename)
                self.season_tables.append((season_db.table('main_db'), season_db.table('trivia_table')))


        log.info('Loaded ' + str(len(self.season_tables)) + ' season tables')


    def reset_trivia(self):
        for cog_name, cog in self.bot.cogs.items():
            cog.extend_trivia_table(self.trivia_table)


    #================ BASECOG INTERFACE ================
    async def on_season_end(self):
        self.trivia_table.truncate()
        self.reset_trivia()
    #==============================================


    def get_check_result_string(self, command, ctype):
        result = None

        # NOTE: economy cog is always loaded in functions prior to calling this, so is expected to be available
        if not command:
            command = 'balance'
            result = 'total ' + config.currency_name + 's'
        elif command == 'given':
            result = 'points given'
        elif command == 'received':
            result = 'points received'
        else:
            for cog_name, cog in self.bot.cogs.items():
                result = cog.get_label_for_command(command)

                if result:
                    break

        if result:
            result = '**[INFO]** ' + ctype + ' users (sorted by ' + result + '):' + linesep + '```'

        # else, return None

        return result


    @commands.command()
    async def bottom(self, context, command=None):
        """Shows bottom ten users for a given aspect. If no argument is given, balance is used. Other options: given, received, br_wins, br_score, br_damage, brs, duel_wins, duel_winnings, duels, races, first_place_bets, race_winnings, gambling_profit."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        result = self.get_check_result_string(command, 'Bottom ten')

        if result is None:
            await self.bot.post_error(context, 'I don\'t have any info on that.')
            return

        if not command:
            command = 'balance'

        bottom_ten = (sorted(main_db.all(), key=itemgetter(command))[:10])[::-1]
        indent = 0

        try:
            indent = max(len(entry['user']) for entry in bottom_ten)
        except ValueError:
            await self.bot.send_revertible(context, context.message.channel, '**[INFO]** There are no users.')
            return

        for entry in bottom_ten:
            username = entry['user']
            result += linesep + username.ljust(indent) + '  ' + str(entry[command])

        result += '```'

        await self.bot.send_revertible(context, context.message.channel, result)


    @commands.command()
    async def top(self, context, command=None):
        """Shows top ten users for a given aspect. If no argument is given, balance is used. Other options: given, received, br_wins, br_score, br_damage, brs, duel_wins, duel_winnings, duels, races, first_place_bets, race_winnings, gambling_profit."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        result = self.get_check_result_string(command, 'Top ten')

        if result is None:
            await self.bot.post_error(context, 'I don\'t have any info on that.')
            return

        if not command:
            command = 'balance'

        top_ten = sorted(main_db.all(), key=itemgetter(command), reverse=True)[:10]
        indent = 0

        try:
            indent = max(len(entry['user']) for entry in top_ten)
        except ValueError:
            await self.bot.send_revertible(context, context.message.channel, 'There are no users.')
            return

        for entry in top_ten:
            username = entry['user']
            result += linesep + username.ljust(indent) + '  ' + str(entry[command])

        result += '```'

        await self.bot.send_revertible(context, context.message.channel, result)


    @commands.command()
    async def all(self, context, command=None):
        """Shows all users in descending order, sorted by a given aspect. If no argument is given, balance is used. Other options: given, received, br_wins, br_score, br_damage, brs, duel_wins, duel_winnings, duels, races, first_place_bets, race_winnings, gambling_profit."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        result = self.get_check_result_string(command, 'All')

        if result is None:
            await self.bot.post_error(context, 'I don\'t have any info on that.')
            return

        if not command:
            command = 'balance'

        all_users = sorted(main_db.all(), key=itemgetter(command), reverse=True)
        indent = 0

        try:
            indent = max(len(entry['user']) for entry in all_users)
        except ValueError:
            await self.bot.send_revertible(context, context.message.channel, 'There are no users.')
            return

        for entry in all_users:
            username = entry['user']
            result += linesep + username.ljust(indent) + '  ' + str(entry[command])

        result += '```'

        await self.bot.send_private_message(context, result)


    @commands.command()
    async def trivia(self, context):
        """Shows some global statistical information."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)

        result = '```Trivia ' + linesep

        for cog_name, cog in self.bot.cogs.items():

            try:
                part_result = cog.extend_trivia_output(self.trivia_table)

                if part_result:
                    result += linesep + part_result
            except Exception as e:
                await self.bot.post_error(context, '**[ERROR]** Oh no, something went wrong. ' + config.additional_error_message)
                log.exception(e)
                pass

        result += '```'

        await self.bot.send_revertible(context, context.message.channel, result)


    @commands.command()
    async def season(self, context, number):
        """Shows statistical information about (previous) season _number_."""
        amnt_seasons = len(self.season_tables)

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)

        try:
            number = int(number)
        except ValueError:
            await self.bot.post_error(context, 'Season number must be an integer.')
            return

        if amnt_seasons < 1:
            await self.bot.send_revertible(context, context.message.channel, 'No previous season data is available, sorry.')
        elif number < 1 or number > amnt_seasons:
            await self.bot.post_error(context, 'Invalid season number. Please choose a number between 1 and ' + str(amnt_seasons) + '.')
        else:
            season_trivia_table = self.season_tables[number - 1][1]
            season_main_db = self.season_tables[number - 1][0]

            result = '```Season ' + str(number) + linesep

            for cog_name, cog in self.bot.cogs.items():
                try:
                    part_result = cog.extend_season_output(number, season_trivia_table, season_main_db, self.season_tables)

                    if part_result:
                        result += linesep + part_result
                except Exception as e:
                    pass

            result += '```'

            await self.bot.send_revertible(context, context.message.channel, result)


async def setup(bot):
    """Stats cog load."""
    await bot.add_cog(Stats(bot))
    log.info("Stats cog loaded")
