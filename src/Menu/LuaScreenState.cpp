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
#include "LuaScreenState.h"
#include <algorithm>
#include <cstdarg>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/InteractiveSurface.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/LuaSandbox.h"
#include "../Engine/Options.h"
#include "../Interface/ComboBox.h"
#include "../Interface/Slider.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextEdit.h"
#include "../Interface/TextList.h"
#include "../Interface/ToggleTextButton.h"
#include "../Interface/Window.h"
#include "../Mod/LuaHost.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

unsigned long long LuaScreenState::_lastId = 0;
std::vector<LuaScreenState*> LuaScreenState::_all;

LuaScreenState::LuaScreenState(LuaSandbox *sandbox, const std::string &category) : _sandbox(sandbox), _category(category), _id(++_lastId)
{
	_screen = false;
	auto *saved = _game->getSavedGame();
	setInterface(_category, false, saved ? saved->getSavedBattle() : nullptr);
	_all.push_back(this);
}

LuaScreenState::~LuaScreenState()
{
	_all.erase(std::remove(_all.begin(), _all.end(), this), _all.end());
	// Lua may have been read again since: the functions kept here went with the old sandbox
	auto *host = LuaHost::active();
	if (host && host->isRunning(_sandbox))
	{
		std::vector<int> kept = { _onKey, _onClose };
		for (const auto &widget : _widgets)
		{
			kept.insert(kept.end(), { widget.onClick, widget.onChange, widget.onEnter });
		}
		for (int fn : kept)
		{
			if (fn)
			{
				_sandbox->drop(fn);
			}
		}
	}
}

LuaScreenState *LuaScreenState::find(unsigned long long id)
{
	for (auto *state : _all)
	{
		if (state->_id == id)
		{
			return state;
		}
	}
	return nullptr;
}

size_t LuaScreenState::openCount()
{
	return std::count_if(_all.begin(), _all.end(), [](const LuaScreenState *state) { return state->_shown; });
}

SavedGame *LuaScreenState::savedGame()
{
	return _game->getSavedGame();
}

bool LuaScreenState::isOnTop() const
{
	// a popup the end of a battle took away is in _all, but was never shown
	for (auto it = _all.rbegin(); it != _all.rend(); ++it)
	{
		if ((*it)->_shown)
		{
			return *it == this;
		}
	}
	return false;
}

bool LuaScreenState::hasSurface(const std::string &name) const
{
	return _game->getMod()->getSurface(name, false) != nullptr;
}

int LuaScreenState::put(Kind kind, Surface *surface, const char *element)
{
	add(surface, element, _category);
	Widget widget;
	widget.kind = kind;
	widget.surface = surface;
	_widgets.push_back(widget);
	return (int)_widgets.size() - 1;
}

int LuaScreenState::addWindow(int x, int y, int w, int h, const std::string &background)
{
	auto *window = new Window(this, w, h, x, y, POPUP_BOTH);
	const int index = put(WINDOW, window, "window");
	if (background.empty())
	{
		setWindowBackground(window, _category);
	}
	else
	{
		setWindowBackgroundImage(window, background);
		window->setInterfaceName(_category);
	}
	_window = window;
	return index;
}

int LuaScreenState::addText(int x, int y, int w, int h, const std::string &text, bool big, int align, bool wrap)
{
	auto *label = new Text(w, h, x, y);
	const int index = put(TEXT, label, "text");
	if (big)
	{
		label->setBig();
	}
	label->setAlign((TextHAlign)align);
	label->setWordWrap(wrap);
	label->setText(say(text));
	return index;
}

int LuaScreenState::addButton(int x, int y, int w, int h, const std::string &text)
{
	auto *button = new TextButton(w, h, x, y);
	const int index = put(BUTTON, button, "button");
	button->setText(say(text));
	button->onMouseClick((ActionHandler)&LuaScreenState::widgetClick);
	return index;
}

int LuaScreenState::addToggle(int x, int y, int w, int h, const std::string &text, bool pressed)
{
	auto *button = new ToggleTextButton(w, h, x, y);
	const int index = put(TOGGLE, button, "button");
	button->setText(say(text));
	button->setPressed(pressed);
	button->onMouseClick((ActionHandler)&LuaScreenState::widgetClick);
	return index;
}

int LuaScreenState::addList(int x, int y, int w, int h, const std::vector<int> &columns, bool selectable)
{
	auto *list = new TextList(w, h, x, y);
	const int index = put(LIST, list, "text");
	int c[MAX_COLUMNS] = { };
	std::copy(columns.begin(), columns.end(), c);
	list->setColumns((int)columns.size(), c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7]);
	list->setBackground(_window);
	list->setSelectable(selectable);
	if (selectable)
	{
		list->onMouseClick((ActionHandler)&LuaScreenState::widgetClick);
	}
	_widgets[index].columns = columns.size();
	return index;
}

