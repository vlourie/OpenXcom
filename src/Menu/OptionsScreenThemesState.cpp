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
#include "OptionsScreenThemesState.h"
#include <algorithm>
#include <functional>
#include <set>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/HdScreenThemes.h"
#include "../Engine/Language.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/SavedGame.h"
#include "OptionsButtonFaceState.h"
#include "OptionsButtonInkState.h"
#include "OptionsCustomColorState.h"

namespace OpenXcom
{

namespace
{

/// The groups the player has opened: kept until the game is closed.
std::set<std::string> &opened()
{
	static std::set<std::string> s;
	return s;
}

/// The name of a screen or a group the player reads: its string, or its identifier while it has none (the names are stage 4).
std::string screenName(const Language *lang, const std::string &screen)
{
	const std::string id = "STR_HD_SCREEN_" + screen;
	return lang->has(id) ? std::string(lang->getString(id)) : screen;
}

/// The name of a colour of the windows: 0 as the battle panel's, then the panel's names (the value + 1; the last is the own colour).
std::string colorName(const Language *lang, int v)
{
	return v <= 0 ? std::string(lang->getString("STR_HD_WINDOW_THEME_COLOR_SAME"))
		: std::string(lang->getString("STR_HD_BATTLE_HUD_COLOR_" + std::to_string(std::min(v - 1, 9))));
}

}

/**
 * Initializes all the elements in the Themes of the Screens window.
 * @param origin Game section that originated this state.
 */
OptionsScreenThemesState::OptionsScreenThemesState(OptionsOrigin origin) : _origin(origin)
{
	setHdScreen("hdWindows");
	_screen = false;

	// Create objects
	_window = new Window(this, 288, 180, 16, 10, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 18);
	_lstScreens = new TextList(264, 112, 28, 36);
	_txtHint = new Text(264, 9, 28, 151);
	_btnOk = new TextButton(120, 16, 100, 163);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	add(_lstScreens, "optionLists", "advancedMenu");
	add(_txtHint, "confirmVideo", "optionsMenu");
	add(_btnOk, "button", "optionsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_HD_SCREEN_THEMES_TITLE"));

	_txtHint->setAlign(ALIGN_CENTER);
	_txtHint->setText(tr("STR_HD_SCREEN_THEMES_HINT"));

	// the mark of a group, the name, what the screen has
	_lstScreens->setColumns(3, 14, 138, 112);
	_lstScreens->setAlign(ALIGN_CENTER, 0);
	_lstScreens->setSelectable(true);
	_lstScreens->setBackground(_window);
	_lstScreens->onMouseClick((ActionHandler)&OptionsScreenThemesState::lstScreensClick, 0);
	_colorGroup = _lstScreens->getSecondaryColor();
	_greyedOutColor = _game->getMod()->getInterface("advancedMenu")->getElement("disabledUserOption")->color;

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&OptionsScreenThemesState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&OptionsScreenThemesState::btnOkClick, Options::keyOk);
	_btnOk->onKeyboardPress((ActionHandler)&OptionsScreenThemesState::btnOkClick, Options::keyCancel);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}

	fillList();
}

/**
 *
 */
OptionsScreenThemesState::~OptionsScreenThemesState()
{

}

/**
 * The list is made again when an edit window closes.
 */
void OptionsScreenThemesState::init()
{
	State::init();
	fillList();
}

/**
 * What the row says of the screen's theme: as the parent's, or the colour it sets (or just "own" when it sets no colour).
 */
std::string OptionsScreenThemesState::stateText(const std::string &screen) const
{
	const HdScreenThemes::Values *v = HdScreenThemes::instance().own(screen);
	if (!v)
	{
		return tr("STR_HD_SCREEN_AS_PARENT");
	}
	return v->color >= 0 ? colorName(_game->getLanguage(), v->color) : std::string(tr("STR_HD_SCREEN_OWN"));
}

/**
 * Fills the list: the groups, and under an open one its screens (the ones this game's ruleset has an interface for, and any a
 * theme was set to).
 */
