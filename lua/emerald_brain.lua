--[[
    Emerald Brain — mGBA Lua-Native Bridge
    Runs INSIDE mGBA-qt 0.10.2. Provides:
      - TCP server on port 8785 for external brain commands
      - Per-frame game state reading from Emerald memory map
      - Non-blocking socket I/O (never stalls the emulator)
      - JSON-lines protocol (one JSON object per line, newline-terminated)

    Commands:
      {"cmd": "ping"}                                    → {"ok": true}
      {"cmd": "state"}                                   → full game state JSON
      {"cmd": "press", "key": "A", "frames": 6}         → hold key for N frames
      {"cmd": "screenshot", "path": "/tmp/screen.png"}   → save screenshot
      {"cmd": "input_state"}                             → current input queue status

    mGBA Lua API reference: https://mgba.io/docs/scripting.html
    Emerald memory map: SaveBlock1/2 pointers in IWRAM
]]

-- ============================================================
-- Configuration
-- ============================================================
local LISTEN_PORT = 8785
local STATE_READ_INTERVAL = 4    -- read game state every N frames (4 ≈ 15 Hz)

-- ============================================================
-- Gen3 character decoding table (Pokemon Emerald encoding)
-- ============================================================
local GEN3_CHARS = {}
-- Uppercase A-Z: 0xBB-0xD4
for i = 0, 25 do GEN3_CHARS[0xBB + i] = string.char(65 + i) end
-- Lowercase a-z: 0xD5-0xEE
for i = 0, 25 do GEN3_CHARS[0xD5 + i] = string.char(97 + i) end
-- Digits 0-9: 0xA1-0xAA
for i = 0, 9 do GEN3_CHARS[0xA1 + i] = string.char(48 + i) end
-- Common symbols
GEN3_CHARS[0x00] = " "
GEN3_CHARS[0xAB] = "!"
GEN3_CHARS[0xAC] = "?"
GEN3_CHARS[0xAD] = "."
GEN3_CHARS[0xAE] = "-"
GEN3_CHARS[0xB0] = "\226\128\166" -- ellipsis
GEN3_CHARS[0xB1] = "\226\128\156" -- left double quote
GEN3_CHARS[0xB2] = "\226\128\157" -- right double quote
GEN3_CHARS[0xB3] = "\226\128\152" -- left single quote
GEN3_CHARS[0xB4] = "\226\128\153" -- right single quote
-- 0xFF = terminator (handled in decode function)

-- GBA Key name → C.GBA_KEY constant mapping
local KEY_MAP = {
    A      = C.GBA_KEY.A,
    B      = C.GBA_KEY.B,
    SELECT = C.GBA_KEY.SELECT,
    START  = C.GBA_KEY.START,
    RIGHT  = C.GBA_KEY.RIGHT,
    LEFT   = C.GBA_KEY.LEFT,
    UP     = C.GBA_KEY.UP,
    DOWN   = C.GBA_KEY.DOWN,
    R      = C.GBA_KEY.R,
    L      = C.GBA_KEY.L,
}

-- ============================================================
-- Minimal JSON encoder (mGBA has no json lib)
-- ============================================================
local json = {}

