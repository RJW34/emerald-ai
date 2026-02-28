--[[
    Emerald Bridge — mGBA Lua Socket Bridge
    Runs INSIDE mGBA-qt. Provides TCP server on port 8779
    for external control of the emulator.

    Protocol: JSON-lines (one JSON object per line, newline-terminated)

    Commands:
      {"action": "press", "button": "A"}                   → tap A for 6 frames
      {"action": "press", "button": "Up", "frames": 12}    → hold Up for 12 frames
      {"action": "hold", "button": "B", "frames": 30}      → hold B for 30 frames
      {"action": "release", "button": "B"}                  → release B immediately
      {"action": "state"}                                   → game state + frame count
      {"action": "ping"}                                    → connection test
      {"action": "screenshot", "path": "/tmp/screen.png"}   → save screenshot
      {"action": "input_state"}                             → current input queue

    Responses:
      {"ok": true, ...}  on success
      {"error": "..."}   on failure

    Load in mGBA: Tools → Scripting → File → Load Script
    Or: mGBA-qt --script emerald_bridge.lua ROM.gba
]]

-- ============================================================
-- Configuration
-- ============================================================
local LISTEN_PORT = 8779
local STATE_READ_INTERVAL = 4    -- read state every N frames (~15 Hz)

-- ============================================================
-- Gen3 character decoding
-- ============================================================
local GEN3_CHARS = {}
for i = 0, 25 do GEN3_CHARS[0xBB + i] = string.char(65 + i) end
for i = 0, 25 do GEN3_CHARS[0xD5 + i] = string.char(97 + i) end
for i = 0, 9 do GEN3_CHARS[0xA1 + i] = string.char(48 + i) end
GEN3_CHARS[0x00] = " "
GEN3_CHARS[0xAB] = "!"
GEN3_CHARS[0xAC] = "?"
GEN3_CHARS[0xAD] = "."
GEN3_CHARS[0xAE] = "-"
GEN3_CHARS[0xB4] = "'"

-- GBA Key mapping
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

-- Species names (common Hoenn + starters)
local SPECIES_NAMES = {
    [252]="Treecko", [253]="Grovyle", [254]="Sceptile",
    [255]="Torchic", [256]="Combusken", [257]="Blaziken",
    [258]="Mudkip", [259]="Marshtomp", [260]="Swampert",
    [261]="Poochyena", [262]="Mightyena", [263]="Zigzagoon", [264]="Linoone",
    [265]="Wurmple", [270]="Lotad", [273]="Seedot",
    [276]="Taillow", [278]="Wingull", [280]="Ralts",
    [285]="Shroomish", [287]="Slakoth", [293]="Whismur",
    [296]="Makuhita", [300]="Skitty", [304]="Aron",
    [309]="Electrike", [318]="Carvanha", [322]="Numel",
    [324]="Torkoal", [328]="Trapinch", [333]="Swablu",
    [339]="Barboach", [341]="Corphish", [343]="Baltoy",
    [349]="Feebas", [352]="Kecleon", [359]="Absol",
    [371]="Bagon", [374]="Beldum",
    [25]="Pikachu", [41]="Zubat", [63]="Abra",
    [66]="Machop", [72]="Tentacool", [74]="Geodude",
    [81]="Magnemite", [129]="Magikarp", [183]="Marill",
}

-- Map names
local MAP_NAMES = {
    ["0,0"]="Petalburg City", ["0,1"]="Slateport City", ["0,2"]="Mauville City",
    ["0,3"]="Rustboro City", ["0,4"]="Fortree City", ["0,5"]="Lilycove City",
    ["0,6"]="Mossdeep City", ["0,7"]="Sootopolis City", ["0,8"]="Ever Grande City",
    ["0,9"]="Littleroot Town", ["0,10"]="Oldale Town", ["0,11"]="Dewford Town",
    ["0,12"]="Lavaridge Town", ["0,13"]="Fallarbor Town", ["0,14"]="Verdanturf Town",
    ["0,15"]="Pacifidlog Town",
}
for r = 101, 134 do MAP_NAMES["0," .. (r - 85)] = "Route " .. r end

