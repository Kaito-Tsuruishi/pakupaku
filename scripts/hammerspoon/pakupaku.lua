-- pakupaku: Hammerspoon hotkey integration
--
-- このファイルを Hammerspoon の init.lua から require する想定:
--   require("pakupaku")
--
-- または ~/.hammerspoon/init.lua にこの内容をそのまま貼り付けても OK。
--
-- macOS の権限要件:
--   - Hammerspoon にアクセシビリティ権限・入力監視権限を付与すること

local socketPath = os.getenv("HOME") .. "/.pakupaku/pakupaku.sock"
local isRecording = false

-- Unix ソケットに 1 行送る (非同期)
local function sendCommand(cmd)
    local client = hs.socket.new()
    client:connect(socketPath, function()
        client:write(cmd .. "\n", function()
            client:disconnect()
        end)
    end)
end

-- ⌃⇧Space: トグル方式 (押下で start、再押下で stop)
hs.hotkey.bind({"ctrl", "shift"}, "space", function()
    if isRecording then
        sendCommand("stop")
        isRecording = false
        hs.alert.show("⏹ pakupaku stop", 0.5)
    else
        sendCommand("start")
        isRecording = true
        hs.alert.show("⏺ pakupaku start", 0.5)
    end
end)

-- ⌃⇧Esc: 強制リセット (録音状態の手動同期)
hs.hotkey.bind({"ctrl", "shift"}, "escape", function()
    isRecording = false
    sendCommand("stop")
    hs.alert.show("pakupaku reset", 0.5)
end)

print("pakupaku: hotkey loaded (ctrl+shift+space)")
