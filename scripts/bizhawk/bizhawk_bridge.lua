--[[
BizHawk Bridge Script - File-based IPC for Python communication.

This script runs inside BizHawk and communicates with Python via files.
Simple, reliable, no socket setup required.

Usage:
    1. Load this script in BizHawk via Tools → Lua Console → Open Script
    2. Python writes commands to command.txt
    3. Lua reads, executes, writes response to response.txt
    4. Python reads response

Commands:
    PING                    - Test connection (returns OK PONG)
    READ8 <addr>            - Read 1 byte from memory
    READ16 <addr>           - Read 2 bytes (little-endian)
    READ32 <addr>           - Read 4 bytes (little-endian)
    READRANGE <addr> <len>  - Read byte range (returns hex)
    WRITE8 <addr> <value>   - Write 1 byte to memory (0-255)
    WRITE16 <addr> <value>  - Write 2 bytes (little-endian, 0-65535)
    WRITE32 <addr> <value>  - Write 4 bytes (little-endian, 0-4294967295)
    TAP <button>            - Tap a button
    HOLD <button> <frames>  - Hold button for N frames
    SCREENSHOT <path>       - Save screenshot to file
    SAVESTATE <slot>        - Save state to slot (1-10)
    LOADSTATE <slot>        - Load state from slot (1-10)
    GAMETITLE               - Get ROM title
    GAMECODE                - Get game code
]]

-- Configuration - Auto-detect script directory from Lua source path
local SCRIPT_DIR = nil
local info = debug.getinfo(1, "S")
if info and info.source then
    local source = info.source:gsub("^@", "")
    -- Handle both Windows and Linux paths
    SCRIPT_DIR = source:match("(.+)[/\\]") or "."
    SCRIPT_DIR = SCRIPT_DIR .. "/"
end
-- Fallback if auto-detect fails
SCRIPT_DIR = SCRIPT_DIR or "/home/ryan/projects/emerald-ai/scripts/bizhawk/"

local COMMAND_FILE = SCRIPT_DIR .. "command.txt"
local RESPONSE_FILE = SCRIPT_DIR .. "response.txt"
local LOCK_FILE = SCRIPT_DIR .. "lock.txt"

-- State tracking for held buttons
local held_buttons = {}
local hold_frames = {}

-- Last command ID processed (to avoid reprocessing)
local last_command_id = ""

-- Button name mapping
local BUTTON_MAP = {
    A = "A",
    B = "B",
    Start = "Start",
    Select = "Select",
    Up = "Up",
    Down = "Down",
    Left = "Left",
    Right = "Right",
    L = "L",
    R = "R"
}

