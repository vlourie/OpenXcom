#pragma once
/*
 * Copyright 2010-2026 OpenXcom Developers.
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */
#include <cstddef>
#include <string>
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class LuaSandbox;
class SavedGame;
class TextButton;
class TextList;
class Text;
class Window;

/**
 * A screen of a Lua mod (docs/portal/LUA_MODS_V2.md, 5.1). The engine's widgets only, so the HD mirrors and the fonts
 * work by themselves. No frame handlers and no timers: Lua runs only when the player does something here.
 */
class LuaScreenState : public State
{
public:
	enum Kind { WINDOW, TEXT, BUTTON, TOGGLE, LIST, COMBO, EDIT, SLIDER, IMAGE };
	static const size_t MAX_WIDGETS = 64, MAX_ROWS = 2000, MAX_COLUMNS = 8, MAX_OPTIONS = 256, MAX_OPEN = 4;

	/// `category` is the interface the colors and the background come from.
	LuaScreenState(LuaSandbox *sandbox, const std::string &category);
	~LuaScreenState();

	/// What a handle of Lua names: null when that screen is closed.
	static LuaScreenState *find(unsigned long long id);
	/// The mod's screens the player has on the stack.
	static size_t openCount();
	/// For the mod's game.getBattle() and game.getGeoscape(), which have no object to start from.
	static SavedGame *savedGame();

	unsigned long long getId() const { return _id; }
	LuaSandbox *getSandbox() const { return _sandbox; }
	bool isBuilding() const { return _building; }
	bool isOnTop() const;
	Kind getKind(int widget) const { return _widgets[widget].kind; }
	size_t getWidgets() const { return _widgets.size(); }
	bool hasWindow() const { return _window != nullptr; }
	/// A picture of the game or of the mod's extraSprites?
	bool hasSurface(const std::string &name) const;

	int addWindow(int x, int y, int w, int h, const std::string &background);
	int addText(int x, int y, int w, int h, const std::string &text, bool big, int align, bool wrap);
	int addButton(int x, int y, int w, int h, const std::string &text);
	int addToggle(int x, int y, int w, int h, const std::string &text, bool pressed);
	int addList(int x, int y, int w, int h, const std::vector<int> &columns, bool selectable);
	int addCombo(int x, int y, int w, int h, const std::vector<std::string> &options, int selected);
	int addEdit(int x, int y, int w, int h, const std::string &text, bool focus);
	int addSlider(int x, int y, int w, int h, int low, int high, int value);
	int addImage(int x, int y, const std::string &image);
	void setHandlers(int widget, int onClick, int onChange, int onEnter, int color);
	void setScreenHandlers(int onKey, int onClose);
	/// The building is over: centers everything and takes the theme of the battle.
	void finish();

	void setVisible(int widget, bool visible);
	bool isVisible(int widget) const;
	void setText(int widget, const std::string &text);
	std::string getText(int widget) const;
	void setPressed(int widget, bool pressed);
	bool isPressed(int widget) const;
	void addRow(int widget, const std::vector<std::string> &cells);
	void clearList(int widget);
	void setCell(int widget, size_t row, size_t column, const std::string &text);
	int getSelected(int widget) const;
	void setSelected(int widget, int selected);
	size_t getRows(int widget) const;
	size_t getColumns(int widget) const;
	/// All lists of the screen: a list is the only widget a mod can grow after the building.
	size_t getScreenRows() const { return _rows; }
	void setOptions(int widget, const std::vector<std::string> &options);
	size_t getOptions(int widget) const;
	int getValue(int widget) const;
	void setValue(int widget, int value);
	void setRange(int widget, int low, int high);
	void setFocus(int widget);
	void setImage(int widget, const std::string &image);
	/// Closes when the running call is over: Lua may not take the state from under its own call.
	void askClose() { _closing = true; }

	void init() override;
	void handle(Action *action) override;
	void widgetClick(Action *action);
	void widgetChange(Action *action);
	void widgetEnter(Action *action);

private:
	/// The text for the player: a key of extraStrings or the text as it is.
	std::string say(const std::string &text) const;
	struct Widget
	{
		Kind kind;
		Surface *surface;
		int onClick = 0, onChange = 0, onEnter = 0, color = -1;
		int lastValue = 0;
		std::string lastText;
		size_t columns = 0, options = 0;
	};
	int put(Kind kind, Surface *surface, const char *element);
	void call(int fn, const char *what, int widget, int value, const std::string *text);
	void close();
	void afterCall();

	static unsigned long long _lastId;
	static std::vector<LuaScreenState*> _all;

	LuaSandbox *_sandbox;
	std::string _category;
	std::vector<Widget> _widgets;
	Window *_window = nullptr;
	unsigned long long _id;
	size_t _rows = 0;
	int _onKey = 0, _onClose = 0;
	bool _building = true, _shown = false, _closing = false;
};

/**
 * The list of the screens the mods declared for the player: game.screen(name, fn, { menu = "STR_NAME" }).
 */
class LuaModsState : public State
{
public:
	LuaModsState();
	void btnCancelClick(Action *action);
	void lstScreensClick(Action *action);

private:
	Window *_window;
	Text *_txtTitle;
	TextList *_lstScreens;
	TextButton *_btnCancel;
};

}
