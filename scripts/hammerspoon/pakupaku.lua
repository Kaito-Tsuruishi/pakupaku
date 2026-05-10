-- pakupaku: Hammerspoon hotkey integration
--
-- このファイルを Hammerspoon の init.lua から require する想定:
--   require("pakupaku")
--
-- または ~/.hammerspoon/init.lua にこの内容をそのまま貼り付けても OK。
--
-- macOS の権限要件:
--   - Hammerspoon にアクセシビリティ権限・入力監視権限を付与すること

require("hs.ipc")

local socketPath = os.getenv("HOME") .. "/.pakupaku/pakupaku.sock"
local isRecording = false

-- 進捗表示 (画面下端に小さく半透明で出っぱなし、置き換え式)
local statusAlertId = nil

local statusAlertStyle = {
    textSize = 16,
    radius = 6,
    strokeWidth = 0,
    fillColor = {white = 0.1, alpha = 0.75},
    textColor = {white = 0.95},
    atScreenEdge = 2,
}

-- フォーカス中ウィンドウのディスプレイを返す。フォーカスがなければメインディスプレイ。
local function targetScreen()
    local win = hs.window.focusedWindow()
    if win ~= nil then
        local screen = win:screen()
        if screen ~= nil then
            return screen
        end
    end
    return hs.screen.mainScreen()
end

-- 進捗を表示する。message が空文字列または nil なら現在のアラートを消す。
-- daemon から hs CLI 経由で呼ばれる (例: hs -c 'pakupakuStatus("処理中...")')
function pakupakuStatus(message)
    if statusAlertId ~= nil then
        hs.alert.closeSpecific(statusAlertId)
        statusAlertId = nil
    end
    if message ~= nil and message ~= "" then
        statusAlertId = hs.alert.show(message, statusAlertStyle, targetScreen(), 99999)
    end
end

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
    else
        sendCommand("start")
        isRecording = true
    end
end)

-- ⌃⇧Esc: 強制リセット (録音状態の手動同期)
hs.hotkey.bind({"ctrl", "shift"}, "escape", function()
    isRecording = false
    sendCommand("stop")
    pakupakuStatus("")
    hs.alert.show("pakupaku reset", 0.5)
end)

print("pakupaku: hotkey loaded (ctrl+shift+space)")