int LuaScreenState::addCombo(int x, int y, int w, int h, const std::vector<std::string> &options, int selected)
{
	auto *combo = new ComboBox(this, w, h, x, y);
	const int index = put(COMBO, combo, "button");
	combo->setBackground(_window);
	std::vector<std::string> shown;
	for (const auto &option : options)
	{
		shown.push_back(say(option));
	}
	combo->setOptions(shown);
	combo->setSelected(selected);
	combo->onChange((ActionHandler)&LuaScreenState::widgetChange);
	_widgets[index].options = options.size();
	_widgets[index].lastValue = selected;
	return index;
}

int LuaScreenState::addEdit(int x, int y, int w, int h, const std::string &text, bool focus)
{
	auto *edit = new TextEdit(this, w, h, x, y);
	const int index = put(EDIT, edit, "text");
	edit->setText(text);
	edit->onChange((ActionHandler)&LuaScreenState::widgetChange);
	edit->onEnter((ActionHandler)&LuaScreenState::widgetEnter);
	if (focus)
	{
		edit->setFocus(true);
	}
	_widgets[index].lastText = text;
	return index;
}

int LuaScreenState::addSlider(int x, int y, int w, int h, int low, int high, int value)
{
	auto *slider = new Slider(w, h, x, y);
	const int index = put(SLIDER, slider, "button");
	slider->setRange(low, high);
	slider->setValue(value);
	slider->onChange((ActionHandler)&LuaScreenState::widgetChange);
	_widgets[index].lastValue = slider->getValue();
	return index;
}

int LuaScreenState::addImage(int x, int y, const std::string &image)
{
	auto *source = _game->getMod()->getSurface(image);
	auto *surface = new InteractiveSurface(source->getWidth(), source->getHeight(), x, y);
	const int index = put(IMAGE, surface, "text");
	source->blitNShade(surface, 0, 0);
	surface->onMouseClick((ActionHandler)&LuaScreenState::widgetClick);
	return index;
}

void LuaScreenState::setHandlers(int widget, int onClick, int onChange, int onEnter, int color)
{
	auto &w = _widgets[widget];
	w.onClick = onClick;
	w.onChange = onChange;
	w.onEnter = onEnter;
	w.color = color;
}

void LuaScreenState::setScreenHandlers(int onKey, int onClose)
{
	if (onKey)
	{
		if (_onKey)
		{
			_sandbox->drop(_onKey);
		}
		_onKey = onKey;
	}
	if (onClose)
	{
		if (_onClose)
		{
			_sandbox->drop(_onClose);
		}
		_onClose = onClose;
	}
}

void LuaScreenState::finish()
{
	centerAllSurfaces();
	auto *saved = _game->getSavedGame();
	if (saved && saved->getSavedBattle())
	{
		applyBattlescapeTheme(_category);
	}
	for (const auto &widget : _widgets)
	{
		if (widget.color >= 0)
		{
			widget.surface->setColor((Uint8)widget.color);
		}
	}
	_building = false;
}

void LuaScreenState::setVisible(int widget, bool visible)
{
	_widgets[widget].surface->setVisible(visible);
}

bool LuaScreenState::isVisible(int widget) const
{
	return _widgets[widget].surface->getVisible();
}

void LuaScreenState::setText(int widget, const std::string &text)
{
	auto &w = _widgets[widget];
	switch (w.kind)
	{
	case TEXT: static_cast<Text*>(w.surface)->setText(say(text)); break;
	case BUTTON:
	case TOGGLE: static_cast<TextButton*>(w.surface)->setText(say(text)); break;
	case EDIT:
		// what the player types: not a key of the strings
		static_cast<TextEdit*>(w.surface)->setText(text);
		w.lastText = text;
		break;
	default: break;
	}
}

std::string LuaScreenState::getText(int widget) const
{
	const auto &w = _widgets[widget];
	switch (w.kind)
	{
	case TEXT: return static_cast<Text*>(w.surface)->getText();
	case EDIT: return static_cast<TextEdit*>(w.surface)->getText();
	default: return std::string();
	}
}

void LuaScreenState::setPressed(int widget, bool pressed)
{
	static_cast<ToggleTextButton*>(_widgets[widget].surface)->setPressed(pressed);
}

bool LuaScreenState::isPressed(int widget) const
{
	return static_cast<ToggleTextButton*>(_widgets[widget].surface)->getPressed();
}

