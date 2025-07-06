####################################################################
# Library & Modules
####################################################################

#discord imports
import discord
from discord import app_commands
from discord.ext import commands

# data analysis
from typing import Optional     # this is supposed to be "cleaner" for array pre-definition

# numbers
import random

# hathor internals
from func import EIGHT_BALL_ANSWERS
from logs import log_cog

####################################################################
# Classes
####################################################################

class Gamba(commands.Cog, name="Gamba"):    # main class for cog
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tree = bot.tree

    @app_commands.command(
        name="8ball",
        description="Ask the magic 8ball a question!"
    )
    @app_commands.describe(question="Your yes/no question")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        answer = random.choice(EIGHT_BALL_ANSWERS)
        await interaction.response.send_message(
            f"🎱 **Question:** {question}\n**Answer:** {answer}"
        )

    ### /roll ##########################################################
    @app_commands.command(name="roll", description="Your favorite number game. 🙂")
    async def roll_command(self, interaction: discord.Interaction, limit: Optional[int] = 100):

        if limit < 2:
            await interaction.response.send_message(f"Roll too low."); return

        else:
            number = random.randint(1,limit)
            output = discord.Embed(title="Roll!", description=f"{interaction.user.nick} rolls {number} (1-{limit})")

            await interaction.response.send_message(embed=output)

async def setup(bot):
    log_cog.info("🎲 Loading [dark_orange]Gamba[/] cog...")
    await bot.add_cog(Gamba(bot))