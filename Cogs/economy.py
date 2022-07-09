import logging
import discord
from discord.ext import commands
from tinydb.operations import subtract
from tinydb import where
import datetime
from operator import itemgetter
from os import linesep
from .base_cog import BaseCog
from conf import config
from dependency_load_error import DependencyLoadError

log = logging.getLogger(__name__)

class Economy(BaseCog):
    """A cog for general economy commands, e.g. !give, !loan."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.main_db = bot.database.table('main_db')
        self.give_table = bot.database.table('give_table')

        bot.info_text += 'Registered users may reward others by giving away a fictional currency called ' + config.currency_name + 's.' + linesep + 'Type !add to initialize your account.' + linesep + linesep
        bot.info_text += 'Free ' + config.currency_name + 's:' + linesep + '  There is a free amount of points you may give away each day without draining your personal balance.' + linesep + '  Free points are reset every day and do not stack. If the amount you wish to transfer exceeds your remaining free points, your personal balance is used as supplement. Additionally, you can use !loan to take out a loan in free points (repaid automatically the next day)' + linesep + '  Free points cannot be used for gambling.' + linesep + linesep

        self.max_points_to_give_per_day = int(config.get('Economy', 'max_points_to_give_per_day', fallback='30'))
        self.initial_balance = int(config.get('Economy', 'initial_balance', fallback='15'))
        self.free_points_per_day = int(config.get('Economy', 'free_points_per_day', fallback='15'))
        self.max_loan =  int(config.get('Economy', 'max_loan', fallback='14'))

        timed_events_cog = BaseCog.load_dependency(self, 'TimedTasks')
        timed_events_cog.register_timed_event(self.refill_free_points)
        timed_events_cog.register_timed_event(self.pay_back_loans)


    #================ BASECOG INTERFACE ================
    def extend_trivia_table(self, trivia_table):
        trivia_table.insert({'name': 'highest_total_owned', 'value': 0, 'person1': '', 'person2': '', 'date': ''})
        trivia_table.insert({'name': 'total_loans', 'value': 0, 'person1': '', 'person2': '', 'date': ''})


    def extend_trivia_output(self, trivia_table):
        total_amnt_users = len(self.main_db)
        current_main_db_total = sum(item['balance'] for item in self.main_db if item['balance'] > 0)

        total_loans = trivia_table.get(self.bot.query.name == 'total_loans')
        result = (config.currency_name + 's currently in circulation').ljust(config.trivia_ljust) + '  ' + str(current_main_db_total) + linesep
        result += ('Total ' + config.currency_name + ' loans taken out').ljust(config.trivia_ljust) + '  ' + str(total_loans['value']) + linesep
        result += 'Amount of users'.ljust(config.trivia_ljust) + '  ' + str(total_amnt_users) + linesep
        return result


    def extend_season_output(self, number, season_trivia_table, season_main_db, season_tables):
        result = ''

        try:
            try:
                current_main_db_total = sum(item['balance'] for item in season_main_db if item['balance'] > 0)
                result += (config.currency_name + 's in circulation').ljust(config.season_ljust) + '  ' + str(current_main_db_total) + linesep
            except Exception:
                pass

            try:
                total_loans = season_trivia_table.get(self.bot.query.name == 'total_loans')
                result += ('Total ' + config.currency_name + ' loans taken out').ljust(config.season_ljust) + '  ' + str(total_loans['value']) + linesep
            except Exception:
                pass

            total_amnt_users = len(season_main_db)
            result += 'Amount of users'.ljust(config.season_ljust) + '  ' + str(total_amnt_users) + linesep + linesep
        except Exception:
            pass

        try:
            highest_given_total = max(season_main_db.all(), key=itemgetter('given'))

            if highest_given_total['given'] > 0:
                result += ('Most ' + config.currency_name + 's given (total)').ljust(config.season_ljust) + '  ' + str(highest_given_total['given']) + ' by ' + highest_given_total['user'] + linesep
        except Exception as e:
            print(str(e))

        try:
            highest_received_total = max(season_main_db.all(), key=itemgetter('received'))

            if highest_received_total['received'] > 0:
                result += ('Most ' + config.currency_name + 's received (total)').ljust(config.season_ljust) + '  ' + str(highest_received_total['received']) + ' by ' + highest_received_total['user'] + linesep
        except Exception:
            pass

        try:
            highest_owned = max(season_main_db.all(), key=itemgetter('balance'))

            if highest_owned['balance'] > 0:
                result += ('Most ' + config.currency_name + 's owned at end of season').ljust(config.season_ljust) + '  ' + str(highest_owned['balance']) + ' by ' + highest_owned['user'] + linesep
        except Exception:
            pass

        try:
            highest_total_owned = season_trivia_table.get(self.bot.query.name == 'highest_total_owned')

            if highest_total_owned['person1'] != '':
                result += ('Most ' + config.currency_name + 's owned at a time').ljust(config.season_ljust) + '  ' + str(highest_total_owned['value']) + ' by ' + highest_total_owned['person1'] + ' on ' + highest_total_owned['date'] + linesep
        except Exception:
            pass

        return result


    async def on_season_end(self):
        self.give_table.truncate()
        self.main_db.update({'free': self.free_points_per_day, 'balance': self.initial_balance, 'given': 0, 'received': 0, 'loan': 0, 'gambling_profit': 0, 'duel_wins': 0, 'duel_winnings': 0, 'duels': 0, 'races': 0, 'first_place_bets': 0, 'top_three_bets': 0, 'race_winnings': 0, 'horse_bets': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'brs': 0, 'br_damage': 0, 'br_wins': 0, 'br_score': 0, 'holiday': 0})
        await self.bot.post_message(None, self.bot.bot_channel, '**[NEW SEASON]** Everyone gets ' + str(self.free_points_per_day) + ' free points and starts with a balance of ' + str(self.initial_balance) + '!')
    #==============================================


    #================ TIMED EVENTS ================
    async def refill_free_points(self):
        """Refill every user's free points to the default value. Usually executed once per day, e.g. at 5AM."""
        try:
            self.give_table.truncate()
            self.main_db.update({'free': self.free_points_per_day})
        except Exception as e:
            await self.bot.post_message(None, self.bot.bot_channel, '**[ERROR]** Oh no, something went wrong while refilling free points. ' + config.additional_error_message)
            log.exception(e)

    async def pay_back_loans(self):
        for user in self.main_db.all():
            try:
                loan = user['loan']

                if loan > 0:
                    freer = user['free']
                    diff = max(freer - loan, 0)

                    self.main_db.update({'free': diff}, self.bot.query.user == user['user'])
                    self.main_db.update({'loan': 0}, self.bot.query.user == user['user'])
                    await self.bot.post_message(None, self.bot.bot_channel, '**[INFO]** ' + user['user'] + ' pays back his loan of ' + str(loan) + ' ' + config.currency_name + 's. They have ' + str(diff) + ' free ' + config.currency_name + 's left for the day.')
            except Exception as e:
                await self.bot.post_message(None, self.bot.bot_channel, '**[ERROR]** Oh no, something went wrong while paying back loans. ' + config.additional_error_message)
                log.exception(e)
    #==============================================

    @commands.command()
    async def add(self, context):
        """Adds a user. Users can only add themselves."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        user = context.message.author.name

        if self.main_db.contains(self.bot.query.user == user):
            await self.bot.post_error(context, 'User ' + user + ' already exists.')
        else:
            await self.add_internal(user)

    async def add_internal(self, user):
        self.main_db.insert({'user': user, 'balance': self.initial_balance, 'free': self.free_points_per_day, 'given': 0, 'received': 0, 'loan': 0, 'gambling_profit': 0, 'duel_wins': 0, 'duel_winnings': 0, 'duels': 0, 'races': 0, 'first_place_bets': 0, 'top_three_bets': 0, 'race_winnings': 0, 'horse_bets': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'brs': 0, 'br_score': 0, 'br_wins': 0, 'br_damage': 0, 'holiday': 0})

        await self.bot.post_message(None, self.bot.bot_channel, '**[INFO]** Added user ' + user + ' with initial ' + config.currency_name + ' balance ' + str(self.initial_balance) + '. You may also spend an additional, free ' + str(self.free_points_per_day) + ' points each day.')


    @commands.command(hidden=True)
    async def deleteuser(self, context, user):
        """Delete a user from the database."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_owner(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        if not self.main_db.contains(self.bot.query.user == user):
            await self.bot.post_error(context, user + ' has not been added yet. They need to type !add to initialize their account.')
            return

        self.main_db.remove(self.bot.query.user == user)
        await self.bot.post_message(context, context.message.channel, '**[INFO]** ' + context.message.author.name + ' has deleted user ' + str(user) + '.')


    @commands.command(hidden=True)
    async def mergeusers(self, context, old_user, user):
        """Delete _old_user_ from the database, adding to their points to the account of _user_."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_owner(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        stats = BaseCog.load_dependency(self, 'Stats')
        trivia_table = stats.trivia_table

        if not self.main_db.contains(self.bot.query.user == user):
            await self.bot.post_error(context, user + ' has not been added yet. They need to type !add to initialize their account.')
            return

        if not self.main_db.contains(self.bot.query.user == old_user):
            await self.bot.post_error(context, old_user + ' has not been added yet. They need to type !add to initialize their account.')
            return

        if user == old_user:
            await self.bot.post_error(context, old_user + ' is the same as ' + user + '.')
            return

        balance_old_user = self.main_db.get(self.bot.query.user == old_user)['balance']
        balance_user = self.main_db.get(self.bot.query.user == user)['balance'] + balance_old_user

        self.main_db.remove(self.bot.query.user == old_user)
        await self.bot.post_message(context, context.message.channel, '**[INFO]** ' + context.message.author.name + ' has deleted user ' + str(old_user) + '.')

        self.main_db.update({'balance': balance_user}, self.bot.query.user == user)

        await self.bot.post_message(context, context.message.channel, '**[INFO]** Transferred ' + str(balance_old_user) + ' ' + config.currency_name + 's to ' + user + '\'s account. They now have ' + str(balance_user) + ' ' + config.currency_name + 's.')

        try:
            highest_total_owned = trivia_table.get(where('name') == 'highest_total_owned')['value']

            if balance_user > highest_total_owned:
                trivia_table.update({'value': balance_user, 'person1': user, 'person2': 'None', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_total_owned')
        except Exception as e:
            await self.bot.post_error(context, 'Could not update some stats (only affects !trivia output).')
            log.exception(e)


    @commands.command()
    async def give(self, context, user, amnt, reason = None):
        """Gives _amnt_ points to _user_. Must specify a _reason_."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        stats = BaseCog.load_dependency(self, 'Stats')
        trivia_table = stats.trivia_table

        try:
            quote = ''

            if context.message.channel != self.bot.bot_channel:
                quote = '`' + context.message.author.name + ': ' + context.message.channel.name + ': ' + context.message.content + '`' + linesep + linesep

            try:
                amnt = int(amnt)
            except ValueError:
                try:
                    tmp = amnt 
                    amnt = int(user)
                    user = tmp
                except ValueError:
                    await self.post_error_private_conditional(context, '!give requires a positive integer as second argument (amount of ' + config.currency_name + 's to give).')
                    return

            user = BaseCog.map_user(self, user)

            if not reason:
                await self.post_error_private_conditional(context, 'You need to specify a reason to give points to ' + user + '.')
            else:
                if amnt < 0:
                    await self.post_error_private_conditional(context, 'Cannot give a negative amount of ' + config.currency_name + 's.')
                elif self.main_db.contains(self.bot.query.user == user):
                    if amnt > self.max_points_to_give_per_day:
                        await self.post_error_private_conditional(context, 'You cannot give ' + user + ' more than ' + str(self.max_points_to_give_per_day) + ' ' + config.currency_name + 's each day, ' + context.message.author.name + '.')
                        return

                    if self.give_table.contains((self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user)):
                        already_given_amount_today = self.give_table.get((self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user))['amount']

                        if already_given_amount_today >= self.max_points_to_give_per_day:
                            await self.post_error_private_conditional(context, 'You have already given ' + user + ' ' + str(self.max_points_to_give_per_day) + ' ' + config.currency_name + 's today, ' + context.message.author.name + ', you will have to wait until tomorrow to give them any more points.')
                            return
                        elif already_given_amount_today + amnt > self.max_points_to_give_per_day:
                            amnt = self.max_points_to_give_per_day - already_given_amount_today # < amnt
                            await self.post_error_private_conditional(context, 'You have already given ' + user + ' ' + str(already_given_amount_today) + ' ' + config.currency_name + 's today, ' + context.message.author.name + ', you can only give ' + str(amnt) + ' more.')
                            quote = ''

                    freep = 0
                    balance = 0
                    other_balance = 0

                    freep = self.main_db.get(self.bot.query.user == context.message.author.name)['free']
                    balance = self.main_db.get(self.bot.query.user == context.message.author.name)['balance']
                    other_balance = self.main_db.get(self.bot.query.user == user)['balance']

                    try:
                        if user == context.message.author.name:
                            await self.post_error_private_conditional(context, 'You cannot give ' + config.currency_name + 's to yourself, ' + context.message.author.name + '.')
                            return # not sure if necessary
                        else:
                            if freep < amnt:
                                rest_pay = amnt - freep # always positive

                                if rest_pay > balance:
                                    await self.post_error_private_conditional(context, 'You do not have enough ' + config.currency_name + 's, ' + context.message.author.name + '. Your balance is ' + str(balance) + ' and you have ' + str(freep) + ' free points left to spend today. Use !loan <amount> to take out a loan in free points (automatically repaid the next day)')
                                    return
                                else:
                                    self.main_db.update({'balance': other_balance + amnt}, self.bot.query.user == user)
                                    self.main_db.update({'free': 0, 'balance': balance - rest_pay}, self.bot.query.user == context.message.author.name)
                                    await self.bot.post_message(context, self.bot.bot_channel, quote + '**[INFO]** ' + context.message.author.name + ' gave ' + str(freep) + ' free ' + config.currency_name + 's and ' + str(rest_pay) + ' ' + config.currency_name + 's to ' + user + '.' )
                            else:
                                self.main_db.update({'balance': other_balance + amnt}, self.bot.query.user == user)
                                self.main_db.update(subtract('free', amnt), self.bot.query.user == context.message.author.name)
                                await self.bot.post_message(context, self.bot.bot_channel, quote + '**[INFO]** ' + context.message.author.name + ' gave ' + str(amnt) + ' (free) ' + config.currency_name + 's to ' + user + '.' )

                            try:
                                if self.give_table.contains((self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user)):
                                    already_given_amount_today = self.give_table.get((self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user))['amount']

                                    try:
                                        self.give_table.update({'amount': already_given_amount_today + amnt}, (self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user))
                                    except Exception as e:
                                        try:
                                            self.give_table.update({'amount': already_given_amount_today}, (self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user))
                                        except Exception as e2:
                                            await self.post_error_private_conditional(context, 'A fatal error occured while trying to update ' + config.currency_name + 's given today from ' + context.message.author.name + ' to ' + user + '. Please note that the transaction may not have completed successfully and/or your balances might be wrong.')
                                            log.exception(e2)
                                        raise
                                else:
                                    self.give_table.insert({'donor': context.message.author.name, 'recipient': user, 'amount': amnt})
                            except Exception as e:
                                raise

                            try:
                                highest_total_owned = trivia_table.get(where('name') == 'highest_total_owned')['value']

                                if other_balance + amnt > highest_total_owned:
                                    trivia_table.update({'value': other_balance + amnt, 'person1': user, 'person2': 'None', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'highest_total_owned')

                                given_total = self.main_db.get(self.bot.query.user == context.message.author.name)['given']
                                self.main_db.update({'given': given_total + amnt}, self.bot.query.user == context.message.author.name)
                                received_total = self.main_db.get(self.bot.query.user == user)['received']
                                self.main_db.update({'received': received_total + amnt}, self.bot.query.user == user)
                            except Exception as e:
                                await self.post_error_private_conditional(context, 'Could not update some stats (only affects !trivia output).')
                                log.exception(e)
                    except Exception as e:
                        try:
                            self.main_db.update({'balance': other_balance}, self.bot.query.user == user)
                            self.main_db.update({'free': freep}, self.bot.query.user == context.message.author.name)
                            self.main_db.update({'balance': balance}, self.bot.query.user == context.message.author.name)
                            await self.post_error_private_conditional(context, 'Oh no, something went wrong.')
                        except Exception as e2:
                            await self.post_error_private_conditional(context, 'A fatal error occured while trying to reset balances. Please note that the transaction may not have completed successfully and/or your balances might be wrong.')
                            log.exception(e2)
                else:
                    await self.post_error_private_conditional(context, '' + user + ' has not been added yet. They need to type !add to initialize their account.')
        except Exception as e:
            raise e
        finally:
            # If this is not the bot channel, delete the message but still quote it in the bot channel.
            if context.message.channel != self.bot.bot_channel:
                await context.message.delete()


    @commands.command()
    async def given(self, context, user):
        """Shows how many points you have given to _user_ today."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        await BaseCog.dynamic_user_add(self, context)

        user = BaseCog.map_user(self, user)

        if self.give_table.contains((self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user)):
            given_amount_today = self.give_table.get((self.bot.query.donor == context.message.author.name) & (self.bot.query.recipient == user))['amount']
            left = self.max_points_to_give_per_day - given_amount_today
            await self.bot.send_revertible(context, context.message.channel, '**[INFO]** Points given to ' + user + ': ' + str(given_amount_today) + ', points left to give them today: ' + str(left) + '.')
        else:
            await self.bot.send_revertible(context, context.message.channel, '**[INFO]** You have not given any ' + config.currency_name + 's to ' + user + ' yet today, ' + context.message.author.name + '.')


    async def post_error_private_conditional(self, context, error_text, add_error_message = ''):
        if context.message.channel != self.bot.bot_channel:
            await self.bot.post_error_private(context, error_text, add_error_message)
        else:
            await self.bot.post_error(context, error_text, add_error_message)


    @commands.command()
    async def loan(self, context, amount):
        """Take out a loan of _amount_ free points, to be repaid the next day."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        await BaseCog.dynamic_user_add(self, context)

        stats = BaseCog.load_dependency(self, 'Stats')
        trivia_table = stats.trivia_table

        try:
            quote = ''

            if context.message.channel != self.bot.bot_channel:
                quote = '`' + context.message.author.name + ': ' + context.message.channel.name + ': ' + context.message.content + '`' + linesep + linesep

            try:
                amount = int(amount)
            except ValueError:
                await self.post_error_private_conditional(context, 'Amount must be an integer.')
            else:
                account = self.main_db.get(self.bot.query.user == context.message.author.name)
                debt = account['loan']
                new_debt = debt + amount

                if debt >= self.max_loan:
                    await self.post_error_private_conditional(context, 'You have already taken out the maximum of ' + str(self.max_loan) + ' ' + config.currency_name + 's in loans today, ' + context.message.author.name + '.')
                elif new_debt > self.max_loan:
                    await self.post_error_private_conditional(context, 'Max loan is ' + str(self.max_loan) + ' ' + config.currency_name + 's.')
                elif amount < 1:
                    await self.post_error_private_conditional(context, 'Min loan is 1 ' + config.currency_name + '.')
                else:
                    freer = account['free']
                    self.main_db.update({'free': freer + amount}, self.bot.query.user == context.message.author.name)
                    self.main_db.update({'loan': new_debt}, self.bot.query.user == context.message.author.name)

                    await self.bot.post_message(context, self.bot.bot_channel, quote + '**[INFO]** ' + context.message.author.name + ' has taken out a small loan of ' + str(amount) + ' (free) ' + config.currency_name + 's.')

                    total_loans = trivia_table.get(self.bot.query.name == 'total_loans')['value']
                    total_loans += amount
                    trivia_table.update({'value': total_loans, 'person1': 'None', 'person2': 'None', 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}, self.bot.query.name == 'total_loans')
        except Exception as e:
            raise e
        finally:
            # If this is not the bot channel, delete the message but still quote it in the bot channel.
            if context.message.channel != self.bot.bot_channel:
                await context.message.delete()


    @commands.command()
    async def check(self, context, user=None, aspect=None):
        """Shows account info for _user_ (name can be omitted). If no argument is given, only balance is shown. To show all info, use !check all. Other options: balance, free, holiday, loan, given, received, br_wins, br_score, br_damage, brs, duel_wins, duel_winnings, duels, races, first_place_bets, race_winnings, gambling_profit."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_forbidden_characters(self, context)
        await BaseCog.dynamic_user_add(self, context)

        if not user and not aspect:
            user = context.message.author.name
        else:
            user_pukcab = user
            user = BaseCog.map_user(self, user)

            if not self.main_db.contains(self.bot.query.user == user):
                if not aspect:
                    aspect = user
                    user = context.message.author.name
                else:
                    await self.bot.post_error(context, 'User ' + user_pukcab + ' has not been added yet. They need to type !add to initialize their account.')
                    return

        main_db_entry = self.main_db.get(self.bot.query.user == user)

        if not aspect:
            aspect = 'balance'
        elif aspect == 'all':
            combined_check_result = '**[INFO]** Checking user ' + user + ':' + linesep + '```' \
                + (config.currency_name + ' balance').ljust(config.check_ljust) + ' ' + str(main_db_entry['balance']) + linesep \
                + 'Free points left today'.ljust(config.check_ljust) + ' ' + str(main_db_entry['free']) + linesep \
                + 'Current debt'.ljust(config.check_ljust) + ' ' + str(main_db_entry['loan']) + linesep \
                + 'Total points given to other users'.ljust(config.check_ljust) + ' ' + str(main_db_entry['given']) + linesep \
                + 'Total points received from other users'.ljust(config.check_ljust) + ' ' + str(main_db_entry['received']) + linesep

            # NOTE: Cog load order determines output !
            for cog_name, cog in self.bot.cogs.items():
                result = cog.extend_check_options(main_db_entry)

                if result:
                    combined_check_result += result + linesep

            await self.bot.send_private_message(context, combined_check_result + '```')
            return

        try:
            stuff = main_db_entry[aspect]
        except KeyError:
            await self.bot.post_error(context, 'No info for ' + aspect + '. Refer to !help check.')
            return

        mes = None

        if aspect == 'balance':
            mes = '' + config.currency_name + ' balance'
        elif aspect == 'free':
            mes = 'Free points left today'
        elif aspect == 'loan':
            mes = ' debt'
        elif aspect == 'given':
            mes = 'Total points given to other users'
        elif aspect == 'received':
            mes = 'Total points received from other users'

        # Each log may register a message corresponding to an aspect
        if not mes:
            for cog_name, cog in self.bot.cogs.items():
                mes = cog.get_check_message_for_aspect(aspect)

                if mes is not None:
                    break

        if not mes:
            await self.bot.post_error(context, 'No info for ' + aspect + '. Refer to !help check. Maybe the cog is not loaded or it does not handle this input correctly.')
        else:
            await self.bot.send_revertible(context, context.message.channel, '**[INFO]** Checking user ' + user + ':' + linesep + '```' + mes.ljust(config.check_ljust) + ' ' + str(stuff) + '```')


    @commands.command(hidden=True)
    async def endseason(self, context):
        """Ends the current season and starts a new one."""

        BaseCog.check_main_server(self, context)
        BaseCog.check_bot_channel(self, context)
        BaseCog.check_owner(self, context)
        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)

        await self.bot.post_message(context, self.bot.bot_channel, '**[NEW SEASON]** Duke ' + context.message.author.name + ' has announced a new season!')

        for cog_name, cog in self.bot.cogs.items():
            await cog.on_season_end()

def setup(bot):
    """Economy cog load."""
    bot.add_cog(Economy(bot))
    log.info("Economy cog loaded")