/**
 * A key of the mod's extraStrings, or the text as it is. getString writes a line to the log
 * for every text that is not a key: 5 ms a cell, 20 seconds on a list of 2000 rows.
 */
std::string LuaScreenState::say(const std::string &text) const
{
	return _game->getLanguage()->has(text) ? std::string(tr(text)) : text;
}

void LuaScreenState::addRow(int widget, const std::vector<std::string> &cells)
{
	auto &w = _widgets[widget];
	std::string shown[MAX_COLUMNS];
	for (size_t i = 0; i < cells.size() && i < MAX_COLUMNS; ++i)
	{
		shown[i] = say(cells[i]);
	}
	static_cast<TextList*>(w.surface)->addRow((int)w.columns, shown[0].c_str(), shown[1].c_str(), shown[2].c_str(), shown[3].c_str(),
		shown[4].c_str(), shown[5].c_str(), shown[6].c_str(), shown[7].c_str());
	++_rows;
}

void LuaScreenState::clearList(int widget)
{
	auto *list = static_cast<TextList*>(_widgets[widget].surface);
	_rows -= list->getTexts();
	list->clearList();
}

void LuaScreenState::setCell(int widget, size_t row, size_t column, const std::string &text)
{
	static_cast<TextList*>(_widgets[widget].surface)->setCellText(row, column, say(text));
}

int LuaScreenState::getSelected(int widget) const
{
	const auto &w = _widgets[widget];
	if (w.kind == LIST)
	{
		return static_cast<TextList*>(w.surface)->getSelectedRow();
	}
	return (int)static_cast<ComboBox*>(w.surface)->getSelected();
}

void LuaScreenState::setSelected(int widget, int selected)
{
	auto &w = _widgets[widget];
	static_cast<ComboBox*>(w.surface)->setSelected(selected);
	w.lastValue = selected;
}

size_t LuaScreenState::getRows(int widget) const
{
	return static_cast<TextList*>(_widgets[widget].surface)->getTexts();
}

size_t LuaScreenState::getColumns(int widget) const
{
	return _widgets[widget].columns;
}

void LuaScreenState::setOptions(int widget, const std::vector<std::string> &options)
{
	auto &w = _widgets[widget];
	std::vector<std::string> shown;
	for (const auto &option : options)
	{
		shown.push_back(say(option));
	}
	auto *combo = static_cast<ComboBox*>(w.surface);
	combo->setOptions(shown);
	combo->setSelected(0);
	w.options = options.size();
	w.lastValue = 0;
}

size_t LuaScreenState::getOptions(int widget) const
{
	return _widgets[widget].options;
}

int LuaScreenState::getValue(int widget) const
{
	return static_cast<Slider*>(_widgets[widget].surface)->getValue();
}

void LuaScreenState::setValue(int widget, int value)
{
	auto &w = _widgets[widget];
	auto *slider = static_cast<Slider*>(w.surface);
	slider->setValue(value);
	w.lastValue = slider->getValue();
}

void LuaScreenState::setRange(int widget, int low, int high)
{
	auto &w = _widgets[widget];
	auto *slider = static_cast<Slider*>(w.surface);
	slider->setRange(low, high);
	slider->setValue(slider->getValue());
	w.lastValue = slider->getValue();
}

void LuaScreenState::setFocus(int widget)
{
	static_cast<TextEdit*>(_widgets[widget].surface)->setFocus(true);
}

void LuaScreenState::setImage(int widget, const std::string &image)
{
	auto *surface = _widgets[widget].surface;
	surface->clear();
	_game->getMod()->getSurface(image)->blitNShade(surface, 0, 0);
}

void LuaScreenState::init()
{
	_shown = true;
	State::init();
}

void LuaScreenState::call(int fn, const char *what, int widget, int value, const std::string *text)
{
	if (auto *host = LuaHost::active())
	{
		host->callScreen(this, fn, what, false, widget, value, text);
	}
	afterCall();
}

void LuaScreenState::afterCall()
{
	if (_closing)
	{
		close();
	}
	auto *host = LuaHost::active();
	while (host)
	{
		auto *next = host->nextScreen();
		if (!next)
		{
			break;
		}
		_game->pushState(next);
	}
}

void LuaScreenState::close()
{
	_closing = false;
	if (_onClose)
	{
		// like the building: a screen that was opened and closed changed nothing
		if (auto *host = LuaHost::active())
		{
			host->callScreen(this, _onClose, "onClose", true, -1, LuaHost::NO_VALUE, nullptr);
		}
	}
	_shown = false;
	_all.erase(std::remove(_all.begin(), _all.end(), this), _all.end());
	_game->popState();
}

