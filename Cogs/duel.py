import logging
import discord
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

class Duel(BaseCog):
    """A cog for the duel minigame."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.duels = {}
        self.duel_ctr = 0
        self.duel_delay = int(config.get('Duel', 'duel_delay', fallback=120))
        self.duel_battle_delay = int(config.get('Duel', 'duel_battle_delay', fallback=10))


    #================ BASECOG INTERFACE ================
    def extend_check_options(self, db_entry):
        result_string = 'Duels fought'.ljust(config.check_ljust) + ' ' + str(db_entry['duels']) + linesep \
                      + 'Duels won'.ljust(config.check_ljust) + ' ' + str(db_entry['duel_wins']) + linesep \
                      + 'Total duel winnings'.ljust(config.check_ljust) + ' ' + str(db_entry['duel_winnings'])

        return result_string


    def extend_trivia_table(self, trivia_table):
        trivia_table.insert({'name': 'highest_duel', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'amnt_duels', 'value': 0, 'person1': '', 'person2': '', 'date': ''})


    def extend_trivia_output(self, trivia_table):
        result = ''

        try:
            amnt_duels = trivia_table.get(self.bot.query.name == 'amnt_duels')

            if amnt_duels['value'] > 0:
                result += 'Total amount of duels fought'.ljust(config.trivia_ljust) + '  ' + str(amnt_duels['value']) + linesep
        except Exception:
            pass

        try:
            highest_duel = trivia_table.get(self.bot.query.name == 'highest_duel')

            if highest_duel['person1'] != '':
                result += 'Highest duel'.ljust(config.trivia_ljust) + '  ' + str(highest_duel['value']) + ' won by ' + highest_duel['person1'] + ' against ' + highest_duel['person2'] + ' on ' + highest_duel['date'] + linesep 
        except Exception:
            pass

        return result


    def extend_season_output(self, number, season_trivia_table, season_main_db, season_tables):
        result = ''

        try:
            amnt_duels = season_trivia_table.get(self.bot.query.name == 'amnt_duels')

            if amnt_duels['value'] > 0:
                result += 'Total amount of duels fought'.ljust(config.season_ljust) + '  ' + str(amnt_duels['value']) + linesep
        except Exception:
            pass

        try:
            most_duels = max(season_main_db.all(), key=itemgetter('duels'))

            if most_duels['duels'] > 0:
                result += 'Most duels fought'.ljust(config.season_ljust) + '  ' + str(most_duels['duels']) + ' by ' + most_duels['user'] + linesep
        except Exception:
            pass
            
        try:
            highest_duel = season_trivia_table.get(self.bot.query.name == 'highest_duel')

            if highest_duel['person1'] != '':
                result += 'Highest duel'.ljust(config.season_ljust) + '  ' + str(highest_duel['value']) + ' won by ' + highest_duel['person1'] + ' against ' + highest_duel['person2'] + ' on ' + highest_duel['date'] + linesep
        except Exception:
            pass

        try:
            most_duel_wins = max(season_main_db.all(), key=itemgetter('duel_wins'))

            if most_duel_wins['duel_wins'] > 0:
                result += 'Most duel wins'.ljust(config.season_ljust) + '  ' + str(most_duel_wins['duel_wins']) + ' by ' + most_duel_wins['user'] + linesep
        except Exception:
            pass

        try:
            highest_amnt_winnings_duel = max(season_main_db.all(), key=itemgetter('duel_winnings'))

            if highest_amnt_winnings_duel['duel_winnings'] > 0:
                result += ('Most ' + config.currency_name + ' winnings in duels').ljust(config.season_ljust) + '  ' + str(highest_amnt_winnings_duel['duel_winnings']) + ' by ' + highest_amnt_winnings_duel['user'] + linesep
        except Exception:
            pass

        return result


    def get_check_message_for_aspect(self, aspect):
        mes = None

        if aspect == 'duels':
            mes = 'Duels fought'
        elif aspect == 'duel_wins':
            mes = 'Duels won'
        elif aspect == 'duel_winnings':
            mes = 'Total duel winnings'

        return mes


    def get_label_for_command(self, command):
        result = None

        if command == 'duel_wins':
            result = 'duels won'
        elif command == 'duel_winnings':
            result = 'duel winnings'
        elif command == 'duels':
            result = 'duels fought'

        return result
    #==============================================


    @commands.command()
    async def rejectduel(self, context):
        """Reject a duel."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db

        challenger = None
        challenged = None
        duel_id = None

        # Check if user has been challenged
        if context.message.author.name in [d[1] for d in self.duels.values()]:
            for did, (c, user, b, accepted) in self.duels.items():
                if user == context.message.author.name and not accepted:
                    challenger = c
                    challenged = user
                    duel_id = did
                    break

        # Check if user has challenged someone else
        elif context.message.author.name in [d[0] for d in self.duels.values()]:
            for did, (c, user, b, accepted) in self.duels.items():
                if c == context.message.author.name and not accepted:
                    challenger = c
                    challenged = user
                    duel_id = did
                    break

        if duel_id is None:
            await self.bot.post_error(context, 'There is no duel to reject, ' + context.message.author.name + '.')
        else:
            await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** There will be no duel between ' + challenger + ' and ' + challenged + '.')
            del self.duels[duel_id]


    @commands.command()
    async def acceptduel(self, context):
        """Accept a duel."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db
        stats = BaseCog.load_dependency(self, 'Stats')
        trivia_table = stats.trivia_table
        gambling = BaseCog.load_dependency(self, 'Gambling')
        weapon_emotes = gambling.weapon_emotes

        if not context.message.author.name in [d[1] for d in self.duels.values()]:
            await self.bot.post_error(context, 'You have not been challenged to a duel, ' + context.message.author.name + '.')
        elif context.message.author.name in [d[0] for d in self.duels.values()]:
            await self.bot.post_error(context, 'You have already challenged someone else to a duel, ' + context.message.author.name + ', you need to finish that duel before you can start another one.')
        else:
            challenger = None
            bet = None
            duel_id = None

            for did, (c, user, b, accepted) in self.duels.items():
                if user == context.message.author.name and not accepted:
                    challenger = c
                    bet = b
                    duel_id = did
                    break

            if challenger is None:
                await self.bot.post_error(context, 'You have not been challenged to a duel, ' + context.message.author.name + '.')
                return

            user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']
            other_balance = main_db.get(self.bot.query.user == challenger)['balance']

            if other_balance < bet:
                await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** ' + challenger + ' doesn\'t even have ' + str(bet) + ' ' + config.currency_name + 's anymore, the duel has been canceled.')
                del self.duels[duel_id]
            elif user_balance < bet:
                await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. ' + challenger + ' wants to fight over ' + str(bet) + ' ' + config.currency_name + 's and your current balance is ' + str(user_balance) + '.') 
                del self.duels[duel_id]
            else:
                self.duels[duel_id] = (challenger, context.message.author.name, bet, True)

                try:
                    main_db.update(subtract('balance', bet), self.bot.query.user == challenger)
                    main_db.update(subtract('balance', bet), self.bot.query.user == context.message.author.name)
                    main_db.update(subtract('gambling_profit', bet), self.bot.query.user == challenger)
                    main_db.update(subtract('gambling_profit', bet), self.bot.query.user == context.message.author.name)
                except Exception as e:
                    await self.bot.post_error(context, 'A fatal error occurred while trying to subtract ' + config.currency_name + 's from respective accounts. Duel is canceled and balances might be wrong.', config.additional_error_message)
                    log.exception(e)
                else:
                    try:
                        await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** Ladies and gentlemen, we are about to see a duel to the death between ' + challenger + ' and ' + context.message.author.name + '. Who is going to prevail, taking ' + str(bet) + ' ' + config.currency_name + 's from their opponent?')
                        await asyncio.sleep(self.duel_battle_delay) # nothing happens during this time
                        duel_participants = []
                        duel_participants.append(context.message.author.name)
                        duel_participants.append(challenger)

                        # Choose winners
                        first = random.choice(duel_participants)
                        second = ''

                        if first == context.message.author.name:
                            second = challenger
                        else:
                            second = context.message.author.name

                        balance_first = 0

                        try:
                            balance_first = main_db.get(self.bot.query.user == first)['balance']
                            main_db.update({'balance': balance_first + bet + bet}, self.bot.query.user == first)
                        except Exception as e:
                            await self.bot.post_error(context, 'A fatal error occurred while trying to add ' + config.currency_name + 's to ' + first + '\'s account. Balances might be wrong.', config.additional_error_message)
                            log.exception(e)
                        else:
                            weapon = random.choice(weapon_emotes)
                            await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** ' + first + ' ' + weapon + ' ' + second )

                            try:
                                gambling_profit_first = main_db.get(self.bot.query.user == first)['gambling_profit']
                                main_db.update({'gambling_profit': gambling_profit_first + bet + bet}, self.bot.query.user == first)

                                first_total_won_duels = main_db.get(self.bot.query.user == first)['duel_winnings']
                                main_db.update({'duel_winnings': first_total_won_duels + bet}, self.bot.query.user == first)
                                highest_total_owned = trivia_table.get(self.bot.query.name == 'highest_total_owned')['value']

                                if balance_first + bet > highest_total_owned:
                                    trivia_table.update({'value': balance_first + bet, 'person1': first, 'person2': 'None', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_total_owned')
                            except Exception as e:
                                await self.bot.post_error(context, 'Could not update some stats (affects !trivia output).', config.additional_error_message)
                                log.exception(e)

                            try:
                                main_db.update(increment('duel_wins'), self.bot.query.user == first)

                                highest_duel = trivia_table.get(self.bot.query.name == 'highest_duel')['value']

                                if bet > highest_duel:
                                    trivia_table.update({'value': bet, 'person1': first, 'person2': second, 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_duel')
                            except Exception as e:
                                await self.bot.post_error(context, 'Could not update some duel stats (affects !trivia output).', config.additional_error_message)
                                log.exception(e)

                            try:
                                main_db.update(increment('duels'), self.bot.query.user == first)
                                main_db.update(increment('duels'), self.bot.query.user == second)
                                trivia_table.update(increment('value'), self.bot.query.name == 'amnt_duels')
                            except Exception as e:
                                await self.bot.post_error(context, 'Could not update some duel stats (affects !trivia output).', config.additional_error_message)
                                log.exception(e)
                    except Exception as e:
                        await self.bot.post_error(context, 'Oh no, something went wrong (duel may or may not have finished).', config.additional_error_message)
                        log.exception(e)

                del self.duels[duel_id]


    @commands.command()
    async def duel(self, context, user, bet=None):
        """Challenges _user_ to a duel. If you win, you receive _bet_ points from them."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        economy = BaseCog.load_dependency(self, 'Economy')
        main_db = economy.main_db
        gambling = BaseCog.load_dependency(self, 'Gambling')

        if not bet:
            await self.bot.post_error(context, '!duel requires a bet.')
            return

        try:
            bet = int(bet)
        except ValueError:
            await self.bot.post_error(context, 'Bet must be an integer.')
            return

        user = BaseCog.map_user(self, user)

        if not main_db.contains(self.bot.query.user == user):
            await self.bot.post_error(context, 'User ' + user + ' has not been added yet. They need to type !add to initialize their account.')
        elif context.message.author.name == user:
            await self.bot.post_error(context, 'You cannot challenge yourself to a duel, ' + context.message.author.name + '.')
        elif context.message.author.name in [d[0] for d in self.duels.values()]:
            await self.bot.post_error(context, 'You have already challenged someone to a duel, ' + context.message.author.name + ', you need to finish that duel before you can start another one.')
        elif context.message.author.name in [d[1] for d in self.duels.values()]:
            await self.bot.post_error(context, 'You have already been challenged to a duel, ' + context.message.author.name + ', you need to finish that duel before you can start another one.')
        elif user in [d[0] for d in self.duels.values()] or user in [d[1] for d in self.duels.values()]:
            await self.bot.post_error(context, '' + user + ' is already in a duel, ' + context.message.author.name + '. Please try again later.')
        elif bet <= 0:
            await self.bot.post_error(context, '!duel requires bets to be greater than zero.')
        else:
            user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']
            other_balance = main_db.get(self.bot.query.user == user)['balance']

            if user_balance < bet:
                await self.bot.post_error(context, 'You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. You want to fight over ' + str(bet) + ' ' + config.currency_name + 's and your current balance is ' + str(user_balance) + '.') 
                return

            if other_balance < bet:
                await self.bot.post_error(context, '' + user + ' does not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. You want to fight over ' + str(bet) + ' ' + config.currency_name + 's and their current balance is ' + str(other_balance) + '.') 
                return

            lock = gambling.lock

            if lock:
                if bet > gambling.lock_max_bet:
                    await self.bot.post_error(context, 'High-stakes gambling is not allowed. Please stay below ' + str(gambling.lock_max_bet) + ' ' + config.currency_name + 's, ' + context.message.author.name + '. Admins can remove this limit using !unlock.') 
                    return

            self.duel_ctr += 1
            duel_id = self.duel_ctr
            self.duels[duel_id] = (context.message.author.name, user, bet, False)

            await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** ' + context.message.author.name + ' has challenged ' + user + ' to a duel. They have two minutes to accept (!acceptduel).')
            await asyncio.sleep(self.duel_delay) # during this time, people can decline or accept

            try:
                found_duel = self.duels[duel_id]
                if not found_duel[-1]:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[DUEL]** There will be no duel between ' + context.message.author.name + ' and ' + user + '.')
                    del self.duels[duel_id]
            except KeyError:
                pass



async def setup(bot):
    """Duels cog load."""
    await bot.add_cog(Duel(bot))
    log.info("Duels cog loaded")
