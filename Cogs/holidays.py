import logging
import random
import json
import discord
from discord.ext import commands
import datetime
from os import linesep
from .base_cog import BaseCog
from conf import config

log = logging.getLogger(__name__)

class Holidays(BaseCog):
    """A cog for managing holidays."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.holiday_announcement_channel = None

        with open(config.cogs_data_path + '/holidays.json', 'r') as holidays_file:
            self.holidays = json.load(holidays_file)

        self.holiday_announcement_channel_id = int(config.get('Private', 'holiday_announcement_channel_id', fallback=''))
        self.free_points_on_holiday = int(config.get('Holidays', 'free_points_on_holiday', fallback=5))
        self.holiday_points = int(config.get('Holidays', 'holiday_points', fallback=5))

        # We need to make sure that when the bot crashes, it keeps info
        # on which minigame was chosen at the beginning of the day for holiday points.
        self.holiday_minigame = self.bot.database.table('holiday_minigame')
        self.minigames = []

        timed_events_cog = BaseCog.load_dependency(self, 'TimedTasks')
        timed_events_cog.register_timed_event(self.print_holiday)

        self.bot.info_text += 'Holidays:' + linesep + '  The bot will post a description of holidays on appropriate days. We celebrate these holidays by gambling a random minigame for free and also by giving away more free points.' + linesep + linesep


    #================ BASECOG INTERFACE ================
    def extend_check_options(self, db_entry):
        result_string = 'Holiday points left today'.ljust(config.check_ljust) + ' ' + str(db_entry['holiday'])
        return result_string


    def get_check_message_for_aspect(self, aspect):
        mes = None

        if aspect == 'holiday':
            mes = 'Holiday points left today'

        return mes
    #==============================================


    @commands.Cog.listener()
    async def on_ready(self):
        """Get holiday announcement channel. Holidays will be posted in that space."""
        self.holiday_announcement_channel = self.bot.get_channel(self.holiday_announcement_channel_id)
        print('Holiday cog is ready. Holiday announcement channel: ' + str(self.holiday_announcement_channel))

    #================ TIMED EVENTS ================
    async def print_holiday(self):
        """If the current day is a specified (in the .json) holiday, print info and grant free/holiday points. Executed once per day."""

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        today = datetime.date.today()
        holiday_dict = None

        try:
            holiday_dict = self.holidays[today.month - 1]
        except Exception as e:
            await self.bot.post_message(None, self.bot.bot_channel, '**[ERROR]** Oh no, something went wrong. ' + config.additional_error_message)
            log.exception(e)
            return

        self.holiday_minigame.truncate()

        try:
            holiday = holiday_dict[str(today.day)]
        except KeyError as e:
            # Make sure nobody has holiday points left over from a recent holiday
            for user in main_db.all():
                main_db.update({'holiday': 0}, self.bot.query.user == user['user'])
        else:
            try:
                for user in main_db.all():
                    freep = user['free']
                    main_db.update({'free': freep + self.free_points_on_holiday}, self.bot.query.user == user['user'])
                    main_db.update({'holiday': self.holiday_points}, self.bot.query.user == user['user'])

                await self.bot.post_message(None, self.holiday_announcement_channel, '**[HOLIDAY]** :confetti_ball: :confetti_ball: :confetti_ball: **' + holiday[0] + '** :confetti_ball: :confetti_ball: :confetti_ball:' + linesep + linesep)
                await self.bot.post_message(None, self.holiday_announcement_channel, '**[HOLIDAY]** *' + holiday[1] + '*' + linesep + linesep)

                if len(self.minigames) > 0:
                    chosen_minigame = random.choice(self.minigames)
                    self.holiday_minigame.insert({'minigame': chosen_minigame})

                    await self.bot.post_message(None, self.bot.bot_channel, '**[HOLIDAY]** :confetti_ball: :confetti_ball: :confetti_ball: **' + holiday[0] + '** :confetti_ball: :confetti_ball: :confetti_ball:' + linesep + linesep)
                    await self.bot.post_message(None, self.bot.bot_channel, '**[HOLIDAY]** To celebrate the holiday, every registered user receives ' + str(self.holiday_points) + ' holiday points that can be spent on a minigame as well as ' + str(self.free_points_on_holiday) + ' free ' + config.currency_name + 's to give away to other users.')
                    await self.bot.post_message(None, self.bot.bot_channel, '**[HOLIDAY]** The chosen minigame for today is ' + chosen_minigame + '. Have fun!')

            except Exception as e:
                await self.bot.post_message(None, self.bot.bot_channel, '**[ERROR]** There\'s supposed to be a holiday, but something went wrong. ' + config.additional_error_message)
                log.exception(e)
    #==============================================

    @commands.command()
    async def holiday(self, context):
        """Displays the current holiday."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        today = datetime.date.today()
        holiday_dict = self.holidays[today.month - 1]

        try:
            holiday = holiday_dict[str(today.day)]
        except KeyError as e:
            await self.bot.send_revertible(context, context.message.channel, 'Today is not a holiday, ' + context.message.author.name + '.' )
        else:
            chosen_minigame = self.holiday_minigame.all()[0]['minigame'] # NOTE: This will return a key error if there is no holiday registered in the database - this should only occur if the database is completely erased and the bot is restarted during a holiday. Complete erasure of the database must never happen and will likely cause other issues too.
            message = '**[HOLIDAY]** :confetti_ball: :confetti_ball: :confetti_ball: **' + holiday[0] + '** :confetti_ball: :confetti_ball: :confetti_ball:' + linesep + linesep + '*' + holiday[1] + '*' + linesep + linesep + 'To celebrate this holiday, every registered user receives ' + str(self.holiday_points) + ' holiday points to use in gambling minigames as well as ' + str(self.free_points_on_holiday) + ' free ' + config.currency_name + 's to give away to other users.'
            await self.bot.send_revertible(context, context.message.channel, message)
            await self.bot.send_revertible(context, context.message.channel, '**[HOLIDAY]** The chosen minigame for today is ' + str(chosen_minigame) + '. Have fun!')



async def setup(bot):
    """Holidays cog load."""
    await bot.add_cog(Holidays(bot))
    log.info("Holidays cog loaded")
