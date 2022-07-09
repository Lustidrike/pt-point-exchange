import logging
import discord
import json
from discord.ext import commands
from tinydb.operations import increment
from tinydb.operations import subtract
import datetime
import asyncio
import random
from operator import itemgetter
from os import linesep
from .base_cog import BaseCog
from conf import config
from dependency_load_error import DependencyLoadError

log = logging.getLogger(__name__)

class Horserace(BaseCog):
    """A cog for the horse race gambling minigame."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.race_participants = {}
        self.race_closed = True
        self.race_last_ann = ''
        self.horse_table = self.bot.database.table('horses')

        with open(config.cogs_data_path + '/gambling.json', 'r') as gambling_config:
            data = json.load(gambling_config)
            self.horse_names = data['horse_names']
            self.horse_emotes = data['horse_emotes']
            self.uninvited_guest_emotes = data['uninvited_guest_emotes']

        self.race_length = int(config.get('Horserace', 'race_length', fallback=69))
        self.race_delay = int(config.get('Horserace', 'race_delay', fallback=180))
        self.race_time_default = float(config.get('Horserace', 'race_time_default', fallback=1))
        self.race_time_end = float(config.get('Horserace', 'race_time_end', fallback=2))
        self.race_time_finish = float(config.get('Horserace', 'race_time_finish', fallback=0.5))
        self.uninvited_chance = float(config.get('Horserace', 'uninvited_chance', fallback=0.15))
        self.max_interwoven_messages = int(config.get('Horserace', 'max_interwoven_messages', fallback=5))

        if len(self.horse_table) < 1:
            self.reset_horses()

        # Register horseraces to be a possible minigame for holiday points
        holidays = self.bot.get_cog('Holidays')

        if holidays is not None:
            holidays.minigames.append('Horseraces')


    def reset_horses(self):
        self.horse_table.truncate()
        for horse_name in self.horse_names:
            self.horse_table.insert({'name': horse_name, 'race_wins': 0, '2nd': 0, '3rd': 0, '4th': 0, '5th': 0, '6th': 0, '7th': 0, '8th': 0, '9th': 0, '10th': 0, 'total_bets': 0})


    #================ BASECOG INTERFACE ================
    def extend_check_options(self, db_entry):
        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        horse_bets = db_entry['horse_bets']
        max_horse_bets = max(horse_bets)
        favourite_horse = 'N/A'

        if max_horse_bets > 0:
            favourite_horse = self.horse_names[horse_bets.index(max_horse_bets)]

        result_string = 'Horse races attended'.ljust(config.check_ljust) + ' ' + str(db_entry['races']) + linesep \
                      + 'Total horse race winnings'.ljust(config.check_ljust) + ' ' + str(db_entry['race_winnings']) + linesep \
                      + 'First place horse race bets'.ljust(config.check_ljust) + ' ' + str(db_entry['first_place_bets']) + linesep \
                      + 'Favourite horse'.ljust(config.check_ljust) + ' ' + favourite_horse

        return result_string


    def extend_trivia_table(self, trivia_table):
        trivia_table.insert({'name': 'highest_accum_bets', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'highest_succ_bet', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'largest_race', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'amnt_races', 'value': 0, 'person1': '', 'person2': '', 'date': ''})


    def extend_trivia_output(self, trivia_table):
        result = ''

        try:
            amnt_races = trivia_table.get(self.bot.query.name == 'amnt_races')

            if amnt_races['value'] > 0:
                result += 'Total amount of horse races arranged'.ljust(config.trivia_ljust) + '  ' + str(amnt_races['value']) + linesep
        except Exception:
            pass

        try:
            largest_race = trivia_table.get(self.bot.query.name == 'largest_race')

            if largest_race['person1'] != '':
                result += 'Most gamblers in one horse race'.ljust(config.trivia_ljust) + '  ' + str(largest_race['value']) + ' won by ' + largest_race['person1'] + ' on ' + largest_race['date'] + linesep
        except Exception:
            pass

        try:
            total_bets = max(self.horse_table.all(), key=itemgetter('total_bets'))

            if total_bets['total_bets'] > 0:
                result += 'Most popular horse'.ljust(config.trivia_ljust) + '  ' + str(total_bets['name']) + ' with ' + str(total_bets['total_bets']) + ' total bets placed.' + linesep
        except Exception:
            pass

        try:
            highest_succ_bet = trivia_table.get(self.bot.query.name == 'highest_succ_bet')

            if highest_succ_bet['person1'] != '':
                result += 'Highest race payout'.ljust(config.trivia_ljust) + '  ' + str(highest_succ_bet['value']) + ' by ' + highest_succ_bet['person1'] + ' on ' + highest_succ_bet['person2'] + ' on ' + highest_succ_bet['date'] + linesep
        except Exception:
            pass

        try:
            highest_accum_bets = trivia_table.get(self.bot.query.name == 'highest_accum_bets')

            if highest_accum_bets['person1'] != '':
                result += 'Most bets in one race'.ljust(config.trivia_ljust) + '  ' + str(highest_accum_bets['value']) + ' on ' + highest_accum_bets['person1'] + ' on ' + highest_accum_bets['date'] + linesep
        except Exception:
            pass

        return result


    def extend_season_output(self, number, season_trivia_table, season_main_db, season_tables):
        result = ''

        try:
            amnt_races = season_trivia_table.get(self.bot.query.name == 'amnt_races')

            if amnt_races['value'] > 0:
                result += 'Total amount of horse races arranged'.ljust(config.season_ljust) + '  ' + str(amnt_races['value']) + linesep
        except Exception:
            pass

        try:
            largest_race = season_trivia_table.get(self.bot.query.name == 'largest_race')

            if largest_race['person1'] != '':
                result += 'Most gamblers in one horse race'.ljust(config.season_ljust) + '  ' + str(largest_race['value']) + ' won by ' + largest_race['person1'] + ' on ' + largest_race['date'] + linesep
        except Exception:
            pass

        try:
            races = max(season_main_db.all(), key=itemgetter('races'))

            if races['races'] > 0:
                result += 'Most horse races attended'.ljust(config.season_ljust) + '  ' + str(races['races']) + ' by ' + races['user'] + linesep
        except Exception:
            pass

        try:
            first_place_bets = max(season_main_db.all(), key=itemgetter('first_place_bets'))

            if first_place_bets['first_place_bets'] > 0:
                result += 'Most first place race bets'.ljust(config.season_ljust) + '  ' + str(first_place_bets['first_place_bets']) + ' by ' + first_place_bets['user'] + linesep
        except Exception:
            pass

        try:
            top_three_bets = max(season_main_db.all(), key=itemgetter('top_three_bets'))

            if top_three_bets['top_three_bets'] > 0:
                result += 'Most top three race bets'.ljust(config.season_ljust) + '  ' + str(top_three_bets['top_three_bets']) + ' by ' + top_three_bets['user'] + linesep
        except Exception:
            pass

        try:
            race_winnings = max(season_main_db.all(), key=itemgetter('race_winnings'))

            if race_winnings['race_winnings'] > 0:
                result += ('Most ' + config.currency_name + ' winnings in horse races').ljust(config.season_ljust) + '  ' + str(race_winnings['race_winnings']) + ' by ' + race_winnings['user'] + linesep
        except Exception:
            pass

        try:
            highest_succ_bet = season_trivia_table.get(self.bot.query.name == 'highest_succ_bet')

            if highest_succ_bet['person1'] != '':
                result += 'Highest race payout'.ljust(config.season_ljust) + '  ' + str(highest_succ_bet['value']) + ' by ' + highest_succ_bet['person1'] + ' on ' + highest_succ_bet['person2'] + ' on ' + highest_succ_bet['date'] + linesep
        except Exception:
            pass

        try:
            highest_accum_bets = season_trivia_table.get(self.bot.query.name == 'highest_accum_bets')

            if highest_accum_bets['person1'] != '':
                result += 'Most bets in one race'.ljust(config.season_ljust) + '  ' + str(highest_accum_bets['value']) + ' on ' + highest_accum_bets['person1'] + ' on ' + highest_accum_bets['date'] + linesep
        except Exception:
            pass

        return result


    def get_check_message_for_aspect(self, aspect):
        mes = None

        if aspect == 'races':
            mes = 'Horse races attended'
        elif aspect == 'race_winnings':
            mes = 'Total horse race winnings'
        elif aspect == 'first_place_bets':
            mes = 'First place horse race bets'

        return mes


    def get_label_for_command(self, command):
        result = None

        if command == 'races':
            result = 'races attended'
        elif command == 'first_place_bets':
            result = 'first place race bets'
        elif command == 'race_winnings':
            result = 'total horse race winnings'

        return result

    async def on_season_end(self):
        self.reset_horses()
    #==============================================


    @commands.command()
    async def horses(self, context):
        """Shows a list of horses and some statistics."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)

        result = '```Horses ' + linesep + linesep

        indent = max(len(h) for h in self.horse_names)
        result += 'Number  ' + 'Name'.ljust(indent) + '  1st' + '  2nd' + '  3rd' + '  4th' + '  5th' + '  6th' + '  7th' + '  8th' + '  9th' + '  10th' + '  Profit' + '  Winrate' + linesep + linesep

        ctr = 1

        stats = BaseCog.load_dependency(self, 'Stats')
        amnt_races = stats.trivia_table.get(self.bot.query.name == 'amnt_races')

        for h in self.horse_names:
            lr_race_wins = self.horse_table.get(self.bot.query.name == h)['race_wins']
            lr_2nd = self.horse_table.get(self.bot.query.name == h)['2nd'] 
            lr_3rd = self.horse_table.get(self.bot.query.name == h)['3rd'] 
            lr_4th = self.horse_table.get(self.bot.query.name == h)['4th'] 
            lr_5th = self.horse_table.get(self.bot.query.name == h)['5th'] 
            if amnt_races['value'] > 0:
                stat_profit = ( 4 * lr_race_wins + 2 * lr_2nd + 1.75 * lr_3rd + 1.25 * lr_4th + 1.00 * lr_5th - amnt_races['value'] ) / amnt_races['value']
                str_profit = '%1.2f' % stat_profit
                stat_winrate = ( lr_race_wins + lr_2nd + lr_3rd + lr_4th + lr_5th ) / amnt_races['value']
                str_winrate = '%1.2f' % stat_winrate
            else:
                stat_profit = 0
                str_profit = '0'
                str_winrate = '0'
            result += str(ctr).ljust(len('Number')) + '  ' + h.ljust(indent) + '  ' + str(lr_race_wins).ljust(3) + '  ' + str(lr_2nd).ljust(3) + '  ' + str(lr_3rd).ljust(3) + '  ' + str(lr_4th).ljust(3) + '  ' + str(lr_5th).ljust(3) + '  ' + str(self.horse_table.get(self.bot.query.name == h)['6th']).ljust(3) + '  ' + str(self.horse_table.get(self.bot.query.name == h)['7th']).ljust(3) + '  ' + str(self.horse_table.get(self.bot.query.name == h)['8th']).ljust(3) + '  ' + str(self.horse_table.get(self.bot.query.name == h)['9th']).ljust(3) + '  ' + str(self.horse_table.get(self.bot.query.name == h)['10th']).ljust(4) + '  ' + str_profit.ljust(len('Profit')) + '  ' + str_winrate.ljust(len('Winrate')) + linesep
            ctr += 1

        result += '```'
        await self.bot.send_private_message(context, result)


    @commands.command(hidden=True)
    async def eathorse(self, context):
        """To let out your anger when your horse lost the race."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        await self.bot.send_revertible(context, self.bot.bot_channel, ':fork_and_knife:')

    @commands.command()
    async def bet(self, context, bet, horse):
        """Stake money on a horse in a horse race. Type !horses to find your favourite steed."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        is_participating = context.message.author.name in self.race_participants

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        try:
            try:
                bet = int(bet)
            except ValueError:
                await self.bot.post_error(context, 'Bet must be an integer.')
                return

            try:
                horse = int(horse)
            except ValueError:
                filtered_names = [(index + 1, horse_name) for index, horse_name in enumerate(self.horse_names) if horse_name.lower() == str(horse).lower()]
                if not filtered_names:
                    await self.bot.post_error(context, 'Horse must be an integer or a valid horse name in quotes. If you need help finding your horse, type `!horses`.')
                    return
                horse = filtered_names[0][0]

            if self.race_closed:
                await self.bot.post_error(context, 'You are too late to place a bet in the recent horse race, ' + context.message.author.name + '. Arrange a new race with !horserace <bet> <horse> if you are so eager to see your favourite breed on the track.')
            elif context.message.author.name in self.race_participants:
                await self.bot.post_error(context, 'You have already placed a bet, ' + context.message.author.name + '.')
            elif bet < 0:
                await self.bot.post_error(context, 'You cannot bet a negative amount of ' + config.currency_name + 's, ' + context.message.author.name + '.')
            elif bet == 0:
                await self.bot.post_error(context, 'You cannot bet zero ' + config.currency_name + 's, ' + context.message.author.name + '.')
            elif horse <= 0 or horse > len(self.horse_names):
                await self.bot.post_error(context, 'Invalid horse number. If you need help finding your horse, type `!horses`.')
            else:
                user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']

                # Check if horserace is today's minigame for holiday points
                holidays = self.bot.get_cog('Holidays')
                is_holiday_minigame = False
                holiday = 0

                if holidays is not None:
                    if holidays.holiday_minigame.contains(self.bot.query.minigame == 'Horseraces'):
                        is_holiday_minigame = True
                        holiday = main_db.get(self.bot.query.user == context.message.author.name)['holiday']

                if user_balance + holiday >= bet:
                    lock = True
                    gambling = self.bot.get_cog('Gambling')

                    if gambling is not None:
                        lock = gambling.lock

                    if lock and bet > gambling.lock_max_bet:
                        await self.bot.post_error(context, 'High-stakes gambling is not allowed. Please stay below ' + str(gambling.lock_max_bet) + ' ' + config.currency_name + 's, ' + context.message.author.name + '. Admins can remove this limit using !unlock.') 
                    else:
                        try:
                            # Remove bet
                            if holiday > 0:
                                leftover = bet - holiday

                                if leftover > 0: # i.e. bet > holiday points
                                    main_db.update(subtract('holiday', holiday), self.bot.query.user == context.message.author.name)
                                    main_db.update(subtract('balance', leftover), self.bot.query.user == context.message.author.name)
                                    main_db.update(subtract('gambling_profit', leftover), self.bot.query.user == context.message.author.name)
                                else: # Note: holiday points do not count as negative gambling profit
                                    main_db.update(subtract('holiday', bet), self.bot.query.user == context.message.author.name)
                            else:
                                main_db.update(subtract('balance', bet), self.bot.query.user == context.message.author.name)
                                main_db.update(subtract('gambling_profit', bet), self.bot.query.user == context.message.author.name)
                        except Exception as e:
                            await self.bot.post_error(context, 'Something went wrong subtracting the bet from your account balance! You have therefore not placed a bet.', config.additional_error_message)
                            log.exception(e)
                        else:
                            self.race_participants[context.message.author.name] = (bet, min(holiday, bet), horse)
                            await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** ' + context.message.author.name + ' has bet ' + str(bet) + ' ' + config.currency_name + 's on ' + self.horse_names[horse - 1] + '!') # first index is 0
                else:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. You wish to stake ' + str(bet) + ' ' + config.currency_name + 's and your current balance is ' + str(user_balance) + '.') 
        except Exception as e:
            if (context.message.author.name in self.race_participants) and not is_participating:
                del self.race_participants[context.message.author.name]

            await self.bot.post_error(context, 'Oh no, something went wrong (you have not placed a bet).', config.additional_error_message)
            log.exception(e)


    @commands.command()
    async def unbet(self, context):
        """Undo your horse race bet."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        is_participating = context.message.author.name in self.race_participants

        if self.race_closed:
            await self.bot.post_error(context, 'You are too late to remove a bet from the recent horse race, ' + context.message.author.name + '.')
        elif context.message.author.name not in self.race_participants:
            await self.bot.post_error(context, 'You have not placed a bet, ' + context.message.author.name + '.')
        else:
            user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']
            bet, holiday_used, horse = self.race_participants[context.message.author.name]

            # Remove bet
            balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']
            gambling_profit = main_db.get(self.bot.query.user == context.message.author.name)['gambling_profit']
            holiday = main_db.get(self.bot.query.user == context.message.author.name)['holiday']
            main_db.update({'gambling_profit': gambling_profit + (bet - holiday_used)}, self.bot.query.user == context.message.author.name)
            main_db.update({'balance': balance + (bet - holiday_used)}, self.bot.query.user == context.message.author.name)
            main_db.update({'holiday': holiday + holiday_used}, self.bot.query.user == context.message.author.name)
            del self.race_participants[context.message.author.name]
            await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** ' + context.message.author.name + ' has removed their bet of ' + str(bet) + ' ' + config.currency_name + 's on ' + self.horse_names[horse - 1] + '.') # first index is 0


    @commands.command()
    async def horserace(self, context, bet, horse):
        """Starts a horse race, placing a bet of _bet_ points on _horse_. Type !horses to find your favourite steed."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db
        stats = BaseCog.load_dependency(self, 'Stats')
        trivia_table = stats.trivia_table
        gambling = BaseCog.load_dependency(self, 'Gambling')

        role = discord.utils.get(context.message.author.guild.roles, name=gambling.subscriber_role)
        role_mention = role.mention + linesep if role else ''

        br_bet = None

        try:
            battleroyale = BaseCog.load_dependency(self, 'BattleRoyale')
            br_bet = battleroyale.br_bet
        except DependencyLoadError:
            # If battle royale cog is not available, shouldn't exit with error
            pass

        try:
            try:
                bet = int(bet)
            except ValueError:
                await self.bot.post_error(context, 'Bet must be an integer.')
                return

            try:
                horse = int(horse)
            except ValueError:
                filtered_names = [(index + 1, horse_name) for index, horse_name in enumerate(self.horse_names) if horse_name.lower() == str(horse).lower()]
                if not filtered_names:
                    await self.bot.post_error(context, 'Horse must be an integer or a valid horse name in quotes. If you need help finding your horse, type `!horses`.')
                    return
                horse = filtered_names[0][0]

            if br_bet and br_bet != 0:
                await self.bot.post_error(context, 'Sorry ' + context.message.author.name + ', please wait for the ongoing battle royale to end so that the messages don\'t interfere.')
                return
            elif self.race_participants:
                await self.bot.post_error(context, 'Not so hasty, keen gambler. There is already a big race taking place.')
                return
            elif bet < 0:
                await self.bot.post_error(context, 'You cannot bet a negative amount of ' + config.currency_name + 's, ' + context.message.author.name + '.')
                return
            elif bet == 0:
                await self.bot.post_error(context, 'You cannot bet zero ' + config.currency_name + 's, ' + context.message.author.name + '.')
                return
            elif horse <= 0 or horse > len(self.horse_names):
                await self.bot.post_error(context, 'Invalid horse number. If you need help finding your horse, type `!horses`.')
                return
            else:
                user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']

                # Check if horserace is today's minigame for holiday points
                holidays = self.bot.get_cog('Holidays')
                is_holiday_minigame = False
                holiday = 0

                if holidays is not None:
                    if holidays.holiday_minigame.contains(self.bot.query.minigame == 'Horseraces'):
                        is_holiday_minigame = True
                        holiday = main_db.get(self.bot.query.user == context.message.author.name)['holiday']

                if user_balance + holiday < bet:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. You wish to stake ' + str(bet) + ' ' + config.currency_name + 's and your current balance is ' + str(user_balance) + '.') 
                    return

                lock = gambling.lock

                if lock:
                    if bet > gambling.lock_max_bet:
                        await self.bot.post_error(context, 'High-stakes gambling is not allowed. Please stay below ' + str(gambling.lock_max_bet) + ' ' + config.currency_name + 's, ' + context.message.author.name + '. Admins can remove this limit using !unlock.') 
                        return

                announcement = 'Listen here, good people. Duke ' + context.message.author.name + ' has announced a majestic horse race. Which is the fastest steed in the lands of Tamriel?'

                amnt_races = trivia_table.get(self.bot.query.name == 'amnt_races')
                indent = max(len(h) for h in self.horse_names)
                horse_list = '```Nr.  ' + 'Name'.ljust(indent) + '  Wins' + '  Profit' + '  Winrate' + linesep
                ctr = 1

                for h in self.horse_names:
                    lr_race_wins = self.horse_table.get(self.bot.query.name == h)['race_wins']
                    lr_2nd = self.horse_table.get(self.bot.query.name == h)['2nd'] 
                    lr_3rd = self.horse_table.get(self.bot.query.name == h)['3rd'] 
                    lr_4th = self.horse_table.get(self.bot.query.name == h)['4th'] 
                    lr_5th = self.horse_table.get(self.bot.query.name == h)['5th'] 
                    if amnt_races['value'] > 0:
                        stat_profit = ( 4 * lr_race_wins + 2 * lr_2nd + 1.75 * lr_3rd + 1.25 * lr_4th + 1.00 * lr_5th - amnt_races['value'] ) / amnt_races['value']
                        str_profit = '%1.2f' % stat_profit
                        stat_winrate = ( lr_race_wins + lr_2nd + lr_3rd + lr_4th + lr_5th ) / amnt_races['value']
                        str_winrate = '%1.2f' % stat_winrate
                    else:
                        stat_profit = 0
                        str_profit = '0'
                        str_winrate = '0'

                    horse_list += str(ctr).ljust(len('Nr.')) + '  ' + h.ljust(indent) + '  ' + str(lr_race_wins).ljust(len('Wins')) + '  ' + str_profit.ljust(len('Profit')) + '  ' + str_winrate.ljust(len('Winrate')) + '   ' + linesep
                    ctr += 1

                horse_list += '```'

                try:
                    # Remove bet
                    if holiday > 0:
                        leftover = bet - holiday

                        if leftover > 0: # i.e. bet > holiday points
                            main_db.update(subtract('holiday', holiday), self.bot.query.user == context.message.author.name)
                            main_db.update(subtract('balance', leftover), self.bot.query.user == context.message.author.name)
                            main_db.update(subtract('gambling_profit', leftover), self.bot.query.user == context.message.author.name)
                        else: # Note: holiday points do not count as negative gambling profit
                            main_db.update(subtract('holiday', bet), self.bot.query.user == context.message.author.name)
                    else:
                        main_db.update(subtract('balance', bet), self.bot.query.user == context.message.author.name)
                        main_db.update(subtract('gambling_profit', bet), self.bot.query.user == context.message.author.name)
                except Exception as e:
                    await self.bot.post_error(context, 'Something went wrong subtracting the bet from your account balance! Horse race is therefore canceled.')
                    log.exception(e)
                    return
                await self.bot.post_message(context, self.bot.bot_channel, role_mention + '**[HORSE RACE]** ' + announcement)
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** Type !bet <bet> <horse> to place a bet on your favourite breed.')
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** Type !unbet to remove your current bet.')
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]**' + linesep + linesep)
                await self.bot.post_message(context, self.bot.bot_channel, horse_list + linesep)
                self.race_participants[context.message.author.name] = (bet, min(holiday, bet), horse)
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** ' + context.message.author.name + ' has bet ' + str(bet) + ' ' + config.currency_name + 's on ' + self.horse_names[horse - 1] + '!') # first index is 0
                self.race_last_ann = announcement
                self.race_closed = False

                if self.race_delay <= 60:
                    await asyncio.sleep(self.race_delay) # during this time, people can use commands to join
                else:
                    await asyncio.sleep(self.race_delay-60) # during this time, people can use commands to join
                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** The race will start in 1 minute. Type !bet <bet> <horse> to take part!')
                    await asyncio.sleep(30) # during this time, people can use commands to join
                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** The race will start in 30 seconds. Type !bet <bet> <horse> to take part!')
                    await asyncio.sleep(30) # during this time, people can use commands to join

                self.race_closed = True

                # _self.race_participants_ is now filled with usernames and bets
                ann_message = '**[HORSE RACE]** Ladies and gentlemen, the glorious race is about to begin. The bets are:' + linesep + linesep + '`'

                ctr = 1

                for h in self.horse_names:
                    accum_bets = sum(b for p, (b, f, h) in self.race_participants.items() if h == ctr)

                    if accum_bets > 0:
                        ann_message += h.ljust(indent) + '  ' + str(accum_bets) + linesep

                    ctr += 1

                await self.bot.post_message(context, self.bot.bot_channel, ann_message + '`' + linesep + linesep)

                # Total positions are (if using default) 69, every horse starts at position 0
                positions = self.race_length
                horse_positions = []
                angery = False

                # Check if another 'horse' joins the race
                if random.uniform(0, 1) < self.uninvited_chance:
                    angery = True

                for h in self.horse_names:
                    horse_positions.append(0);

                if angery:
                    horse_positions.append(0);
                    self.horse_names.append( '???' )

                    uninvited_guest = random.choice(self.uninvited_guest_emotes)
                    self.horse_emotes.append(uninvited_guest)

                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** Looks like there is an uninvited guest on the race track ' + uninvited_guest + '. The crowd is enraged, but the race continues.' + linesep + linesep)

                placements = []
                await asyncio.sleep(self.race_time_end)
                len_placements = 0
                horse_message = None
                last_message_id = None
                message_count = 0

                while len_placements != len(self.horse_names):
                    ctr = 0
                    update = ':checkered_flag: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post: :triangular_flag_on_post:'

                    len_placements = len(placements)

                    # Update visuals
                    for h in self.horse_names:
                        update += linesep
                        ctr += 1
                        horse_position = horse_positions[ctr - 1]
                        emoj = self.horse_emotes[ctr - 1]

                        if horse_position == 0:
                            update += '| '

                            for i in range(1, positions):
                                update += '-'

                            update += ' | ' + emoj + ' ' + str(ctr) + ' ' + h
                        elif horse_position >= positions:
                            update += '' + emoj + ' | '

                            for i in range(1, positions):
                                update += '-'

                            update += ' | ' + str(ctr) + ' ' + h

                            if placements.index(ctr) == 0:
                                update += ' :first_place:'
                            elif placements.index(ctr) == 1:
                                update += ' :second_place:'
                            elif placements.index(ctr) == 2:
                                update += ' :third_place:'
                        else:
                            update += '| '

                            # Let's say we have 5 positions total, the horse is on position 2; we need to add 3 dashes in front of it: 1 to 5 - 2
                            for i in range(1, positions - horse_position):
                                update += '-'

                            update += ' ' + emoj + ' '

                            # Let's say the horse is on position 4, we need to add 3 more dashes behind it: 0 to 2
                            for i in range(0, horse_position - 1):
                                update += '-'

                            update += ' | ' + str(ctr) + ' ' + h

                    async for message in self.bot.bot_channel.history(limit=1):
                        if message.id != last_message_id:
                            message_count += 1
                            if message_count >= self.max_interwoven_messages or last_message_id is None:
                                horse_messages = await self.bot.post_message(context, self.bot.bot_channel, update)
                                horse_message = horse_messages[-1]
                                message_count = 0
                                last_message_id = horse_message.id
                            else:
                                last_message_id = message.id
                        else:
                            await horse_message.edit(content=update);

                        break # defensive coding, there really should only be one message returned

                    if len(placements) >= 3:
                        await asyncio.sleep(self.race_time_finish)
                    elif max(horse_positions) > positions - 6:
                        await asyncio.sleep(self.race_time_end)
                    else:
                        await asyncio.sleep(self.race_time_default)

                    step_list = [1, 2, 3]
                    step_probabilities = [0.65, 0.25, 0.1]
                    new_placements = []

                    for idhp, horse_position in enumerate(horse_positions):
                        x = random.uniform(0, 1)
                        cum_prob = 0

                        for i, i_p in zip(step_list, step_probabilities):
                            cum_prob += i_p

                            if x < cum_prob:
                                break

                        horse_position += i
                        horse_positions[idhp] = horse_position
                        hnr = idhp + 1

                        if horse_position >= positions and hnr not in placements:
                            new_placements.append(hnr)

                    random.shuffle(new_placements)
                    placements.extend(new_placements)

                # NOTE on naming, it's not *actually* the index (it's the horse number)
                first_index = placements[0]
                second_index = placements[1]
                third_index = placements[2]
                fourth_index = placements[3]
                fifth_index = placements[4]
                first = self.horse_names[first_index - 1]
                second = self.horse_names[second_index - 1]
                third = self.horse_names[third_index - 1]
                fourth = self.horse_names[fourth_index - 1]
                fifth = self.horse_names[fifth_index - 1]
                amnt_first = sum(1 for p, (b, f, h) in self.race_participants.items() if h == first_index)
                amnt_second = sum(1 for p, (b, f, h) in self.race_participants.items() if h == second_index)
                amnt_third = sum(1 for p, (b, f, h) in self.race_participants.items() if h == third_index)
                amnt_fourth = sum(1 for p, (b, f, h) in self.race_participants.items() if h == fourth_index)
                amnt_fifth = sum(1 for p, (b, f, h) in self.race_participants.items() if h == fifth_index)

                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** The race is over, valued spectators, and all placements are decided. What a divine spectacle!')
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** In fifth place is ' + fifth + ', anticipated by ' + str(amnt_fifth) + ' users.')
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** In fourth place is ' + fourth + ', anticipated by ' + str(amnt_fourth) + ' users.')
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** In third place is ' + third + ', anticipated by ' + str(amnt_third) + ' users.')
                await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** In second place is ' + second + ', anticipated by ' + str(amnt_second) + ' users.')

                if amnt_first == 0:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** ...and in first place is the amazingly swift ' + first + '! Looks like nobody saw this coming. What a surprise!')
                else:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[HORSE RACE]** ...and in first place is the amazingly swift ' + first + ', anticipated by ' + str(amnt_first) + ' users! Congratulations!')

                # Add winnings and update some trivia
                try:
                    highest_total_owned = trivia_table.get(self.bot.query.name == 'highest_total_owned')['value']
                    highest_succ_bet = trivia_table.get(self.bot.query.name == 'highest_succ_bet')['value'] # which user received the highest amount of ' + config.currency_name + 's through one bet

                    payout_message = ''
                    payout = False

                    for p, (b, f, h) in self.race_participants.items():
                        multiplier = 0

                        if h == first_index:
                            multiplier = 4
                            main_db.update(increment('first_place_bets'), self.bot.query.user == p)
                            main_db.update(increment('top_three_bets'), self.bot.query.user == p)
                        elif h == second_index:
                            multiplier = 2
                            main_db.update(increment('top_three_bets'), self.bot.query.user == p)
                        elif h == third_index:
                            multiplier = 1.8
                            main_db.update(increment('top_three_bets'), self.bot.query.user == p)
                        elif h == fourth_index:
                            multiplier = 1.3
                            main_db.update(increment('top_three_bets'), self.bot.query.user == p)
                        elif h == fifth_index:
                            multiplier = 1
                            main_db.update(increment('top_three_bets'), self.bot.query.user == p)
                        else:
                            continue

                        payout = True
                        race_winnings = main_db.get(self.bot.query.user == p)['race_winnings']
                        balance = main_db.get(self.bot.query.user == p)['balance'] # prior to update
                        winnings = int(round(b * multiplier))
                        new_balance = balance + winnings
                        main_db.update({'race_winnings': race_winnings + winnings - b}, self.bot.query.user == p)
                        gambling_profit = main_db.get(self.bot.query.user == p)['gambling_profit']
                        main_db.update({'gambling_profit': gambling_profit + winnings}, self.bot.query.user == p) # do not subtract bet because that's already done in bet()
                        main_db.update({'balance': new_balance}, self.bot.query.user == p)

                        if new_balance > highest_total_owned:
                            trivia_table.update({'value': new_balance, 'person1': p, 'person2': 'None', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_total_owned')
                            highest_total_owned = new_balance

                        if winnings > highest_succ_bet:
                            trivia_table.update({'value': winnings, 'person1': p, 'person2': self.horse_names[h - 1], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_succ_bet')
                            highest_succ_bet = winnings

                        payout_message += p + ': ' + str(winnings) + linesep

                    if payout:
                        payout_message = '**[HORSE RACE]** The payouts are:' + linesep + linesep + payout_message
                        await self.bot.post_message(context, self.bot.bot_channel, payout_message)
                except Exception as e:
                    await self.bot.post_error(context, 'Something went wrong handing out the cash! Balances and stats might be inconsistent now.', config.additional_error_message)
                    log.exception(e)

                # Update horses and other trivia
                try:
                    self.horse_table.update(increment('race_wins'), self.bot.query.name == first) # updates amount of races won by this HORSE, not user
                    self.horse_table.update(increment('2nd'), self.bot.query.name == second)
                    self.horse_table.update(increment('3rd'), self.bot.query.name == third)

                    # Update total number of bets ever placed on this horse
                    for p, (b, f, h) in self.race_participants.items():
                        total_bets = self.horse_table.get(self.bot.query.name == self.horse_names[h - 1])['total_bets']
                        self.horse_table.update({'total_bets': total_bets + b}, self.bot.query.name == self.horse_names[h - 1])
                        horse_bets = main_db.get(self.bot.query.user == p)['horse_bets']
                        horse_bets[h - 1] += 1
                        main_db.update({'horse_bets': horse_bets}, self.bot.query.user == p)

                    trivia_table.update(increment('value'), self.bot.query.name == 'amnt_races')
                    highest_accum_bets = trivia_table.get(self.bot.query.name == 'highest_accum_bets')['value'] # which horse had the highest amount of bets in one race
                    largest_race = trivia_table.get(self.bot.query.name == 'largest_race')['value'] # which race had the most people betting on horses

                    loc_highest_accum_bets = 0
                    loc_highest_accum_bets_horse = None

                    for h, name in enumerate(self.horse_names):
                        sum_ = 0

                        for p, (b, f, hs) in self.race_participants.items():
                            if h + 1 == hs: # h starts at 0
                                sum_ += b

                        if sum_ > loc_highest_accum_bets:
                            loc_highest_accum_bets = sum_
                            loc_highest_accum_bets_horse = name

                    if loc_highest_accum_bets > highest_accum_bets:
                        trivia_table.update({'value': loc_highest_accum_bets, 'person1': loc_highest_accum_bets_horse, 'person2': 'None', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_accum_bets')

                    if len(self.race_participants) > largest_race:
                        trivia_table.update({'value': len(self.race_participants), 'person1': first, 'person2': second, 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'largest_race')

                    for placement, horse in enumerate(placements):
                        if placement == 3:
                            self.horse_table.update(increment('4th'), self.bot.query.name == self.horse_names[horse - 1])
                        elif placement == 4: 
                            self.horse_table.update(increment('5th'), self.bot.query.name == self.horse_names[horse - 1])
                        elif placement == 5: 
                            self.horse_table.update(increment('6th'), self.bot.query.name == self.horse_names[horse - 1])
                        elif placement == 6: 
                            self.horse_table.update(increment('7th'), self.bot.query.name == self.horse_names[horse - 1])
                        elif placement == 7: 
                            self.horse_table.update(increment('8th'), self.bot.query.name == self.horse_names[horse - 1])
                        elif placement == 8: 
                            self.horse_table.update(increment('9th'), self.bot.query.name == self.horse_names[horse - 1])
                        elif placement == 9: 
                            self.horse_table.update(increment('10th'), self.bot.query.name == self.horse_names[horse - 1])
                except Exception as e:
                    await self.bot.post_error(context, 'Could not update some horse race stats (only affects !trivia output).', config.additional_error_message)
                    log.exception(e)

                try:
                    for p in self.race_participants:
                        main_db.update(increment('races'), self.bot.query.user == p)
                except Exception as e:
                    await self.bot.post_error(context, 'Could not update some horse race stats (only affects !trivia output).', config.additional_error_message)
                    log.exception(e)

                # Remove emote and name from array so that :angery: doesn't automatically participate next race
                if angery:
                    self.horse_emotes = self.horse_emotes[:-1]
                    self.horse_names = self.horse_names[:-1]
        except Exception as e:
            await self.bot.post_error(context, 'Oh no, something went wrong.', config.additional_error_message)
            log.exception(e)

        # Reset stuff
        self.race_closed = True
        self.race_participants = {}


def setup(bot):
    """Horserace cog load."""
    bot.add_cog(Horserace(bot))
    log.info("Horserace cog loaded")
