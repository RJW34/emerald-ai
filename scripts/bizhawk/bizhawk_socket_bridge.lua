--[[
BizHawk Socket Bridge - TCP socket communication with Python.

Uses BizHawk's built-in comm.socketServer* API to connect to a Python
TCP server for low-latency bidirectional communication.

IMPORTANT: BizHawk 2.6.2+ requires length-prefixed messages:
    Format: "{length} {message}"
    Example: "4 PONG" (length 4, message "PONG")

Setup:
    1. Start the Python socket server first (it listens on port)
    2. Load this script in BizHawk via Tools → Lua Console → Open Script
    3. The script will auto-connect to the Python server

Protocol:
    Python sends:  "{len} {command}"
    Lua responds:  "{len} {response}"

Commands (same as file-based bridge):
    PING                    → PONG
    READ8 <addr>            → OK <value>
    READ16 <addr>           → OK <value>
    READ32 <addr>           → OK <value>
    READRANGE <addr> <len>  → OK <hex_string>
    TAP <button>            → OK
    HOLD <button> <frames>  → OK
    PRESS <btns> <frames>   → OK
    SCREENSHOT <path>       → OK
    SAVESTATE <slot>        → OK
    LOADSTATE <slot>        → OK
    GAMETITLE               → OK <title>
    GAMECODE                → OK <code>
    FRAMECOUNT              → OK <frame>
    GETSTATE                → OK <json_state_dump>
]]

-- Configuration
local SERVER_IP = "127.0.0.1"
local SERVER_PORT = 51055
local POLL_INTERVAL = 0  -- Check every frame (fastest)

-- State tracking for held buttons
local held_buttons = {}
local hold_frames = {}

-- Button name mapping
local BUTTON_MAP = {
    A = "A", B = "B", Start = "Start", Select = "Select",
    Up = "Up", Down = "Down", Left = "Left", Right = "Right",
    L = "L", R = "R"
}

-- Connection state
local connected = false
local reconnect_timer = 0
local RECONNECT_DELAY = 60  -- frames between reconnect attempts

-- Memory addresses for bulk state reads (Emerald US - BPEE)
local MEM = {
    SAVE_BLOCK_1_PTR = 0x03005D8C,
    SAVE_BLOCK_2_PTR = 0x03005D90,
    BATTLE_TYPE_FLAGS = 0x02022FEC,
    BATTLE_MONS = 0x02024084,
    BATTLE_MON_SIZE = 88,
    BATTLE_WEATHER = 0x02024DB8,
    CALLBACK1 = 0x030022C0,
    CALLBACK2 = 0x030022C4,
    TEXT_PRINTERS = 0x020201B0,
}

-- ============================================================================
-- Length-prefixed message helpers (BizHawk 2.6.2+ protocol)
-- ============================================================================

