import logging
import discord
import asyncio
import copy
from os import linesep
from conf import config
from .base_cog import BaseCog
from collections import deque

log = logging.getLogger(__name__)

class MessageCacheItem:
    """An item in the message cache.
    
    The message cache associates each message posted in a bridge channel with several webhook messages that were posted in order to forward this to other channels.
    Note that multiple webhook messages might be posted per bridged channel, so the number of webhook messages is larger or equal to the number of bridged channels (minus the one the message was originally posted in).

    We only store message ids instead of message objects to save memory and to catch errors with deleted messages.
    """

    def __init__(self, message_id: int, channel_id: int):
        self.message_id = message_id
        self.channel_id = channel_id # This is needed since we have to find the original message (to get its author) by its id for replies, which is only possible with the channel it was posted in. Also, we need to restrict mentions to that channel.

        # These are per bridged channel.
        # Every bridged channel gets a list of webhook message ids.
        # Note that we also keep the channel id for each message to know which webhook to delete or edit each message with.
        self.webhook_message_ids = []

    def find_message_for_reply(self, webhook_message_id):
        """Check if this message is the one the user is replying to."""

        # Test content messages first:
        if webhook_message_id in [x[0] for x in self.webhook_message_ids]:
            return True
        return False

    def find_message(self, message_id):
        return self.message_id == message_id


