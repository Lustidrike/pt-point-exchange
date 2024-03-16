import logging
import json
import discord
from discord.ext import commands
from tinydb.operations import increment
from tinydb.operations import subtract
from collections import defaultdict
from operator import itemgetter
import math
import datetime
import asyncio
import random
from os import linesep
from .base_cog import BaseCog
from conf import config
from dependency_load_error import DependencyLoadError

log = logging.getLogger(__name__)

class BattleRoyale(BaseCog):
    """A cog for the battle royale minigame."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.br_participants = []
        self.br_holiday_points_used = []
        self.br_last_ann = ''
        self.br_pool = 0
        self.br_bet = 0
        self.br_closed = True
        self.potion_emote = '<:potion:815382651103477781>'

        with open(config.cogs_data_path + '/gambling.json', 'r') as gambling_config:
            data = json.load(gambling_config)
            self.arena_init_texts = data['arena_init_texts']
            self.custom_weapons = data['custom_weapons']
            self.custom_suicides = data['custom_suicides']
            self.suicide_emotes = data['suicide_emotes']
            self.exotic_weapons = data['exotic_weapons']

        self.br_delay = int(config.get('BattleRoyale', 'br_delay', fallback=180))
        self.br_min_bet = int(config.get('BattleRoyale', 'br_min_bet', fallback=5))
        self.br_min_users = int(config.get('BattleRoyale', 'br_min_users', fallback=3))
        self.br_wait_threshold = int(config.get('BattleRoyale', 'br_wait_threshold', fallback=5))
        self.br_wait = int(config.get('BattleRoyale', 'br_wait', fallback=3))
        self.br_skillbook_boost = int(config.get('BattleRoyale', 'br_skillbook_boost', fallback=25))
        self.br_fight_message_delay = int(config.get('BattleRoyale', 'br_fight_message_delay', fallback=1))
        self.p_event = float(config.get('BattleRoyale', 'p_event', fallback=0.3))
        self.p_suicide = float(config.get('BattleRoyale', 'p_suicide', fallback=0.05))
        self.p_block = float(config.get('BattleRoyale', 'p_block', fallback=0.3))
        self.p_critical = float(config.get('BattleRoyale', 'p_critical', fallback=0.1))
        self.p_bomb_pickup = float(config.get('BattleRoyale', 'p_bomb_pickup', fallback=0.2))
        self.p_exotic_pickup = float(config.get('BattleRoyale', 'p_exotic_pickup', fallback=0.1))
        self.p_skillbook_pickup = float(config.get('BattleRoyale', 'p_skillbook_pickup', fallback=0.2))
        self.p_potion_pickup = float(config.get('BattleRoyale', 'p_potion_pickup', fallback=0.45))
        self.p_both_hit = float(config.get('BattleRoyale', 'p_both_hit', fallback=0.6))
        self.p_drink_potion = float(config.get('BattleRoyale', 'p_drink_potion', fallback=0.75))
        self.br_potion_buff = int(config.get('BattleRoyale', 'br_potion_buff', fallback=50))
        self.br_health = int(config.get('BattleRoyale', 'br_health', fallback=100))
        self.br_critical_min_damage = int(config.get('BattleRoyale', 'br_critical_min_damage', fallback=50))
        self.br_critical_max_damage = int(config.get('BattleRoyale', 'br_critical_max_damage', fallback=100))
        self.br_min_damage = int(config.get('BattleRoyale', 'br_min_damage', fallback=1))
        self.br_max_damage = int(config.get('BattleRoyale', 'br_max_damage', fallback=50))

        # We use the same random generator as with events to calculate if both players make a hit. Both players make a hit if the random value is larger than the threshold for events, and smaller than the threshold for events PLUS this offset, i.e. the respective fraction of the probability that there is a fight.
        self.p_event_offset = (1 - self.p_event) * self.p_both_hit;

        # Some sanity checks:
        if self.p_bomb_pickup + self.p_exotic_pickup + self.p_skillbook_pickup + self.p_potion_pickup + self.p_suicide != 1.0:
            raise RuntimeError('Probabilities of BR pickups do not add up to 1!')

        if self.br_min_damage > self.br_max_damage or self.br_min_damage < 0:
            raise RuntimeError('Invalid min/max BR damage!')

        if self.br_health < 0:
            raise RuntimeError('Invalid BR health!')

        if self.p_exotic_pickup == 1:
            raise RuntimeError('This will cause an infinite loop, please use a value lower than 1 for exotic weapon pickup!')

        if self.p_block < 0 or self.p_block > 1 or self.p_critical < 0 or self.p_critical > 1 or self.p_suicide < 0 or self.p_suicide > 1 or self.p_event < 0 or self.p_event > 1:
            raise RuntimeError('Invalid BR probabilities!')

        if self.br_critical_min_damage < self.br_min_damage or self.br_max_damage > self.br_critical_max_damage or self.br_critical_min_damage > self.br_critical_max_damage:
            raise RuntimeError('Invalid min/max BR critical damage!')

        # Register battle royale to be a possible minigame for holiday points
        holidays = self.bot.get_cog('Holidays')

        if holidays is not None:
            holidays.minigames.append('Battle Royale')


    #================ BASECOG INTERFACE ================
    def extend_check_options(self, db_entry):
        result_string = 'Battle royales fought'.ljust(config.check_ljust) + ' ' + str(db_entry['brs']) + linesep \
                      + 'Battle royale wins'.ljust(config.check_ljust) + ' ' + str(db_entry['br_wins']) + linesep \
                      + 'Total damage in battle royale'.ljust(config.check_ljust) + ' ' + str(db_entry['br_damage']) + linesep \
                      + 'Total battle royale score'.ljust(config.check_ljust) + ' ' + str(db_entry['br_score'])

        return result_string


    def extend_trivia_table(self, trivia_table):
        trivia_table.insert({'name': 'highest_br_pool', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'largest_br', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'amnt_brs', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'exotic_weapons', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'blocked_hits', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'potions', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'skillbooks', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'bombs', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'suicides', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'critical', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'amnt_trades', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        # Starting with BR 2.0 (2021), highest_streak was cut in favor of the most_damage !check stat. Also, some new stats were introduced related to new features.


    def extend_trivia_output(self, trivia_table):
        result = ''

        try:
            amnt_brs = trivia_table.get(self.bot.query.name == 'amnt_brs')

            if amnt_brs['value'] > 0:
                result += 'Total amount of battle royales fought'.ljust(config.trivia_ljust) + '  ' + str(amnt_brs['value']) + linesep
        except Exception:
            pass

        try:
            highest_br_pool = trivia_table.get(self.bot.query.name == 'highest_br_pool')

            if highest_br_pool['person1'] != '':
                result += 'Highest battle royale score '.ljust(config.trivia_ljust) + '  ' + str(highest_br_pool['value']) + ' won by ' + highest_br_pool['person1'] + ' on ' + highest_br_pool['date'] + linesep
        except Exception:
            pass

        try:
            largest_br = trivia_table.get(self.bot.query.name == 'largest_br')

            if largest_br['person1'] != '':
                result += 'Most participants in a battle royale'.ljust(config.trivia_ljust) + '  ' + str(largest_br['value']) + ' won by ' + largest_br['person1'] + ' on ' + largest_br['date'] + linesep
        except Exception:
            pass

        try:
            blocked_hits = trivia_table.get(self.bot.query.name == 'blocked_hits')

            if blocked_hits['person1'] != '':
                result += 'Blocked hits in BR'.ljust(config.trivia_ljust) + '  ' + str(blocked_hits['value']) + linesep
        except Exception:
            pass
        try:
            amnt_trades = trivia_table.get(self.bot.query.name == 'amnt_trades')

            if amnt_trades['person1'] != '':
                result += 'Trade kills in BR'.ljust(config.trivia_ljust) + '  ' + str(amnt_trades['value']) + linesep
        except Exception:
            pass
        try:
            critical = trivia_table.get(self.bot.query.name == 'critical')

            if critical['person1'] != '':
                result += 'Critical hits in BR'.ljust(config.trivia_ljust) + '  ' + str(critical['value']) + linesep
        except Exception:
            pass
        try:
            exotic_weapons = trivia_table.get(self.bot.query.name == 'exotic_weapons')

            if exotic_weapons['person1'] != '':
                result += 'Exotic weapons picked up in BR'.ljust(config.trivia_ljust) + '  ' + str(exotic_weapons['value']) + linesep
        except Exception:
            pass
        try:
            potions = trivia_table.get(self.bot.query.name == 'potions')

            if potions['person1'] != '':
                result += 'Potions picked up in BR'.ljust(config.trivia_ljust) + '  ' + str(potions['value']) + linesep
        except Exception:
            pass
        try:
            skillbooks = trivia_table.get(self.bot.query.name == 'skillbooks')

            if skillbooks['person1'] != '':
                result += 'Skillbooks picked up in BR'.ljust(config.trivia_ljust) + '  ' + str(skillbooks['value']) + linesep
        except Exception:
            pass
        try:
            bombs = trivia_table.get(self.bot.query.name == 'bombs')

            if bombs['person1'] != '':
                result += 'Bombs picked up in BR'.ljust(config.trivia_ljust) + '  ' + str(bombs['value']) + linesep
        except Exception:
            pass
        try:
            suicides = trivia_table.get(self.bot.query.name == 'suicides')

            if suicides['person1'] != '':
                result += 'Suicides committed in BR'.ljust(config.trivia_ljust) + '  ' + str(suicides['value']) + linesep
        except Exception:
            pass

        return result


    def extend_season_output(self, number, season_trivia_table, season_main_db, season_tables):
        result = ''

        try:
            amnt_brs = season_trivia_table.get(self.bot.query.name == 'amnt_brs')

            if amnt_brs['value'] > 0:
                result += 'Total amount of battle royales fought'.ljust(config.season_ljust) + '  ' + str(amnt_brs['value']) + linesep
        except Exception:
            pass

        try:
            highest_br_pool = season_trivia_table.get(self.bot.query.name == 'highest_br_pool')

            # NOTE: the wording here is "prize pool" - not score - to make it compatible with previous seasons. In BR2.0, the prize pool is split among all participants that made kills, so the "prize pool" is just the remainder of the original pool.
            if highest_br_pool['person1'] != '':
                if number < 13:
                    result += 'Highest battle royale prize pool'.ljust(config.season_ljust) + '  ' + str(highest_br_pool['value']) + ' won by ' + highest_br_pool['person1'] + ' on ' + highest_br_pool['date'] + linesep
                else:
                    result += 'Highest battle royale score'.ljust(config.season_ljust) + '  ' + str(highest_br_pool['value']) + ' by ' + highest_br_pool['person1'] + ' on ' + highest_br_pool['date'] + linesep
        except Exception:
            pass

        try:
            largest_br = season_trivia_table.get(self.bot.query.name == 'largest_br')

            if largest_br['person1'] != '':
                result += 'Most participants in a battle royale'.ljust(config.season_ljust) + '  ' + str(largest_br['value']) + ' won by ' + largest_br['person1'] + ' on ' + largest_br['date'] + linesep + linesep
        except Exception:
            pass

        try:
            most_brs = max(season_main_db.all(), key=itemgetter('brs'))

            if most_brs['brs'] > 0:
                result += 'Most battle royales fought'.ljust(config.season_ljust) + '  ' + str(most_brs['brs']) + ' by ' + most_brs['user'] + linesep
        except Exception:
            pass

        try:
            most_br_wins = max(season_main_db.all(), key=itemgetter('br_wins'))

            if most_br_wins['br_wins'] > 0:
                result += 'Most battle royale wins'.ljust(config.season_ljust) + '  ' + str(most_br_wins['br_wins']) + ' by ' + most_br_wins['user'] + linesep
        except Exception:
            pass

        try:
            most_br_score = max(season_main_db.all(), key=itemgetter('br_score'))

            if most_br_score['br_score'] > 0:
                result += 'Highest total battle royale score'.ljust(config.season_ljust) + '  ' + str(most_br_score['br_score']) + ' by ' + most_br_score['user'] + linesep
        except Exception:
            pass

        # Only valid for seasons 1-12:
        if number < 13:
            try:
                most_kills = season_trivia_table.get(self.bot.query.name == 'most_br_score')

                if most_kills['person1'] != '':
                    result += 'Highest score in a battle royale'.ljust(config.season_ljust) + '  ' + str(most_kills['value']) + ' by ' + most_kills['person1'] + ' (won by ' + most_kills['person2'] + ') on ' + most_kills['date'] + linesep
            except Exception:
                pass

            try:
                highest_br_winnings = max(season_main_db.all(), key=itemgetter('br_winnings'))

                if highest_br_winnings['br_winnings'] > 0:
                    result += ('Most ' + config.currency_name + ' winnings in battle royale').ljust(config.season_ljust) + '  ' + str(highest_br_winnings['br_winnings']) + ' by ' + highest_br_winnings['user'] + linesep
            except Exception:
                pass

            try:
                longest_streak = season_trivia_table.get(self.bot.query.name == 'longest_streak')

                if longest_streak['person1'] != '':
                    result += 'Longest kill streak in a battle royale'.ljust(config.season_ljust) + '  ' + str(longest_streak['value']) + ' by ' + longest_streak['person1'] + ' (won by ' + longest_streak['person2'] + ') on ' + longest_streak['date'] + linesep
            except Exception:
                pass

        # Only valid for BR2.0 (season 13+)
        try:
            most_damage = max(season_main_db.all(), key=itemgetter('br_damage'))

            if most_damage['br_damage'] > 0:
                result += 'Most damage dealt in battle royale'.ljust(config.season_ljust) + '  ' + str(most_damage['br_damage']) + ' by ' + most_damage['user'] + linesep
        except Exception:
            pass

        # More BR2.0 stuff:
        try:
            blocked_hits = season_trivia_table.get(self.bot.query.name == 'blocked_hits')

            if blocked_hits['person1'] != '':
                result += 'Blocked hits in BR'.ljust(config.season_ljust) + '  ' + str(blocked_hits['value']) + linesep
        except Exception:
            pass
        try:
            amnt_trades = season_trivia_table.get(self.bot.query.name == 'amnt_trades')

            if amnt_trades['person1'] != '':
                result += 'Trade kills in BR'.ljust(config.season_ljust) + '  ' + str(amnt_trades['value']) + linesep
        except Exception:
            pass
        try:
            critical = season_trivia_table.get(self.bot.query.name == 'critical')

            if critical['person1'] != '':
                result += 'Critical hits in BR'.ljust(config.season_ljust) + '  ' + str(critical['value']) + linesep
        except Exception:
            pass
        try:
            exotic_weapons = season_trivia_table.get(self.bot.query.name == 'exotic_weapons')

            if exotic_weapons['person1'] != '':
                result += 'Exotic weapons picked up in BR'.ljust(config.season_ljust) + '  ' + str(exotic_weapons['value']) + linesep
        except Exception:
            pass
        try:
            potions = season_trivia_table.get(self.bot.query.name == 'potions')

            if potions['person1'] != '':
                result += 'Potions picked up in BR'.ljust(config.season_ljust) + '  ' + str(potions['value']) + linesep
        except Exception:
            pass
        try:
            skillbooks = season_trivia_table.get(self.bot.query.name == 'skillbooks')

            if skillbooks['person1'] != '':
                result += 'Skillbooks picked up in BR'.ljust(config.season_ljust) + '  ' + str(skillbooks['value']) + linesep
        except Exception:
            pass
        try:
            bombs = season_trivia_table.get(self.bot.query.name == 'bombs')

            if bombs['person1'] != '':
                result += 'Bombs picked up in BR'.ljust(config.season_ljust) + '  ' + str(bombs['value']) + linesep
        except Exception:
            pass
        try:
            suicides = season_trivia_table.get(self.bot.query.name == 'suicides')

            if suicides['person1'] != '':
                result += 'Suicides committed in BR'.ljust(config.season_ljust) + '  ' + str(suicides['value']) + linesep
        except Exception:
            pass

        return result


    def get_check_message_for_aspect(self, aspect):
        mes = None

        if aspect == 'brs':
            mes = 'Battle royales fought'
        elif aspect == 'br_wins':
            mes = 'Battle royale wins'
        elif aspect == 'br_damage':
            mes = 'Total damage in battle royale'
        elif aspect == 'br_score':
            mes = 'Total battle royale score'

        return mes


    def get_label_for_command(self, command):
        result = None

        if command == 'br_wins':
            result = 'battle royale wins'
        elif command == 'br_damage':
            result = 'battle royale damage'
        elif command == 'br_score':
            result = 'total battle royale score'
        elif command == 'brs':
            result = 'battle royales fought in'

        return result
    #==============================================

    @commands.command()
    async def joinbr(self, context):
        """Joins the battle royale with an entry fee."""

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
        weapon_emotes = gambling.weapon_emotes

        is_participating = context.message.author.name in self.br_participants

        try:
            pukcab_pool = self.br_pool

            if self.br_closed:
                await self.bot.post_error(context, 'You are too late to join the recent battle royale, ' + context.message.author.name + '. Start a new one with !battleroyale <bet> if you are so eager to fight.')
            elif context.message.author.name in self.br_participants:
                await self.bot.post_error(context, 'You are already taking part in this battle royale, ' + context.message.author.name + '.')
            else:
                user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']

                # Check if battle royale is today's minigame for holiday points
                holidays = self.bot.get_cog('Holidays')
                is_holiday_minigame = False
                holiday = 0

                if holidays is not None:
                    if holidays.holiday_minigame.contains(self.bot.query.minigame == 'Battle Royale'):
                        is_holiday_minigame = True
                        holiday = main_db.get(self.bot.query.user == context.message.author.name)['holiday']

                if user_balance + holiday >= self.br_bet:
                    self.br_participants.append(context.message.author.name)
                    self.br_pool += self.br_bet

                    # Remove entry fee
                    if holiday > 0:
                        leftover = self.br_bet - holiday

                        if leftover > 0: # i.e. br bet > holiday points
                            main_db.update(subtract('holiday', holiday), self.bot.query.user == context.message.author.name)
                            self.br_holiday_points_used.append(holiday)
                            main_db.update(subtract('balance', leftover), self.bot.query.user == context.message.author.name)
                            main_db.update(subtract('gambling_profit', leftover), self.bot.query.user == context.message.author.name)
                        else: # Note: holiday points do not count as negative gambling profit
                            main_db.update(subtract('holiday', self.br_bet), self.bot.query.user == context.message.author.name)
                            self.br_holiday_points_used.append(self.br_bet)
                    else:
                        main_db.update(subtract('balance', self.br_bet), self.bot.query.user == context.message.author.name)
                        main_db.update(subtract('gambling_profit', self.br_bet), self.bot.query.user == context.message.author.name)
                        self.br_holiday_points_used.append(0)

                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** ' + context.message.author.name + ' has joined the challengers! The prize pool is now at ' + str(self.br_pool) + ' ' + config.currency_name + 's.')
                else:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. The entry fee is ' + str(self.br_bet) + ' ' + config.currency_name + 's and your current balance is ' + str(user_balance) + '.') 
        except Exception as e:
            try:
                if (context.message.author.name in self.br_participants) and not is_participating:
                    self.br_participants.pop()

                    # Careful: We might have crashed before even adding the used holiday points, so can't always pop!
                    if len(self.br_participants) < len(self.br_holiday_points_used):
                        self.br_holiday_points_used.pop()

                self.br_pool = pukcab_pool
                await self.bot.post_error(context, 'Oh no, something went wrong (you are not part of the challengers).', config.additional_error_message)
                log.exception(e)
            except Exception as e2:
                await self.bot.post_error(context, 'Oh no, something went wrong (you are not part of the challengers).', config.additional_error_message)
                log.exception(e2)


    @commands.command()
    async def battleroyale(self, context, bet=None):
        """Starts a battle royale with a forced bet of _bet_ points."""

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
        weapon_emotes = gambling.weapon_emotes

        role = discord.utils.get(context.message.author.guild.roles, name=gambling.subscriber_role)
        role_mention = role.mention + linesep if role else ''

        race_participants = None

        try:
            horserace = BaseCog.load_dependency(self, 'Horserace')
            race_participants = horserace.race_participants
        except DependencyLoadError:
            # If horse race cog is not available, shouldn't exit with error
            pass

        class Player:
            def __init__(self, name, health):
                self.health        = int(health)
                self.damage_dealt  = int(0)
                self.weapon        = ''
                self.bombs         = int(0)
                self.potions       = int(0)
                self.damage_bonus  = int(0)
                self.exotic_weapon = None
                self.points        = int(0)
                self.name          = name

        try:
            if not bet:
                #await self.bot.post_error(context, '!battleroyale requires a forced bet.')
                #return
                bet = gambling.lock_max_bet

            try:
                bet = int(bet)
            except ValueError:
                await self.bot.post_error(context, 'Bet must be an integer.')
                return

            if self.br_bet != 0:
                await self.bot.post_error(context, 'Not so hasty, courageous fighter. There is already a battle royale in progress.')
                return
            elif race_participants is not None and len(race_participants) > 0:
                await self.bot.post_error(context, 'Sorry ' + context.message.author.name + ', please wait for the ongoing horse race to end so that the messages don\'t interfere.')
            elif bet < self.br_min_bet:
                await self.bot.post_error(context, '!battleroyale requires the initial forced bet to be at least ' + str(self.br_min_bet) + ' ' + config.currency_name + 's.')
                return
            else:
                user_balance = main_db.get(self.bot.query.user == context.message.author.name)['balance']

                # Check if battle royale is today's minigame for holiday points
                holidays = self.bot.get_cog('Holidays')
                is_holiday_minigame = False
                holiday = 0

                if holidays is not None:
                    if holidays.holiday_minigame.contains(self.bot.query.minigame == 'Battle Royale'):
                        is_holiday_minigame = True
                        holiday = main_db.get(self.bot.query.user == context.message.author.name)['holiday']

                if user_balance + holiday < bet:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. The desired entry fee is ' + str(bet) + ' ' + config.currency_name + 's and your current balance is ' + str(user_balance) + '.') 
                    return

                lock = True
                gambling = self.bot.get_cog('Gambling')

                if gambling is not None:
                    lock = gambling.lock

                if lock:
                    if bet > gambling.lock_max_bet:
                        await self.bot.post_error(context, 'High-stakes gambling is not allowed. Please stay below ' + str(gambling.lock_max_bet) + ' ' + config.currency_name + 's, ' + context.message.author.name + '. Admins can remove this limit using !unlock.') 
                        return

                self.br_participants.append(context.message.author.name)
                self.br_pool = bet
                self.br_bet = bet

                if holiday > 0:
                    leftover = bet - holiday

                    if leftover > 0: # i.e. br bet > holiday points
                        main_db.update(subtract('holiday', holiday), self.bot.query.user == context.message.author.name)
                        self.br_holiday_points_used.append(holiday)
                        main_db.update(subtract('balance', leftover), self.bot.query.user == context.message.author.name)
                        main_db.update(subtract('gambling_profit', leftover), self.bot.query.user == context.message.author.name)
                    else: # Note: holiday points do not count as negative gambling profit
                        main_db.update(subtract('holiday', bet), self.bot.query.user == context.message.author.name)
                        self.br_holiday_points_used.append(bet)
                else:
                    main_db.update(subtract('balance', bet), self.bot.query.user == context.message.author.name)
                    main_db.update(subtract('gambling_profit', bet), self.bot.query.user == context.message.author.name)
                    self.br_holiday_points_used.append(0)

                announcement = self.br_last_ann

                while announcement == self.br_last_ann:
                    announcement = random.choice(self.arena_init_texts).replace('[USER]', context.message.author.name)

                await self.bot.post_message(context, self.bot.bot_channel, role_mention + '**[BATTLE ROYALE]** ' + announcement)
                await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** Type !joinbr (entry fee is ' + str(bet) + ') to join the ranks of the challengers.')
                self.br_last_ann = announcement
                self.br_closed = False
                amount_asked = 0

                while len(self.br_participants) < self.br_wait_threshold and amount_asked < self.br_wait:
                    if self.br_delay <= 60:
                        await asyncio.sleep(self.br_delay) # during this time, people can use commands to join
                    else:
                        await asyncio.sleep(self.br_delay-60) # during this time, people can use commands to join
                        await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** Battle royale will start in 1 minute. Type !joinbr to take part! Participants: (' + str(len(self.br_participants)) + '/' + str(self.br_wait_threshold) + ')')
                        await asyncio.sleep(30) # during this time, people can use commands to join
                        await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** Battle royale will start in 30 seconds. Type !joinbr to take part! Participants: (' + str(len(self.br_participants)) + '/' + str(self.br_wait_threshold) + ')')
                        await asyncio.sleep(30) # during this time, people can use commands to join

                    if len(self.br_participants) < self.br_wait_threshold:
                        await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** Waiting for more people to join the bloodshed (' + str(len(self.br_participants)) + '/' + str(self.br_wait_threshold) + ')')

                    amount_asked += 1

                self.br_closed = True

                if len(self.br_participants) < self.br_min_users:
                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** The battle royale has been canceled due to a lack of interest in the bloodshed. Cowards! (min ' + str(self.br_min_users) + ' participants).')
                    for i, p in enumerate(self.br_participants):
                        try:
                            balance_p = main_db.get(self.bot.query.user == p)['balance']
                            gambling_pr = main_db.get(self.bot.query.user == p)['gambling_profit']
                            main_db.update({'gambling_profit': gambling_pr + (self.br_bet - self.br_holiday_points_used[i])}, self.bot.query.user == p)
                            if self.br_holiday_points_used[i] > 0:
                                holiday_p = main_db.get(self.bot.query.user == p)['holiday']
                                main_db.update({'holiday': holiday_p + self.br_holiday_points_used[i]}, self.bot.query.user == p)
                                main_db.update({'balance': balance_p + self.br_bet - self.br_holiday_points_used[i]}, self.bot.query.user == p)
                            else:
                                main_db.update({'balance': balance_p + self.br_bet}, self.bot.query.user == p)
                        except Exception as e:
                            await self.bot.post_error(context, 'Could not refund bet to ' + context.message.author.name + '.', config.additional_error_message)
                            log.exception(e)
                else:
                    # _self.br_participants_ is now filled with usernames
                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** Ladies and gentlemen, the battle royale is about to begin. ' + str(len(self.br_participants)) + ' brave fighters have stepped into the arena after ' + context.message.author.name + ' called for a grand battle. They fight over ' + str(self.br_pool) + ' ' + config.currency_name + 's. Good luck! :drum:')

                    kill_map = defaultdict(int)
                    time_intervals = [8, 10, 12, 14, 16] # maybe make this configurable?
                    weapons = {}
                    players = [Player(p, self.br_health) for p in self.br_participants]
                    survivors = []

                    # Assign random weapon emotes to players. If there is a custom emote, that takes precedence:
                    for index, p in enumerate(self.br_participants):
                        survivors.append(index)
                        if p in self.custom_weapons:
                            players[index].weapon = self.custom_weapons[p]
                        else:
                            players[index].weapon = random.choice(weapon_emotes)

                    g_ctr_exotics = 0
                    g_ctr_blocked = 0
                    g_ctr_trades = 0
                    g_ctr_potions = 0
                    g_ctr_skillbooks = 0
                    g_ctr_bombs = 0
                    g_ctr_suicides = 0
                    g_ctr_critical = 0
                    g_points_per_kill = math.ceil(self.br_bet/2.0)
                    first_round = True

                    while len(survivors) > 1:
                        try:
                            await asyncio.sleep(random.choice(time_intervals))

                            event = random.uniform(0, 1)

                            if event < self.p_event and not first_round:
                                # Nobody is damaged this round, some random event should happen

                                person_index = random.choice(survivors)
                                person = players[person_index]
                                reroll = True
                                message = ''
                                acc_a = self.p_potion_pickup
                                acc_b = acc_a + self.p_bomb_pickup
                                acc_c = acc_b + self.p_exotic_pickup
                                acc_d = acc_c + self.p_suicide 
                                acc_e = acc_d + self.p_skillbook_pickup 
                                suicide = False

                                # Re-roll for actual chosen event, and
                                # keep re-rolling if we pick up an exotic and we already have one:
                                while reroll:
                                    event = random.uniform(0, 1)
                                    reroll = False

                                    if event < acc_a:
                                        # Potion pickup
                                        g_ctr_potions += 1
                                        person.potions += 1
                                        message = person.name + ' has found a potion! ' + self.potion_emote + ' This item instantly brings back ' + str(self.br_potion_buff) + ' health points if they get a chance to use it.'
                                    elif event < acc_b:
                                        # Bomb pickup
                                        g_ctr_bombs += 1
                                        person.bombs += 1
                                        message = person.name + ' has found a bomb! :bomb: This item deals critical damage and can avenge players even after death.'
                                    elif event < acc_c:
                                        if not person.exotic_weapon:
                                            # Exotic pickup
                                            g_ctr_exotics += 1
                                            ex_wp = random.choice(self.exotic_weapons)
                                            person.exotic_weapon = ex_wp
                                            person.weapon = ex_wp
                                            message = person.name + ' has found ' + ex_wp + ' and picks it up as their new weapon! This item deals critical damage until the end of the round.'
                                        else:
                                            # continue loop, as we don't want to replace exotic weapons. That would be a disadvantage for the chosen player as it makes no difference in gameplay but denies other events.
                                            reroll = True
                                    elif event < acc_d:
                                        # Suicide
                                        suicide = True
                                        g_ctr_suicides += 1
                                        survivors[:] = (i for i in survivors if i != person_index)
                                        if person.name in self.custom_suicides:
                                            message = person.name + ' ' + self.custom_suicides[person.name]
                                        else:
                                            suicide_emote = random.choice(self.suicide_emotes)
                                            message = person.name + ' ' + suicide_emote + ' ' + person.name
                                    elif event < acc_e:
                                        # Skillbook pickup
                                        g_ctr_skillbooks += 1
                                        person.damage_bonus += self.br_skillbook_boost
                                        message = person.name + ' has found a skillbook! :book: Their weapon damage has increased by ' + str(self.br_skillbook_boost) + ' points.'

                                await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** ' + message)
                                # Players may drink potions during events
                                # NOTE: no probability check here on purpose
                                if not suicide:
                                    while person.potions > 0 and person.health < self.br_health:
                                        person.health = min(person.health + self.br_potion_buff, self.br_health)
                                        person.potions -= 1
                                        await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** ' + person.name + ' uses ' + self.potion_emote + ' to get back to ' + str(person.health) + ' health!')
                            else:
                                # Calculate the amount of individual fights in this round:
                                if len(survivors) > 3:
                                    max_damaged = math.ceil(len(survivors)/3)
                                    amnt_probabilities = [0.5]
                                    amnt_list = []

                                    for i in range(1, max_damaged):
                                        amnt_list.append(i)
                                        amnt_probabilities.append(0.5 / (max_damaged - 1))

                                    amnt_list.append(max_damaged)

                                    x = random.uniform(0, 1)
                                    cum_prob = 0

                                    for i, i_p in zip(amnt_list, amnt_probabilities):
                                        cum_prob += i_p

                                        if x < cum_prob:
                                            break

                                    amnt_fights = max(i, 1)
                                else:
                                    amnt_fights = 1

                                # Now do the actual fights:
                                for i in range(0, amnt_fights):
                                    # We do not allow both players to take damage if they are the last to fight:
                                    player2_hits = event < self.p_event + self.p_event_offset and len(survivors) > 2 

                                    fighters = random.sample(survivors, 2)
                                    player1 = players[fighters[0]]
                                    player2 = players[fighters[1]]
                                    player1_prev_health = player1.health
                                    player2_prev_health = player2.health
                                    weapon1 = player1.weapon
                                    weapon2 = player2.weapon
                                    player1_bomb = False
                                    player2_bomb = False
                                    player1_critical = False
                                    player2_critical = False
                                    player1_critical_for_ctr = False
                                    player2_critical_for_ctr = False
                                    result = ''

                                    if player1.bombs > 0:
                                        weapon1 = ':bomb:'
                                        player1_critical = True
                                        block2 = False
                                        player1_bomb = True
                                        player1.bombs -= 1
                                    else:
                                        block2 = random.uniform(0, 1) < self.p_block
                                        if not block2:
                                            if player1.exotic_weapon is not None:
                                                player1_critical = True
                                            else:
                                                player1_critical_for_ctr = random.uniform(0, 1) < self.p_critical
                                                player1_critical = player1_critical_for_ctr

                                    if player1_critical:
                                        player1_damage = math.floor(random.randrange(self.br_critical_min_damage, self.br_critical_max_damage))
                                    else:
                                        player1_damage = math.floor(random.randrange(self.br_min_damage, self.br_max_damage))

                                    player1_damage += player1.damage_bonus
                                    new_player2_health = player2.health

                                    if not block2:
                                        new_player2_health -= player1_damage
                                        player1.damage_dealt += min(player1_damage, player2.health) # if the opponent is killed, damage should be capped or the stats will be too high (i.e. they won't match the damage values displayed)
                                        g_ctr_critical += player1_critical_for_ctr
                                    else:
                                        g_ctr_blocked += 1

                                    if player2_hits:
                                        if player2.bombs > 0:
                                            weapon2 = ':bomb:'
                                            player2_critical = True
                                            block1 = False
                                            player2_bomb = True
                                        else:
                                            block1 = random.uniform(0, 1) < self.p_block
                                            if not block1:
                                                if player2.exotic_weapon is not None:
                                                    player2_critical = True
                                                else:
                                                    player2_critical_for_ctr = random.uniform(0, 1) < self.p_critical
                                                    player2_critical = player2_critical_for_ctr

                                        if player2_critical:
                                            player2_damage = math.floor(random.randrange(self.br_critical_min_damage, self.br_critical_max_damage))
                                        else:
                                            player2_damage = math.floor(random.randrange(self.br_min_damage, self.br_max_damage))

                                        player2_damage += player2.damage_bonus
                                        new_player1_health = player1.health

                                        if not block1:
                                            new_player1_health -= player2_damage
                                        # stats are updated below

                                    killed1 = False
                                    killed2 = False

                                    if new_player2_health <= 0:
                                        killed2 = True

                                    if player2_hits and new_player1_health <= 0:
                                        killed1 = True

                                    # Trade kills are not allowed unless a grenade is used.
                                    # Player 1 always takes precedence
                                    if killed1 and killed2 and not player2_bomb:
                                        killed1 = False
                                        player2_hits = False
                                    if killed1 and killed2:
                                        g_ctr_trades += 1

                                    # Now that we're sure player2 has hit, update stats:
                                    if player2_hits:
                                        if player2_bomb:
                                            player2.bombs -= 1
                                        if block1:
                                            g_ctr_blocked += 1
                                        else:
                                            player2.damage_dealt += min(player2_damage, player1.health)
                                            g_ctr_critical += player2_critical_for_ctr

                                    if player2_hits:
                                        player1.health = new_player1_health;
                                        if not killed1:
                                            death1_opt = ''
                                        else:
                                            death1_opt = ':skull: '
                                            survivors[:] = (i for i in survivors if players[i].name != player1.name)
                                            player2.points += g_points_per_kill
                                        opt2 = ''
                                        if player2_critical:
                                            opt2 += ' (Critical hit)'
                                        if player2.damage_bonus > 0 and not block1:
                                            opt2 += ' (Skill bonus: +' + str(player2.damage_bonus) + ')'

                                    player2.health = new_player2_health;
                                    if not killed2:
                                        death2_opt = ''
                                    else:
                                        death2_opt = ':skull: '
                                        survivors[:] = (i for i in survivors if players[i].name != player2.name)
                                        player1.points += g_points_per_kill
                                    opt1 = ''
                                    if player1_critical:
                                        opt1 += ' (Critical hit)'
                                    if player1.damage_bonus > 0 and not block2:
                                        opt1 += ' (Skill bonus: +' + str(player1.damage_bonus) + ')'

                                    result = ''

                                    # Couple cases in which player2 needs to go first (swap order of damage messages):
                                    # a) player2 dies AND player1 does not die. If player2 threw a bomb, they can go second (post-mortem damage)
                                    # b) player2 dies AND player1 dies. If player1 threw a bomb, they should go second. If both threw bombs or player2 threw a bomb, the order is fine.
                                    # Yes, this is the worst and absolutely most terrible way to code this.
                                    player2_display_block = block2
                                    player1_display_opt = opt1
                                    player1_display = player1
                                    player2_display = player2
                                    player1_prev_health_display = player1_prev_health
                                    player2_prev_health_display = player2_prev_health
                                    player1_weapon_display = weapon1
                                    player2_weapon_display = weapon2
                                    player1_health_display = max(player1.health, 0)
                                    player2_health_display = max(player2.health, 0)
                                    if player2_hits:
                                        player1_display_block = block1
                                        player1_death_opt = death1_opt
                                        player2_display_opt = opt2
                                    player2_death_opt = death2_opt
                                    if player2_hits and ((killed2 and not killed1 and not player2_bomb) or (killed1 and killed2 and player1_bomb and not player2_bomb)):
                                        player1_display = player2
                                        player2_display = player1
                                        player1_weapon_display = weapon2
                                        player2_weapon_display = weapon1
                                        player1_death_opt = death2_opt
                                        player2_death_opt = death1_opt
                                        player1_prev_health_display = player2_prev_health
                                        player2_prev_health_display = player1_prev_health
                                        player1_health_display = max(player2.health, 0)
                                        player2_health_display = max(player1.health, 0)
                                        player1_display_opt = opt2
                                        player2_display_opt = opt1
                                        player1_display_block = block2
                                        player2_display_block = block1

                                    if player2_display_block:
                                        player2_death_opt = ' :shield: '
                                    result = '**[BATTLE ROYALE]** ' + player1_display.name + ' ' + player1_weapon_display + player2_death_opt + ' ' + player2_display.name + ' *(~~' + str(player2_prev_health_display) + '~~ __**' + str(player2_health_display) + '**__)' + player1_display_opt + '*'
                                    await self.bot.post_message(context, self.bot.bot_channel, result)

                                    if player2_hits:
                                        if player1_display_block:
                                            player1_death_opt = ' :shield: '
                                        result = '**[BATTLE ROYALE]** ' + player2_display.name + ' ' + player2_weapon_display + player1_death_opt + ' ' + player1_display.name + ' *(~~' + str(player1_prev_health_display) + '~~ __**' + str(player1_health_display) + '**__)' + player2_display_opt + '*'
                                        await self.bot.post_message(context, self.bot.bot_channel, result)

                                    if len(survivors) > 1:
                                        # Players pick up items from defeated opponents:
                                        list_pickup = ''
                                        pickup_player = None
                                        pickup_ded_player = None
                                        if killed1 and not killed2:
                                            pickup_player = player2
                                            pickup_ded_player = player1
                                        elif killed2 and not killed1:
                                            pickup_player = player1
                                            pickup_ded_player = player2

                                        if pickup_player and pickup_ded_player:
                                            if not pickup_player.exotic_weapon and pickup_ded_player.exotic_weapon:
                                                pickup_player.exotic_weapon = pickup_ded_player.exotic_weapon
                                                pickup_player.weapon = pickup_ded_player.exotic_weapon
                                                list_pickup += pickup_ded_player.exotic_weapon
                                            if pickup_ded_player.bombs > 0:
                                                pickup_player.bombs += pickup_ded_player.bombs
                                                for i in range(0, pickup_ded_player.bombs):
                                                    list_pickup += ':bomb:'
                                            if pickup_ded_player.potions > 0:
                                                pickup_player.potions += pickup_ded_player.potions
                                                for i in range(0, pickup_ded_player.potions):
                                                    list_pickup += self.potion_emote

                                            if list_pickup:
                                                await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** ' + pickup_player.name + ' picks up ' + list_pickup + ' from ' + pickup_ded_player.name + '.')

                                        # After the fight, surviving players may drink potions to get themselves back up:
                                        if not killed1:
                                            if random.uniform(0, 1) < self.p_drink_potion:
                                                while player1.potions > 0 and player1.health < self.br_health:
                                                    player1.health = min(player1.health + self.br_potion_buff, self.br_health)
                                                    player1.potions -= 1
                                                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** ' + player1.name + ' uses ' + self.potion_emote + ' to get back to ' + str(player1.health) + ' health!')
                                        if not killed2:
                                            if random.uniform(0, 1) < self.p_drink_potion:
                                                while player2.potions > 0 and player2.health < self.br_health:
                                                    player2.health = min(player2.health + self.br_potion_buff, self.br_health)
                                                    player2.potions -= 1
                                                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** ' + player2.name + ' uses ' + self.potion_emote + ' to get back to ' + str(player2.health) + ' health!')

                                        await asyncio.sleep(self.br_fight_message_delay)
                                    first_round = False
                        except Exception as e:
                            await self.bot.post_error(context, 'Oh no, something went wrong. Skipping this round. The battle will continue, however there might be some inconsistencies with some stats and/or player states might have been affected. ' + config.additional_error_message)
                            log.exception(e)

                    #####   BATTLE IS DONE   #####
                    ##### (now update stats) #####

                    winner = players[survivors[0]]
                    indent = max(len(p.name) for p in players)
                    result = '```Scoreboard ' + linesep + linesep
                    non_winners_result_part = ''
                    for p in sorted(players, key=lambda x: x.points)[::-1]:
                        if p.name != winner.name:
                            self.br_pool -= p.points
                            non_winners_result_part += p.name.ljust(indent) + '   ' + str(p.points) + linesep

                    winner.points = self.br_pool
                    result += winner.name.ljust(indent) + '   ' + str(winner.points) + linesep + non_winners_result_part + '```'

                    await self.bot.post_message(context, self.bot.bot_channel, '**[BATTLE ROYALE]** :trumpet: ' + winner.name + ' wins, taking home the remaining pool of ' + str(winner.points) + ' ' + config.currency_name + 's! :trumpet:')
                    await self.bot.post_message(context, self.bot.bot_channel, result)

                    highest_total_owned = trivia_table.get(self.bot.query.name == 'highest_total_owned')['value']
                    for p in players:
                        # Update balances
                        try:
                            balance = main_db.get(self.bot.query.user == p.name)['balance']
                            new_balance = balance + p.points
                            main_db.update({'balance': balance + p.points}, self.bot.query.user == p.name)

                            if new_balance > highest_total_owned:
                                trivia_table.update({'value': new_balance, 'person1': p.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_total_owned')
                                highest_total_owned = new_balance
                        except Exception as e:
                            await self.bot.post_error(context, 'Could not update balance for player ' + p.name + '.', config.additional_error_message)
                            log.exception(e)
                        # Update damage stats
                        try:
                            damage = main_db.get(self.bot.query.user == p.name)['br_damage']
                            main_db.update({'br_damage': damage + p.damage_dealt}, self.bot.query.user == p.name)
                        except Exception as e:
                            await self.bot.post_error(context, 'Could not update damage dealt for player ' + p.name + '.', config.additional_error_message)
                            log.exception(e)
                        # Update gambling profit
                        try:
                            gambling_profit = main_db.get(self.bot.query.user == p.name)['gambling_profit']
                            main_db.update({'gambling_profit': gambling_profit + p.points}, self.bot.query.user == p.name)
                        except Exception as e:
                            await self.bot.post_error(context, 'Could not update gambling profit for player ' + p.name + '.', config.additional_error_message)
                            log.exception(e)
                        # Update score
                        try:
                            if p.points > 0:
                                br_score = main_db.get(self.bot.query.user == p.name)['br_score']
                                main_db.update({'br_score': br_score + p.points}, self.bot.query.user == p.name)
                        except Exception as e:
                            await self.bot.post_error(context, 'Could not update total score for player ' + p.name + '.', config.additional_error_message)
                            log.exception(e)
                        # Update amount of BRs participated in
                        try:
                            main_db.update(increment('brs'), self.bot.query.user == p.name)
                        except Exception as e:
                            await self.bot.post_error(context, 'Could not update total BRs participated in for player ' + p.name + '.', config.additional_error_message)
                            log.exception(e)

                    # Other trivia
                    try:
                        trivia_table.update(increment('value'), self.bot.query.name == 'amnt_brs')
                        main_db.update(increment('br_wins'), self.bot.query.user == winner.name)

                        highest_br_pool = trivia_table.get(self.bot.query.name == 'highest_br_pool')['value']
                        largest_br = trivia_table.get(self.bot.query.name == 'largest_br')['value']
                        exotic_weapons = trivia_table.get(self.bot.query.name == 'exotic_weapons')['value']
                        blocked = trivia_table.get(self.bot.query.name == 'blocked_hits')['value']
                        amnt_trades = trivia_table.get(self.bot.query.name == 'amnt_trades')['value']
                        potions = trivia_table.get(self.bot.query.name == 'potions')['value']
                        skillbooks = trivia_table.get(self.bot.query.name == 'skillbooks')['value']
                        bombs = trivia_table.get(self.bot.query.name == 'bombs')['value']
                        suicides = trivia_table.get(self.bot.query.name == 'suicides')['value']
                        critical = trivia_table.get(self.bot.query.name == 'critical')['value']

                        if self.br_pool > highest_br_pool:
                            trivia_table.update({'value': self.br_pool, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_br_pool')

                        if len(self.br_participants) > largest_br:
                            trivia_table.update({'value': len(self.br_participants), 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'largest_br')

                        trivia_table.update({'value': exotic_weapons + g_ctr_exotics, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'exotic_weapons')
                        trivia_table.update({'value': blocked + g_ctr_blocked, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'blocked_hits')
                        trivia_table.update({'value': potions + g_ctr_potions, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'potions')
                        trivia_table.update({'value': skillbooks + g_ctr_skillbooks, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'skillbooks')
                        trivia_table.update({'value': bombs + g_ctr_bombs, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'bombs')
                        trivia_table.update({'value': suicides + g_ctr_suicides, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'suicides')
                        trivia_table.update({'value': critical + g_ctr_critical, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'critical')
                        trivia_table.update({'value': amnt_trades + g_ctr_trades, 'person1': winner.name, 'person2': '', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'amnt_trades')
                    except Exception as e:
                        await self.bot.post_error(context, 'Could not update some battle royale stats (only affects !trivia and !season outputs).', config.additional_error_message)
                        log.exception(e)
        except Exception as e:
            await self.bot.post_error(context, 'Oh no, something went wrong.', config.additional_error_message)
            log.exception(e)

            # Hand out refunds:
            for i, p in enumerate(self.br_participants):
                try:
                    balance_p = main_db.get(self.bot.query.user == p)['balance']
                    gambling_pr = main_db.get(self.bot.query.user == p)['gambling_profit']
                    main_db.update({'gambling_profit': gambling_pr + (self.br_bet - self.br_holiday_points_used[i])}, self.bot.query.user == p)
                    if self.br_holiday_points_used[i] > 0:
                        holiday_p = main_db.get(self.bot.query.user == p)['holiday']
                        main_db.update({'holiday': holiday_p + self.br_holiday_points_used[i]}, self.bot.query.user == p)
                        main_db.update({'balance': balance_p + self.br_bet - self.br_holiday_points_used[i]}, self.bot.query.user == p)
                    else:
                        main_db.update({'balance': balance_p + self.br_bet}, self.bot.query.user == p)
                except Exception as e:
                    await self.bot.post_error(context, 'Could not refund bet to ' + context.message.author.name + '.', config.additional_error_message)
                    log.exception(e)

        # Reset stuff
        self.br_closed = True
        self.br_pool = 0
        self.br_bet = 0
        self.br_participants = []
        self.br_holiday_points_used = []



async def setup(bot):
    """Battle royale cog load."""
    await bot.add_cog(BattleRoyale(bot))
    log.info("Battle royale cog loaded")
