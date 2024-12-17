import logging
import discord
from tinydb.operations import increment
from functools import cmp_to_key
from discord.ext import commands
from operator import itemgetter
from os import linesep
from conf import config
from .base_cog import BaseCog

log = logging.getLogger(__name__)

class Labels(BaseCog):
    """A cog for setting, updating and showing arbitrary info associated with label keys."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.bot = bot
        self.label_table = self.bot.database.table('label_table')
        self.label_frequencies = self.bot.database.table('label_frequencies')
        self.bot.info_text += 'Labels:' + linesep + '  The label feature allows users to store (!set/!update) and retrieve (!show) pieces of information - such as images or generic text - in a database for frequent use. For convenience, you may use !<label> as a shortcut for !show <label> if that labels exists. Keep in mind that actual commands always take precedence over labels.' + linesep + linesep


    def extend_trivia_output(self, trivia_table):
        result = ''

        try:
            amnt_labels = len(self.label_table)

            if amnt_labels > 0:
                result += 'Total amount of labels'.ljust(config.trivia_ljust) + '  ' + str(amnt_labels) + linesep
        except Exception:
            pass

        try:
            sorted_table = sorted(self.label_frequencies.all(), key=cmp_to_key(lambda x,y: 0 if x['count'] > y['count'] else -1))
            if sorted_table:
                result += 'Most popular label'.ljust(config.trivia_ljust) + '  ' + sorted_table[-1]['iid'] + ' (shown ' + str(sorted_table[-1]['count']) + ' times)' + linesep
        except Exception:
            pass

        return result


    @commands.command()
    async def popular(self, context, count = None):
        """Shows a list of _count_ popular images/messages/emotes previously set using using !set <label> <value>. If _count_ is not specified, shows the top ten. NOTE: This will PM you the results of your search query, even if you post this message in a channel."""

        BaseCog.check_forbidden_characters(self, context)

        try:
            count = int(count)
            if count == 0:
                raise ValueError
        except (ValueError, TypeError):
            count = 10

        len_table = len(self.label_frequencies.all())
        if self.label_frequencies and len_table > 0:
            count = min(len_table, count)
            sorted_table = sorted(self.label_frequencies.all(), key=cmp_to_key(lambda x,y: -1 if x['count'] > y['count'] else 0))[:count]
            max_len = max(len(item['iid']) for item in sorted_table)
            quote = ''
            if context.guild is not None:
                message_minus_forbidden = context.message.content.replace('@', '')
                message_minus_forbidden = message_minus_forbidden.replace('`', '')
                quote = '`' + context.message.author.name + ' (' + context.guild.name + '|' + context.message.channel.name + '):` `' + message_minus_forbidden + '`' + linesep + linesep
            result = quote + '**[INFO]** Popular labels (sorted by amount of times shown):' + linesep + '```'
            for label in sorted_table:
                new_part = label['iid'].ljust(max_len) + '   ' + str(label['count']) + linesep
                new_string = result + new_part

                if len(new_string) > 1991:
                    await self.bot.send_private_message(context, result + '```', None, False)
                    result = '```'

                result += new_part

            result += '```'
            await self.bot.send_private_message(context, result, None, False)
        else:
            await self.bot.send_private_message(context, '**[INFO]** There are no labels.')


    @commands.command()
    async def update(self, context, label, *, value):
        """Update an existing message/image/emote _value_ that can subsequently be displayed via !show _label_. This will only work if the label already exists. Use !set <label> to create a new entry."""

        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        BaseCog.check_admin(self, context)
        label = label.lower()

        if label == 'label':
            await self.bot.post_error(context, 'The correct syntax is !update <label> <content>.')
            return

        if not value:
            await self.bot.post_error(context, 'Labels cannot be empty, sorry.')
            return

        if self.label_table.contains(self.bot.query.iid == label):
            self.label_table.update({'url': value}, self.bot.query.iid == label)
            await self.bot.post_message(context, context.message.channel, '**[INFO]** ' + context.message.author.name + ' has updated the label ' + str(label) + '.')
        else:
            await self.bot.post_error(context, 'The label \'' + label + '\' does not exist and therefore cannot be updated, ' + context.message.author.name + '. If it is your wish to set a new label, you may use the !set command for that purpose.')


    @commands.command()
    async def set(self, context, label, *, value):
        """Store a message/image/emote _value_ that can subsequently be displayed via !show _label_. If the label exists, it will be updated with the new value. Please only use lowercase letters."""

        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        BaseCog.check_dev(self, context)
        label = label.lower()

        if label == 'label':
            await self.bot.post_error(context, 'The correct syntax is !set <label> <content>.')
            return

        if not value:
            await self.bot.post_error(context, 'Labels cannot be empty, sorry.')
            return

        if self.label_table.contains(self.bot.query.iid == label):
            await self.bot.post_error(context, 'The label \'' + label + '\' already exists, ' + context.message.author.name + '. If it is your wish to update this label, you may use the !update command for that purpose.')
        else:
            self.label_table.insert({'iid': label, 'url': value})
            await self.bot.post_message(context, context.message.channel, '**[INFO]** ' + context.message.author.name + ' has set a new label ' + str(label) + '.')


    async def show_internal(self, label):
        label = label.lower()

        if not self.label_table.contains(self.bot.query.iid == label):
            return ''
        else:
            url = self.label_table.get(self.bot.query.iid == label)['url']
            if not self.label_frequencies.contains(self.bot.query.iid == label):
                self.label_frequencies.insert({'iid': label, 'count': 0})
            else:
                self.label_frequencies.update(increment('count'), self.bot.query.iid == label)
            return url


    @commands.command()
    async def show(self, context, label):
        """Display a message/image/emote with the given label _label_. Note: This will not work without previously setting up the label using !set _label_ <value>. Use the command !labels <search_text> to show available labels containing \'search_text\'."""

        BaseCog.check_forbidden_characters(self, context)
        url = await self.show_internal(label)

        if not url:
            await context.message.add_reaction('\U0000274C')
        else:
            await self.bot.send_revertible(context, context.message.channel, url)


    @commands.command(hidden=True)
    async def jamie(self, context, pull, up, label):
        """Display a message/image/emote with the given label _label_. Note: This will not work without previously setting up the label using !set _label_ <value>. Use the command !labels <search_text> to show available labels containing \'search_text\'. This command only works like this: !jamie pull up <label>"""

        BaseCog.check_forbidden_characters(self, context)
        
        if pull.lower() != 'pull' or up.lower() != 'up':
            await context.message.add_reaction('\U0000274C')
            return

        url = await self.show_internal(label)

        if not url:
            await context.message.add_reaction('\U0000274C')
        else:
            await self.bot.send_revertible(context, context.message.channel, url)


    async def labels_internal(self, context, search_text):
        if self.label_table:
            if search_text is None:
                combined_table = [e['iid'] for e in sorted(self.label_table.all(), key=itemgetter('iid'), reverse=False)]
            else:
                search_text = search_text.lower()
                combined_table = [e['iid'] for e in filter(lambda x: search_text in x['iid'], sorted(self.label_table.all(), key=itemgetter('iid'), reverse=False))]

            if len(combined_table) > 0:
                quote = ''
                if context.guild is not None:
                    message_minus_forbidden = context.message.content.replace('@', '')
                    message_minus_forbidden = message_minus_forbidden.replace('`', '')
                    quote = '`' + context.message.author.name + ' (' + context.guild.name + '|' + context.message.channel.name + '):` `' + message_minus_forbidden + '`' + linesep + linesep
                result = quote + '```Labels: ' + linesep
                for image in combined_table:
                    new_part = '  ' + image + linesep
                    new_string = result + new_part

                    if len(new_string) > 1991:
                        await self.bot.send_private_message(context, result + '```', None, False)
                        result = '```'

                    result += new_part

                result += '```'
                await self.bot.send_private_message(context, result, None, False)
            else:
                await self.bot.send_private_message(context, '**[INFO]** There are no labels like ' + search_text + '.')
        else:
            await self.bot.send_private_message(context, '**[INFO]** There are no labels.')


    @commands.command()
    async def labels(self, context, search_text = None):
        """Shows a list of images/messages/emotes containing _search_text_ in their label that can be shown using !show <label> or simply !label and set/updated using !set <label> <value> and !update <label> <value> respectively. Note: \'!alllabels\' will print all labels. NOTE: This will PM you the results of your search query, even if you post this message in a channel."""

        BaseCog.check_forbidden_characters(self, context)
        if not search_text:
            await self.bot.post_error(context, 'Please specify a search term, e.g. \'!labels tr_map\'. To show all labels, use the !alllabels command.')
        else:
            await self.labels_internal(context, search_text)


    @commands.command()
    async def alllabels(self, context):
        """NOTE: THE OUTPUT OF THIS COMMAND IS LONG; consider using !labels <search_term> instead. Shows a list of all images/messages/emotes that can be shown using !show <label> or simply !label and set/updated using !set <label> <value> and !update <label> <value> respectively. NOTE: This will PM you the results of your search query, even if you post this message in a channel."""

        BaseCog.check_forbidden_characters(self, context)
        await self.labels_internal(context, None)


    async def delete_internal(self, context, label):
        label = label.lower()

        if not self.label_table.contains(self.bot.query.iid == label):
            await self.bot.post_error(context, 'The label ' + label + ' does not exist, ' + context.message.author.name + '.')
        else:
            self.label_table.remove(self.bot.query.iid == label)
            await self.bot.post_message(context, context.message.channel, '**[INFO]** ' + context.message.author.name + ' has deleted the label ' + str(label) + '.')


    @commands.command()
    async def deletelabel(self, context, label):
        """Remove a message/image/emote with label _label_ from the database."""

        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        BaseCog.check_admin(self, context)
        await self.delete_internal(context, label)


    @commands.command()
    async def delete(self, context, label):
        """Remove a message/image/emote with label _label_ from the database."""

        BaseCog.check_forbidden_characters(self, context)
        BaseCog.check_not_private(self, context)
        BaseCog.check_admin(self, context)
        await self.delete_internal(context, label)


async def setup(bot):
    """Labels cog load."""
    await bot.add_cog(Labels(bot))
    log.info("Labels cog loaded")
