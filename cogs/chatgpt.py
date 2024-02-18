import discord
from discord.ext import commands
import openai
from openai import OpenAI
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
    client = OpenAI(api_key=config.BOT_OPENAI_KEY)

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
    # trigger: !chatgpt
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
                response = client.chat.completions.create(
                    model=config.BOT_CHATGPT_MODEL,
                    messages=conversation,
                    temperature=0.8,
                    max_tokens=1000
                )
            except openai.ServiceUnavailableError:
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
                response = client.chat.completions.create(
                    model=config.BOT_CHATGPT_MODEL,
                    messages=conversation,
                    temperature=0.8,
                    max_tokens=1000
                )
            except openai.ServiceUnavailableError:
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
    # trigger: !gptimagine
    # ----
    # Pivots a chatgpt request to dall-e for even more detail.
    ####################################################################
    @commands.command(name='gptimagine')
    async def ask_gptdalle(
        self, ctx, *,
        request = commands.parameter(default=None, description="Prompt request")
        ):
        """
        Uses ChatGPT to create a DALL-E prompt, then returns the result.

        Syntax:
            !gptimagine prompt
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
        if len(request) < 5:
            await FancyErrors("SHORT", ctx.channel)
            return
        
        # prep our message
        output = discord.Embed(title="OpenAI Generation", description="Generating request...")

        conversation = [
                    { "role": "system", "content": f"Provide only the information requested. Include a lot of detail. Limit response to 800 characters." },
                    { "role": "user", "content": f"Write a DALL-E prompt for the following: {request}" }
                ]

        try:

            # Prep our message
            output.add_field(name="Prompt:", value=request, inline=False)
            message = await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

            # get chatgpt response
            response = client.chat.completions.create(
                model=config.BOT_CHATGPT_MODEL,
                messages=conversation,
                temperature=0.8,
                max_tokens=1000
            )

            # include chatgpt results in message
            output.add_field(name="ChatGPT Prompt:", value=response.choices[0].message.content, inline=False)
            await message.edit(embed=output, allowed_mentions=discord.AllowedMentions.none())

            # generate dall-e image from chatgpt result
            await asyncio.create_task(self.generate_dalle_image(ctx, response.choices[0].message.content))

        except openai.ServiceUnavailableError:
            return

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

        # try:
        # Offload the image generation to a background asyncio task
        await asyncio.create_task(self.generate_dalle_image(ctx, request))

        # except:
        #     return

    async def generate_dalle_image(self, ctx, request):
        # try:
        response = client.images.generate(
            model=config.BOT_DALLE_MODEL,
            prompt=request,
            quality='hd',
            n=1
        )

        for image_data in response.data:
            image_data_bytes = BytesIO(requests.get(image_data.url).content)

            # Send the image as a file attachment
            await ctx.send(file=discord.File(image_data_bytes, filename='dalle_image.png'))

        # except openai.OpenAIError as e:
        #     print(f"OpenAI API error: {e}")