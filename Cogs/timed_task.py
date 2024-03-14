import logging
import discord
from discord.ext import commands
import asyncio
import datetime
from conf import config
from .base_cog import BaseCog

log = logging.getLogger(__name__)

class TimedTasks(BaseCog):
    """A cog for (daily) timed events; e.g. holidays, free points, paying back loans."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)

        self.hour = int(config.get('TimedTasks', 'timed_task_hour', fallback='5'))
        self.minute = int(config.get('TimedTasks', 'timed_task_minute', fallback='0'))
        self.second = int(config.get('TimedTasks', 'timed_task_second', fallback='0'))

        # If the bot dies during the day and is restarted, self.time_until_execute will be set correctly
        # HOWEVER, if the bot is dead in that moment when it should execute its tasks and is restarted subsequently it will not execute the timed tasks.
        # This is a known issue but 'fixed' e.g. by running a cronjob to restart the bot 5 minutes before the timed events should be executed.

        self.timed_task = bot.loop.create_task(self.timed_task())
        self.timed_events = [] # Cogs register their tasks here that should be executed

        # Figure out number of seconds until next time we need to execute our events
        tomorrow = datetime.datetime.now() + datetime.timedelta(1)

        execute_time = datetime.datetime(
            year=tomorrow.year,
            month=tomorrow.month,
            day=tomorrow.day,
            hour=self.hour,
            minute=self.minute,
            second=self.second
        )

        self.time_until_execute = (execute_time - datetime.datetime.now()).seconds
        print(self.time_until_execute)


    def register_timed_event(self, event):
        self.timed_events.append(event)


    async def timed_task(self):
        """Asynchronous timer loop that executes a set of tasks at a specific time. Examples are paying back loans, resetting free points, or printing holidays."""

        try:
            await self.bot.wait_until_ready()

            while True:
                await asyncio.sleep(self.time_until_execute)
                self.time_until_execute = 86400  # 1 day

                try:
                    # Execute all registered events:
                    for event in self.timed_events:
                        await event()
                except Exception as e:
                    await self.bot.post_message(None, self.bot.bot_channel, '**[ERROR]** Oh no, something went wrong. ' + config.additional_error_message)
                    log.fatal('EXCEPTION OCCURRED WHILE EXECUTING TIMED EVENT:')
                    log.exception(e)
        except Exception as e:
            await self.bot.post_message(None, self.bot.bot_channel, '**[ERROR]** Oh no, something went wrong. ' + config.additional_error_message)
            log.fatal('EXCEPTION OCCURRED WHILE RUNNING TIMED EVENTS LOOP:')
            log.exception(e)

    def cog_unload(self):
        """Cancel timed task on cog unload."""
        self.timed_task.cancel()


async def setup(bot):
    """Load timed tasks cog."""
    await bot.add_cog(TimedTasks(bot))
    log.info("Timed tasks cog loaded")
