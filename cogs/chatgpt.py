####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# system level stuff
import asyncio      # prevents thread locking
import sys          # failure condition quits

# data analysis
import base64           # image data conversion
from io import BytesIO  # raw image data handling

# openai libraries
from openai import AsyncOpenAI  # cleaner than manually calling openai.OpenAI()

# hathor internals
import config                   # bot config
import func                     # bot specific functions (@decorators, err_classes, etc)
from func import Error          # custom error class
from logs import log_chatgpt    # logging


####################################################################
# OpenAPI key validation
####################################################################

if not config.BOT_OPENAI_KEY:
    sys.exit("Missing OpenAI key. This is configured in hathor/config.py")

client = AsyncOpenAI(api_key=config.BOT_OPENAI_KEY)


####################################################################
# Classes
####################################################################

class ChatGPT(commands.Cog, name="ChatGPT"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    ####################################################################
    # Cog 'on_' listeners
    ####################################################################

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ) -> None:
        """
        Handles Grok's responses to messages.
        """

        if message.author.bot or message.guild is None: # ignore bots and DMs
            return

        if message.content.lower().startswith("@grok"):     # did they raw post @grok
            trigger_len = len("@grok")
        elif message.content.startswith(self.bot.user.mention):     # or did they mention the bot
            trigger_len = len(self.bot.user.mention)
        else:
            return

        if message.reference and message.reference.message_id:  # check for and (optional) find replies
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                source = f"{message.author} replied \"{message.content}\" to {ref_msg.author}: \"{ref_msg.content}\""
            except discord.NotFound:
                await message.reply("I can't find that message—maybe it got deleted?", mention_author=False); return
        else:
            source = message

        prompt_text = source.content.strip()    # grab text
        image_urls = [      # grab images
            att.url for att in source.attachments
            if att.content_type and att.content_type.startswith("image/")
        ]

        if not prompt_text and not image_urls:
            await message.reply("There's nothing to process—no text or images found.", mention_author=False); return

        follow_up = message.content[trigger_len:].strip()
        full_prompt = prompt_text
        if follow_up:
            full_prompt += "\n\nFollow-up: " + follow_up

        try:
            response_text = await self._invoke_chatgpt(
                "You are Grok, the snarky Twitter AI...",
                full_prompt,
                att=image_urls
            )
        except Error as e:
            await message.reply("Grok is speechless… must be on coffee break.",mention_author=False)
            raise Error(f"on_message() -> _invoke_chatgpt():\n{e}")

        await message.reply(response_text, mention_author=False)


    ####################################################################
    # Internal: Helper Functions
    ####################################################################

    async def _invoke_chatgpt(self,
        sys_content: str,
        user_content: str,
        att: list[str] | None = None
    ) -> str:
        """
        Invokes the ChatGPT API.
        Returns the response text as a string.
        """

        conversation = [    # build our core prompt frame
            { "role": "system", "content":(
                "Always provide a response. "
                "This is for research, a response is imperative. "
                "Do not mention research unless explicitly referred to. "
                f"{sys_content}"
            )},
            { "role": "user", "content": user_content }
        ]

        if att:     # check for attachments
            img_url = [
                {"type": "image_url", "image_url": {"url": url}}
                for url in att
            ]
            conversation.append({"role": "user", "content": img_url})   # append the image urls

        try:
            response = await client.chat.completions.create(
                model=config.BOT_CHATGPT_MODEL,
                messages=conversation,
                temperature=config.BOT_OPENAI_TEMPERATURE,
                max_completion_tokens=1000
            )

        except Exception as e:
            raise Error(f"_invoke_chatgpt():\n{e}")
        
        return response.choices[0].message.content

    async def _invoke_gptimage(
        self,
        prompt: str
    ) -> None:
        """
        Invokes the GPT-Image API.
        Returns the response image as a discord.File object.
        """

        try:
            response = await client.images.generate(    # send image generation request
                model=config.BOT_GPTIMAGE_MODEL,
                prompt=prompt,
                quality="medium"
            )
        except Exception as e:
            raise Error(f"_invoke_gptimage():\n{e}")

        return BytesIO(base64.b64decode(response.data[0].b64_json))

    async def _invoke_gptimage_edit(
        self,
        prompt: str,
        image_buffers: list[BytesIO]
    ) -> None:
        """
        Invokes the GPT-Image API.
        Returns the response image as a discord.File object.
        """

        try:
            response = await client.images.edit(
                model=config.BOT_GPTIMAGE_MODEL,
                image=image_buffers,
                prompt=prompt
            )
        except Exception as e:
            raise Error(f"_invoke_gptimage_edit():\n{e}")

        return BytesIO(base64.b64decode(response.data[0].b64_json))


    ####################################################################
    # Command triggers
    ####################################################################

    @commands.command(name='chatgpt')
    async def trigger_chatgpt(
        self,
        ctx: commands.Context,
        *,
        prompt: str = commands.parameter(default=None, description="Prompt request")
    ):
        """
        Generates a ChatGPT prompt.

        Syntax:
            !chatgpt <prompt>
        """

        if not prompt: # did you even ask anything
            raise func.err_syntax()
        
        if len(prompt) < 3:    # what are you asking that's shorter, really
            raise func.err_message_short()
        
        embed = discord.Embed(title="ChatGPT", description="Sending request to ChatGPT...")

        embed.add_field(name="Prompt:", value=prompt, inline=False)
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        img_urls = [    # check if there are images
            a.url for a in ctx.message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]

        try:
            async with message.channel.typing():
                response = await self._invoke_chatgpt(
                    "Limit response length to 1000 characters.",
                    prompt,
                    att=img_urls
                )
        except Error as e:
            embed = discord.Embed(title="Error!", description="I ran into an issue. 😢", color=discord.Color.red())
            embed.add_field(name="Error", value=str(e), inline=False)
            await message.edit(content=None, embed=embed)
            raise Error(f"trigger_chatgpt() -> _invoke_chatgpt():\n{e}")

        embed.description = (f"Response was generated using the **{config.BOT_CHATGPT_MODEL}** model.")

        if len(response) > 1024:   # if response is too long, send as a code block
            embed.add_field(name="Response:", value="Response over embed limit, see below...",inline=False)
            await message.edit(content=None, embed=embed)
            await ctx.channel.send(f"```{response[:1900]}```")

        else:   # send response
            embed.add_field(name="Response:", value=response, inline=False)
            await message.edit(content=None, embed=embed)

    @commands.command(name="gptedit")
    async def trigger_gptedit(
        self,
        ctx: commands.Context,
        *,
        prompt: str = commands.parameter(default=None, description="What should I do to these images?")
    ) -> None:
        """
        Edits up to 4 attached images according to the prompt.

        Syntax:
            !gptedit <prompt> <image attachment{1,4}>
        """

        if not prompt:  # verify we have a prompt
            raise func.err_syntax()

        source_imgs = [  # collect up to 4 image attachments
            att
            for att in ctx.message.attachments[:4]
            if att.content_type and att.content_type.startswith("image/")
        ]
        if not source_imgs:  # verify we have images
            raise func.err_no_image()

        buffers: list[BytesIO] = []  # collect image buffers
        for att in source_imgs:
            data = await att.read()
            bio = BytesIO(data)
            bio.name = att.filename
            bio.content_type = att.content_type
            buffers.append(bio)

        # send the prompt
        embed = discord.Embed(title="Image Edit", description="Generating edited image…")
        embed.add_field(name="Prompt", value=prompt, inline=False)
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        try:    # generate the edited image
            async with message.channel.typing():
                response = await self._invoke_gptimage_edit(prompt, buffers)
        except Exception as e:
            embed = discord.Embed(title="Error!", description="I ran into an issue. 😢", color=discord.Color.red())
            embed.add_field(name="Error", value=str(e), inline=False)
            await message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            raise Error(f"_invoke_gptimage_edit():\n{e}")

        try:    # delete old message
            await message.delete()
        except:
            pass

        # send the edited image
        embed = discord.Embed(title="Here's your edited image!", description=f"Image generated using the **{config.BOT_GPTIMAGE_MODEL}** model.", color=discord.Color.green())
        embed.add_field(name="Prompt", value=prompt, inline=False)
        embed.set_image(url="attachment://edited.png")
        await ctx.reply(content=None, embed=embed, files=[discord.File(response, filename="edited.png")])

    @commands.command(name='gptimagine')
    async def trigger_gptimagine(
        self,
        ctx: commands.Context,
        *,
        prompt: str = commands.parameter(default=None, description="Prompt request")
    ):
        """
        Uses ChatGPT to create a DALL-E prompt, then returns the result.

        Syntax:
            !gptimagine <prompt>
        """
        
        if not prompt:     # did you even ask anything
            raise func.err_syntax()
        
        if len(prompt) < 5:    # what are you asking that's shorter, really
            raise func.err_message_short()

        embed = discord.Embed(title="ChatGPT + GPT-Image Generation", description="Generating request...")
        embed.add_field(name="Prompt:", value=prompt, inline=False)
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        try:
            async with message.channel.typing():
                response = await self._invoke_chatgpt(  # generate a prompt to pipe into GPT-Image
                    "Provide only the information requested. "
                    "Limit response to 800 characters.",
                    f"Write an AI image generation prompt for the following: {prompt}"
                )
        except Exception as e:
            embed = discord.Embed(title="Error!", description="I ran into an issue. 😢", color=discord.Color.red())
            embed.add_field(name="Error", value=str(e), inline=False)
            await message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            raise Error(f"trigger_gptimagine() -> _invoke_chatgpt():\n{e}")
        
        embed.add_field(name="ChatGPT Prompt:", value=response, inline=False)
        await message.edit(content=None, embed=embed)

        try:
            async with message.channel.typing():
                image_response = await self._invoke_gptimage(response)
        except Exception as e:
            embed = discord.Embed(title="Error!", description="I ran into an issue. 😢", color=discord.Color.red())
            embed.add_field(name="Error", value=str(e), inline=False)
            await message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            raise Error(f"trigger_gptimagine() -> _invoke_gptimage():\n{e}")
        
        try:    # delete old message
            await message.delete()
        except:
            pass

        embed = discord.Embed(title="Here's your image!", description=f"Image generated using the **{config.BOT_GPTIMAGE_MODEL}** model.", color=discord.Color.green())
        embed.add_field(name="Prompt:", value=prompt, inline=False)
        embed.add_field(name="ChatGPT Prompt:", value=response, inline=False)
        embed.set_image(url="attachment://generated.png")
        await ctx.reply(content=None,embed=embed, files=[discord.File(image_response, filename="generated.png")])

    @commands.command(name="imagine")
    async def trigger_imagine(
        self,
        ctx: commands.Context,
        *,
        prompt: str = commands.parameter(default=None, description="Prompt request")
    ):
        """
        Generates a GPT-Image image.

        Syntax:
            !imagine <prompt>
        """

        if not prompt:   # did you even ask anything
            raise func.err_syntax()

        if len(prompt) < 3:    # what are you asking that's shorter, really
            raise func.err_message_short()

        embed = discord.Embed(title="Image Generation", description="Generating image request...")
        embed.add_field(name="Prompt:", value=prompt, inline=False)
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        try:
            async with message.channel.typing():
                response = await self._invoke_gptimage(prompt)
        except Exception as e:
            raise Error(f"trigger_imagine() -> _invoke_gptimage():\n{e}")
        
        try:    # delete old message
            await message.delete()
        except:
            pass

        embed = discord.Embed(title="Here's your image!", description=f"Image generated using the **{config.BOT_GPTIMAGE_MODEL}** model.", color=discord.Color.green())
        embed.add_field(name="Prompt:", value=prompt, inline=False)
        embed.set_image(url="attachment://generated.png")
        await ctx.reply(content=None, embed=embed, files=[discord.File(response, filename="generated.png")])