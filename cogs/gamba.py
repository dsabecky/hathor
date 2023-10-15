import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

import random

# logging
from func import err
from logs import log_gamba

# define the class
class Gamba(commands.Cog, name="Gamba"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # on_ready()
    ####################################################################

    # @commands.Cog.listener()
    # async def on_ready(self):

    @app_commands.command(name="roll", description="Your favorite number game. 🙂")
    async def roll_command(self, interaction: discord.Interaction, limit: Optional[int] = 100):

        if limit < 2:
            await interaction.response.send_message(f"{random.choice(err['quote'])} ({err['code']['QUEUE_RANGE']})")
            return
        else:
            number = random.randint(1,limit)
            output = discord.Embed(title="Roll!", description=f"{interaction.user.nick} rolls {number} (1-{limit})")

            await interaction.response.send_message(embed=output)