local BADGE_NAMES = {"Stone","Knuckle","Dynamo","Heat","Balance","Feather","Mind","Rain"}

-- ============================================================
-- Minimal JSON encoder/decoder
-- ============================================================
local json = {}

function json.encode(val)
    local t = type(val)
    if val == nil then return "null"
    elseif t == "boolean" then return val and "true" or "false"
    elseif t == "number" then
        if val ~= val then return "null" end
        if val == math.floor(val) and val >= -2147483648 and val <= 2147483647 then
            return string.format("%d", val)
        end
        return tostring(val)
    elseif t == "string" then
        local escaped = val:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
        escaped = escaped:gsub('[\x00-\x1f]', function(c) return string.format('\\u%04x', string.byte(c)) end)
        return '"' .. escaped .. '"'
    elseif t == "table" then
        local is_array = true
        local max_i = 0
        local count = 0
        for k, _ in pairs(val) do
            count = count + 1
            if type(k) == "number" and k == math.floor(k) and k >= 1 then
                if k > max_i then max_i = k end
            else
                is_array = false
                break
            end
        end
        if is_array and max_i == count then
            local parts = {}
            for i = 1, #val do parts[i] = json.encode(val[i]) end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(val) do
                parts[#parts + 1] = json.encode(tostring(k)) .. ":" .. json.encode(v)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

function json.decode(str)
    if not str or str == "" then return nil end
    str = str:match("^%s*(.-)%s*$")
    if str == "" then return nil end
    local pos = 1
    local function skip_ws() pos = str:find("[^ \t\r\n]", pos) or (#str + 1) end
    local parse_value
    local function parse_string()
        if str:sub(pos, pos) ~= '"' then return nil end
        pos = pos + 1
        local result = {}
        while pos <= #str do
            local c = str:sub(pos, pos)
            if c == '"' then pos = pos + 1; return table.concat(result)
            elseif c == '\\' then
                pos = pos + 1
                local esc = str:sub(pos, pos)
                if esc == '"' then result[#result+1] = '"'
                elseif esc == '\\' then result[#result+1] = '\\'
                elseif esc == 'n' then result[#result+1] = '\n'
                elseif esc == 'r' then result[#result+1] = '\r'
                elseif esc == 't' then result[#result+1] = '\t'
                else result[#result+1] = esc end
                pos = pos + 1
            else result[#result+1] = c; pos = pos + 1 end
        end
        return nil
    end
    local function parse_number()
        local start = pos
        if str:sub(pos, pos) == '-' then pos = pos + 1 end
        while pos <= #str and str:sub(pos, pos):match("%d") do pos = pos + 1 end
        if pos <= #str and str:sub(pos, pos) == '.' then
            pos = pos + 1
            while pos <= #str and str:sub(pos, pos):match("%d") do pos = pos + 1 end
        end
        if pos <= #str and str:sub(pos, pos):match("[eE]") then
            pos = pos + 1
            if pos <= #str and str:sub(pos, pos):match("[%+%-]") then pos = pos + 1 end
            while pos <= #str and str:sub(pos, pos):match("%d") do pos = pos + 1 end
        end
        return tonumber(str:sub(start, pos - 1))
    end
    local function parse_object()
        pos = pos + 1
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
        pos = pos + 1
        local arr = {}
        skip_ws()
        if str:sub(pos, pos) == ']' then pos = pos + 1; return arr end
        while true do
            arr[#arr+1] = parse_value()
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
-- Memory reading
-- ============================================================
local function decode_gen3_string(addr, max_len)
    local chars = {}
    for i = 0, (max_len or 7) - 1 do
        local byte = emu:read8(addr + i)
        if byte == 0xFF then break end
        chars[#chars + 1] = GEN3_CHARS[byte] or "?"
    end
    return table.concat(chars)
end

local cached_state = {}
local last_state_frame = -999

local function read_game_state()
    local frame = emu:currentFrame()
    if (frame - last_state_frame) < STATE_READ_INTERVAL then
        return cached_state
    end
    last_state_frame = frame

    local state = { frame = frame, scene = "unknown" }

    -- SaveBlock pointers from IWRAM
    local sb1_ptr = emu:read32(0x03005D8C)
    local sb2_ptr = emu:read32(0x03005D90)

    local sb1_valid = (sb1_ptr >= 0x02000000 and sb1_ptr <= 0x0203FFFF)
    local sb2_valid = (sb2_ptr >= 0x02000000 and sb2_ptr <= 0x0203FFFF)

    if not sb1_valid or not sb2_valid then
        state.scene = "title_screen"
        cached_state = state
        return state
    end

    -- Player name
    local player_name = decode_gen3_string(sb2_ptr + 0x00, 8)
    state.player_name = player_name

    if player_name == "" then
        state.scene = "title_screen"
        cached_state = state
        return state
    end

    -- Position
    state.pos_x = emu:read16(sb1_ptr + 0x00)
    state.pos_y = emu:read16(sb1_ptr + 0x02)
    state.map_group = emu:read8(sb1_ptr + 0x04)
    state.map_num = emu:read8(sb1_ptr + 0x05)
    local map_key = state.map_group .. "," .. state.map_num
    state.location = MAP_NAMES[map_key] or ("Map " .. map_key)

    -- Play time
    state.play_hours = emu:read16(sb2_ptr + 0x0E)
    state.play_minutes = emu:read8(sb2_ptr + 0x10)
    state.play_seconds = emu:read8(sb2_ptr + 0x11)

    -- Gender
    state.gender = emu:read8(sb2_ptr + 0x08) == 0 and "Male" or "Female"

    -- Party
    state.party_count = emu:read32(sb1_ptr + 0x234)
    if state.party_count > 6 then state.party_count = 0 end

    local SUB_ORDERS = {
        [0]={0,1,2,3}, [1]={0,1,3,2}, [2]={0,2,1,3}, [3]={0,3,1,2},
        [4]={0,2,3,1}, [5]={0,3,2,1}, [6]={1,0,2,3}, [7]={1,0,3,2},
        [8]={2,0,1,3}, [9]={3,0,1,2}, [10]={2,0,3,1}, [11]={3,0,2,1},
        [12]={1,2,0,3}, [13]={1,3,0,2}, [14]={2,1,0,3}, [15]={3,1,0,2},
        [16]={2,3,0,1}, [17]={3,2,0,1}, [18]={1,2,3,0}, [19]={1,3,2,0},
        [20]={2,1,3,0}, [21]={3,1,2,0}, [22]={2,3,1,0}, [23]={3,2,1,0},
    }

    state.party = {}
    for i = 0, math.min(state.party_count, 6) - 1 do
        local base = sb1_ptr + 0x238 + (i * 100)
        local mon = {}
        mon.personality = emu:read32(base + 0x00)
        mon.ot_id = emu:read32(base + 0x04)
        mon.nickname = decode_gen3_string(base + 0x08, 10)
        mon.level = emu:read8(base + 0x54)
        mon.hp = emu:read16(base + 0x56)
        mon.max_hp = emu:read16(base + 0x58)

        -- Decrypt species
        local key = (mon.personality ~ mon.ot_id)
        local order = SUB_ORDERS[mon.personality % 24]
        if order then
            local growth_pos = -1
            for p = 1, 4 do
                if order[p] == 0 then growth_pos = p - 1; break end
            end
            if growth_pos >= 0 then
                local growth_addr = base + 0x20 + (growth_pos * 12)
                local encrypted_word = emu:read32(growth_addr)
                local decrypted = (encrypted_word ~ key)
                mon.species_id = (decrypted & 0xFFFF)
                mon.species = SPECIES_NAMES[mon.species_id] or ("Pokemon #" .. mon.species_id)
            end
        end

        state.party[i + 1] = mon
    end

    -- Money (encrypted)
    local money_raw = emu:read32(sb1_ptr + 0x0490)
    local money_key = emu:read32(sb2_ptr + 0xAC)
    state.money = (money_raw ~ money_key)
    if state.money > 999999 then state.money = 0 end

    -- Badges
    state.badge_count = 0
    state.badges = {}
    for badge = 0, 7 do
        local flag_id = 0x807 + badge
        local byte_offset = math.floor(flag_id / 8)
        local bit_offset = flag_id % 8
        local flag_byte = emu:read8(sb1_ptr + 0x1270 + byte_offset)
        local has = (flag_byte & (1 << bit_offset)) ~= 0
        state.badges[badge + 1] = has
        if has then
            state.badge_count = state.badge_count + 1
        end
    end

    -- Battle detection
    local battle_type = emu:read32(0x02022B4C)
    if battle_type ~= 0 then
        state.scene = "battle"
        state.battle_type = battle_type
    else
        state.scene = "overworld"
    end

    cached_state = state
    return state
end

-- ============================================================
-- Input queue
-- ============================================================
local input_queue = {}
local held_keys = {}  -- keys held indefinitely until released

local function queue_input(key_name, frames)
    local key_const = KEY_MAP[key_name:upper()]
    if not key_const then
        return false, "unknown button: " .. key_name
    end
    input_queue[#input_queue + 1] = {key = key_const, name = key_name:upper(), frames = frames or 6}
    return true
end

local function hold_key(key_name)
    local key_const = KEY_MAP[key_name:upper()]
    if not key_const then
        return false, "unknown button: " .. key_name
    end
    held_keys[key_name:upper()] = key_const
    return true
end

local function release_key(key_name)
    local key_const = KEY_MAP[key_name:upper()]
    if not key_const then
        return false, "unknown button: " .. key_name
    end
    held_keys[key_name:upper()] = nil
    emu:clearKey(key_const)
    return true
end

local function process_inputs()
    -- Process timed inputs
    local i = 1
    while i <= #input_queue do
        local entry = input_queue[i]
        if entry.frames > 0 then
            emu:addKey(entry.key)
            entry.frames = entry.frames - 1
            i = i + 1
        else
            emu:clearKey(entry.key)
            table.remove(input_queue, i)
        end
    end

    -- Process indefinite holds
    for _, key_const in pairs(held_keys) do
        emu:addKey(key_const)
    end
end

-- ============================================================
-- TCP Server
-- ============================================================
local server = nil
local client = nil
local recv_buffer = ""

local function start_server()
    local ok, err = pcall(function()
        server = socket.bind(nil, LISTEN_PORT)
        if server then
            server:listen(1)
            console:log("[bridge] TCP server on port " .. LISTEN_PORT)
        else
            console:error("[bridge] Failed to bind port " .. LISTEN_PORT)
        end
    end)
    if not ok then
        console:error("[bridge] Bind error: " .. tostring(err))
    end
end

local function handle_command(cmd_obj)
    if not cmd_obj or type(cmd_obj) ~= "table" then
        return {error = "invalid command"}
    end

    local action = cmd_obj.action or cmd_obj.cmd
    if not action then
        return {error = "missing 'action' field"}
    end

    if action == "ping" then
        return {ok = true, frame = emu:currentFrame()}

    elseif action == "state" then
        last_state_frame = -999
        local s_ok, result = pcall(read_game_state)
        if s_ok then
            return result
        else
            return {error = "state_read_failed: " .. tostring(result), scene = "error"}
        end

    elseif action == "press" then
        local button = cmd_obj.button or cmd_obj.key
        local frames = cmd_obj.frames or 6
        if not button then return {error = "missing 'button' field"} end
        local ok, err = queue_input(button, frames)
        if ok then
            return {ok = true, button = button, frames = frames, queue_len = #input_queue}
        else
            return {error = err}
        end

    elseif action == "hold" then
        local button = cmd_obj.button or cmd_obj.key
        local frames = cmd_obj.frames
        if not button then return {error = "missing 'button' field"} end
        if frames then
            local ok, err = queue_input(button, frames)
            if ok then
                return {ok = true, button = button, frames = frames}
            else
                return {error = err}
            end
        else
            local ok, err = hold_key(button)
            if ok then
                return {ok = true, button = button, held = true}
            else
                return {error = err}
            end
        end

    elseif action == "release" then
        local button = cmd_obj.button or cmd_obj.key
        if not button then return {error = "missing 'button' field"} end
        local ok, err = release_key(button)
        if ok then
            return {ok = true, button = button, released = true}
        else
            return {error = err}
        end

    elseif action == "screenshot" then
        local path = cmd_obj.path or "/tmp/emerald_screen.png"
        local s_ok, s_err = pcall(function() emu:screenshot(path) end)
        if s_ok then
            return {ok = true, path = path}
        else
            return {error = "screenshot failed: " .. tostring(s_err)}
        end

    elseif action == "input_state" then
        local active = {}
        for _, entry in ipairs(input_queue) do
            active[#active + 1] = {name = entry.name, frames = entry.frames}
        end
        local holds = {}
        for name, _ in pairs(held_keys) do
            holds[#holds + 1] = name
        end
        return {ok = true, queue = active, queue_len = #input_queue, held = holds}

    elseif action == "read8" then
        local addr = cmd_obj.addr
        if not addr then return {error = "missing 'addr'"} end
        return {ok = true, value = emu:read8(addr)}

    elseif action == "read16" then
        local addr = cmd_obj.addr
        if not addr then return {error = "missing 'addr'"} end
        return {ok = true, value = emu:read16(addr)}

    elseif action == "read32" then
        local addr = cmd_obj.addr
        if not addr then return {error = "missing 'addr'"} end
        return {ok = true, value = emu:read32(addr)}

    else
        return {error = "unknown action: " .. tostring(action)}
    end
end

local function process_socket()
    if not server then return end

    -- Accept new connections
    if not client then
        local ok, err = pcall(function()
            if server:hasdata() then
                local new_client = server:accept()
                if new_client then
                    client = new_client
                    recv_buffer = ""
                    console:log("[bridge] Client connected")
                end
            end
        end)
        if not ok then
            console:warn("[bridge] Accept error: " .. tostring(err))
        end
    end

    -- Read from client
    if client then
        local ok, err = pcall(function()
            if client:hasdata() then
                local data, recv_err = client:receive(4096)
                if data then
                    recv_buffer = recv_buffer .. data
                    while true do
                        local nl = recv_buffer:find("\n")
                        if not nl then break end
                        local line = recv_buffer:sub(1, nl - 1):gsub("\r$", "")
                        recv_buffer = recv_buffer:sub(nl + 1)
                        if line ~= "" then
                            local cmd_obj = json.decode(line)
                            local response = handle_command(cmd_obj)
                            local resp_str = json.encode(response) .. "\n"
                            local s_ok, s_err = pcall(function() client:send(resp_str) end)
                            if not s_ok then
                                console:warn("[bridge] Send error: " .. tostring(s_err))
                                client = nil
                                recv_buffer = ""
                                return
                            end
                        end
                    end
                else
                    console:log("[bridge] Client disconnected: " .. tostring(recv_err))
                    client = nil
                    recv_buffer = ""
                end
            end
        end)
        if not ok then
            console:warn("[bridge] Socket error: " .. tostring(err))
            client = nil
            recv_buffer = ""
        end
    end
end

-- ============================================================
-- Frame callback
-- ============================================================
local frame_count = 0

local function on_frame()
    frame_count = frame_count + 1
    local ok, err = pcall(process_inputs)
    if not ok then console:warn("[bridge] Input error: " .. tostring(err)) end
    local s_ok, s_err = pcall(process_socket)
    if not s_ok then console:warn("[bridge] Socket error: " .. tostring(s_err)) end
    if frame_count % STATE_READ_INTERVAL == 0 then
        pcall(read_game_state)
    end
end

-- ============================================================
-- Init
-- ============================================================
console:log("========================================")
console:log("[bridge] Emerald Bridge v2.0 (port " .. LISTEN_PORT .. ")")
start_server()
callbacks:add("frame", on_frame)
console:log("[bridge] Ready! Waiting for connection...")
console:log("========================================")
