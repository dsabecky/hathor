import discord
from discord.ext import commands
import openai

import config
import func
from func import LoadSettings, FancyErrors

settings = LoadSettings()

# enable openai if we set a key
if config.BOT_OPENAI_KEY:
    openai.api_key = config.BOT_OPENAI_KEY

# define the class
class ChatGPT(commands.Cog, name="ChatGPT"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # on_ready()
    ####################################################################

    # @commands.Cog.listener()
    # async def on_ready(self):

    ####################################################################
    # trigger: !ai
    # ----
    # request: pseudo-variable
    # system_request: when split with a |, will set the tone of the prompt
    # user_request:   the request to be sent
    # ----
    # Sends a request to chatgpt.
    ####################################################################
    @commands.command(name='ai')
    async def ask_chatgpt(
        self, ctx, *,
        request = commands.parameter(default=None, description="Prompt request")
        ):
        """
        Generates a ChatGPT prompt.
        If the seperator | is used, you can provide a tone followed by your prompt.

        Syntax:
            !ai prompt
            !ai tone | prompt
        """

        # is there an api key present?
        if not config.BOT_OPENAI_KEY:
            await FancyErrors("DISABLED_FEATURE", ctx.channel)
            return

        # did you even ask anything
        if not request:
            await FancyErrors("SYNTAX", ctx.channel)
            return
        
        # what are you asking that's shorter, really
        if len(request) < 3:
            await FancyErrors("SHORT", ctx.channel)
            return
        
        # prep our message
        output = discord.Embed(title="ChatGPT", description="Sending request to ChatGPT...")

        # figure out if we're sending system request or not
        delimiter = "|"
        if delimiter in request:
            temp_split = request.split(delimiter)
            system_request = temp_split[0].strip()
            user_request = temp_split[1].strip()

            # Prep our message
            output.add_field(name="Tone:", value=system_request, inline=False)
            output.add_field(name="Prompt:", value=user_request, inline=False)
            message = await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

            conversation = [
                { "role": "system", "content": f"Limit response length to 1000 characters. {system_request}" },
                { "role": "user", "content": user_request }
            ]

            try:
                response = openai.ChatCompletion.create(
                    model=config.BOT_OPENAI_MODEL,
                    messages=conversation,
                    temperature=0.8,
                    max_tokens=1000
                )
            except openai.error.ServiceUnavailableError:
                reponse = "SERVICE_UNAVAILABLE"

        else:
            user_request = request

            # Prep our message
            output.add_field(name="Prompt:", value=user_request, inline=False)
            message = await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

            conversation = [
                { "role": "system", "content": f"Limit response length to 1000 characters." },
                { "role": "user", "content": user_request }
            ]

            try:
                response = openai.ChatCompletion.create(
                    model=config.BOT_OPENAI_MODEL,
                    messages=conversation,
                    temperature=0.8,
                    max_tokens=1000
                )
            except openai.error.ServiceUnavailableError:
                reponse = "SERVICE_UNAVAILABLE"

        # update our message with the reponse
        if response == "SERVICE_UNAVAILABLE":
            output.add_field(name="Error!", value="ChatGPT servers are experiencing higher than usual traffic. Please try again in a minute.", inline=False)
            output.description = f"ERROR"
            await message.edit(content=None, embed=output)
        else:
            output.add_field(name="Response:", value=response.choices[0].message.content, inline=False)
            output.description = f"Reponse was generated using the **{config.BOT_OPENAI_MODEL}** model."
            await message.edit(content=None, embed=output)