void OptionsScreenThemesState::fillList()
{
	const size_t scroll = _lstScreens->getScroll(); // clearList() scrolls to the top
	_lstScreens->clearList();
	_rows.clear();
	const HdScreenThemes &themes = HdScreenThemes::instance();
	const Language *lang = _game->getLanguage();
	auto addRow = [&](const std::string &screen, bool group, const std::string &mark, const std::string &label)
	{
		const std::string state = stateText(screen);
		_lstScreens->addRow(3, mark.c_str(), label.c_str(), state.c_str());
		_rows.push_back(Row{ screen, group });
		const size_t row = _lstScreens->getLastRowIndex();
		if (group)
		{
			_lstScreens->setCellColor(row, 0, _colorGroup);
			_lstScreens->setCellColor(row, 1, _colorGroup);
		}
		if (!themes.own(screen))
		{
			_lstScreens->setCellColor(row, 2, _greyedOutColor);
		}
	};
	// a screen is listed when this ruleset has an interface for it (or it has none by its nature), or a theme was set to it, or a
	// screen under it is listed
	std::function<bool(const std::string &)> listed = [&](const std::string &screen)
	{
		if (_game->getMod()->getInterface(screen, false) || themes.own(screen) || HdScreenThemes::hasNoCategory(screen))
		{
			return true;
		}
		for (const std::string &child : HdScreenThemes::childrenOf(screen))
		{
			if (listed(child)) return true;
		}
		return false;
	};
	// the groups (level 0) and the screens under them, two levels at most: every row with screens under it has the mark at the left
	std::function<void(const std::string &, int)> addTree = [&](const std::string &parent, int depth)
	{
		for (const std::string &screen : HdScreenThemes::childrenOf(parent))
		{
			if (!listed(screen)) continue;
			bool expandable = false;
			for (const std::string &child : HdScreenThemes::childrenOf(screen))
			{
				if (depth < 2 && listed(child)) { expandable = true; break; }
			}
			const bool open = expandable && opened().count(screen) != 0;
			addRow(screen, expandable, expandable ? (open ? "-" : "+") : "", std::string(depth * 2, ' ') + screenName(lang, screen));
			if (open)
			{
				addTree(screen, depth + 1);
			}
		}
	};
	for (const std::string &group : HdScreenThemes::groups())
	{
		const bool open = opened().count(group) != 0;
		addRow(group, true, open ? "-" : "+", screenName(lang, group));
		if (open)
		{
			addTree(group, 1);
		}
	}
	_lstScreens->scrollTo(scroll);
}

/**
 * The mark of a group (or the right button on it) opens and closes the group; any other click opens the theme of the row.
 * @param action Pointer to an action.
 */
void OptionsScreenThemesState::lstScreensClick(Action *action)
{
	const Uint8 button = action->getDetails()->button.button;
	if (button != SDL_BUTTON_LEFT && button != SDL_BUTTON_RIGHT)
	{
		return;
	}
	const int sel = _lstScreens->getSelectedRow();
	if (sel < 0 || sel >= (int)_rows.size())
	{
		return;
	}
	const Row row = _rows[sel];
	const int x = (int)(action->getRelativeXMouse() / action->getXScale());
	if (row.group && (x < 14 || button == SDL_BUTTON_RIGHT))
	{
		if (!opened().erase(row.screen))
		{
			opened().insert(row.screen);
		}
		fillList();
		return;
	}
	// (the list is made again when the window closes: init)
	_game->pushState(new OptionsScreenThemeEditState(_origin, row.screen));
}

/**
 * Closes the window; every edit was kept or dropped in its own window already.
 * @param action Pointer to an action.
 */
void OptionsScreenThemesState::btnOkClick(Action *)
{
	_game->popState();
}


/**
 * Initializes all the elements in the Theme of a Screen window.
 * @param origin Game section that originated this state.
 * @param screen The screen or the group.
 */