void LuaScreenState::handle(Action *action)
{
	if (action->getDetails()->type == SDL_KEYDOWN)
	{
		const SDLKey key = action->getDetails()->key.keysym.sym;
		// a mod cannot keep the player here, not even with the focus in its text field
		if (key == Options::keyCancel)
		{
			close();
			return;
		}
		if (_onKey && !_modal)
		{
			const std::string name = SDL_GetKeyName(key);
			call(_onKey, "onKey", -1, LuaHost::NO_VALUE, &name);
			if (std::find(_all.begin(), _all.end(), this) == _all.end())
			{
				return;
			}
		}
	}
	State::handle(action);
}

void LuaScreenState::widgetClick(Action *action)
{
	for (size_t i = 0; i < _widgets.size(); ++i)
	{
		const auto &w = _widgets[i];
		if (w.surface == action->getSender())
		{
			if (w.onClick)
			{
				call(w.onClick, "onClick", (int)i, w.kind == LIST ? getSelected((int)i) + 1 : LuaHost::NO_VALUE, nullptr);
			}
			return;
		}
	}
}

void LuaScreenState::widgetChange(Action *)
{
	// the combo box calls this for the list inside it, the sender says nothing: what changed is what has another value
	for (size_t i = 0; i < _widgets.size(); ++i)
	{
		auto &w = _widgets[i];
		if (w.kind == EDIT)
		{
			const std::string now = getText((int)i);
			if (now != w.lastText)
			{
				w.lastText = now;
				if (w.onChange)
				{
					call(w.onChange, "onChange", (int)i, LuaHost::NO_VALUE, &now);
				}
				return;
			}
		}
		else if (w.kind == COMBO || w.kind == SLIDER)
		{
			const int now = w.kind == COMBO ? getSelected((int)i) : getValue((int)i);
			if (now != w.lastValue)
			{
				w.lastValue = now;
				if (w.onChange)
				{
					call(w.onChange, "onChange", (int)i, w.kind == COMBO ? now + 1 : now, nullptr);
				}
				return;
			}
		}
	}
}

void LuaScreenState::widgetEnter(Action *action)
{
	for (size_t i = 0; i < _widgets.size(); ++i)
	{
		const auto &w = _widgets[i];
		if (w.kind == EDIT && w.surface == action->getSender())
		{
			if (w.onEnter)
			{
				const std::string now = getText((int)i);
				call(w.onEnter, "onEnter", (int)i, LuaHost::NO_VALUE, &now);
			}
			return;
		}
	}
}

LuaModsState::LuaModsState()
{
	_screen = false;
	_window = new Window(this, 216, 160, 52, 20, POPUP_BOTH);
	_txtTitle = new Text(206, 17, 57, 32);
	_lstScreens = new TextList(180, 88, 70, 52);
	_btnCancel = new TextButton(180, 18, 70, 150);

	auto *saved = _game->getSavedGame();
	auto *battle = saved ? saved->getSavedBattle() : nullptr;
	setInterface("pauseMenu", false, battle);

	add(_window, "window", "pauseMenu");
	add(_txtTitle, "text", "pauseMenu");
	add(_lstScreens, "text", "pauseMenu");
	add(_btnCancel, "button", "pauseMenu");

	centerAllSurfaces();

	setWindowBackground(_window, "pauseMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_MODS"));

	_lstScreens->setColumns(2, 110, 70);
	_lstScreens->setBackground(_window);
	_lstScreens->setSelectable(true);
	_lstScreens->onMouseClick((ActionHandler)&LuaModsState::lstScreensClick);
	if (auto *host = LuaHost::active())
	{
		for (const auto &item : host->menuScreens())
		{
			_lstScreens->addRow(2, _game->getLanguage()->has(item.first) ? tr(item.first).c_str() : item.first.c_str(), item.second.c_str());
		}
	}

	_btnCancel->setText(tr("STR_CANCEL_UC"));
	_btnCancel->onMouseClick((ActionHandler)&LuaModsState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&LuaModsState::btnCancelClick, Options::keyCancel);

	if (battle)
	{
		applyBattlescapeTheme("pauseMenu");
	}
}

void LuaModsState::btnCancelClick(Action *)
{
	_game->popState();
}

void LuaModsState::lstScreensClick(Action *)
{
	if (auto *host = LuaHost::active())
	{
		if (auto *screen = host->openMenuScreen((size_t)_lstScreens->getSelectedRow()))
		{
			_game->pushState(screen);
		}
	}
}

}
