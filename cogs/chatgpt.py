####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# data analysis
import base64           # image data conversion
from io import BytesIO  # raw image data handling
import re               # regex

# openai libraries
from openai import AsyncOpenAI  # cleaner than manually calling openai.OpenAI()

# hathor internals
import config                                   # bot config
from func import Error, ERROR_CODES, FancyError # custom error class
from func import build_embed                   # custom embeds
from logs import log_cog                        # logging


####################################################################
# OpenAI Client
####################################################################

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


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

        if not message.content.lower().startswith("@grok") and not message.content.startswith(self.bot.user.mention):   # no @grok
            return

        temp_prompt = message.content.replace(self.bot.user.mention, "@grok").strip()   # replace bot mention with @grok

        if temp_prompt.lower() == "@grok":  # empty response, be snarky
            await message.reply("Ah, the classic 'say nothing, get nothing' approach—bold move. Try putting some words in there next time, genius. 🥱", mention_author=False); return
        
        ref_img = []
        if message.reference and message.reference.message_id:  # check for and (optional) find replies
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                temp_prompt = f"{message.author} replied '{temp_prompt}' to {ref_msg.author}'s message '{ref_msg.content}'"

                ref_img = [      # grab images
                    att.url for att in ref_msg.attachments
                    if att.content_type and att.content_type.startswith("image/")
                ]
            except discord.NotFound:
                await message.reply("I see you tried to reply quote a message, but I can't access it.", mention_author=False); return

        img = [      # grab images
            att.url for att in message.attachments
            if att.content_type and att.content_type.startswith("image/")
        ]

        if not temp_prompt and not img:
            await message.reply("Ah, the classic 'say nothing, get nothing' approach—bold move. Try putting some words in there next time, genius. 🥱", mention_author=False); return

        async with message.channel.typing():
            try:
                response_text = await self._invoke_chatgpt(
                    "You are Grok, the snarky Twitter AI. "
                    "You are oblivious to your attitide. "
                    "Limit your response to fit in a tweet. "
                    "Be your typical rude self, but don't be too mean.",
                    temp_prompt,
                    att=img + ref_img
                )
            except Error as e:
                await message.reply("Grok is speechless… must be on coffee break.",mention_author=False)
                raise Error(f"on_message() -> _invoke_chatgpt():\n{e}")

        await message.reply(response_text, mention_author=False, suppress_embeds=True)


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

        is_reasoning = True if re.search(r"^o\d+", config.CHATGPT_MODEL) else False # check if the model is a reasoning model

        conversation = [    # build our core prompt frame
            { "role": "system", "content": sys_content},
            { "role": "user", "content": user_content }
        ]

        if att:     # check attachments and append to conversation
            image_context = 'image_url' if is_reasoning else 'input_image'
            img_url = [
                { "type": image_context, "image_url": url }
                for url in att
            ]
            conversation.append({"role": "user", "content": img_url})

        try:
            if is_reasoning:
                response = await client.chat.completions.create(
                    model=config.CHATGPT_MODEL,
                    messages=conversation,
                    temperature=config.CHATGPT_TEMPERATURE
                )
                
                return response.choices[0].message.content
                
            else:
                conversation.append({"role": "system", "content": " You have optional access to the internet."})
                response = await client.responses.create(
                    model=config.CHATGPT_MODEL,
                    temperature=config.CHATGPT_TEMPERATURE,
                    input=conversation,
                    tool_choice= "auto",
                    tools=[{"type": "web_search_preview"}])
                

                return response.output[-1].content[0].text

        except Exception as e:
            raise Error(f"_invoke_chatgpt():\n{e}")

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
                model=config.GPTIMAGE_MODEL,
                prompt=prompt,
                quality=config.GPTIMAGE_QUALITY
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
                model=config.GPTIMAGE_MODEL,
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
        prompt: str
    ) -> None:
        """
        Generates a ChatGPT prompt.

        Syntax:
            !chatgpt <prompt>
        """
        
        if len(prompt) < 3:    # what are you asking that's shorter, really
            raise FancyError(ERROR_CODES['message_short'])
        
        message = await ctx.reply(embed=build_embed('ChatGPT', 'Sending request to ChatGPT…', 'p', [('Prompt:', prompt, False)]), allowed_mentions=discord.AllowedMentions.none())

        img = [    # check if there are images
            a.url for a in ctx.message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]

        try:
            async with message.channel.typing():
                response = await self._invoke_chatgpt(
                    "You are a discord bot. "
                    "You have access to discord's markdown formatting. "
                    "Limit response length to 900 characters.",
                    prompt, att=img
                )
        except Error as e:
            await message.edit(content=None, embed=build_embed('err', 'I ran into an issue. 😢', 'r', [('Prompt:', prompt, False), ('Error:', str(e), False)])); return
        try:
            await message.edit(content=None, embed=build_embed('ChatGPT', 'txt', 'g', [('Prompt:', prompt, False), ('Response:', response, False)]))
        except:
            await message.edit(content=None, embed=build_embed('ChatGPT', 'txt', 'g', [('Prompt:', prompt, False), ('Response:', 'Response below (over embed limit).', False)]))
            await message.reply(f"{response[:1900]}", mention_author=False)
            

    @commands.command(name="gptedit")
    async def trigger_gptedit(
        self,
        ctx: commands.Context,
        *,
        prompt: str
    ) -> None:
        """
        Edits up to 4 attached images according to the prompt.

        Syntax:
            !gptedit <prompt> <image attachment{1,4}>
        """

        if len(prompt) < 3:    # what are you asking that's shorter, really
            raise FancyError(ERROR_CODES['message_short'])

        img = [  # collect up to 4 image attachments
            att
            for att in ctx.message.attachments[:4]
            if att.content_type and att.content_type.startswith('image/')
        ]
        if not img:  # verify we have images
            raise FancyError(ERROR_CODES['no_image'])

        buffers: list[BytesIO] = []  # collect image buffers
        for att in img:
            data = await att.read()
            bio = BytesIO(data); bio.name = att.filename; bio.content_type = att.content_type
            buffers.append(bio)

        # send the prompt
        message = await ctx.reply(embed=build_embed('Image Edit', 'Generating edited image…', 'p', [('Prompt:', prompt, False)]), allowed_mentions=discord.AllowedMentions.none())

        try:    # generate the edited image
            async with message.channel.typing():
                response = await self._invoke_gptimage_edit(prompt, buffers)
        except Exception as e:
            await message.edit(embed=build_embed('err', 'I ran into an issue. 😢', 'r', [('Prompt:', prompt, False), ('Error:', str(e), False)])); return

        try:    # delete old message
            await message.delete()
        except:
            pass

        # send the edited image
        embed = build_embed('Image Edit', 'img', 'g', [('Prompt:', prompt, False)]); embed.set_image(url="attachment://edited.png")
        await ctx.reply(content=None, embed=embed, files=[discord.File(response, filename="edited.png")])

    @commands.command(name='gptimagine')
    async def trigger_gptimagine(
        self,
        ctx: commands.Context,
        *,
        prompt: str
    ) -> None:
        """
        Uses ChatGPT to create a GPT-Image prompt, then returns the result.

        Syntax:
            !gptimagine <prompt>
        """
        
        if len(prompt) < 5:    # what are you asking that's shorter, really
            raise FancyError(ERROR_CODES['message_short'])

        message = await ctx.reply(embed=build_embed('ChatGPT + Image Generation', 'Generating request…', 'p', [('Prompt:', prompt, False)]), allowed_mentions=discord.AllowedMentions.none())

        try:
            async with message.channel.typing():
                response = await self._invoke_chatgpt(  # generate a prompt to pipe into GPT-Image
                    "Provide only the information requested. "
                    "Limit response to 800 characters.",
                    f"Write an AI image generation prompt for the following: {prompt}"
                )
        except Exception as e:
            await message.edit(content=None, embed=build_embed('err', 'I ran into an issue. 😢', 'r', [('Prompt:', prompt, False), ('Error:', str(e), False)])); return
        
        await message.edit(content=None, embed=build_embed('ChatGPT + Image Generation', 'txt', 'p', [('Prompt:', prompt, False), ('Response:', response, False)]))

        try:
            async with message.channel.typing():
                image_response = await self._invoke_gptimage(response)
        except Exception as e:
            await message.edit(content=None, embed=build_embed('err', 'I ran into an issue. 😢', 'r', [('Prompt:', prompt, False), ('Error:', str(e), False)])); return

        try:    # delete old message
            await message.delete()
        except:
            pass

        embed = build_embed('ChatGPT + Image Generation', 'imgtxt', 'g', [('Prompt:', prompt, False), ('Response:', response, False)]); embed.set_image(url="attachment://generated.png")
        await ctx.reply(content=None,embed=embed, files=[discord.File(image_response, filename="generated.png")])

    @commands.command(name="imagine")
    async def trigger_imagine(
        self,
        ctx: commands.Context,
        *,
        prompt: str
    ) -> None:
        """
        Generates a GPT-Image image.

        Syntax:
            !imagine <prompt>
        """

        if len(prompt) < 3:    # what are you asking that's shorter, really
            raise FancyError(ERROR_CODES['message_short'])

        message = await ctx.reply(embed=build_embed('Image Generation', 'Generating image request…', 'p', [('Prompt:', prompt, False)]), allowed_mentions=discord.AllowedMentions.none())

        try:
            async with message.channel.typing():
                response = await self._invoke_gptimage(prompt)
        except Exception as e:
            await message.edit(embed=build_embed('err', 'I ran into an issue. 😢', 'r', [('Prompt:', prompt, False), ('Error:', str(e), False)])); return
        
        try:    # delete old message
            await message.delete()
        except:
            pass

        embed = build_embed('Image Generation', 'img', 'g', [('Prompt:', prompt, False)]); embed.set_image(url="attachment://generated.png")
        await ctx.reply(content=None, embed=embed, files=[discord.File(response, filename="generated.png")])


####################################################################
# Launch Cog
####################################################################

async def setup(bot):
    log_cog.info("Loading [dark_orange]ChatGPT[/] cog...")
    await bot.add_cog(ChatGPT(bot))