OptionsScreenThemeEditState::OptionsScreenThemeEditState(OptionsOrigin origin, const std::string &screen) : _origin(origin), _name(screen)
{
	setHdScreen("hdWindows");
	_screen = false;

	// from now on the options are the screen's theme, for every window on the stack, until OK or Cancel (or anything that deletes this)
	HdScreenThemes::instance().beginEdit(_name);

	// Create objects
	_window = new Window(this, 288, 180, 16, 10, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 18);
	_txtParent = new Text(264, 9, 28, 36);
	_lstColor = new TextList(140, 90, 28, 48);
	_btnCustom = new TextButton(116, 16, 176, 48);
	_btnFace = new TextButton(116, 16, 176, 68);
	_btnInk = new TextButton(116, 16, 176, 88);
	_btnText = new TextButton(116, 16, 176, 106);
	_btnParent = new TextButton(116, 16, 176, 124);
	_txtState = new Text(264, 9, 28, 144);
	_btnOk = new TextButton(120, 16, 28, 163);
	_btnCancel = new TextButton(120, 16, 172, 163);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	add(_txtParent, "confirmVideo", "optionsMenu");
	add(_lstColor, "optionLists", "advancedMenu");
	add(_btnCustom, "button", "optionsMenu");
	add(_btnFace, "button", "optionsMenu");
	add(_btnInk, "button", "optionsMenu");
	add(_btnText, "button", "optionsMenu");
	add(_btnParent, "button", "optionsMenu");
	add(_txtState, "confirmVideo", "optionsMenu");
	add(_btnOk, "button", "optionsMenu");
	add(_btnCancel, "button", "optionsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	const Language *lang = _game->getLanguage();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(screenName(lang, _name));

	const std::string parent = HdScreenThemes::parentOf(_name);
	_txtParent->setAlign(ALIGN_CENTER);
	_txtParent->setText(std::string(tr("STR_HD_SCREEN_PARENT")) + ": " + (parent == "all" ? std::string(tr("STR_HD_SCREEN_ALL")) : screenName(lang, parent)));

	// the colours: as the battle panel's, then the panel's names; the last one is the own colour, made in its own window
	_lstColor->setColumns(1, 140);
	_lstColor->setSelectable(true);
	_lstColor->setBackground(_window);
	_lstColor->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::lstColorClick, 0);
	for (int v = 0; v <= 10; ++v)
	{
		_lstColor->addRow(1, (colorName(lang, v) + (v == 10 ? " >" : "")).c_str());
	}
	_colorGroup = _lstColor->getSecondaryColor();

	_btnCustom->setText(std::string(tr("STR_HD_BATTLE_HUD_COLOR_9")) + " >");   // (the list's last row: "Own colour")
	_btnCustom->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnCustomClick);

	_btnFace->setText(std::string(tr("STR_HD_BUTTON_FACE_TITLE")) + " >");
	_btnFace->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnFaceClick);

	_btnInk->setText(std::string(tr("STR_HD_BUTTON_INK_BTN")) + " >");
	_btnInk->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnInkClick);

	_btnText->setText(std::string(tr("STR_HD_SCREEN_TEXT_BTN")) + " >");
	_btnText->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnTextClick);

	_btnParent->setText(tr("STR_HD_SCREEN_PARENT_BTN"));
	_btnParent->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnParentClick);

	_txtState->setAlign(ALIGN_CENTER);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&OptionsScreenThemeEditState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&OptionsScreenThemeEditState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&OptionsScreenThemeEditState::btnCancelClick, Options::keyCancel);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}

	show();
}

/**
 * Gives the options back (a no-op after OK or Cancel; the way out for any other).
 */
OptionsScreenThemeEditState::~OptionsScreenThemeEditState()
{
	HdScreenThemes::instance().endEdit(false);
}

/**
 * The options may have been changed by a window that closed: shows them.
 */
void OptionsScreenThemeEditState::init()
{
	State::init();
	show();
}

/**
 * Marks the colour the options hold on the list and says whether the screen would have a theme of its own.
 */
void OptionsScreenThemeEditState::show()
{
	const int now = std::min(std::max(Options::oxceHdWindowThemeColor, 0), 10);
	for (int v = 0; v <= 10; ++v)
	{
		_lstColor->setRowColor(v, v == now ? _colorGroup : _lstColor->getColor());
	}
	const bool own = HdScreenThemes::instance().editResult().any();
	_txtState->setText(std::string(tr("STR_HD_SCREEN_NOW")) + ": " + std::string(tr(own ? "STR_HD_SCREEN_OWN" : "STR_HD_SCREEN_AS_PARENT")));
}

/**
 * Picks the colour clicked; the last one, the own colour, opens the window where the player makes it.
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::lstColorClick(Action *)
{
	const int sel = _lstColor->getSelectedRow();
	if (sel < 0 || sel > 10)
	{
		return;
	}
	if (sel == 10)
	{
		btnCustomClick(nullptr);
		return;
	}
	Options::oxceHdWindowThemeColor = sel;
	show();
}

/**
 * Opens the window of the windows' own colour (it works on the options: the screen's theme now).
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnCustomClick(Action *)
{
	_game->pushState(new OptionsCustomColorState(_origin, true));
}

/**
 * Opens the window of the buttons' look.
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnFaceClick(Action *)
{
	_game->pushState(new OptionsButtonFaceState(_origin));
}

/**
 * Opens the window of the buttons' letters.
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnInkClick(Action *)
{
	_game->pushState(new OptionsButtonInkState(_origin));
}

/**
 * Opens the window of the plain texts' colour (it works on the text theme the edit holds).
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnTextClick(Action *)
{
	_game->pushState(new OptionsCustomColorState(_origin, false, true));
}

/**
 * The screen takes its parent's theme again: the options show it, OK drops the screen's record.
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnParentClick(Action *)
{
	HdScreenThemes::instance().editAsParent();
	show();
}

/**
 * Keeps the theme: the screen's record is written to the file.
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnOkClick(Action *)
{
	HdScreenThemes::instance().endEdit(true);
	_game->popState();
}

/**
 * Gives back everything as it was.
 * @param action Pointer to an action.
 */
void OptionsScreenThemeEditState::btnCancelClick(Action *)
{
	HdScreenThemes::instance().endEdit(false);
	_game->popState();
}

}
