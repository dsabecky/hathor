import discord
from discord import app_commands
from discord.ext import commands
import requests
import math
from typing import Literal
from urllib.parse import urlparse

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
    # trigger: /rio score
    # ----
    # Gathers keys to obtain score!
    ####################################################################
    @group.command(name="score", description="Gathers keys to obtain score!")
    async def rio_score(self, interaction: discord.Interaction, url: str):
        parsed_url = urlparse(url)

        if '/' not in url:
            await interaction.response.send_message('input error :(')
            return

        region = parsed_url.path.split('/')[2]
        realm = parsed_url.path.split('/')[3]
        character = parsed_url.path.split('/')[4]

        if not character:
            await interaction.response.send_message('input error :(')
            return
        
        key_table = {
            'AD' : { 'name': "Atal'Dazar", 'level': { 9: 0, 10: 0 } },
            'BRH' : { 'name': 'Black Rook Hold', 'level': { 9: 0, 10: 0 } },
            'FALL' : { 'name': "Galakrond's Fall", 'level': { 9: 0, 10: 0 } },
            'DHT' : { 'name': 'Darkheart Thicket', 'level': { 9: 0, 10: 0 } },
            'TOTT' : { 'name': 'Throne of the Tides', 'level': { 9: 0, 10: 0 } },
            'EB' : { 'name': 'Everbloom', 'level': { 9: 0, 10: 0 } },
            'WM' : { 'name': 'Waycrest Manor', 'level': { 9: 0, 10: 0 } },
            'RISE' : { 'name': "Murozond's Rise", 'level': { 9: 0, 10: 0 } },
        }

        score_table = {
            2: 33,
            3: 40.5,
            4: 48,
            5: 55.5,
            6: 63,
            7: 70.5,
            8: 78,
            9: 85.5,
            10: 93,
            11: 100.5,
            12: 108,
            13: 115.5,
            14: 123,
            15: 130.5,
            16: 138,
            17: 145.5,
            18: 153,
            19: 160.5,
            20: 168,
            21: 175.5,
            22: 183,
            23: 190.5,
            24: 198,
            25: 205.5,
            26: 213,
            27: 220.5,
            28: 228,
            29: 235.5,
            30: 243,
            31: 250.5,
            32: 258,
            33: 265.5,
            34: 273,
            35: 280.5
        }

        # rio urls
        pri_url = f'https://raider.io/api/v1/characters/profile?region={region}&realm={realm}&name={character}&fields=mythic_plus_best_runs%2Cmythic_plus_scores_by_season%3Acurrent'
        alt_url = f'https://raider.io/api/v1/characters/profile?region={region}&realm={realm}&name={character}&fields=mythic_plus_alternate_runs'

        # data['mythic_plus_scores_by_season'][0]['scores']['all']

        #try:

        response = requests.get(pri_url, headers={'User-Agent': 'Hathor'})
        pri_data = response.json()

        response = requests.get(alt_url, headers={'User-Agent': 'Hathor'})
        alt_data = response.json()

        # get best keys
        for data in pri_data['mythic_plus_best_runs']:
            key_table[data['short_name']]['level'][data['affixes'][0]['id']] = { 'level': data['mythic_level'], 'score': data['score'] }

        # get alt keys
        for data in alt_data['mythic_plus_alternate_runs']:
            key_table[data['short_name']]['level'][data['affixes'][0]['id']] = { 'level': data['mythic_level'], 'score': data['score'] }

        # basic player information
        output = discord.Embed(title="Score Calculator")
        output.set_thumbnail(url=pri_data['thumbnail_url'])
        output.add_field(name=f"{pri_data['name']} - {pri_data['realm']} ({pri_data['mythic_plus_scores_by_season'][0]['scores']['all']})", value=f"{pri_data['race']} {pri_data['active_spec_name']} {pri_data['class']}", inline=False)


        for info in key_table.values():

            fort = info['level'][10] and info['level'][10]['level'] or 0
            fort = fort == 0 and 2 or fort
            fort_score = fort > 0 and info['level'][10]['score'] or 0

            tyran = info['level'][9] and info['level'][9]['level'] or 0
            tyran = tyran == 0 and 2 or tyran
            tyran_score = tyran > 0 and info['level'][9]['score'] or 0

            output.add_field(name=f"{info['name']} T+{tyran} F+{fort}", value=f" \
                Tyrannical: \
                +{tyran + 1} ({'{:.1f}'.format(score_table[tyran+1] - tyran_score)}) / \
                +{tyran + 2} ({'{:.1f}'.format(score_table[tyran+2] - tyran_score)}) / \
                +{tyran + 3} ({'{:.1f}'.format(score_table[tyran+3] - tyran_score)}) \
                \nFortified: \
                +{fort + 1} ({'{:.1f}'.format(score_table[fort+1] - fort_score)}) / \
                +{fort + 2} ({'{:.1f}'.format(score_table[fort+2] - fort_score)}) / \
                +{fort + 3} ({'{:.1f}'.format(score_table[fort+3] - fort_score)}) \
                ", inline=False)
            

        await interaction.response.send_message(embed=output, allowed_mentions=discord.AllowedMentions.none())

       #except Exception as e:
            #await interaction.response.send_message('raider.io api error. 😢')

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