-- Read file contents
local function read_file(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local content = f:read("*all")
    f:close()
    return content
end

-- Write file contents
local function write_file(path, content)
    local f = io.open(path, "w")
    if not f then return false end
    f:write(content)
    f:close()
    return true
end

-- Check if file exists
local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

-- Delete file
local function delete_file(path)
    os.remove(path)
end

-- Parse command into parts
local function parse_command(cmd)
    local parts = {}
    for part in cmd:gmatch("%S+") do
        table.insert(parts, part)
    end
    return parts
end

-- Handle incoming command
-- Resolve GBA address to BizHawk domain + local offset
local function resolve_address(addr)
    if addr >= 0x02000000 and addr <= 0x0203FFFF then
        return "EWRAM", addr - 0x02000000
    elseif addr >= 0x03000000 and addr <= 0x03007FFF then
        return "IWRAM", addr - 0x03000000
    else
        return "System Bus", addr
    end
end

local function domain_read_u8(addr)
    local domain, local_addr = resolve_address(addr)
    return memory.read_u8(local_addr, domain)
end

local function domain_read_u16(addr)
    local domain, local_addr = resolve_address(addr)
    return memory.read_u16_le(local_addr, domain)
end

local function domain_read_u32(addr)
    local domain, local_addr = resolve_address(addr)
    return memory.read_u32_le(local_addr, domain)
end

local function domain_write_u8(addr, value)
    local domain, local_addr = resolve_address(addr)
    memory.write_u8(local_addr, value, domain)
end

local function domain_write_u16(addr, value)
    local domain, local_addr = resolve_address(addr)
    memory.write_u16_le(local_addr, value, domain)
end

local function domain_write_u32(addr, value)
    local domain, local_addr = resolve_address(addr)
    memory.write_u32_le(local_addr, value, domain)
end

local function handle_command(cmd)
    cmd = cmd:match("^%s*(.-)%s*$")  -- Trim whitespace

    local parts = parse_command(cmd)
    local command = parts[1]

    if not command then
        return "ERROR Empty command"
    end

    command = command:upper()

    -- PING - Test connection
    if command == "PING" then
        return "OK PONG"

    -- READ8 - Read single byte
    elseif command == "READ8" then
        local addr = tonumber(parts[2])
        if not addr then return "ERROR Invalid address" end
        local value = domain_read_u8(addr)
        return "OK " .. value

    -- READ16 - Read 2 bytes
    elseif command == "READ16" then
        local addr = tonumber(parts[2])
        if not addr then return "ERROR Invalid address" end
        local value = domain_read_u16(addr)
        return "OK " .. value

    -- READ32 - Read 4 bytes
    elseif command == "READ32" then
        local addr = tonumber(parts[2])
        if not addr then return "ERROR Invalid address" end
        local value = domain_read_u32(addr)
        return "OK " .. value

    -- WRITE8 - Write single byte
    elseif command == "WRITE8" then
        local addr = tonumber(parts[2])
        local value = tonumber(parts[3])
        if not addr then return "ERROR Invalid address" end
        if not value then return "ERROR Invalid value" end
        if value < 0 or value > 255 then return "ERROR Value out of range (0-255)" end
        domain_write_u8(addr, value)
        return "OK"

    -- WRITE16 - Write 2 bytes (little-endian)
    elseif command == "WRITE16" then
        local addr = tonumber(parts[2])
        local value = tonumber(parts[3])
        if not addr then return "ERROR Invalid address" end
        if not value then return "ERROR Invalid value" end
        if value < 0 or value > 65535 then return "ERROR Value out of range (0-65535)" end
        domain_write_u16(addr, value)
        return "OK"

    -- WRITE32 - Write 4 bytes (little-endian)
    elseif command == "WRITE32" then
        local addr = tonumber(parts[2])
        local value = tonumber(parts[3])
        if not addr then return "ERROR Invalid address" end
        if not value then return "ERROR Invalid value" end
        if value < 0 or value > 4294967295 then return "ERROR Value out of range (0-4294967295)" end
        domain_write_u32(addr, value)
        return "OK"

    -- READRANGE - Read byte range
    elseif command == "READRANGE" then
        local addr = tonumber(parts[2])
        local length = tonumber(parts[3])
        if not addr or not length then return "ERROR Invalid address or length" end
        local hex = ""
        for i = 0, length - 1 do
            hex = hex .. string.format("%02X", domain_read_u8(addr + i))
        end
        return "OK " .. hex

    -- TAP - Tap a button
    elseif command == "TAP" then
        local button = parts[2]
        if not button or not BUTTON_MAP[button] then
            return "ERROR Invalid button: " .. tostring(button)
        end
        held_buttons[button] = true
        hold_frames[button] = 6
        return "OK"

    -- HOLD - Hold button for N frames
    elseif command == "HOLD" then
        local button = parts[2]
        local frames = tonumber(parts[3]) or 6
        if not button or not BUTTON_MAP[button] then
            return "ERROR Invalid button: " .. tostring(button)
        end
        held_buttons[button] = true
        hold_frames[button] = frames
        return "OK"

    -- SCREENSHOT - Save screenshot
    elseif command == "SCREENSHOT" then
        local path = cmd:match("SCREENSHOT%s+(.+)")
        if not path then return "ERROR No path specified" end
        local ok, err = pcall(function() client.screenshot(path) end)
        if ok then return "OK" else return "ERROR " .. tostring(err) end

    -- SAVESTATE - Save state
    elseif command == "SAVESTATE" then
        local slot = tonumber(parts[2])
        if not slot or slot < 1 or slot > 10 then return "ERROR Invalid slot" end
        savestate.saveslot(slot)
        return "OK"

    -- LOADSTATE - Load state
    elseif command == "LOADSTATE" then
        local slot = tonumber(parts[2])
        if not slot or slot < 1 or slot > 10 then return "ERROR Invalid slot" end
        savestate.loadslot(slot)
        return "OK"

    -- GAMETITLE - Get ROM title
    elseif command == "GAMETITLE" then
        local title = gameinfo.getromname()
        return "OK " .. title

    -- GAMECODE - Get game code
    elseif command == "GAMECODE" then
        local code = ""
        for i = 0, 3 do
            code = code .. string.char(memory.read_u8(0x080000AC + i))
        end
        return "OK " .. code

    -- FRAMECOUNT - Get current frame
    elseif command == "FRAMECOUNT" then
        return "OK " .. emu.framecount()

    else
        return "ERROR Unknown command: " .. command
    end
end

-- Process held buttons each frame
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

-- Check for and process commands
local function process_commands()
    -- Check if command file exists
    if not file_exists(COMMAND_FILE) then
        return
    end
    
    -- Skip if locked (Python is writing)
    if file_exists(LOCK_FILE) then
        return
    end

    -- Read command file
    local content = read_file(COMMAND_FILE)
    if not content or content == "" then
        return
    end

    -- Parse command ID and command
    -- Format: "ID:COMMAND" where ID is a unique identifier
    local id, cmd = content:match("^([^:]+):(.+)$")

    if not id or not cmd then
        -- Old format without ID, just process as command
        cmd = content
        id = content
    end

    -- Skip if we already processed this command
    if id == last_command_id then
        return
    end

    -- Process the command
    local response = handle_command(cmd)

    -- Write response with same ID (atomic - create lock, write, delete lock)
    write_file(LOCK_FILE, "1")
    write_file(RESPONSE_FILE, id .. ":" .. response)
    delete_file(LOCK_FILE)

    -- Remember this command ID
    last_command_id = id

    -- Delete command file to signal we're ready for next
    delete_file(COMMAND_FILE)
end

-- Initialize
print("BizHawk Bridge (File IPC) initializing...")
print("Script directory: " .. SCRIPT_DIR)
print("Command file: " .. COMMAND_FILE)
print("Response file: " .. RESPONSE_FILE)

-- Clean up any stale files
delete_file(COMMAND_FILE)
delete_file(RESPONSE_FILE)
delete_file(LOCK_FILE)

-- Register frame callback with error protection
event.onframeend(function()
    local ok, err = pcall(function()
        process_commands()
        process_buttons()
    end)
    if not ok then
        print("[BRIDGE ERROR] " .. tostring(err))
        -- Don't crash - keep the bridge alive
    end
end)

print("")
print("BizHawk Bridge ready!")
print("Waiting for commands...")
