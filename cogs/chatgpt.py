import discord
from discord.ext import commands
import openai
import asyncio
import requests
from io import BytesIO
import base64
import imghdr

import config
import func
from func import FancyErrors

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
    @commands.command(name='chatgpt')
    async def ask_chatgpt(
        self, ctx, *,
        request = commands.parameter(default=None, description="Prompt request")
        ):
        """
        Generates a ChatGPT prompt.
        If the seperator | is used, you can provide a tone followed by your prompt.

        Syntax:
            !chatgpt prompt
            !chatgpt tone | prompt
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
        if len(request) < 3 and not ctx.message.attachments:
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

            # including an image?
            if ctx.message.attachments and ctx.message.attachments[0].content_type.startswith('image/'):
                image_data = await ctx.message.attachments[0].read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                image_type = imghdr.what(None, h=image_data)

                conversation = [
                    { "role": "system", "content": f"Limit response length to 1000 characters. {system_request}" },
                    { "role": "user", "content": [ { "type": "text", "text": user_request }, { "type": "image_url", "image_url": { "url": f"data:image/{image_type};base64,{image_base64}" } } ] }
                ]
            else:
                conversation = [
                    { "role": "system", "content": f"Limit response length to 1000 characters. {system_request}" },
                    { "role": "user", "content": user_request }
                ]

            try:
                response = openai.ChatCompletion.create(
                    model=config.BOT_CHATGPT_MODEL,
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

            # including an image?
            if ctx.message.attachments and ctx.message.attachments[0].content_type.startswith('image/'):
                image_data = await ctx.message.attachments[0].read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                image_type = imghdr.what(None, h=image_data)

                conversation = [
                    { "role": "system", "content": f"Limit response length to 1000 characters." },
                    { "role": "user", "content": [ { "type": "text", "text": user_request }, { "type": "image_url", "image_url": { "url": f"data:image/{image_type};base64,{image_base64}" } } ] }
                ]
            else:
                conversation = [
                    { "role": "system", "content": f"Limit response length to 1000 characters." },
                    { "role": "user", "content": user_request }
                ]

            try:
                response = openai.ChatCompletion.create(
                    model=config.BOT_CHATGPT_MODEL,
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
            output.description = f"Reponse was generated using the **{config.BOT_CHATGPT_MODEL}** model."

            response_content = response.choices[0].message.content
            if len(response_content) > 1024:
                output.add_field(name="Response:", value="Listed below due to length...", inline=False)
                await message.edit(content=None, embed=output)
                await ctx.channel.send(f"```{response_content[:1990]}```")
            else:
                output.add_field(name="Response:", value=response_content, inline=False)
                await message.edit(content=None, embed=output)

    ####################################################################
    # trigger: !imagine
    # ----
    # Sends a request to dall-e.
    ####################################################################
    @commands.command(name='imagine')
    async def ask_dalle(
        self, ctx, *,
        request = commands.parameter(default=None, description="Prompt request")
        ):
        """
        Generates a Dall-E prompt.

        Syntax:
            !imagine prompt
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
        if len(request) < 10:
            await FancyErrors("SHORT", ctx.channel)
            return
        
        # prep our message
        output = discord.Embed(title="DALL-E", description="Sending request to DALL-E...")

        # Prep our message
        output.add_field(name="Prompt:", value=request, inline=False)
        message = await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        try:
            # Offload the image generation to a background asyncio task
            await asyncio.create_task(self.generate_dalle_image(ctx, request))

        except:
            return

    async def generate_dalle_image(self, ctx, request):
        try:
            response = openai.Image.create(
                model=config.BOT_DALLE_MODEL,
                prompt=request,
                quality='hd',
                n=1
            )

            image_data = BytesIO(requests.get(response['data'][0]['url']).content)
            await ctx.send(file=discord.File(image_data, filename='dalle_image.png'))

        except openai.error.OpenAIError as e:
            print(f"OpenAI API error: {e}")