class ServerBridge(BaseCog):
    """A cog for forwarding messages between servers. Multiple servers can be involved in a bridge, but every server can only have one channel per bridge. You can, however, have multiple bridges per server."""

    def __init__(self, bot):
        BaseCog.__init__(self, bot)
        self.bot = bot
        self.bot.info_text += 'Server bridge:' + linesep + '  The bridge feature allows forwarding messages between multiple servers. Every server can have one or more channels per bridge, and a server can have multiple bridges. Please contact the bot admin to set up a server bridge.' + linesep + linesep

        self.inconsistency_text = '**[BRIDGE]** Some recent messages may not have been forwarded during bot downtime.'

        # First, split by spaces between bridges.
        all_bridges = config.get('ServerBridge', 'bridges', fallback='').split()

        # Now build a list of lists, each nested list containing IDs of linked channels.
        self.bridges = [[int(element) for element in bridge.split(',')] for bridge in all_bridges]

        self.bot_id = int(config.get('ServerBridge', 'bot_id', fallback='0'))

        self.cache_size_per_bridge = int(config.get('ServerBridge', 'cache_size_per_bridge', fallback='100'))

        # This will be filled with (channel id, (webhook, bridge index)) pairs.
        self.webhooks = {}

        # This is a runtime cache that associates messages sent by users with webhook messages of the forwarded post.
        # This is needed to be able to edit, delete or reply to webhook messages to mirror user actions.
        # I considered a dictionary from webhook message Id to message Ids, but we would have to keep an additional timestamp and purge the table periodically via a timed task. This seems a little complex for such an easy problem. Therefore, a double-ended queue is used to solve the timestamping problem "naturally" since older messages will be removed first from the deque once it is full. This makes finding messages O(n*m) in the reply case, and O(n) in the edit/delete case. This is not optimal, but we usually limit these deques to 100 elements per bridge, which should be reasonably few to iterate a linked list (and a regular one of <10 elements within). I reckon the message fetch is much more likely to be a bottleneck in practice (though I haven't done any measurements). By appending to the left, can find recent elements more quickly.
        self.message_cache = []


    async def on_ready(self):
        """Called by bot client's on_ready()."""

        try:
            print('=== BEGIN SERVER BRIDGE ===')
            print('Bot id: ' + str(self.bot_id))

            # If any of these cannot be retrieved or created (e.g. because missing permissions), the bridge will be ignored.
            for bridge_index, bridge in enumerate(self.bridges):
                self.message_cache.append(None)
                bridge_str = 'Bridge ' + str(bridge_index) + ': '
                channel = None
                loc_webhooks = []
                consistency_check_messages = []
                try:
                    for channel_id in bridge:
                        channel = self.bot.get_channel(channel_id)

                        found = False
                        for webhook in await channel.webhooks():
                            if webhook.name == '_bridge':
                                loc_webhooks.append((channel_id, webhook))
                                found = True
                                print('Found existing webhook for channel: ' + channel.name)
                                break
                        if not found:
                            webhook = await channel.create_webhook(name='_bridge')
                            loc_webhooks.append((channel_id, webhook))
                            print('Create new webhook for channel: ' + channel.name)
                        bridge_str += str(channel.name) + ', '

                        # Do a consistency check on all channels in this bridge. For this purpose, we collect the last messages from each channel and test for intersection later
                        try:
                            async for message in channel.history(limit=1):
                                consistency_check_messages.append(message.content)
                                break
                        except Exception as e:
                            log.exception(e)
                            await self.bot.log_channel.send('**[ERROR]** Error during startup consistency check of bridge ' + str(bridge_index) + '! ' + config.additional_error_message)
                except discord.Forbidden as e:
                    print('Missing manage webhooks permission on channel ' + str(channel.name))
                    await self.bot.log_channel.send('**[ERROR]** Missing manage webhooks permission on channel ' + str(channel.name) + '. ' + config.additional_error_message)
                except Exception as e:
                    log.exception(e)
                    print('Encountered error during bridge startup on bridge ' + str(bridge_index) + '. Check logs')
                    await self.bot.log_channel.send('**[ERROR]** Encountered error during bridge startup on bridge ' + str(bridge_index) + '. Check logs. ' + config.additional_error_message)
                else:
                    if len(loc_webhooks) == len(bridge):
                        # Successfully validated this bridge: Every channel has a webhook that exists in our dictionary.
                        for channel_id, webhook in loc_webhooks:
                            self.webhooks[channel_id] = (webhook, bridge_index)
                        if bridge_str:
                            bridge_str = bridge_str[:-2]
                        self.message_cache[bridge_index] = deque(maxlen=self.cache_size_per_bridge)
                    else:
                        print('Invalid bridge has ' + str(len(bridge)) + ' channels, but ' + str(len(loc_webhooks)) + ' webhooks. ')
                        await self.bot.log_channel.send('**[ERROR]** Invalid bridge has ' + str(len(bridge)) + ' channels, but ' + str(len(loc_webhooks)) + ' webhooks. ' + config.additional_error_message)

                    print(bridge_str)

                    # For the consistency check, we are looking for a single message that is contained within all others.
                    # We cannot check for equality since bridges messages will generally be supersets of the original ones,
                    # but finding one will account for all cases including empty messages as well as ones posted by the bot.
                    # NOTE: There are some false negatives for the detection such as if multiple messages have been posted in different channels when the bot was down that happen to be subsets of one another.
                    # NOTE: There are also false positives, so this could be improved; this mostly happens with split messages
                    print('Consistency startup check: ' + str(bridge_index))
                    fully_forwarded = False
                    if len(consistency_check_messages) == 0:
                        fully_forwarded = True
                    else:
                        for message_a in consistency_check_messages:
                            not_fully_forwarded = False
                            for message_b in consistency_check_messages:
                                if not message_b.startswith(message_a):
                                    not_fully_forwarded = True
                                    break
                            if not not_fully_forwarded:
                                fully_forwarded = True
                                break

                    if not fully_forwarded:
                        print('Consistency startup check found missing messages on bridge ' + str(bridge_index) + '!')
                        for channel_id in bridge:
                            channel = self.bot.get_channel(channel_id)
                            await channel.send(self.inconsistency_text)

            if len(self.message_cache) != len(self.bridges):
                raise ValueError('Message cache has len ' + str(len(self.message_cache)) + ' elements, while there are ' + str(len(self.bridges)) + ' bridges.')

            print('=== END SERVER BRIDGE ===')
        except Exception as e:
            print('Failed to initialize bridges. Check logs')
            await self.bot.log_channel.send('**[ERROR]** Failed to initialize bridges. Check logs. ' + config.additional_error_message)
            log.fatal(e)
            self.webhooks = {} # Make sure we never attempt to do anything


    async def on_message(self, message):
        """React to messages. Called by bot client."""

        # NOTE: exceptions are caught by calling function

        if message.type != discord.MessageType.default:
            # Ignore system messages
            return

        if int(message.author.id) != int(self.bot_id) or self.inconsistency_text not in message.content:
            webhook_entry = self.webhooks.get(message.channel.id)
            if webhook_entry:
                # Make sure this is not one of our connected webhooks posting (else we'd endlessly ping-pong the same message)
                if message.webhook_id:
                    for channel_id, (webhook, bridge_index) in self.webhooks.items():
                        if message.webhook_id == webhook.id:
                            return

                # This channel is bridged, so we broadcast the message to all linked channels
                try:
                    await self.broadcast_message(message, webhook_entry[1])
                except Exception as e:
                    log.exception(e)
                    await self.bot.log_channel.send('**[ERROR]** A critical error occurred while broadcasting a message on server bridge (top level). Check logs. ' + config.additional_error_message)


    async def pin_or_unpin_message(self, message_id, channel_id, original_message):
        """Pin or unpin a message in a specific channel."""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                raise ValueError('Failed to find channel with id ' + str(channel_id))

            message = await channel.fetch_message(message_id)
            if not message:
                raise ValueError('Failed to find webhook message with id ' + str(message_id))

            if original_message.pinned and not message.pinned:
                await message.pin()
            elif not original_message.pinned and message.pinned:
                await message.unpin()
        except Exception as e:
            log.exception(e)
            await self.bot.log_channel.send('**[ERROR]** Critical error trying to pin/unpin message in channel ' + str(channel_id) + ' ' + config.additional_error_message)


    async def handle_changed_pin_status(self, message, bridge_index):
        """Pin or unpin a message in all channels of a server bridge."""

        # NOTE: top-level exceptions are caught by calling function

        for i, cached_message in enumerate(self.message_cache[bridge_index]):
            if cached_message.find_message(message.id) or cached_message.find_message_for_reply(message.id):
                index = i

                # Found message in our cache, now pin/unpin all webhook messages associated with this:
                for (webhook_message_id, channel_id) in cached_message.webhook_message_ids:
                    await self.pin_or_unpin_message(webhook_message_id, channel_id, message)

                # Also try to pin or unpin the message itself it the pin/unpin was done on a webhook message:
                await self.pin_or_unpin_message(cached_message.message_id, cached_message.channel_id, message)

                # Found and handled the message, we are done
                break

    async def broadcast_message(self, message, bridge_index):
        """Broadcast a message to all subscribers in a server bridge."""

        bridge = self.bridges[bridge_index]
        
        # NOTE: exceptions are caught by calling function
        wait = True
        tts = False
        file = None
        files = None
        embed = None
        embeds = []

        allowed_mentions = discord.AllowedMentions(everyone=False, users=True, roles=False, replied_user=False)

        # Images are just pasted after the message contents to show up via discord's built-in expansion
        # NOTE: gen_text is actually abused by fallback error messages and reply mentions as well
        gen_text = ''

        # =====
        # NOTE: Since pinging replies are disabled, these should stay None throughout this function!
        reference_author_mention = None
        channel_with_mention = None # If we should ping a user in a channel, this will be set to the channel id
        # =====

        # NOTE: We build the reply embed before collecting attachments since we might add the @<author> bit towards the end of the message contents, so the quote has to come first if it exists
        reference_author = await self.get_reference_author_with_reply_embeds(message, embeds, reference_author_mention, channel_with_mention)

        embeds.extend(message.embeds)

        # Assemble a list of URLs and embeds to represent images and other attachments
        gen_text += await self.collect_attachments(message, embeds)

        message_cache_item = MessageCacheItem(message.id, message.channel.id)

        # Broadcast the message.
        for channel_id in bridge:
            try:
                # This is the channel the message was posted in, skip
                if channel_id == message.channel.id:
                    continue

                # Replies prepend the original author's name similar to Matrix bridge
                # The only time we want to include an actual mention is when a user replies to the bot (indicated by reference_author_mention being something other than None) - NOTE: This behavior is currently DISABLED!
                if message.reference and message.reference.message_id:
                    gen_text_with_reference = copy.copy(gen_text)

                    if not channel_with_mention or channel_with_mention != channel_id:
                        gen_text_with_reference += '\n(@' + reference_author + ')\n'
                    elif reference_author_mention:
                        gen_text_with_reference += '\n(' + reference_author_mention + ')\n'
                    else:
                        gen_text_with_reference += '\n(@<unknown user>)\n'
                else:
                    gen_text_with_reference = gen_text

                channel_webhook = self.webhooks.get(channel_id)[0]
                await self.send_with_webhook(channel_webhook, wait, message.author.display_name, message.author.avatar_url, tts, file, files, embed, embeds, allowed_mentions, gen_text_with_reference, message, message_cache_item)
            except Exception as e:
                log.exception(e)
                await self.bot.log_channel.send('**[ERROR]** A critical error occurred while forwarding a message on server bridge (low level) to channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
            # Now keep trying to send this message to the other channels if any remain

        try:
            # Record any messages that we were able to send. Even if any of the above calls threw, we still want to be able to work with other messages that were sent successfully so those can be deleted, edited or replied to
            if message_cache_item.webhook_message_ids:
                self.message_cache[bridge_index].appendleft(message_cache_item)
                # Debug code:
                #print('================== POST SEND ' + str(bridge_index))
                #for mci in self.message_cache[bridge_index]:
                #    print(str(mci.message_id) + ', ' + str(mci.channel_id) + ', ' + str(mci.webhook_message_ids))
        except Exception as e:
            log.exception(e)
            await self.bot.log_channel.send('**[ERROR]** Failed to cache message ' + str(message.id) + ' in channel ' + str(message.channel.name) + ' ' + config.additional_error_message)


    async def get_reference_author_with_reply_embeds(self, message, embeds, reference_author_mention, channel_with_mention):
        """Handle message replies by building an embed that contains the original author, their avatar, the message contents (up to a character limit) and a timestamp when the original message was sent. Returns a string containing the author of the reference message."""

        reference_author = '<unknown user>'
        if message.reference and message.reference.message_id:
            quoted_content = ''
            avatar_url = None
            created_at = None

            try:
                reference_message = message.reference.cached_message
                if not reference_message:
                    reference_message = await message.channel.fetch_message(message.reference.message_id)

                if reference_message:
                    # User is replying to a forwarded message, hence we should ping the actual author of the original one (but only in the respective channel...)
                    # NOTE: There seems to be no way to know if the reply was a "pinging" one or not and we should respect that property, so this code is disabled!
                    #if reference_message.webhook_id is not None:
                        #try:
                            ## Try to find the cached message so that we know who posted the original one and where
                            #for cached_message in self.message_cache[bridge_index]:
                                #if cached_message.find_message_for_reply(reference_message.id):
                                    #original_channel = self.bot.get_channel(cached_message.channel_id)
                                    #if original_channel:
                                        #original_message = await original_channel.fetch_message(cached_message.message_id)
                                        #if original_message:
                                            ## NOTE: This doesn't work, so we can't actually ping.
                                            ## Only ping this user if the reply was set to ping
                                            #if original_message.author in message.mentions:
                                                #reference_author_mention = original_message.author.mention
                                                #channel_with_mention = original_channel.id
                                    #break
                        #except Exception as e:
                            #log.exception(e)
                            #await self.bot.log_channel.send('**[WARNING]** Failed to mention author on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
                            ## NOTE: reference_author_mention is now None, so we use the default one that doesn't ping

                    if reference_message.author.display_name:
                        reference_author = reference_message.author.display_name
                    if reference_message.author.avatar_url:
                        avatar_url = reference_message.author.avatar_url
                    created_at = reference_message.created_at
                    if reference_message.content:
                        chunk_size = 256 # This is not the actual character limit for embed descriptions, but we don't want the reply to become too bloated

                        # Use clean content to avoid mentions in the original message tagging people on replies
                        if len(reference_message.content) <= chunk_size:
                            quoted_content = reference_message.clean_content
                        else:
                            quoted_content = reference_message.clean_content[:chunk_size - 3] + '...'
            except discord.errors.NotFound as e:
                quoted_content = '_<This message was deleted>_'
            except Exception as e:
                log.exception(e)
                await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to collect info for reply embed on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
                quoted_content = '_<The message referenced by this reply could not be forwarded due to an internal error>_'
            finally:
                try:
                    quote_embed = discord.Embed()
                    if avatar_url:
                        quote_embed.set_author(name=reference_author, icon_url=avatar_url)
                    else:
                        quote_embed.set_author(name=reference_author)
                    quote_embed.description = quoted_content
                    if created_at:
                        quote_embed.timestamp = created_at
                    embeds.append(quote_embed)
                except Exception as e:
                    log.exception(e)
                    await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to build reply embed on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)

        return reference_author

    async def collect_attachments(self, message, embeds):
        """Utility function re-used by edits. Returns generated text containing links to append to the message when being forwarded. _embeds_ is also an OUTPUT."""

        auto_generated = ''
        gen_text = ''

        # Collect lists of attachment URLs
        try:
            if message.attachments:
                for attachment in message.attachments:
                    # Images can be embedded by discord
                    if attachment.content_type and attachment.content_type.startswith('image'):
                        gen_text += attachment.url + '\n'
                    # Other attachments go in a separate list of URLs to place inside an embed
                    else:
                        auto_generated += attachment.url + '\n'
        except Exception as e:
            log.exception(e)
            await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to build list of attachment URLs on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
            try:
                error_embed = discord.Embed()
                error_embed.description = '_<The original message contains attachments that could not be forwarded due to an internal error>_'
                embeds.append(error_embed)
            except Exception as e:
                log.exception(e)
                await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to build attachment error embed on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
                gen_text += '_<The original message contains attachments that could not be forwarded due to an internal error>_\n'

        # Build the URL embeds
        try:
            if auto_generated:

                # This must not exceed the maximum amount of characters in an embed field
                chunk_size = 1024
                if len(auto_generated) <= chunk_size:
                    attachments_embed = discord.Embed()
                    attachments_embed.add_field(name='Attachments (auto-generated):', value=auto_generated, inline=True)
                    embeds.append(attachments_embed)
                else:
                    # Too large, has to be split
                    increment = chunk_size
                    i = 0
                    j = 0
                    while i < len(auto_generated):
                        attachments_embed = discord.Embed()
                        chunk = auto_generated[i:i+increment]
                        newline = chunk.rfind('\n')
                        if newline == -1:
                            # This attachment has an url that's longer than the maximum size of an embed field.
                            # We don't know where the next url starts so just abort and tell everyone that the rest of the attachments is missing
                            attachments_embed.add_field(name='Attachments (auto-generated, pt. ' + str(j+1) + '):', value='<missing some attachments due to an internal error>', inline=True)
                            embeds.append(attachments_embed)
                            await self.bot.log_channel.send('**[WARNING]** Attachment URL is longer than maximum size of an embed field! ' + str(message.channel.name) + ' ' + config.additional_error_message)
                            break
                        if newline < i+chunk_size-1:
                            # We are trying to split in the middle of an url, don't do that
                            chunk = auto_generated[i:i+newline]
                            increment = newline + 1
                        else:
                            increment = chunk_size
                        i += increment
                        j += 1

                        # If this goes beyond discord's 25 fields limit, we throw an error and the message is not forwarded;
                        # let's keep in mind that discord (at the time of this writing) only supports 10 attachments per message, so this should never happen.
                        attachments_embed.add_field(name='Attachments (auto-generated, pt. ' + str(j) + '):', value=chunk, inline=True)
                        embeds.append(attachments_embed)
        except Exception as e:
            log.exception(e)
            await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to build attachment list embed on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
            try:
                error_embed = discord.Embed()
                error_embed.description = '_<The original message contains attachments that could not be forwarded due to an internal error>_'
                embeds.append(error_embed)
            except Exception as e:
                log.exception(e)
                await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to build attachment error embed (non-image) on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
                gen_text += '_<The original message contains attachments that could not be forwarded due to an internal error>_\n'

        # Discord has a hard limit of 10 embeds per message
        max_embeds = 10
        if len(embeds) > max_embeds:
            await self.bot.log_channel.send('**[WARNING]** Someone sent a message that resulted in more than ' + str(max_embeds) + ' embeds! ' + str(message.channel.name) + ' ' + config.additional_error_message)
            try:
                #embeds = embeds[:max_embeds-1] # NOTE: This ceased to work when I moved this whole logic into a function, see alternative below:
                while len(embeds) > max_embeds:
                    embeds.pop()
                # Erase another one to get space for the error embed
                if len(embeds) > 0:
                    embeds.pop()
                error_embed = discord.Embed()
                error_embed.description = '_<Warning: This message is incomplete due to an internal error>_'
                embeds.append(error_embed)
            except Exception as e:
                log.exception(e)
                await self.bot.log_channel.send('**[ERROR]** A critical error occurred while trying to cut down embeds to max length on channel ' + str(message.channel.name) + '. Check logs. ' + config.additional_error_message)
                gen_text += '_<Warning: This message is incomplete due to an internal error>_\n'

        return gen_text


    async def send_with_webhook(self, webhook, wait, username, avatar_url, tts, file, files, embed, embeds, allowed_mentions, gen_text, message, message_cache_item):
        """Forward a message using a webhook."""

        out_messages = []
        posted_anything = False

        try:
            await self.split_message(embeds, gen_text, message, out_messages)

            if out_messages:
                if len(out_messages) > 1:
                    for msg in out_messages[:-1]:
                        await self.send_with_webhook_internal(webhook=webhook, content=msg, wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=None, files=None, embed=None, embeds=None, allowed_mentions=allowed_mentions, sent_webhook_messages=message_cache_item.webhook_message_ids, message=message)
                        posted_anything = True

                # Last message carries the embeds
                await self.send_with_webhook_internal(webhook=webhook, content=out_messages[-1], wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=file, files=files, embed=embed, embeds=embeds, allowed_mentions=allowed_mentions, sent_webhook_messages=message_cache_item.webhook_message_ids, message=message)
                posted_anything = True # Not strictly necessary, but probably good practice
            elif embeds:
                await self.send_with_webhook_internal(webhook=webhook, content=message.clean_content, wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=file, files=files, embed=embed, embeds=embeds, allowed_mentions=allowed_mentions, sent_webhook_messages=message_cache_item.webhook_message_ids, message=message)
                posted_anything = True # Not strictly necessary, but probably good practice
            else:
                raise ValueError('No messages and embeds to send after splitting!')

        # Catch exceptions here to let people know that the message was incomplete; if this fails (i.e. throws), we still get the log
        except Exception as e:
            log.exception(e)
            await self.bot.log_channel.send('**[ERROR]** Critical error occurred while posting messages! ' + str(message.channel.name) + ' ' + config.additional_error_message)
            error_embed = discord.Embed()
            error_embed.description = '_<The original message contains some content that could not be forwarded due to an internal error>_'
            # If we sent nothing due to an exception, we should still send the original content together with the error embed so that at least the message itself is forwarded.
            except_message_content = message.clean_content if not posted_anything else ''
            await self.send_with_webhook_internal(webhook=webhook, content=except_message_content, wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=None, files=None, embed=error_embed, embeds=None, allowed_mentions=allowed_mentions, sent_webhook_messages=message_cache_item.webhook_message_ids, message=message)


    async def split_message(self, embeds, gen_text, message, out_messages):
        """Split a message in case it has too many characters."""

        # NOTE: exceptions are caught by calling function

        chunk_size = 2000
        final_content = message.clean_content + '\n' + gen_text

        if len(final_content) <= chunk_size:
            # No splitting required, this message will be sent with all the embeds
            out_messages.append(final_content)
        else:
            # Too large, has to be split
            increment = chunk_size
            i = 0
            while i < len(final_content):
                chunk = final_content[i:i+increment]
                newline = chunk.rfind('\n')
                if newline == -1 or newline >= i+chunk_size-1:
                    # len(final_content) - 1 = x + i
                    increment = min(chunk_size, len(final_content) - 1 - i)
                else:
                    # We are trying to split in the middle of an url, don't do that
                    chunk = final_content[i:i+newline]
                    increment = newline + 1
                i += increment
                if chunk:
                    out_messages.append(chunk)


    async def send_with_webhook_internal(self, webhook, content, wait, username, avatar_url, tts, file, files, embed, embeds, allowed_mentions, sent_webhook_messages, message):
        """Sends a message with a webhook. No splicing of content to handle oversized messages."""

        try:
            webhook_message = await webhook.send(content=content, wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=file, files=files, embed=embed, embeds=embeds, allowed_mentions=allowed_mentions)
        except discord.errors.HTTPException as e:
            # Discord has a hard limit of 6000 characters across all embeds (including title, description, ...)
            if 'Invalid Form Body' in str(e):
                log.exception(e)
                await self.bot.log_channel.send('**[WARNING]** Someone sent a message that resulted in a 400 invalid form body! ' + str(message.channel.name) + ' ' + config.additional_error_message)

                # If this message had embeds, try sending without them but post an error (since this is likely due to the 6000 character across all embeds limit)
                if len(embeds) > 0 or embed:
                    error_embed = discord.Embed()
                    error_embed.description = '_<The original message contains some additional non-text elements that could not be forwarded due to an internal error>_'
                    try:
                        webhook_message = await webhook.send(content=content, wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=file, files=files, embed=error_embed, embeds=None, allowed_mentions=allowed_mentions)
                    except Exception as e:
                        log.exception(e)
                        await self.bot.log_channel.send('**[ERROR]** Critical error occurred while trying to send invalid form body error message! ' + str(message.channel.name) + ' ' + config.additional_error_message)
                        # Tough luck, try without any embeds
                        webhook_message = await webhook.send(content=content, wait=wait, username=username, avatar_url=avatar_url, tts=tts, file=file, files=files, embed=None, embeds=None, allowed_mentions=allowed_mentions)
            else:
                raise e

        # Not sure if this can actually happen
        if not webhook_message:
            await self.bot.log_channel.send('**[ERROR]** Sent message via webhook without exception, but the message is NONE! ' + str(message.channel.name) + ' ' + config.additional_error_message)
        else:
            sent_webhook_messages.append((webhook_message.id, webhook_message.channel.id))


    async def on_message_edit(self, before, after):
        """React to edited messages. Called by bot client."""

        # NOTE: exceptions are caught by calling function
        if int(after.author.id) != int(self.bot_id):
            webhook_entry = self.webhooks.get(after.channel.id)
            if webhook_entry:
                author_name = str(after.author.display_name)
                if not author_name:
                    await self.bot.log_channel.send('**[ERROR]** Unknown author, rejecting edit on message in ' + str(after.channel.name) + ' ' + config.additional_error_message)
                    return

                bridge_index = webhook_entry[1]

                # This is a pin/unpin event, handle only this aspect of it
                if before.pinned != after.pinned:
                    try:
                        await self.handle_changed_pin_status(after, bridge_index)
                    except Exception as e:
                        log.exception(e)
                        await self.bot.log_channel.send('**[ERROR]** Failed to pin/unpin message in channel ' + str(after.channel.name) + ' ' + config.additional_error_message)

                    return

                # Make sure this is not one of our connected webhooks editing
                if after.webhook_id:
                    for channel_id, (webhook, bridge_index) in self.webhooks.items():
                        if after.webhook_id == webhook.id:
                            return

                gen_text = ''
                embeds = []

                # =====
                # NOTE: Since pinging replies are disabled, these should stay None throughout this function!
                reference_author_mention = None
                channel_with_mention = None # If we should ping a user in a channel, this will be set to the channel id
                # =====

                # NOTE: We build the reply embed before collecting attachments since we might add the @<author> bit towards the end of the message contents, so the quote has to come first if it exists
                reference_author = await self.get_reference_author_with_reply_embeds(after, embeds, reference_author_mention, channel_with_mention)

                embeds.extend(after.embeds)
                gen_text += await self.collect_attachments(after, embeds)

                # Try to find the cached message so that we know which webhook messages we need to edit
                for cached_message in self.message_cache[bridge_index]:
                    if cached_message.find_message(after.id):
                        out_messages = []

                        # Replies prepend the original author's name similar to Matrix bridge
                        # The only time we want to include an actual mention is when a user replies to the bot (indicated by reference_author_mention being something other than None) - NOTE: This behavior is currently DISABLED! TODO: If there is ever a way to find out if a reply is pinging or not, this needs to be adjusted to work like the code in broadcast_message!
                        if after.reference and after.reference.message_id:
                            gen_text += '\n(@' + reference_author + ')\n'

                        # Found this message in the cache, so we know we can edit its counterparts.
                        await self.split_message(embeds, gen_text, after, out_messages)

                        if not out_messages:
                            await self.bot.log_channel.send('**[ERROR]** Message edited by ' + author_name + ' on channel ' + str(after.channel.name) + ' is empty, rejecting. ' + config.additional_error_message)
                            return

                        allowed_mentions = discord.AllowedMentions(everyone=False, users=True, roles=False, replied_user=False)

                        # Go through all channels in this bridge, collect all messages posted in each respective channel, and try to fill them with the new content
                        for channel_id in self.bridges[bridge_index]:
                            if channel_id == after.channel.id:
                                continue

                            try:
                                message_list = [y[0] for y in list(filter(lambda x: (x[1] == channel_id), cached_message.webhook_message_ids))]

                                if not message_list:
                                    await self.bot.log_channel.send('**[ERROR]** Message edited by ' + author_name + ' on channel ' + str(after.channel.name) + ' found no messages, rejecting. ' + config.additional_error_message)
                                    continue

                                channel_webhook = self.webhooks.get(channel_id)[0]

                                if len(out_messages) != len(message_list):
                                    await self.bot.log_channel.send('**[WARNING]** Message edited by ' + author_name + ' on channel ' + str(after.channel.name) + ' has ' + str(len(out_messages)) + ' to edit but ' + str(len(message_list)) + ' messages available. ' + config.additional_error_message)

                                if len(out_messages) > len(message_list):
                                    # We cannot insert new messages into the timeline in hindsight and if we just went with the message content we would lose some attachments.
                                    # Therefore, we send an error embed to notify the user.
                                    await self.bot.log_channel.send('**[ERROR]** Edit by ' + author_name + ' resulted in more messages than before! ' + str(after.channel.name) + ' ' + config.additional_error_message)

                                    # Embed array needs to be copied so that the error embed is not duplicated for other channels.
                                    embeds_copy = copy.copy(embeds)
                                    error_embed = discord.Embed()
                                    error_embed.description = '_<This message was edited and now exceeds the character limit. Please ask the original author to resend the text contents.>_'
                                    embeds_copy.append(error_embed)

                                    for index, webhook_message_id in enumerate(message_list[:-1]):
                                        # We have more messages to send than messages to edit, so this needs to be checked
                                        if index < len(out_messages):
                                            updated_content = out_messages[index]

                                            # Try to edit these but don't throw so that we can try getting the embeds through with the last message
                                            try:
                                                await channel_webhook.edit_message(webhook_message_id, content=updated_content, allowed_mentions=allowed_mentions)
                                            finally:
                                                pass

                                    updated_content = out_messages[len(message_list)-1] # Last message that we can send...
                                    webhook_message_id = message_list[-1] # Last webhook message we can use to edit in content

                                    # Last message carries the embeds.
                                    await channel_webhook.edit_message(webhook_message_id, content=updated_content, embeds=embeds_copy, allowed_mentions=allowed_mentions)
                                else:
                                    # Check if we need to delete any obsolete messages (text shrinked due to edit)
                                    message_index = len(message_list) - 1

                                    while len(out_messages) < len(message_list):
                                        webhook_message_id = None
                                        try:
                                            webhook_message_id = message_list.pop()
                                            cached_message.webhook_message_ids = [x for x in cached_message.webhook_message_ids if x[0] != webhook_message_id]
                                            await channel_webhook.delete_message(webhook_message_id)
                                        except Exception as e:
                                            log.exception(e)
                                            await self.bot.log_channel.send('**[ERROR]** Failed to delete message edited by ' + author_name + ' in channel ' + str(after.channel.name) + ' ' + config.additional_error_message)
                                            if webhook_message_id:
                                                error_embed = discord.Embed()
                                                error_embed.description = '_<This message was edited out but could not be deleted.>_'
                                                await channel_webhook.edit_message(webhook_message_id, content='', allowed_mentions=allowed_mentions, embed=error_embed)
                                                # If anything here threw, we don't continue editing since we have too many messages

                                    if len(out_messages) > 1:
                                        for index, webhook_message_id in enumerate(message_list[:-1]):
                                            # We might have more messages to send than messages to edit, so this needs to be checked
                                            if index < len(out_messages):
                                                updated_content = out_messages[index]
                                                await channel_webhook.edit_message(webhook_message_id, content=updated_content, allowed_mentions=allowed_mentions)

                                    # Last message carries the embeds
                                    updated_content = out_messages[-1]
                                    webhook_message_id = message_list[-1]
                                    await channel_webhook.edit_message(webhook_message_id, content=updated_content, embeds=embeds, allowed_mentions=allowed_mentions)

                            except Exception as e:
                                log.exception(e)
                                await self.bot.log_channel.send('**[ERROR]** Failed to edit message from channel ' + str(after.channel.name) + ' (author: ' + author_name + ') in channel ' + str(channel_id) + '. ' + config.additional_error_message)

                        # Debug code:
                        #print('================== POST EDIT ' + str(bridge_index))
                        #for mci in self.message_cache[bridge_index]:
                        #    print(str(mci.message_id) + ', ' + str(mci.channel_id) + ', ' + str(mci.webhook_message_ids))

                        # Found our message, no need to search further
                        break


    async def on_message_delete(self, message):
        """React to deleted messages. Called by bot client."""

        # NOTE: exceptions are caught by calling function
        if int(message.author.id) != int(self.bot_id):
            webhook_entry = self.webhooks.get(message.channel.id)
            if webhook_entry:
                # Make sure this is not one of our connected webhooks deleting
                if message.webhook_id:
                    for channel_id, (webhook, bridge_index) in self.webhooks.items():
                        if message.webhook_id == webhook.id:
                            return

                bridge_index = webhook_entry[1]
                index = -1

                # Try to find the cached message so that we know which webhook messages we need to delete
                for i, cached_message in enumerate(self.message_cache[bridge_index]):
                    if cached_message.find_message(message.id):
                        index = i

                        # This is the one, now delete all webhook messages associated with this:
                        for (webhook_message_id, channel_id) in cached_message.webhook_message_ids:
                            try:
                                channel_webhook = self.webhooks.get(channel_id)[0]
                                await channel_webhook.delete_message(webhook_message_id)
                            except Exception as e:
                                log.exception(e)
                                await self.bot.log_channel.send('**[ERROR]** Critical error trying to delete content webhook message in channel ' + str(channel_id) + ' deleted by ' + str(message.author.display_name) + ' ' + config.additional_error_message)

                try:
                    # O(n) again, but we don't do this too often
                    if index != -1:
                        del self.message_cache[bridge_index][index]
                except Exception as e:
                    # Failed, too bad but not critical
                    log.exception(e)
                    await self.bot.log_channel.send('**[WARNING]** Failed to delete message from cache ' + config.additional_error_message)

                # Debug code:
                #print('================== POST DELETE ' + str(bridge_index))
                #for mci in self.message_cache[bridge_index]:
                #    print(str(mci.message_id) + ', ' + str(mci.channel_id) + ', ' + str(mci.webhook_message_ids))



def setup(bot):
    """ServerBridge cog load."""
    bot.add_cog(ServerBridge(bot))
    log.info("ServerBridge cog loaded")
