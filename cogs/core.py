import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context
from typing import Literal, Optional
import config
import func
from func import FancyErrors

class Core(commands.Cog, name="Core"):
    """Core commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="botleave")
    @func.requires_owner_perms()
    async def trigger_botleave(
        self,
        ctx: commands.Context,
        guild_id: int | None = None
    ) -> None:
        """
        BOT OWNER. Leave the provided discord server.
        
        Syntax:
            !botleave <guildID>
        """

        if not guild_id:
            await FancyErrors("SYNTAX", ctx.channel)
            return

        guild = self.bot.get_guild(guild_id)

        # let them know
        await ctx.send(f"👋 Leaving **{guild.name}** (ID: {guild.id})…")

        # bye felicia
        await guild.leave()

    @commands.command(name="botservers")
    @func.requires_owner_perms()
    async def trigger_botservers(
        self,
        ctx: commands.Context
    ) -> None:
        """
        BOT OWNER. Lists all guilds the bot is currently in.

        Syntax:
            !botservers
        """

        # build a list of lines "Name (ID: ...)"
        lines = [f"{g.name} (ID: {g.id})" for g in self.bot.guilds]

        # assemble embed
        embed = discord.Embed(
            title="🤖 Bot is in the following guilds:",
            description="\n".join(lines) or "None",
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Total guilds: {len(lines)}")

        # send to channel
        await ctx.send(embed=embed)

    @commands.command(name="botsync")
    @func.requires_owner_perms()
    async def trigger_botsync(
        self,
        ctx: Context,
        guilds: Greedy[discord.Object],
        spec: Literal["guild", "globalguild", "clearguild"] | None = None
    ) -> None:
        """
        BOT OWNER. Syncronizes /slash commands.

        Syntax:
            !botsync [ guild | globalguild | clearguild ]
        """

        if not guilds:
            if spec == "guild":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "globalguild":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "clearguild":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}")
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.command(name='permissions', aliases=['perms', 'roles'])
    @func.requires_author_perms()
    async def trigger_permissions(
        self,
        ctx: commands.Context,
        action: Literal["add", "remove"] | None = None,
        group: Literal["channel", "role", "user"] | None = None,
        target: int | None = None
    ) -> None:
        """
        BOT MOD. Modifies bot permissions for the server.

        Syntax:
            !permissions [ add | remove ] user <userID>
            !permissions [ add | remove ] role <roleID>
            !permissions [ add | remove ] channel <chanID>
        """
        global settings

        guild_str = str(ctx.guild.id)

        if not action:    # print permissions for server
            user_lines = [   # build users list
                f"{(await self.bot.fetch_user(u)).display_name} (id:{u})"
                for u in config.settings[guild_str]["perms"]["user_id"]
            ]
            owner = await self.bot.fetch_user(ctx.guild.owner_id)    # required to get the owner's name
            user_lines.insert(0, f"{owner.display_name} (id: {ctx.guild.owner_id})")
            users = "\n".join(user_lines)

            roles = "\n".join(   # build roles list
                f"{(role := discord.utils.get(ctx.guild.roles, id=id)).name} (id: {id})"
                for id in config.settings[guild_str]["perms"]["role_id"]
            )

            channels = "\n".join(   # build channels list
                f"#{(channel := self.bot.get_channel(id)).name} (id: {id})"
                for id in config.settings[guild_str]["perms"]["channel_id"]
            )

            embed = discord.Embed(    # build embed
                title=f"Permissions for {ctx.guild.name}",
                description="The following channels are enabled for bot commands, and the following users and roles are permitted for elevated permissions."
            )
            embed.add_field(name="Users:", value=users, inline=False)
            embed.add_field(name="Roles:", value=roles, inline=False)
            embed.add_field(name="Channels:", value=channels, inline=False)
            await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none()); return


        if not group or not target:    # syntax error
            raise func.err_syntax(); return

        target = int(target)    # convert to int
        
        if action == "add":    # add permission
            if target in config.settings[guild_str]["perms"][f"{group}_id"]:
                raise func.err_permissions_exist(); return

            config.settings[guild_str]["perms"][f"{group}_id"].append(target)
            config.SaveSettings()

        elif action == "remove":    # remove permission
            if target not in config.settings[guild_str]["perms"][f"{group}_id"]:
                raise func.err_permissions_exist(); return

            config.settings[guild_str]["perms"][f"{group}_id"].remove(target)
            config.SaveSettings()

        else:    # syntax error
            raise func.err_syntax(); return
        
        await ctx.reply(f"Successfully {action}ed {target} to {group}.", allowed_mentions=discord.AllowedMentions.none()); return

async def setup(bot: commands.Bot):
    await bot.add_cog(Core(bot))