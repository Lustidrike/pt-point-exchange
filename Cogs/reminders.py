import logging
import discord
from discord.ext import commands
import asyncio
from datetime import timedelta
from datetime import datetime
from conf import config
from .base_cog import BaseCog
from tinydb import Query
from os import linesep
from concurrent.futures import CancelledError

log = logging.getLogger(__name__)

class Reminders(BaseCog):
    """A cog for timed reminders."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.reminder_table = self.bot.database.table('reminder_table')
        self.users = Query()
        self.bot.info_text += 'Reminders:' + linesep + '  Using the command !remind, users may set custom reminders for the bot to send at specific points in time. Type !help remind for details on how to use this feature.' + linesep + linesep
        self.tasks = {}


    @commands.Cog.listener()
    async def on_ready(self):
        for item in self.reminder_table:
            try:
                timed_until_execute = (datetime.strptime(item['time_then'], "%m/%d/%y %H:%M:%S") - datetime.now()).seconds
                author = self.bot.get_user(item['author_id'])
                if author is not None:
                    if item['channel'] == 0:
                        self.tasks[item['time_then']] = self.bot.loop.create_task(self.timed_task(None, author, author.name, item['message'], timed_until_execute, item['time_then']))
                    else:
                        channel = self.bot.get_channel(item['channel'])
                        if channel is not None:
                            self.tasks[item['time_then']] = self.bot.loop.create_task(self.timed_task(None, channel, author.name, item['message'], timed_until_execute, item['time_then']))
                        else:
                            log.fatal('Failed to retrieve channel with id ' + str(item['channel']))
                else:
                    log.fatal('Failed to retrieve author with id ' + str(item['author_id']))
            except Exception as e:
                log.fatal('EXCEPTION OCCURRED WHILE RUNNING REMINDER SETUP')
                log.exception(e)

    @commands.command()
    async def reminders(self, context):
        """Shows all reminders created by you."""

        BaseCog.check_forbidden_characters(self, context)
        reminders = self.reminder_table.search(self.users.author_id == context.message.author.id)
        if len(reminders) > 0:
            result = '```Reminders ' + linesep + linesep

            channel_indent = max(len(self.bot.get_channel(reminder['channel']).name) if self.bot.get_channel(reminder['channel']) is not None else len('Channel') for reminder in reminders)
            time_indent = max(len(reminder['time_then']) for reminder in reminders)

            result += 'Index  ' + 'Channel'.ljust(channel_indent) + '  ' + 'Time'.ljust(time_indent) + '  ' + 'Message' + linesep + linesep
            ctr = 1

            for reminder in reminders:
                channel_obj = self.bot.get_channel(reminder['channel'])
                channel_name = channel_obj.name if channel_obj is not None else 'PM'
                time = reminder['time_then']
                message = reminder['message']

                result += str(ctr).ljust(len('Index')) + '  ' + str(channel_name).ljust(channel_indent) + '  ' + time.ljust(time_indent) + '  ' + str(message) + linesep
                ctr += 1

            result += '```'
            await self.bot.send_private_message(context, result)
        else:
            await self.bot.send_private_message(context, '**[INFO]** You have set no reminders.')


    @commands.command()
    async def clearreminder(self, context, index):
        """Clears reminder at index _index_. Only respects reminders set by you. You can retrive an appropriate index via !reminders."""

        BaseCog.check_forbidden_characters(self, context)

        try:
            index = int(index)
        except ValueError:
            await self.bot.post_error(context, 'Index must be a valid integer.')
            return

        reminders = self.reminder_table.search(self.users.author_id == context.message.author.id)
        if len(reminders) > 0:
            if index < 1 or index > len(reminders):
                await self.bot.post_error(context, 'Invalid index. Please choose a number between 1 and ' + str(len(reminders)))

            reminder = reminders[index - 1]
            time_then = reminder['time_then']
            self.tasks[time_then].cancel()
            del self.tasks[time_then]
            self.reminder_table.remove(self.users.time_then == time_then)

            await self.bot.send_private_message(context, '**[INFO]** You have removed a reminder at index ' + str(index) + '.')
        else:
            await self.bot.send_private_message(context, '**[INFO]** You have set no reminders.')


    @commands.command()
    async def remind(self, context, minutes, hours, *, message):
        """Sends a reminder to the author of this command in the current channel in _minutes_ minutes and _hours_ hours. If specifying hours only, set minutes to 0: !remind 0 2 Example reminder. Quotes are not needed around the reminder message. NOTE: You can ping other users in the reminder text like you would in a regular message."""

        try:
            message_combined = message #'`{}`'.format(message)

            BaseCog.check_forbidden_characters(self, context)
            time_now = datetime.now()
            try:
                minutes = int(minutes)
            except ValueError:
                await self.bot.post_error(context, 'Minutes must be a valid integer.')
                return

            try:
                hours = int(hours)
            except ValueError:
                await self.bot.post_error(context, 'Hours must be left blank or be a valid integer.')
                return

            if context.message.guild is None:
                channel_id = 0
            else:
                channel_id = context.message.channel.id

            message_minus_forbidden = message_combined.replace('@everyone', 'everyone')
            message_minus_forbidden = message_minus_forbidden.replace('@here', 'here')

            time_then = time_now + timedelta(minutes = minutes, hours = hours)
            time_until_execute = (time_then - time_now).total_seconds()
            time_formatted = time_then.strftime('%m/%d/%y %H:%M:%S')
            self.reminder_table.insert({'channel': channel_id, 'author_id': context.message.author.id, 'message': message_combined, 'time_then': time_formatted})
            self.tasks[time_formatted] = self.bot.loop.create_task(self.timed_task(context, context.message.channel, context.message.author.name, message_combined, time_until_execute, time_formatted))
            await self.bot.post_message(context, context.message.channel, context.message.author.name + ' has set a reminder at ' + time_formatted + ' (' + "{:.2f}".format(time_until_execute / 3600) + ' hours from now)')
        except Exception as e:
            await self.bot.post_error(context, 'Oh no, something went wrong.', config.additional_error_message)
            log.exception(e)


    async def timed_task(self, context, channel, author_name, message, time_until_execute, time_formatted):
        """Asynchronous timer loop that executes a task at a specific time."""

        try:
            await self.bot.wait_until_ready()
            while True:
                await asyncio.sleep(time_until_execute)
                try:
                    self.reminder_table.remove(self.users.message == message)
                    del self.tasks[time_formatted]
                    await self.bot.post_message(None, channel, '**[REMINDER]** ' + author_name + ': ' + message + '.')
                    break
                except Exception as e:
                    if context is None:
                        await self.bot.post_message(None, self.bot.log_channel, '**[ERROR]** Oh no, something went wrong in a timed task loop.')
                    else:
                        await self.bot.post_error(context,'Oh no, something went wrong. ' + config.additional_error_message) 
                    log.fatal('EXCEPTION OCCURRED WHILE EXECUTING TIMED EVENT:')
                    log.exception(e)
                    break
        except CancelledError as e:
            log.exception(e)
            pass
        except Exception as e:
            if context is None:
                await self.bot.post_message(None, self.bot.log_channel, '**[ERROR]** Oh no, something went wrong in a timed task loop.')
            else:
                await self.bot.post_error(context,'Oh no, something went wrong. ' + config.additional_error_message) 
            log.fatal('EXCEPTION OCCURRED WHILE RUNNING TIMED EVENTS LOOP:')
            log.exception(e)


async def setup(bot):
    """Load reminder cog."""
    await bot.add_cog(Reminders(bot))
    log.info("Reminder cog loaded")
