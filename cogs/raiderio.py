import discord
from discord import app_commands
from discord.ext import commands
import requests
from typing import Literal

# define the class
class RaiderIO(commands.Cog, name="RaiderIO"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # on_ready()
    ####################################################################

    #@commands.Cog.listener()
    #async def on_ready(self):



    ####################################################################
    # trigger: /rio
    # ----
    # Container command for rio related things
    ####################################################################
    group = app_commands.Group(name="rio", description="test")

    ####################################################################
    # trigger: /rio player
    # ----
    # Provides information about a player via raider.io api.
    ####################################################################
    @group.command(name="player", description="Provides information about a player via raider.io")
    async def rio_player(
        self,
        interaction: discord.Interaction,
        region: Literal['us', 'eu', 'kr', 'tw'],
        realm: Literal[
            'aegwynn', 'aerie peak', 'antonidas', 'archimonde', 'area 52', 'argent dawn', 'arthas', 'azralon',
            'barthilas', 'dalaran', 'darkspear', 'drakkari', 'earthen ring', 'emerald dream', 'illidan',
            'kelthuzad', 'stormrage'
        ],
        player: str
    ):
        try:
            # fetch mythic+ data using the raider.io api
            url = f'https://raider.io/api/v1/characters/profile?region={region}&realm={realm}&name={player}&fields=mythic_plus_scores_by_season%3Acurrent%2Cmythic_plus_best_runs%2Craid_progression'
            headers = {'User-Agent': 'Hathor'}
            response = requests.get(url, headers=headers)
            data = response.json()

            # basic player information
            output = discord.Embed(title="Player Lookup")
            output.set_thumbnail(url=data['thumbnail_url'])
            output.add_field(name=f"{data['name']} - {data['realm']}", value=f"{data['race']} {data['active_spec_name']} {data['class']}", inline=False)

            # achievement points
            output.add_field(name="Achievement Points", value=f"{data['achievement_points']}")

            # raid progression
            raid_progression_fields = []
            for key, value in data['raid_progression'].items():
                formatted_key = format_key(key)
                summary = value['summary']
                raid_progression_fields.append(f"{formatted_key}: {summary}")
            output.add_field(name="Raid Progress", value='\n'.join(raid_progression_fields), inline=False)

            # shorten these since the array names are long egg
            score_all = data['mythic_plus_scores_by_season'][0]['scores']['all']
            score_dps = data['mythic_plus_scores_by_season'][0]['scores']['dps']
            score_heal = data['mythic_plus_scores_by_season'][0]['scores']['healer']
            score_tank = data['mythic_plus_scores_by_season'][0]['scores']['tank']

            # mythic+ best runs (sorted by name)
            score_bestruns = ""
            for run in sorted(data['mythic_plus_best_runs'], key=lambda run: run['short_name']):
                short_name = run['dungeon']
                mythic_level = run['mythic_level']
                score_bestruns += f"{short_name}+{mythic_level}\n"

            # mythic+ progression
            output.add_field(name=f"M+ Score: {score_all}", value=f"{self.bot.get_emoji(1142626648571773018)} {score_tank} {self.bot.get_emoji(1142626695678013551)} {score_dps} {self.bot.get_emoji(1142626743161725071)} {score_heal}", inline=False)
            output.add_field(name="M+ Best Runs", value=score_bestruns, inline=False)

            await interaction.response.send_message(embed=output, allowed_mentions=discord.AllowedMentions.none())

        except Exception as e:
            await interaction.response.send_message('raider.io api error. 😢')

    ####################################################################
    # trigger: /rio affix
    # ----
    # Provides weekly affixes via raider.io api.
    ####################################################################
    @group.command(name="affix", description="Provides weekly affixes.")
    async def rio_player(self, interaction: discord.Interaction):
        try:
            # fetch mythic+ data using the raider.io api
            url = 'https://raider.io/api/v1/mythic-plus/affixes?region=us&locale=en'
            headers = {'User-Agent': 'Hathor'}
            response = requests.get(url, headers=headers)
            data = response.json()

            output = discord.Embed(title="Weekly Affixes")

            for affix in data['affix_details']:
                output.add_field(name=f"{affix['name']}", value=f"{affix['description']}")

            await interaction.response.send_message(embed=output)

        except Exception as e:
            await interaction.response.send_message('raider.io api error. 😢')

####################################################################
# function: format_key
# ----
# key: string to be pretty
# ----
# Makes a string pretty.
####################################################################
def format_key(key):
    parts = key.split('-')
    return ' '.join(part.capitalize() for part in parts)