function json.encode(val)
    local t = type(val)
    if val == nil then
        return "null"
    elseif t == "boolean" then
        return val and "true" or "false"
    elseif t == "number" then
        if val ~= val then return "null" end          -- NaN
        if val == math.huge then return "1e308" end
        if val == -math.huge then return "-1e308" end
        -- Use integer format when possible
        if val == math.floor(val) and val >= -2147483648 and val <= 2147483647 then
            return string.format("%d", val)
        end
        return tostring(val)
    elseif t == "string" then
        -- Escape special characters
        local escaped = val:gsub('\\', '\\\\')
                           :gsub('"', '\\"')
                           :gsub('\n', '\\n')
                           :gsub('\r', '\\r')
                           :gsub('\t', '\\t')
        -- Escape control characters
        escaped = escaped:gsub('[\x00-\x1f]', function(c)
            return string.format('\\u%04x', string.byte(c))
        end)
        return '"' .. escaped .. '"'
    elseif t == "table" then
        -- Detect array vs object
        local is_array = true
        local max_index = 0
        local count = 0
        for k, _ in pairs(val) do
            count = count + 1
            if type(k) == "number" and k == math.floor(k) and k >= 1 then
                if k > max_index then max_index = k end
            else
                is_array = false
                break
            end
        end
        if is_array and max_index == count then
            -- Array
            local parts = {}
            for i = 1, #val do
                parts[i] = json.encode(val[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            -- Object
            local parts = {}
            for k, v in pairs(val) do
                parts[#parts + 1] = json.encode(tostring(k)) .. ":" .. json.encode(v)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

-- Minimal JSON decoder (handles the simple command objects we receive)
function json.decode(str)
    if not str or str == "" then return nil end
    str = str:match("^%s*(.-)%s*$")  -- trim
    if str == "" then return nil end

    local pos = 1

    local function skip_ws()
        pos = str:find("[^ \t\r\n]", pos) or (#str + 1)
    end

    local function peek()
        skip_ws()
        return str:sub(pos, pos)
    end

    local parse_value  -- forward declaration

    local function parse_string()
        if str:sub(pos, pos) ~= '"' then return nil end
        pos = pos + 1
        local result = {}
        while pos <= #str do
            local c = str:sub(pos, pos)
            if c == '"' then
                pos = pos + 1
                return table.concat(result)
            elseif c == '\\' then
                pos = pos + 1
                local esc = str:sub(pos, pos)
                if esc == '"' then result[#result + 1] = '"'
                elseif esc == '\\' then result[#result + 1] = '\\'
                elseif esc == '/' then result[#result + 1] = '/'
                elseif esc == 'n' then result[#result + 1] = '\n'
                elseif esc == 'r' then result[#result + 1] = '\r'
                elseif esc == 't' then result[#result + 1] = '\t'
                else result[#result + 1] = esc end
                pos = pos + 1
            else
                result[#result + 1] = c
                pos = pos + 1
            end
        end
        return nil  -- unterminated string
    end

    local function parse_number()
        local start = pos
        if str:sub(pos, pos) == '-' then pos = pos + 1 end
        while pos <= #str and str:sub(pos, pos):match("[%d]") do pos = pos + 1 end
        if pos <= #str and str:sub(pos, pos) == '.' then
            pos = pos + 1
            while pos <= #str and str:sub(pos, pos):match("[%d]") do pos = pos + 1 end
        end
        if pos <= #str and str:sub(pos, pos):match("[eE]") then
            pos = pos + 1
            if pos <= #str and str:sub(pos, pos):match("[%+%-]") then pos = pos + 1 end
            while pos <= #str and str:sub(pos, pos):match("[%d]") do pos = pos + 1 end
        end
        return tonumber(str:sub(start, pos - 1))
    end

    local function parse_object()
        pos = pos + 1  -- skip '{'
        local obj = {}
        skip_ws()
        if str:sub(pos, pos) == '}' then pos = pos + 1; return obj end
        while true do
            skip_ws()
            local key = parse_string()
            if not key then return nil end
            skip_ws()
            if str:sub(pos, pos) ~= ':' then return nil end
            pos = pos + 1
            local val = parse_value()
            obj[key] = val
            skip_ws()
            local c = str:sub(pos, pos)
            if c == '}' then pos = pos + 1; return obj end
            if c ~= ',' then return nil end
            pos = pos + 1
        end
    end

    local function parse_array()
        pos = pos + 1  -- skip '['
        local arr = {}
        skip_ws()
        if str:sub(pos, pos) == ']' then pos = pos + 1; return arr end
        while true do
            arr[#arr + 1] = parse_value()
            skip_ws()
            local c = str:sub(pos, pos)
            if c == ']' then pos = pos + 1; return arr end
            if c ~= ',' then return nil end
            pos = pos + 1
        end
    end

    parse_value = function()
        skip_ws()
        local c = str:sub(pos, pos)
        if c == '"' then return parse_string()
        elseif c == '{' then return parse_object()
        elseif c == '[' then return parse_array()
        elseif c == 't' then pos = pos + 4; return true
        elseif c == 'f' then pos = pos + 5; return false
        elseif c == 'n' then pos = pos + 4; return nil
        elseif c == '-' or c:match("%d") then return parse_number()
        end
        return nil
    end

    return parse_value()
end

-- ============================================================
-- Memory reading helpers
-- ============================================================

--- Decode a Gen3-encoded string from a bus address
local function decode_gen3_string(addr, max_len)
    local chars = {}
    for i = 0, (max_len or 7) - 1 do
        local byte = emu:read8(addr + i)
        if byte == 0xFF then break end  -- terminator
        chars[#chars + 1] = GEN3_CHARS[byte] or "?"
    end
    return table.concat(chars)
end

--- Read the full game state from memory. Returns a Lua table.
local cached_state = {}
local last_state_frame = -999

local function read_game_state()
    local frame = emu:currentFrame()
    -- Return cached if within interval
    if (frame - last_state_frame) < STATE_READ_INTERVAL then
        return cached_state
    end
    last_state_frame = frame

    local state = {
        frame = frame,
        scene = "unknown",
    }

    -- Read SaveBlock pointers from IWRAM
    local sb1_ptr = emu.memory.iwram:read32(0x5D8C)
    local sb2_ptr = emu.memory.iwram:read32(0x5D90)

    state.sb1_ptr = sb1_ptr
    state.sb2_ptr = sb2_ptr

    -- Validate pointers (must be in EWRAM range 0x02000000-0x0203FFFF)
    local sb1_valid = (sb1_ptr >= 0x02000000 and sb1_ptr <= 0x0203FFFF)
    local sb2_valid = (sb2_ptr >= 0x02000000 and sb2_ptr <= 0x0203FFFF)

    if not sb1_valid or not sb2_valid then
        state.scene = "title_screen"
        state.error = "invalid_sb_ptrs"
        cached_state = state
        return state
    end

    -- Player name from SB2+0x00 (up to 7 chars + terminator)
    local player_name = decode_gen3_string(sb2_ptr + 0x00, 8)
    state.player_name = player_name

    if player_name == "" then
        state.scene = "title_screen"
        cached_state = state
        return state
    end

    -- Position from SB1+0x00
    state.pos_x = emu:read16(sb1_ptr + 0x00)
    state.pos_y = emu:read16(sb1_ptr + 0x02)
    state.map_group = emu:read8(sb1_ptr + 0x04)
    state.map_num = emu:read8(sb1_ptr + 0x05)

    -- Play time from SB2+0x0E
    state.play_hours = emu:read16(sb2_ptr + 0x0E)
    state.play_minutes = emu:read8(sb2_ptr + 0x10)
    state.play_seconds = emu:read8(sb2_ptr + 0x11)

    -- Party count from SB1+0x234
    state.party_count = emu:read32(sb1_ptr + 0x234)
    if state.party_count > 6 then state.party_count = 0 end  -- sanity

    -- Party data: read species + level for each party member
    -- Each Pokemon struct is 100 bytes starting at SB1+0x238
    -- Species at offset 0x00 (within the Pokemon struct's "growth" substructure)
    -- For simplicity, read the decrypted fields that are at known positions
    -- In the party data, Pokemon are 100 bytes each:
    --   +0x00: personality (u32)
    --   +0x04: otId (u32)
    --   +0x08: nickname (10 bytes, gen3 encoded)
    --   +0x54: level (u8) — in the battle stats section at offset 0x54 from party start
    --   +0x20: data substructs start (48 bytes, encrypted with personality XOR otId)
    -- The "growth" substruct has species at offset 0 (u16)
    -- Substruct order depends on personality % 24
    -- For now, read nickname + level (unencrypted fields in party struct)
    state.party = {}
    for i = 0, math.min(state.party_count, 6) - 1 do
        local base = sb1_ptr + 0x238 + (i * 100)
        local mon = {}
        mon.personality = emu:read32(base + 0x00)
        mon.ot_id = emu:read32(base + 0x04)
        mon.nickname = decode_gen3_string(base + 0x08, 10)
        mon.level = emu:read8(base + 0x54)
        -- Current HP and max HP (in battle stats section)
        mon.hp = emu:read16(base + 0x56)
        mon.max_hp = emu:read16(base + 0x58)

        -- Decrypt species from the growth substruct
        -- Substructure order is determined by personality % 24
        -- Growth substruct is always one of the 4 positions
        local key = bit32.bxor(mon.personality, mon.ot_id)
        local sub_order_idx = mon.personality % 24
        -- Substruct order table (G=0, A=1, E=2, M=3)
        local SUB_ORDERS = {
            [0]  = {0,1,2,3}, [1]  = {0,1,3,2}, [2]  = {0,2,1,3}, [3]  = {0,3,1,2},
            [4]  = {0,2,3,1}, [5]  = {0,3,2,1}, [6]  = {1,0,2,3}, [7]  = {1,0,3,2},
            [8]  = {2,0,1,3}, [9]  = {3,0,1,2}, [10] = {2,0,3,1}, [11] = {3,0,2,1},
            [12] = {1,2,0,3}, [13] = {1,3,0,2}, [14] = {2,1,0,3}, [15] = {3,1,0,2},
            [16] = {2,3,0,1}, [17] = {3,2,0,1}, [18] = {1,2,3,0}, [19] = {1,3,2,0},
            [20] = {2,1,3,0}, [21] = {3,1,2,0}, [22] = {2,3,1,0}, [23] = {3,2,1,0},
        }

        local order = SUB_ORDERS[sub_order_idx]
        if order then
            -- Find which position the Growth substruct (0) is in
            local growth_pos = -1
            for p = 1, 4 do
                if order[p] == 0 then growth_pos = p - 1; break end
            end
            if growth_pos >= 0 then
                -- Each substruct is 12 bytes, starts at base + 0x20
                local growth_addr = base + 0x20 + (growth_pos * 12)
                -- Read first 4 bytes (encrypted), XOR with key
                local encrypted_word = emu:read32(growth_addr)
                local decrypted = bit32.bxor(encrypted_word, key)
                -- Species is the low 16 bits of the first word in Growth
                mon.species = bit32.band(decrypted, 0xFFFF)
                -- Item held is the high 16 bits
                mon.held_item = bit32.rshift(decrypted, 16)
            end
        end

        state.party[i + 1] = mon
    end

    -- Battle detection: check callback1 at IWRAM offset 0x22C0
    -- In Emerald, the main callback pointers are used to track game state
    -- callback1 is at IWRAM 0x030022C0 → IWRAM offset 0x22C0
    local callback1 = emu.memory.iwram:read32(0x22C0)
    state.callback1 = callback1

    -- Also read callback2 for more nuanced state detection
    local callback2 = emu.memory.iwram:read32(0x22C4)
    state.callback2 = callback2

    -- Scene classification
    if callback1 ~= 0 then
        -- callback1 being nonzero often indicates battle or special scene
        -- Known battle callback addresses in Emerald (US):
        -- 0x0803DA21 = BattleMainCB1 (approximate)
        -- For now, use a simpler heuristic: check battle flag
        -- gBattleTypeFlags at 0x02022B4C
        local battle_type = emu:read32(0x02022B4C)
        if battle_type ~= 0 then
            state.scene = "battle"
            state.battle_type = battle_type
        else
            state.scene = "overworld"
        end
    else
        state.scene = "overworld"
    end

    -- Trainer ID from SB2+0x0A
    state.trainer_id = emu:read16(sb2_ptr + 0x0A)
    state.secret_id = emu:read16(sb2_ptr + 0x0C)

    -- Gender from SB2+0x08
    state.gender = emu:read8(sb2_ptr + 0x08)

    -- Money from EWRAM — SB1+0x0490 (encrypted with encryption key at SB2+0xAC)
    -- For simplicity, read raw value; the brain can decrypt if needed
    state.money_raw = emu:read32(sb1_ptr + 0x0490)
    local money_key = emu:read32(sb2_ptr + 0xAC)
    state.money = bit32.bxor(state.money_raw, money_key)

    -- Badge flags: In Emerald US, badges are stored as event flags
    -- Specifically, badge flags are in SaveBlock2 at offset 0x?? 
    -- Actually: badges live in BADGE_01_GET through BADGE_08_GET flags
    -- These are flag IDs 0x807-0x80E, stored in SB1+0x1270 flag array
    -- Flag byte = (flag_id / 8), bit = (flag_id % 8)
    -- Flag 0x807 = badge 1 → byte 0x100, bit 7 → SB1+0x1270+0x100 bit 7
    local badge_count = 0
    local badges = {}
    for badge = 0, 7 do
        local flag_id = 0x807 + badge
        local byte_offset = math.floor(flag_id / 8)
        local bit_offset = flag_id % 8
        local flag_byte = emu:read8(sb1_ptr + 0x1270 + byte_offset)
        local has_badge = bit32.band(flag_byte, bit32.lshift(1, bit_offset)) ~= 0
        badges[badge + 1] = has_badge
        if has_badge then badge_count = badge_count + 1 end
    end
    state.badges = badges
    state.badge_count = badge_count

    cached_state = state
    return state
end

-- ============================================================
-- Input queue — handles key presses with frame durations
-- ============================================================
local input_queue = {}   -- list of {key_const, frames_remaining}

local function queue_input(key_name, frames)
    local key_const = KEY_MAP[key_name:upper()]
    if not key_const then
        return false, "unknown key: " .. key_name
    end
    input_queue[#input_queue + 1] = {key = key_const, frames = frames or 6}
    return true
end

local function process_inputs()
    -- Process all active inputs: add keys that have frames remaining
    local i = 1
    while i <= #input_queue do
        local entry = input_queue[i]
        if entry.frames > 0 then
            emu:addKey(entry.key)
            entry.frames = entry.frames - 1
            i = i + 1
        else
            -- Remove completed input
            emu:clearKey(entry.key)
            table.remove(input_queue, i)
            -- don't increment i since we removed
        end
    end
end

-- ============================================================
-- TCP Server — non-blocking socket handling
-- ============================================================
local server = nil
local client = nil
local recv_buffer = ""

local function start_server()
    local ok, err = pcall(function()
        server = socket.bind(nil, LISTEN_PORT)
        if server then
            server:listen(1)
            console:log("[emerald_brain] TCP server listening on port " .. LISTEN_PORT)
        else
            console:error("[emerald_brain] Failed to bind to port " .. LISTEN_PORT)
        end
    end)
    if not ok then
        console:error("[emerald_brain] Server bind error: " .. tostring(err))
    end
end

local function handle_command(cmd_obj)
    if not cmd_obj or type(cmd_obj) ~= "table" then
        return {error = "invalid command"}
    end

    local cmd = cmd_obj.cmd
    if not cmd then
        return {error = "missing 'cmd' field"}
    end

    if cmd == "ping" then
        return {ok = true, frame = emu:currentFrame()}

    elseif cmd == "state" then
        -- Force a fresh read
        last_state_frame = -999
        return read_game_state()

    elseif cmd == "press" then
        local key = cmd_obj.key
        local frames = cmd_obj.frames or 6
        if not key then
            return {error = "missing 'key' field"}
        end
        local ok, err = queue_input(key, frames)
        if ok then
            return {ok = true, key = key, frames = frames, queue_len = #input_queue}
        else
            return {error = err}
        end

    elseif cmd == "screenshot" then
        local path = cmd_obj.path or "/tmp/emerald_screen.png"
        local ok, err = pcall(function() emu:screenshot(path) end)
        if ok then
            return {ok = true, path = path}
        else
            return {error = "screenshot failed: " .. tostring(err)}
        end

    elseif cmd == "input_state" then
        local active = {}
        for _, entry in ipairs(input_queue) do
            active[#active + 1] = {key = entry.key, frames = entry.frames}
        end
        return {ok = true, queue = active, queue_len = #input_queue}

    elseif cmd == "read8" then
        local addr = cmd_obj.addr
        if not addr then return {error = "missing 'addr'"} end
        return {ok = true, value = emu:read8(addr)}

    elseif cmd == "read16" then
        local addr = cmd_obj.addr
        if not addr then return {error = "missing 'addr'"} end
        return {ok = true, value = emu:read16(addr)}

    elseif cmd == "read32" then
        local addr = cmd_obj.addr
        if not addr then return {error = "missing 'addr'"} end
        return {ok = true, value = emu:read32(addr)}

    else
        return {error = "unknown command: " .. tostring(cmd)}
    end
end

local function process_socket()
    if not server then return end

    -- Accept new connections (non-blocking: check hasdata first)
    if not client then
        local ok, err = pcall(function()
            if server:hasdata() then
                local new_client = server:accept()
                if new_client then
                    client = new_client
                    recv_buffer = ""
                    console:log("[emerald_brain] Client connected")
                end
            end
        end)
        if not ok then
            console:warn("[emerald_brain] Accept error: " .. tostring(err))
        end
    end

    -- Read from client (non-blocking)
    if client then
        local ok, err = pcall(function()
            if client:hasdata() then
                local data, recv_err = client:receive(4096)
                if data then
                    recv_buffer = recv_buffer .. data
                    -- Process complete lines (JSON-lines protocol)
                    while true do
                        local newline_pos = recv_buffer:find("\n")
                        if not newline_pos then break end

                        local line = recv_buffer:sub(1, newline_pos - 1)
                        recv_buffer = recv_buffer:sub(newline_pos + 1)

                        -- Strip carriage return if present
                        line = line:gsub("\r$", "")

                        if line ~= "" then
                            local cmd_obj = json.decode(line)
                            local response = handle_command(cmd_obj)
                            local response_str = json.encode(response) .. "\n"
                            local send_ok, send_err = pcall(function()
                                client:send(response_str)
                            end)
                            if not send_ok then
                                console:warn("[emerald_brain] Send error: " .. tostring(send_err))
                                client = nil
                                recv_buffer = ""
                                return
                            end
                        end
                    end
                else
                    -- Client disconnected or error
                    console:log("[emerald_brain] Client disconnected: " .. tostring(recv_err))
                    client = nil
                    recv_buffer = ""
                end
            end
        end)
        if not ok then
            console:warn("[emerald_brain] Socket read error: " .. tostring(err))
            client = nil
            recv_buffer = ""
        end
    end
end

-- ============================================================
-- Frame callback — the main loop
-- ============================================================
local frame_count = 0

local function on_frame()
    frame_count = frame_count + 1

    -- Process pending input holds
    local input_ok, input_err = pcall(process_inputs)
    if not input_ok then
        console:warn("[emerald_brain] Input error: " .. tostring(input_err))
    end

    -- Poll socket for commands (every frame for responsiveness)
    local sock_ok, sock_err = pcall(process_socket)
    if not sock_ok then
        console:warn("[emerald_brain] Socket error: " .. tostring(sock_err))
    end

    -- Periodically read game state to keep cache warm
    if frame_count % STATE_READ_INTERVAL == 0 then
        local state_ok, state_err = pcall(read_game_state)
        if not state_ok then
            console:warn("[emerald_brain] State read error: " .. tostring(state_err))
        end
    end
end

-- ============================================================
-- Initialization
-- ============================================================
console:log("========================================")
console:log("[emerald_brain] Emerald Brain v1.0")
console:log("[emerald_brain] Starting TCP server on port " .. LISTEN_PORT .. "...")
start_server()
console:log("[emerald_brain] Registering frame callback...")
callbacks:add("frame", on_frame)
console:log("[emerald_brain] Ready! Waiting for brain connection...")
console:log("========================================")
