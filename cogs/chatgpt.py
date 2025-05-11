####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# system level stuff
import asyncio          # prevents thread locking
import requests         # grabbing raw data from url


# data analysis
import ast              # parsing json error codes from openai
import base64           # image data conversion
import imghdr           # grab image header / x-image-type
from io import BytesIO  # raw image data handling
import re               # regex for various filtering

# openai libraries
import openai               # ai playlist generation, etc
from openai import OpenAI   # cleaner than manually calling openai.OpenAI()

# hathor internals
import config                   # bot config
import func                     # bot specific functions (@decorators, err_classes, etc)
from logs import log_chatgpt    # logging


####################################################################
# OpenAPI key validation
####################################################################

if not config.BOT_OPENAI_KEY:
    sys.exit("Missing OpenAI key. This is configured in hathor/config.py")

client = OpenAI(api_key=config.BOT_OPENAI_KEY)


####################################################################
# Classes
####################################################################

class ChatGPT(commands.Cog, name="ChatGPT"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # Command triggers
    ####################################################################

    ### !chatgpt #######################################################
    @commands.command(name='chatgpt')
    async def trigger_chatgpt(
        self, ctx, *,
        request = commands.parameter(default=None, description="Prompt request")
    ):
        """
        Generates a ChatGPT prompt.
        If the seperator | is used, you can provide a tone followed by your prompt.

        Syntax:
            !chatgpt <prompt>
            !chatgpt <tone> | <prompt>
        """

        if not request: # did you even ask anything
            raise func.err_syntax(); return
        
        # what are you asking that's shorter, really
        if len(request) < 3 or not ctx.message.attachments:
            raise func.err_message_short(); return
        
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
                    { "role": "system", "content": f"Limit response length to 500 characters. {system_request}" },
                    { "role": "user", "content": [ { "type": "text", "text": user_request }, { "type": "image_url", "image_url": { "url": f"data:image/{image_type};base64,{image_base64}" } } ] }
                ]
            else:
                conversation = [
                    { "role": "system", "content": f"Limit response length to 500 characters. {system_request}" },
                    { "role": "user", "content": user_request }
                ]

            try:
                response = client.chat.completions.create(
                    model=config.BOT_CHATGPT_MODEL,
                    messages=conversation,
                    temperature=config.BOT_OPENAI_TEMPERATURE,
                    max_completion_tokens=1000
                )
            except Exception as e:
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
                    temperature=config.BOT_OPENAI_TEMPERATURE,
                    max_completion_tokens=1000
                )
            except Exception as e:
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
    # trigger: !gptedit
    # ----
    # Edits up to 4 attached images according to provided prompt.
    ####################################################################
    @commands.command(name="gptedit")
    async def edit_gptimage(
        self,
        ctx,
        *,
        prompt: str = commands.parameter(default=None, description="What should I do to these images?")
    ):
        """
        Edits up to 4 attached images according to the prompt.

        Syntax:
            !gptedit <prompt> <image attachment{1,4}>
        """

        if not prompt:
            raise func.err_syntax(); return

        # collect up to 4 image attachments
        buffers = []
        for attachment in ctx.message.attachments[:4]:
            if not attachment.content_type or \
            not attachment.content_type.startswith("image/"):
                continue
            buf = BytesIO(await attachment.read())
            buf.name = attachment.filename
            buf.content_type = attachment.content_type
            buffers.append(buf)

        if not buffers:
            raise func.err_no_image(); return

        # send the “Generating edit…” embed
        waiting = discord.Embed(
            title="Image Edit", description="Generating edited image…"
        )
        waiting.add_field(name="Prompt", value=prompt, inline=False)
        waiting_msg = await ctx.reply(
            embed=waiting,
            allowed_mentions=discord.AllowedMentions.none()
        )

        # background work
        asyncio.create_task(self.generate_image_edit(ctx, prompt, buffers, waiting_msg, ctx.message))

    ####################################################################
    # trigger: !gptimagine
    # ----
    # Pivots a chatgpt request to dall-e for even more detail.
    ####################################################################
    @commands.command(name='gptimagine')
    async def ask_gptdalle(
        self, ctx, *,
        request=commands.parameter(default=None, description="Prompt request")
    ):
        """
        Uses ChatGPT to create a DALL-E prompt, then returns the result.

        Syntax:
            !gptimagine <prompt>
        """
        
        # did you even ask anything
        if not request:
            raise func.err_syntax(); return
        
        # what are you asking that's shorter, really
        if len(request) < 5:
            raise func.err_message_short(); return

        # build your embed
        output = discord.Embed(title="OpenAI Generation", description="Generating request...")
        output.add_field(name="Prompt:", value=request, inline=False)

        # send it and keep the message object
        message = await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        # call ChatGPT synchronously
        response = client.chat.completions.create(
            model=config.BOT_CHATGPT_MODEL,
            messages=[
                {"role":"system","content":(
                    "Provide only the information requested. "
                    "Include a lot of detail. Limit response to 800 characters."
                )},
                {"role":"user","content":f"Write an ai image generation prompt for the following: {request}"}
            ],
            temperature=config.BOT_OPENAI_TEMPERATURE,
            max_completion_tokens=1000
        )

        # add ChatGPT’s result into that same embed
        output.add_field(
            name="ChatGPT Prompt:",
            value=response.choices[0].message.content,
            inline=False
        )
        await message.edit(
            embed=output,
            allowed_mentions=discord.AllowedMentions.none()
        )

        # now fire-and-forget, passing along the embed + message
        asyncio.create_task(self.generate_dalle_image(ctx, response.choices[0].message.content, message, output, ctx.message))


    ####################################################################
    # trigger: !imagine
    # ----
    # Sends a request to dall-e.
    ####################################################################
    @commands.command(name="imagine")
    async def ask_dalle(
        self, ctx, *, 
        request=commands.parameter(default=None, description="Prompt request")
    ):
        """
        Generates a Dall-E prompt.

        Syntax:
            !imagine <prompt>
        """

        if not request:
            raise func.err_syntax(); return

        if len(request) < 10:
            raise func.err_message_short(); return

        # 1) build and send the "Generating..." embed
        embed = discord.Embed(title="Image Generation", description="Generating image request...")
        embed.add_field(name="Prompt:", value=request, inline=False)
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        # 2) fire-and-forget, passing along ctx, prompt, message & embed
        asyncio.create_task(self.generate_dalle_image(ctx, request, message, embed, ctx.message))


    ####################################################################
    # function: generate_dalle_image
    # ----
    # Image generation logic.
    ####################################################################
    async def generate_dalle_image(
        self,
        ctx,
        prompt: str,
        original_message: discord.Message,
        original_embed: discord.Embed,
        user_message: discord.Message
    ):

        # helper: parse the "{'error': {...}}" JSON out of str(exc)
        def parse_error(exc) -> dict:
            text = str(exc)
            m = re.search(r"(\{'.*'error':\s*\{.*\}\})", text)
            if m:
                try:
                    return ast.literal_eval(m.group(1))["error"]
                except Exception:
                    pass
            return {"message": text, "code": None}

        try:
            # run the blocking call in a thread
            def blocking():
                return client.images.generate(
                    model=config.BOT_GPTIMAGE_MODEL,
                    prompt=prompt,
                    quality='medium'
                )
            response = await asyncio.to_thread(blocking)

        except openai.BadRequestError as e:
            err = parse_error(e)
            msg = err.get("message", str(e))

            # delete "Generating..." message
            try:
                await original_message.delete()
            except discord.NotFound:
                pass

            # build and send the error embed
            err_embed = discord.Embed(
                title="Image Generation Blocked",
                description="Your prompt was rejected by OpenAI’s safety system.",
                color=discord.Color.red()
            )
            err_embed.add_field(name="Prompt", value=prompt, inline=False)
            err_embed.add_field(name="Error",  value=msg,    inline=False)

            await user_message.reply(embed=err_embed, allowed_mentions=discord.AllowedMentions.none())
            return

        try:
            await original_message.delete()
        except discord.NotFound:
            pass

        img_b64 = response.data[0].b64_json
        image_bytes = base64.b64decode(img_b64)
        buffer = BytesIO(image_bytes)

        new_embed = discord.Embed(
            title=original_embed.title,
            description="Here’s your generated image!",
            color=discord.Color.green()
        )
        for f in original_embed.fields:
            new_embed.add_field(name=f.name, value=f.value, inline=f.inline)

        new_embed.set_image(url="attachment://generated.png")

        await user_message.reply(
            embed=new_embed,
            file=discord.File(buffer, filename="generated.png"),
            allowed_mentions=discord.AllowedMentions.none()
        )

    ####################################################################
    # function: generate_image_edit
    # ----
    # Image generation logic.
    ####################################################################
    async def generate_image_edit(
        self,
        ctx,
        prompt: str,
        image_buffers: list[BytesIO],
        waiting_msg: discord.Message,
        user_message: discord.Message
    ):
 
        def parse_error(exc) -> dict:
            text = str(exc)
            m = re.search(r"(\{'.*'error':\s*\{.*\}\})", text)
            if m:
                try:
                    return ast.literal_eval(m.group(1))["error"]
                except Exception:
                    pass
            return {"message": text, "code": None}

        # run the edit call in a thread
        try:
            def blocking():
                return client.images.edit(
                    model=config.BOT_GPTIMAGE_MODEL,
                    image=image_buffers,
                    prompt=prompt
                )
            result = await asyncio.to_thread(blocking)

        except BadRequestError as e:
            err = parse_error(e)
            msg = err.get("message", str(e))

            # delete waiting
            try:
                await waiting_msg.delete()
            except discord.NotFound:
                pass

            # send an error embed
            error_embed = discord.Embed(
                title="Image Edit Blocked",
                description="OpenAI’s safety system rejected your request.",
                color=discord.Color.red()
            )
            error_embed.add_field(name="Prompt", value=prompt, inline=False)
            error_embed.add_field(name="Error", value=msg, inline=False)

            await user_message.reply(
                embed=error_embed,
                allowed_mentions=discord.AllowedMentions.none()
            )
            return

        # success path: delete waiting, decode and reply with image
        try:
            await waiting_msg.delete()
        except discord.NotFound:
            pass

        b64 = result.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        out = BytesIO(img_bytes)

        final_embed = discord.Embed(
            title="Here’s your edited image!",
            color=discord.Color.green()
        )
        final_embed.add_field(name="Prompt", value=prompt, inline=False)
        final_embed.set_image(url="attachment://edited.png")

        await user_message.reply(
            embed=final_embed,
            file=discord.File(out, filename="edited.png"),
            allowed_mentions=discord.AllowedMentions.none()
        )