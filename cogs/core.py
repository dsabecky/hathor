####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context

# data analysis
from typing import Literal  # type hints

# hathor internals
from func import requires_owner_perms, requires_author_perms
from func import ERROR_CODES, FancyError, build_embed
from logs import log_cog

####################################################################
# Classes
####################################################################

class Core(commands.Cog, name="Core"):
    """Core commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    ####################################################################
    # Command triggers
    ####################################################################

    @commands.command(name="botleave")
    @requires_owner_perms()
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
            raise FancyError(ERROR_CODES["syntax"])

        guild = self.bot.get_guild(guild_id)

        await ctx.send(f"Leaving **{guild.name}** (ID: {guild.id}) ✌️")
        await guild.leave()

    @commands.command(name="botservers")
    @requires_owner_perms()
    async def trigger_botservers(
        self,
        ctx: commands.Context
    ) -> None:
        """
        BOT OWNER. Lists all guilds the bot is currently in.

        Syntax:
            !botservers
        """

        lines = [f"{g.name} (ID: {g.id})" for g in self.bot.guilds]

        embed = build_embed('🤖 Bot is in the following guilds:', '\n'.join(lines) or "None", 'p')
        embed.set_footer(text=f"Total guilds: {len(lines)}")
        await ctx.send(embed=embed)

    @commands.command(name="botsync")
    @requires_owner_perms()
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

    @commands.group(name="permissions", aliases=["perms", "roles"])
    @requires_author_perms()
    async def trigger_permissions(self, ctx: commands.Context):
        """
        BOT MOD. Modifies bot permissions for the server.
        """

        if not ctx.invoked_subcommand:
            allstates = self.bot.settings[ctx.guild.id]

            user_lines = [   # build users list
                f"{(await self.bot.fetch_user(u)).display_name} (id:{u})"
                for u in allstates.perms["user_id"]
            ]
            owner = await self.bot.fetch_user(ctx.guild.owner_id)    # required to get the owner's name
            user_lines.insert(0, f"{owner.display_name} (id: {ctx.guild.owner_id})")
            users = "\n".join(user_lines)

            roles = "\n".join(   # build roles list
                f"{(role := discord.utils.get(ctx.guild.roles, id=id)).name} (id: {id})"
                for id in allstates.perms["role_id"]
            )

            channels = "\n".join(   # build channels list
                f"#{(channel := self.bot.get_channel(id)).name} (id: {id})"
                for id in allstates.perms["channel_id"]
            )

            embed = build_embed(f"Permissions for {ctx.guild.name}", "The following channels are enabled for bot commands, and the following users and roles are permitted for elevated permissions.", 'p')
            embed.add_field(name="Users:", value=users, inline=False)
            embed.add_field(name="Roles:", value=roles, inline=False)
            embed.add_field(name="Channels:", value=channels, inline=False)
            await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return

    @trigger_permissions.command(name="add")
    @requires_author_perms()
    async def trigger_permissions_add(
        self,
        ctx: commands.Context,
        group: Literal["channel", "role", "user"] | None,
        target: int | None
    ) -> None:
        """
        BOT MOD. Modifies bot permissions for the server.
        """

        allstates = self.bot.settings[ctx.guild.id]

        if not group or not target:    # syntax error
            raise FancyError(ERROR_CODES["syntax"])

        target = int(target)    # convert to int
        
        if target in allstates.perms[f"{group}_id"]:
            raise FancyError(ERROR_CODES["permissions_exist"])

        allstates.perms[f"{group}_id"].append(target)

        allstates._save_settings()
        await ctx.reply(f"Successfully added {target} to {group}.", allowed_mentions=discord.AllowedMentions.none())

    @trigger_permissions.command(name="remove")
    @requires_author_perms()
    async def trigger_permissions_remove(
        self,
        ctx: commands.Context,
        group: Literal["channel", "role", "user"] | None,
        target: int | None
    ) -> None:
        """
        BOT MOD. Modifies bot permissions for the server.
        """

        allstates = self.bot.settings[ctx.guild.id]

        if not group or not target:    # syntax error
            raise FancyError(ERROR_CODES["syntax"])

        target = int(target)    # convert to int

        if target not in allstates.perms[f"{group}_id"]:
            raise FancyError(ERROR_CODES["permissions_exist"])

        allstates.perms[f"{group}_id"].remove(target)

        allstates._save_settings()
        await ctx.reply(f"Successfully removed {target} from {group}.", allowed_mentions=discord.AllowedMentions.none())


####################################################################
# Launch Cog
####################################################################

async def setup(bot: commands.Bot):
    log_cog.info("Loading [dark_orange]Core[/] cog…")
    await bot.add_cog(Core(bot))