local function send_response(msg)
    local prefixed = tostring(#msg) .. " " .. msg
    comm.socketServerSend(prefixed)
end

-- ============================================================================
-- Command Handlers
-- ============================================================================

local function parse_command(cmd)
    local parts = {}
    for part in cmd:gmatch("%S+") do
        table.insert(parts, part)
    end
    return parts
end

local function handle_command(cmd)
    cmd = cmd:match("^%s*(.-)%s*$")  -- trim
    local parts = parse_command(cmd)
    local command = parts[1]

    if not command then return "ERROR Empty command" end
    command = command:upper()

    if command == "PING" then
        return "PONG"

    elseif command == "READ8" then
        local addr = tonumber(parts[2])
        if not addr then return "ERROR Invalid address" end
        return "OK " .. memory.read_u8(addr)

    elseif command == "READ16" then
        local addr = tonumber(parts[2])
        if not addr then return "ERROR Invalid address" end
        return "OK " .. memory.read_u16_le(addr)

    elseif command == "READ32" then
        local addr = tonumber(parts[2])
        if not addr then return "ERROR Invalid address" end
        return "OK " .. memory.read_u32_le(addr)

    elseif command == "READRANGE" then
        local addr = tonumber(parts[2])
        local length = tonumber(parts[3])
        if not addr or not length then return "ERROR Invalid params" end
        if length > 4096 then return "ERROR Range too large (max 4096)" end
        local hex = ""
        for i = 0, length - 1 do
            hex = hex .. string.format("%02X", memory.read_u8(addr + i))
        end
        return "OK " .. hex

    elseif command == "TAP" then
        local button = parts[2]
        if not button or not BUTTON_MAP[button] then
            return "ERROR Invalid button: " .. tostring(button)
        end
        held_buttons[button] = true
        hold_frames[button] = 6
        return "OK"

    elseif command == "HOLD" then
        local button = parts[2]
        local frames = tonumber(parts[3]) or 6
        if not button or not BUTTON_MAP[button] then
            return "ERROR Invalid button"
        end
        held_buttons[button] = true
        hold_frames[button] = frames
        return "OK"

    elseif command == "PRESS" then
        local btns_str = parts[2]
        local frames = tonumber(parts[3]) or 1
        if not btns_str then return "ERROR No buttons" end
        for btn in btns_str:gmatch("[^,]+") do
            if BUTTON_MAP[btn] then
                held_buttons[btn] = true
                hold_frames[btn] = frames
            end
        end
        return "OK"

    elseif command == "SCREENSHOT" then
        local path = cmd:match("SCREENSHOT%s+(.+)")
        if not path then return "ERROR No path" end
        local ok, err = pcall(function() client.screenshot(path) end)
        if ok then return "OK" else return "ERROR " .. tostring(err) end

    elseif command == "SAVESTATE" then
        local slot = tonumber(parts[2])
        if not slot or slot < 1 or slot > 10 then return "ERROR Invalid slot" end
        savestate.saveslot(slot)
        return "OK"

    elseif command == "LOADSTATE" then
        local slot = tonumber(parts[2])
        if not slot or slot < 1 or slot > 10 then return "ERROR Invalid slot" end
        savestate.loadslot(slot)
        return "OK"

    elseif command == "GAMETITLE" then
        return "OK " .. gameinfo.getromname()

    elseif command == "GAMECODE" then
        local code = ""
        for i = 0, 3 do
            code = code .. string.char(memory.read_u8(0x080000AC + i))
        end
        return "OK " .. code

    elseif command == "FRAMECOUNT" then
        return "OK " .. emu.framecount()

    -- Bulk state read - returns all key game state in one call
    elseif command == "GETSTATE" then
        local sb1 = memory.read_u32_le(MEM.SAVE_BLOCK_1_PTR)
        local sb2 = memory.read_u32_le(MEM.SAVE_BLOCK_2_PTR)
        local battle_flags = memory.read_u32_le(MEM.BATTLE_TYPE_FLAGS)
        local cb1 = memory.read_u32_le(MEM.CALLBACK1)
        local cb2 = memory.read_u32_le(MEM.CALLBACK2)
        local frame = emu.framecount()

        -- Player position (from Save Block 1)
        local px, py, mg, mn = 0, 0, 0, 0
        if sb1 >= 0x02000000 and sb1 <= 0x0203FFFF then
            px = memory.read_u16_le(sb1 + 0x0)
            py = memory.read_u16_le(sb1 + 0x2)
            mg = memory.read_u8(sb1 + 0x4)
            mn = memory.read_u8(sb1 + 0x5)
        end

        local result = string.format(
            "OK sb1=%d sb2=%d bf=%d cb1=%d cb2=%d frame=%d px=%d py=%d mg=%d mn=%d",
            sb1, sb2, battle_flags, cb1, cb2, frame, px, py, mg, mn
        )

        -- If in battle, include battle mon data
        if battle_flags ~= 0 then
            local weather = memory.read_u16_le(MEM.BATTLE_WEATHER)
            -- Player lead (battler 0)
            local p_base = MEM.BATTLE_MONS
            local p_species = memory.read_u16_le(p_base + 0x00)
            local p_hp = memory.read_u16_le(p_base + 0x28)
            local p_maxhp = memory.read_u16_le(p_base + 0x2C)
            local p_level = memory.read_u8(p_base + 0x2A)
            -- Enemy lead (battler 1)
            local e_base = MEM.BATTLE_MONS + MEM.BATTLE_MON_SIZE
            local e_species = memory.read_u16_le(e_base + 0x00)
            local e_hp = memory.read_u16_le(e_base + 0x28)
            local e_maxhp = memory.read_u16_le(e_base + 0x2C)
            local e_level = memory.read_u8(e_base + 0x2A)

            result = result .. string.format(
                " weather=%d ps=%d php=%d pmhp=%d plv=%d es=%d ehp=%d emhp=%d elv=%d",
                weather, p_species, p_hp, p_maxhp, p_level,
                e_species, e_hp, e_maxhp, e_level
            )
        end

        return result

    else
        return "ERROR Unknown: " .. command
    end
end

-- ============================================================================
-- Button Processing
-- ============================================================================

local function process_buttons()
    local input_table = {}
    for button, held in pairs(held_buttons) do
        if held and hold_frames[button] and hold_frames[button] > 0 then
            input_table[BUTTON_MAP[button]] = true
            hold_frames[button] = hold_frames[button] - 1
        else
            held_buttons[button] = false
            hold_frames[button] = 0
        end
    end
    if next(input_table) then
        joypad.set(input_table)
    end
end

-- ============================================================================
-- Socket Communication
-- ============================================================================

local function try_connect()
    comm.socketServerSetIp(SERVER_IP)
    comm.socketServerSetPort(SERVER_PORT)
    comm.socketServerSetTimeout(100)  -- 100ms timeout for non-blocking

    -- Test connection with a ping
    local ok, _ = pcall(function()
        send_response("HELLO")
    end)

    if ok and comm.socketServerSuccessful() then
        connected = true
        console.log("Connected to Python server at " .. SERVER_IP .. ":" .. SERVER_PORT)
        return true
    else
        connected = false
        return false
    end
end

local function process_socket()
    if not connected then
        reconnect_timer = reconnect_timer + 1
        if reconnect_timer >= RECONNECT_DELAY then
            reconnect_timer = 0
            try_connect()
        end
        return
    end

    -- Try to receive a command
    local ok, raw = pcall(function()
        return comm.socketServerResponse()
    end)

    if not ok or not raw or raw == "" then
        -- Check if connection was lost
        if not comm.socketServerSuccessful() then
            connected = false
            console.log("Connection lost, will retry...")
        end
        return
    end

    -- Parse length-prefixed message: "{length} {message}"
    local msg_len, msg = raw:match("^(%d+)%s(.+)$")
    local command = msg or raw  -- fallback if no prefix

    -- Handle command and send response
    local response = handle_command(command)
    send_response(response)
end

-- ============================================================================
-- Main Loop
-- ============================================================================

print("========================================")
print("BizHawk Socket Bridge v1.0")
print("Server: " .. SERVER_IP .. ":" .. SERVER_PORT)
print("========================================")

-- Initial connection attempt
try_connect()

-- Register frame callback
event.onframeend(function()
    process_socket()
    process_buttons()
end)

print("Bridge running! Waiting for commands...")
