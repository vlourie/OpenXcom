# Мод пробы экранов API 2: банк и экран со всеми виджетами. Общий для снимков страницы и stage1.py.
RUL = """extraSprites:
  - type: S1_ICON.PNG
    singleImage: true
    files:
      0: Resources/s1_icon.png
extended:
  tags:
    GeoscapeGame:
      S1_BANK: int
extraStrings:
  - type: en-US
    strings:
      STR_S1_BANK: "THE PIRATE BANK"
      STR_S1_MENU_BANK: "Pirate bank"
      STR_S1_MENU_ALL: "All widgets"
      STR_S1_DEPOSIT: "Deposit 1000"
      STR_S1_WITHDRAW: "Take 1000"
      STR_S1_CLOSE: "Close"
      STR_S1_NOTE: "Your money stays in the bank between battles."
  - type: ru
    strings:
      STR_S1_BANK: "ПИРАТСКИЙ БАНК"
      STR_S1_MENU_BANK: "Пиратский банк"
      STR_S1_MENU_ALL: "Все виджеты"
      STR_S1_DEPOSIT: "Вложить 1000"
      STR_S1_WITHDRAW: "Забрать 1000"
      STR_S1_CLOSE: "Закрыть"
      STR_S1_NOTE: "Деньги лежат в банке и между боями."
"""

LUA = r'''
local function balance()
  return game.getGeoscape():getTag("S1_BANK")
end

game.screen("bank", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:text{ x = 40, y = 30, w = 240, h = 17, text = "STR_S1_BANK", big = true, align = "center" }
  ui:text{ x = 50, y = 52, w = 220, h = 18, text = "STR_S1_NOTE", wrap = true }
  local sum = ui:text{ x = 50, y = 76, w = 220, h = 10, text = "" }
  local log = ui:list{ x = 50, y = 90, w = 220, h = 34, columns = { 120, 80 } }
  local function show()
    sum:setText(tostring(balance()))
  end
  show()
  ui:button{ x = 50, y = 130, w = 106, h = 18, text = "STR_S1_DEPOSIT", onClick = function()
    game.getGeoscape():setTag("S1_BANK", balance() + 1000)
    game.log("S1 deposit", balance())
    log:addRow("+1000", tostring(balance()))
    show()
  end }
  ui:button{ x = 164, y = 130, w = 106, h = 18, text = "STR_S1_WITHDRAW", onClick = function()
    game.getGeoscape():setTag("S1_BANK", balance() - 1000)
    game.log("S1 withdraw", balance())
    log:addRow("-1000", tostring(balance()))
    show()
  end }
  ui:button{ x = 50, y = 154, w = 220, h = 18, text = "STR_S1_CLOSE", onClick = function()
    ui:close()
  end }
  ui:onClose(function() game.log("S1 bank closed") end)
  game.log("S1 bank built", tostring(game.getBattle() ~= nil), balance())
end, { menu = "STR_S1_MENU_BANK" })

game.screen("widgets", function(ui)
  ui:window{ x = 10, y = 6, w = 300, h = 188 }
  ui:text{ x = 20, y = 12, w = 280, h = 17, text = "STR_S1_MENU_ALL", big = true, align = "center" }
  ui:text{ x = 20, y = 32, w = 130, h = 10, text = "text, color", color = 133 }
  local toggle = ui:toggleButton{ x = 20, y = 44, w = 130, h = 16, text = "toggleButton", pressed = true, onClick = function(b)
    game.log("S1 toggle", tostring(b:isPressed()))
  end }
  local slider = ui:slider{ x = 20, y = 64, w = 130, h = 16, min = 0, max = 100, value = 40, onChange = function(s, v)
    game.log("S1 slider", v, s:getValue())
  end }
  local edit = ui:edit{ x = 20, y = 84, w = 130, h = 10, text = "edit", onChange = function(e, t)
    game.log("S1 edit", t)
  end, onEnter = function(e, t)
    game.log("S1 enter", t)
  end }
  local list = ui:list{ x = 160, y = 32, w = 140, h = 90, columns = { 70, 60 }, selectable = true, onClick = function(l, row)
    game.log("S1 row", row, l:getSelected())
  end }
  for i = 1, 30 do list:addRow("row " .. i, tostring(i * i)) end
  ui:comboBox{ x = 160, y = 126, w = 140, h = 16, options = { "first", "second", "third" }, selected = 2, onChange = function(c, n)
    game.log("S1 combo", n, c:getSelected())
  end }
  ui:image{ x = 20, y = 100, image = "S1_ICON.PNG", onClick = function() game.log("S1 image") end }
  ui:button{ x = 20, y = 170, w = 280, h = 18, text = "STR_S1_CLOSE", onClick = function() ui:close() end }
  ui:onKey(function(key) game.log("S1 key", key) end)
end, { menu = "STR_S1_MENU_ALL" })
'''

META = 'id: s1bank\nname: "s1bank"\nversion: 0.1\nmaster: "piratez"\nluaApi: 2\nluaCaps: [screens]\n'


def icon(path):
    """Значок 64×32 в индексах палитры игры: движок читает 8-битный PNG как есть."""
    from PIL import Image
    img = Image.new("P", (64, 32))
    img.putpalette([v for i in range(256) for v in (i, i, i)])
    img.putdata([16 + (x // 8) * 16 + y // 4 for y in range(32) for x in range(64)])
    img.save(path)


def write(mods):
    own = mods / "s1bank"
    (own / "lua").mkdir(parents=True)
    (own / "Ruleset").mkdir()
    (own / "Resources").mkdir()
    icon(own / "Resources/s1_icon.png")
    (own / "metadata.yml").write_text(META, encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(LUA, encoding="utf-8", newline="\n")
    (own / "Ruleset/s1.rul").write_text(RUL, encoding="utf-8", newline="\n")
