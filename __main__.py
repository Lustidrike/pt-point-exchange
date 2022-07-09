import logging
from conf import config
from bot import EconomyBot
from discord.ext import commands
import discord

logging.basicConfig(filename=config.logfile, format='%(asctime)s - [%(levelname)s] %(name)s : %(message)s')
log = logging.getLogger(__name__)

try:
    intents = discord.Intents.default()
    intents.members = False
    intents.presences = False
    bot = EconomyBot(command_prefix=config.prefix, description=config.description, case_insensitive=True, help_command=commands.DefaultHelpCommand(dm_help=True), chunk_guilds_at_startup=False, intents=intents)
    bot.run(config.token)
except Exception as e:
    log.exception(e)
