import logging
import discord
from discord.ext import commands
from os import linesep
from .base_cog import BaseCog

log = logging.getLogger(__name__)

class Northmarker(BaseCog):
    """A cog for calculating northmarker rotation."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.bot = bot
        self.bot.info_text += 'Northmarker:' + linesep + '  Using the command !northmarker, users can quickly find the right northmarker rotation for their interior. Type !help northmarker for details on how to use this feature.' + linesep + linesep

    @commands.command()
    async def northmarker(self, context, ext_z, int_z):
        """Calculate northmarker rotation with exterior door at _ext_z_ and interior door at _int_z_ degrees."""

        BaseCog.check_forbidden_characters(self, context)

        try:
            ext_z = float(ext_z)
            int_z = float(int_z)
        except ValueError:
            await self.bot.post_error(context, 'Arguments must be numbers.')
        else:
            rot = (((360 - ext_z) % 360) + ((int_z + 180) % 360)) % 360
            formatted_rot = "{:.1f}".format(rot)
            await self.bot.send_revertible(context, context.message.channel, '**[INFO]** Northmarker rotation is ' + formatted_rot + '.')


async def setup(bot):
    """Northmarker cog load."""
    await bot.add_cog(Northmarker(bot))
    log.info("Northmarker cog loaded")
