import logging
import socket
from os import linesep
import sys 
import asyncio
from traceback import format_exc
from aiohttp import AsyncResolver, ClientSession, TCPConnector
import aiodns
from dependency_load_error import DependencyLoadError
import discord
from discord.ext import commands
from conf import config
from tinydb import TinyDB, Query

logging.basicConfig()

log = logging.getLogger(__name__)

log.setLevel(logging.INFO)

__all__ = ('EconomyBot')

class EconomyBot(commands.Bot):
    """The Economy bot."""

    def __init__(self, **kwargs):
        try:
            super().__init__(**kwargs)

            self.http_session = ClientSession(
                connector=TCPConnector(resolver=AsyncResolver(), family=socket.AF_INET)
            )

            self.log_channel = None
            self.admin_roles = [int(admin_role_id) for admin_role_id in config.admin_roles]

            # Main database for current season
            self.database = TinyDB(config.database)
            self.message_cache = self.database.table('messages')
            self.query = Query()
            log.info('Main database loaded')

            self.info_text = ''
            self.info_text += linesep + linesep + config.description
            self.info_text += linesep + linesep + config.additional_info_text
            self.info_text += linesep + linesep + 'Type !help to see a list of available commands.' + linesep + linesep

            # TimedTask must be started first if at all
            if 'timed_task' in config.cogs and config.cogs[0] != 'timed_task':
                log.fatal('TimedTask is specified to be loaded; has to be loaded first!')
                sys.exit()

        except Exception as e:
            # If any exception occurs at this point, better not execute the thing and let the bot admin figure out what's going on.
            log.exception(e)
            sys.exit()


    async def clear_message_cache(self):
        """Clear message cache once a day. This means that users cannot auto-delete bot messages by removing their own commands in hindsight after 24 hours."""
        self.message_cache.truncate()


    async def on_message_delete(self, message):
        """Delete bot messages corresponding to deleted user commands."""
        try:
            try:
                bridge_cog = self.get_cog('ServerBridge')
                if bridge_cog is not None:
                    await bridge_cog.on_message_delete(message)
            except Exception as e:
                await self.log_channel.send('**[ERROR]** A critical error occurred while handling deleted message on server bridge. Check logs. ' + config.additional_error_message)
                log.exception(e)

            message_minus_forbidden = message.content.replace('@', '')
            message_minus_forbidden = message_minus_forbidden.replace('`', '')
            if self.message_cache.contains(self.query.id == message.id):
                res = self.message_cache.get(self.query.id == message.id)['res_id']
                for mess_id in res:
                    res_message = await message.channel.fetch_message(mess_id)
                    if res_message is not None:
                        await res_message.delete()
                        message_minus_forbidden = message.content.replace('@', '')
                        message_minus_forbidden = message_minus_forbidden.replace('`', '')
        except Exception as e:
            await self.log_channel.send('**[ERROR]** A critical error occurred while handling deleted message. Check logs. ' + config.additional_error_message)
            log.exception(e)


    async def on_message(self, message):
        """Scan messages in specific channels and broadcast them to all other channels that are being scanned."""
        try:
            bridge_cog = self.get_cog('ServerBridge')
            if bridge_cog is not None:
                await bridge_cog.on_message(message)
        except Exception as e:
            await self.log_channel.send('**[ERROR]** A critical error occurred while handling message on server bridge. Check logs. ' + config.additional_error_message)
            log.exception(e)

        # NOTE: overriding on_message breaks command processing, so do this now
        try:
            await self.process_commands(message)
        except Exception as e:
            await self.log_channel.send('**[ERROR]** A critical error occurred while processing commands. Check logs. ' + config.additional_error_message)
            log.exception(e)


    async def on_message_edit(self, before, after):
        """Handle edited messages."""
        try:
            bridge_cog = self.get_cog('ServerBridge')
            if bridge_cog is not None:
                await bridge_cog.on_message_edit(before, after)
        except Exception as e:
            await self.log_channel.send('**[ERROR]** A critical error occurred while handling edited message. Check logs. ' + config.additional_error_message)
            log.exception(e)


    async def on_ready(self):
        # Go through cogs and load them as extensions
        # NOTE: Each cog adds its own bit to _self.info_text_
        amnt_failed = 0
        for cog_name in config.cogs:
            try:
                cog_name = 'Cogs.' + cog_name
                await self.load_extension(cog_name)
            except Exception as e:
                amnt_failed += 1
                print('Failed to load extension ' + cog_name + ' with error ' + str(e))
            else:
                log.info('Loading extension ' + cog_name)
        
        timed_events_cog = self.get_cog('TimedTasks')
        if timed_events_cog is not None:
            timed_events_cog.register_timed_event(self.clear_message_cache)
 
        # If any cogs aren't loaded, bot behaviour is undefined because many cogs depend on each other - better not execute the thing and let the bot admin figure out what's going on.
        if amnt_failed > 0:
            log.exception('Summary:\n Num failed extension loads:', amnt_failed)
            sys.exit()

        print('Ready for use.')
        print('--------------')
        self.bot_channel = self.get_channel(config.bot_channel_id)
        print('Bot channel: ' + str(self.bot_channel))
        if config.log_channel_id != 0:
            self.log_channel = self.get_channel(config.log_channel_id)
            print('Log channel: ' + str(self.log_channel))

        # This could be generic at some point, but for now only bridge needs to react to this event
        bridge_cog = self.get_cog('ServerBridge')
        if bridge_cog is not None:
            await bridge_cog.on_ready()


    async def on_command_error(self, context, error):
        try:
            if isinstance(error, commands.CheckFailure):
                if str(error):
                    await self.post_error(context, str(error))
                else: # wrong channel does not post an error, but still marks message as invalid
                    await context.message.add_reaction('\U0000274C')
            elif isinstance(error, commands.MissingRequiredArgument):
                await self.post_error(context, 'A required argument is missing, ' + context.message.author.name + '. Use the command !help <command> to learn its arguments.')
            elif isinstance(error, commands.ArgumentParsingError):
                await self.post_error(context, 'An error occurred parsing your supplied arguments, ' + context.message.author.name + '. Please try again.')
            elif isinstance(error, commands.ExpectedClosingQuoteError):
                await self.post_error(context, 'Your input is missing a closing quote, ' + context.message.author.name + '. Please try again.')
            elif isinstance(error, commands.CommandNotFound):
                # Ignore all messages that start with repeated exclamation marks
                if context.message.content[1] == '!':
                    return

                token = context.message.content.partition(' ')[0][1:] # parse for anything after the exclamation mark and before the first whitespace
                if token == 'free':
                    economy_cog = self.get_cog('Economy')
                    if economy_cog is not None:
                        try:
                            await economy_cog.check(context, context.message.author.name, token)
                        except Exception as e:
                            # Wrong channel ?
                            await context.message.add_reaction('\U0000274C')
                        return

                # For convenience, we attempt to map unknown commands to labels.
                labels_cog = self.get_cog('Labels')

                if labels_cog is not None:
                    url = await labels_cog.show_internal(token)
                    if url:
                        await self.send_revertible(context, context.message.channel, url)
                        return
                    # else this was just a mistake and not actually an attempt to print a label without using !show

                await context.message.add_reaction('\U00002753') # 2754
            elif isinstance(error, commands.UserInputError):
                await self.post_error(context, 'A general input error occurred, ' + context.message.author.name + '. Sorry. Please try again.')
            elif isinstance(error, DependencyLoadError):
                await self.post_error(context, 'This feature is currently not available, ' + context.message.author.name + '. Sorry. Please notify your bot admin about loading the required dependencies.')
            else:
                raise error
        except Exception as e:
            log.exception(e)
            await self.post_error(context, 'Oh no, something went wrong. ' + config.additional_error_message)
            await self.log_channel.send('**[ERROR]** A critical error occurred handling the following command (Check logs ' + config.additional_error_message + '):')
            await self.log_command(context)

    async def post_error_private(self, context, error_text, add_error_message = ''):
        """Post an error message in a private message. React to original message with an X emote for the record and as a notification."""
        await self.post_error_commmon(context, context.message.author, error_text, add_error_message)


    async def post_error(self, context, error_text, add_error_message = ''):
        """Post an error message in the bot channel (or in a private message *if* the command was given in a PM). React to original message with an X emote for the record and as a notification."""
        await self.post_error_commmon(context, context.message.channel, error_text, add_error_message)


    async def send_revertible(self, context, channel, message):
        """Post a message that will be deleted if the user deletes their command message. NOTE: The message can only be deleted within 24 hours after the original post. Also, this will cease to work as soon as the message is removed from the local (discord's built-in) message cache."""
        res = [message.id for message in await self.post_message(context, channel, message)]
        if self.message_cache.contains(self.query.id == context.message.id):
            res_ex = self.message_cache.get(self.query.id == context.message.id)['res_id']
            res_ex.extend(res)
            self.message_cache.update({'res_id': res_ex}, self.query.id == context.message.id)
        else:
            self.message_cache.insert({'id': context.message.id, 'res_id': res})


    async def post_error_commmon(self, context, channel, error_text, add_error_message = ''):
        """Post an error message in the specified channel. React to original message with an X emote for the record and as a notification."""

        try:
            await context.message.add_reaction('\U0000274C')

            if context.guild is None:
                await self.post_message(None, context.message.author, '**[ERROR]** ' + error_text + ' ' + add_error_message)
            else:
                # Note: Avoid abuse by stripping forbidden characters, which might break the quote formatting or make the bot tag @everyone.
                message_minus_forbidden = context.message.content.replace('@', '')
                message_minus_forbidden = message_minus_forbidden.replace('`', '')
                quote = '`' + context.message.author.name + ' (' + context.guild.name + '|' + context.message.channel.name + '):` `' + message_minus_forbidden + '`' + linesep + linesep
                if channel == context.message.author:
                    await self.post_message(context, channel, quote + '**[ERROR]** ' + error_text + ' ' + add_error_message)
                else:
                    await self.send_revertible(context, channel, '**[ERROR]** ' + error_text + ' ' + add_error_message)
        except Exception as e:
            log.fatal('EXCEPTION OCCURRED WHILE POSTING ERROR:')
            log.exception(e)


    async def send_private_message(self, context, message_text, embed = None, do_quote = True):
        """Respond to a command in a private message."""

        try:
            await context.message.add_reaction('\U0001F4AC')
            quote = ''
            if context.guild is not None and do_quote:
                message_minus_forbidden = context.message.content.replace('@', '')
                message_minus_forbidden = message_minus_forbidden.replace('`', '')
                quote = '`' + context.message.author.name + ' (' + context.guild.name + '|' + context.message.channel.name + '):` `' + message_minus_forbidden + '`' + linesep + linesep
            await self.post_message(context, context.message.author, quote + message_text, embed)
        except Exception as e:
            await self.log_channel.send('**[ERROR]** A critical error occurred in a private message response.' + ' ' + config.additional_error_message)
            log.fatal('EXCEPTION OCCURRED WHILE POSTING MESSAGE:')
            log.exception(e)


    async def log_command(self, ctx):
        try:
            message_minus_forbidden = ctx.message.content.replace('@', '')
            message_minus_forbidden = message_minus_forbidden.replace('`', '')
            if ctx.guild is None:
                quote = '`' + ctx.message.author.name + ' (PM):` `' + message_minus_forbidden + '`' + linesep + linesep
            else:
                quote = '`' + ctx.message.author.name + ' (' + ctx.guild.name + '|' + ctx.message.channel.name + '): ` `' + message_minus_forbidden + '`' + linesep + linesep
            await self.log_channel.send('**[LOG]** ' + quote)
        except Exception as e:
            await self.log_channel.send('**[ERROR]** A critical error occurred while logging commands. ' + config.additional_error_message)
            log.fatal('EXCEPTION OCCURRED WHILE LOGGING:')
            log.exception(e)


    async def post_message(self, ctx, channel, message_text, embed = None):
        """Post a message in the respective channel."""

        try:
            sent_messages = []

            if embed is None:
                # Discord character limit is 2000; split up the message if it's too long
                chunk_size = 2000

                if message_text.endswith('```'):
                    message_text = message_text[:-3]
                    chunk_size = 1994

                for i in range(0, len(message_text), chunk_size):
                    text_chunk = message_text[i:i+chunk_size]

                    # Special case for markdown blocks
                    if chunk_size == 1994:
                        if i > 0:
                            text_chunk = '```' + text_chunk
                        text_chunk += '```'

                    attempts = 0

                    while attempts < config.repost_attempts:
                        try:
                            res = await channel.send(text_chunk)
                            sent_messages.append(res)
                        except discord.errors.HTTPException as e:
                            await self.log_channel.send('**[ERROR]** HTTP exception occurred while posting message - check logs. ' + config.additional_error_message)
                            log.warning('HTTP EXCEPTION OCCURRED WHILE POSTING A MESSAGE:')
                            log.exception(e)

                            attempts += 1
                            await asyncio.sleep(2)
                        else:
                            break
            else:
                attempts = 0

                while attempts < config.repost_attempts:
                    try:
                        res = await channel.send(embed=embed)
                        sent_messages.append(res)
                    except discord.errors.HTTPException as e:
                        log.warning('HTTP EXCEPTION OCCURRED WHILE POSTING AN EMBED:')
                        log.exception(e)

                        if 'Invalid Form Body' in str(e):
                            await self.log_channel.send('**[ERROR]** Failed to send an embed due to a form error - check logs. ' + config.additional_error_message)
                            break
                        else:
                            await self.log_channel.send('**[ERROR]** HTTP exception occurred while posting embed - check logs. ' + config.additional_error_message)

                        attempts += 1
                        await asyncio.sleep(2)
                    else:
                        break
            return sent_messages
        except Exception as e:
            await self.bot_channel.send('**[ERROR]** A critical error occurred.' + ' ' + config.additional_error_message)
            log.fatal('EXCEPTION OCCURRED WHILE POSTING MESSAGE:')
            log.exception(e)
