# pt-point-exchange
A Discord bot written in Python 3 that is used by the Project Tamriel and Tamriel Rebuilt modding communities.

# About the provice mods
Project Tamriel (https://www.project-tamriel.com/) and Tamriel Rebuilt (https://www.tamriel-rebuilt.org/) are collaborative Elder Scrolls video game mods that aim to create various provinces of the fictional game world "Tamriel" in the game "Morrowind".

# About the name
Originally, this bot introduced an artificial economy to reward users with a (centralized) virtual currency.
These 'points' could in turn be given away to others or they could be gambled with in a variety of fun minigames.
The idea of this currency was to add an incentive to contribute to the projects.
Since then, the bot has grown beyond this initial purpose with a variety of added features. The name stuck, however.

# List of (main) features
### PT Points (economy)
The original purpose of this bot explained in the above section.

### Labels/commands
A feature that allows users on any server that invited the bot to set and subsequently retrieve an arbitrary string given a fitting "label" to display.
I.e. using "!set tr_map <url>" and "!tr_map" will have the bot display the URL that was set.

### Server bridge
The bot can listen to messages posted in specific channels and forward these messages to other channels on multiple servers. This way, users not present on all servers can exchange infos and discuss development without participating in the other project at all (or even join the respective server).
Message forwarding is implemented via Discord webhooks.

Limitations of the server bridge are:
* No reactions
* No editing/deleting messages that are older than the cache_size_per_bridge value set in the bot.ini config file
* No editing/deleting messages that were posted in a different "session", i.e. posted before the bot has been restarted
* No mention on replies
* No threads

### Gambling minigames
Because PT Points themselves have no particular use, a set of minigames was introduced that can be played by anyone on the server. Users "stake" their PT Points for a chance of a higher reward. Example minigames are horseraces and battle royale.

### Holidays
On a (usually fictional) holiday, sends a message in a designated channel with some description of the holiday.

### Northmarker
A utility command that allows modders to find out the right rotation for their northmarker in an interior (given exterior and interior door rotation).

# About the code:
I (Scamp) am not 'actually' a python programmer and mostly self-taught, i.e. I read other people's code and Stack Overflow answers. That said, neither do I know much of the 'pythonic' ways, nor is it guaranteed that the bot executes flawlessly. There are some failsafe mechanisms, but the author(s) can in no way be held reliable for damage or inconveniences of any kind caused by usage of the bot.

I don't know what the python standard naming conventions/best practices are, and hence I do not follow them.

Everyone may feel free to fork the project to fix bugs or to add their own gambling minigames and other features.

# How to install/run:
1. Clone this repository
2. Install dependencies: tinydb, discord.py
3. Fill in your info in bot.ini (an example .ini is included, but not used by default). The important fields are: bot_channel_id, token, main_server and optionally holiday_announcement_channel_id if using the holidays cog. All IDs are long integers you can get by right-clicking a channel or server in discord. You will get your token by creating a discord 'app'. More info on discordapp.com/developers/applications/me.
4. Fill in your log_channel_id - this channel is used *exclusively* to post errors that occur during message processing so that the project maintainer can fix any unexpected bugs.
5. If using the server bridge feature, fill in your bot_id and bridges (bridges are separated by spaces, channels within a bridge separated by commas).
6. Fill in your info in Cogs/data/gambling.json and Cogs/data/holidays.json. Appropriate examples are placed in that directory, but not used by default.
7. List your admins roles in bot.ini (using role IDs) as well as your subscriber role (by name) in the [Gambling] section if using the gambling cog. Admins roles should be separated by commas.
8. Run 'python3 .' in the root directory.

# Asserts:
- Stats cog must be loaded last
- Timed Events cog must be loaded first
- Holidays cog must be loaded before gambling minigames

# Known issues:
- !trivia and !season outputs sometimes miss empty lines between cog outputs depending on the current database state and/or amount of loaded cogs
- If the bot is dead while it should be executing a timed task, the timed task will not be executed at all that day. Workaround: run a cronjob to restart the bot five minutes before the timed tasks are run.
