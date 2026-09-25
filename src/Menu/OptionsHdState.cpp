/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "OptionsHdState.h"
#include <sstream>
#include "../Engine/Game.h"
#include "../Engine/Action.h"
#include "../Engine/HdUi.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "AdultChoiceState.h"
#include "OptionDetailState.h"

namespace OpenXcom
{

/// The mod the HD settings act on.
static const std::string HD_MOD = "hd";
/// The categories of Options.cpp shown here, in this order; the first one also holds the art version row.
static const char *const HD_CATEGORIES[] = { "STR_HD_ART", "STR_HD_BATTLE", "STR_HD_INTERFACE", "STR_HD_SPEED" };
/// Row markers in _rows.
static const int ROW_NONE = -1, ROW_ART = -2;

/**
 * Initializes all the elements in the HD Options window.
 * @param origin Game section that originated this state.
 */
OptionsHdState::OptionsHdState(OptionsOrigin origin) : OptionsBaseState(origin)
{
	setCategory(_btnHd);

	_lstOptions = new TextList(200, 136, 94, 8);

	if (origin != OPT_BATTLESCAPE)
	{
		_greyedOutColor = _game->getMod()->getInterface("advancedMenu")->getElement("disabledUserOption")->color;
		add(_lstOptions, "optionLists", "advancedMenu");
	}
	else
	{
		_greyedOutColor = _game->getMod()->getInterface("battlescape")->getElement("disabledUserOption")->color;
		add(_lstOptions, "optionLists", "battlescape");
	}

	centerAllSurfaces();

	// the value column is as wide as the widest value it can show
	Text text = Text(100, 9, 0, 0);
	text.initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	int rightcol = 0;
	for (const char *s : { "STR_YES", "STR_NO", "STR_HD_ART_ORIGINAL", "STR_HD_ART_HD", "STR_HD_ART_ADULT" })
	{
		text.setText(tr(s));
		rightcol = std::max(rightcol, text.getTextWidth());
	}
	rightcol += 2;

	_lstOptions->setAlign(ALIGN_RIGHT, 1);
	_lstOptions->setColumns(2, _lstOptions->getWidth() - rightcol, rightcol);
	_lstOptions->setWordWrap(true);
	_lstOptions->setSelectable(true);
	_lstOptions->setBackground(_window);
	_lstOptions->onMouseClick((ActionHandler)&OptionsHdState::lstOptionsClick, 0);
	_lstOptions->onMouseOver((ActionHandler)&OptionsHdState::lstOptionsMouseOver);
	_lstOptions->onMouseOut((ActionHandler)&OptionsHdState::lstOptionsMouseOut);

	_colorGroup = _lstOptions->getSecondaryColor();

	_adultShipped = AdultChoiceState::adultArtShipped();
	_hdActive = false;
	for (const auto& mod : Options::mods)
	{
		if (mod.first == HD_MOD)
		{
			_hdActive = mod.second;
		}
	}

	for (const char *category : HD_CATEGORIES)
	{
		Group group;
		group.title = category;
		for (const auto& optionInfo : Options::getOptionInfo())
		{
			if (optionInfo.type() != OPTION_KEY && !optionInfo.description().empty() && optionInfo.category() == category)
			{
				// asking at every start only means something when there is an adult tree to choose
				// (asBool throws on an option of another type, so the type is checked first)
				if (optionInfo.type() == OPTION_BOOL && optionInfo.asBool() == &Options::oxceAdultAsk && !_adultShipped)
				{
					continue;
				}
				group.settings.push_back(optionInfo);
			}
		}
		_groups.push_back(group);
	}
}

/**
 *
 */
OptionsHdState::~OptionsHdState()
{

}

/**
 * Refreshes the UI.
 */
void OptionsHdState::init()
{
	OptionsBaseState::init();
	updateList();
}

void OptionsHdState::addRow(int group, int index, const std::string &name, const std::string &value)
{
	_lstOptions->addRow(2, name.c_str(), value.c_str());
	_rows.push_back(Row{ group, index });
}

/**
 * Fills the settings list: a line about the mod when it is off, then the groups.
 */
void OptionsHdState::updateList()
{
	_lstOptions->clearList();
	_rows.clear();

	if (!_hdActive)
	{
		addRow(ROW_NONE, 0, tr("STR_HD_MOD_OFF"), "");
		_lstOptions->setRowColor(_lstOptions->getLastRowIndex(), _greyedOutColor);
		addRow(ROW_NONE, 0, "", "");
	}

	auto& fixeduserOptions = _game->getMod()->getFixedUserOptions();
	for (size_t g = 0; g < _groups.size(); ++g)
	{
		const Group &group = _groups[g];
		const bool withArt = g == 0;
		if (group.settings.empty() && !withArt)
		{
			continue;
		}
		if (!_rows.empty() && _rows.back().group != ROW_NONE)
		{
			addRow(ROW_NONE, 0, "", "");
		}
		addRow(ROW_NONE, 0, tr(group.title), "");
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 0, _colorGroup);
		if (withArt)
		{
			addRow(ROW_ART, 0, tr("STR_HD_ART_VERSION"), artText());
		}
		for (size_t i = 0; i < group.settings.size(); ++i)
		{
			const OptionInfo &info = group.settings[i];
			addRow((int)g, (int)i, tr(info.description()), valueText(info));
			_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 1, valueColor(info));
			// grey out options a mod fixes
			if (fixeduserOptions.find(info.id()) != fixeduserOptions.end())
			{
				_lstOptions->setRowColor(_lstOptions->getLastRowIndex(), _greyedOutColor);
			}
		}
	}
}

/**
 * A "no" reads apart from a "yes" at a glance: in the color of a disabled option.
 */
Uint8 OptionsHdState::valueColor(const OptionInfo &info) const
{
	return info.type() == OPTION_BOOL && !*info.asBool() ? _greyedOutColor : _lstOptions->getColor();
}

std::string OptionsHdState::valueText(const OptionInfo &info) const
{
	if (info.type() == OPTION_BOOL)
	{
		return *info.asBool() ? tr("STR_YES") : tr("STR_NO");
	}
	// the HD font is picked by name: the number alone says nothing about which face it is
	if (info.asInt() == &Options::oxceHdUiFont)
	{
		return HdUi::instance().fontSetName(Options::oxceHdUiFont);
	}
	if (info.asInt() == &Options::oxceHdReticle)
	{
		const int r = Options::oxceHdReticle;
		if (r >= 2 && r - 2 < (int)Mod::HD_RETICLES.size())
		{
			return tr("STR_HD_RETICLE_" + Mod::HD_RETICLES[r - 2]);
		}
		return tr(r == 1 ? "STR_HD_RETICLE_STOCK" : "STR_HD_RETICLE_PACK");
	}
	std::ostringstream ss;
	ss << *info.asInt();
	return ss.str();
}

/**
 * The art version is two options seen as one: the classic pixels (HD sprites off),
 * the ordinary HD pictures, or the adult ones.
 */
std::string OptionsHdState::artText() const
{
	if (Options::oxceHdMode == 0)
	{
		return tr("STR_HD_ART_ORIGINAL");
	}
	return Options::oxceAdultArt ? tr("STR_HD_ART_ADULT") : tr("STR_HD_ART_HD");
}

/**
 * Steps the art version. The adult tree is read while the mods load, so switching it
 * needs a reload of the resources - which only the main menu does (OptionsBaseState::btnOkClick);
 * elsewhere the version stays within the tree that is loaded.
 */
void OptionsHdState::cycleArt(int increment)
{
	const bool canSwitchTree = _adultShipped && _origin == OPT_MENU;
	// 0 original, 1 HD, 2 HD 18+; without a reload only the loaded tree is reachable
	std::vector<int> versions = { 0 };
	if (canSwitchTree || !Options::oxceAdultArt)
	{
		versions.push_back(1);
	}
	if (canSwitchTree || Options::oxceAdultArt)
	{
		versions.push_back(2);
	}
	const int now = Options::oxceHdMode == 0 ? 0 : Options::oxceAdultArt ? 2 : 1;
	int pos = 0;
	for (size_t i = 0; i < versions.size(); ++i)
	{
		if (versions[i] == now)
		{
			pos = (int)i;
		}
	}
	pos = (pos + increment + (int)versions.size()) % (int)versions.size();
	const int next = versions[pos];

	if (next == 0)
	{
		Options::oxceHdMode = 0;
	}
	else
	{
		if (Options::oxceHdMode == 0)
		{
			Options::oxceHdMode = 2;                  // the default: packs plus xBRZ for the rest
		}
		const bool adult = next == 2;
		if (adult != Options::oxceAdultArt)
		{
			Options::oxceAdultArt = adult;
			Options::reload = true;
		}
	}
}

/**
 * Changes the clicked setting.
 * @param action Pointer to an action.
 */
void OptionsHdState::lstOptionsClick(Action *action)
{
	Uint8 button = action->getDetails()->button.button;
	if (button != SDL_BUTTON_LEFT && button != SDL_BUTTON_RIGHT && button != SDL_BUTTON_MIDDLE)
	{
		return;
	}
	const size_t sel = _lstOptions->getSelectedRow();
	if (sel >= _rows.size())
	{
		return;
	}
	if (button == SDL_BUTTON_MIDDLE)
	{
		showDetail(sel);
		return;
	}
	changeSetting(sel, button);
}

/**
 * Changes the setting of a row as a click on it does.
 * @param sel Row of the list.
 * @param button Mouse button: left steps forward, right back.
 */
void OptionsHdState::changeSetting(size_t sel, Uint8 button)
{
	const int increment = (button == SDL_BUTTON_LEFT) ? 1 : -1; // left-click increases, right-click decreases
	const Row row = _rows[sel];
	if (row.group == ROW_ART)
	{
		cycleArt(increment);
		updateList();                                 // the HD sprites row shows the same option
		return;
	}
	if (row.group < 0)
	{
		return;
	}
	OptionInfo *setting = &_groups[row.group].settings[row.index];

	// greyed out options are fixed, cannot be changed by the user
	auto& fixeduserOptions = _game->getMod()->getFixedUserOptions();
	if (fixeduserOptions.find(setting->id()) != fixeduserOptions.end())
	{
		return;
	}

	if (setting->type() == OPTION_BOOL)
	{
		bool *b = setting->asBool();
		*b = !*b;
		_lstOptions->setCellColor(sel, 1, valueColor(*setting));
	}
	else if (setting->type() == OPTION_INT)
	{
		int *i = setting->asInt();
		*i += increment;

		int min = 0, max = 0;
		if (i == &Options::oxceHdScale)
		{
			min = 1;
			max = 4;
		}
		else if (i == &Options::oxceHdMode || i == &Options::oxceHdUi)
		{
			min = 0;
			max = 2;
		}
		else if (i == &Options::oxceHdUiSkin)
		{
			min = 0;
			max = 3;
		}
		else if (i == &Options::oxceHdUiFont)
		{
			min = 0;
			max = HdUi::instance().fontSetCount();
		}
		else if (i == &Options::oxceHdReticle)
		{
			min = 0;
			max = 1 + (int)Mod::HD_RETICLES.size();
		}
		else if (i == &Options::oxceHdThreads)
		{
			min = 0;                                  // 0 = all cores but two
			max = 32;
		}
		else if (i == &Options::oxceHdFrameSkip)
		{
			min = 0;
			max = 8;
		}
		if (*i < min)
		{
			*i = max;
		}
		else if (*i > max)
		{
			*i = min;
		}
		if (i == &Options::oxceHdUiFont)
		{
			// load it right away, so the list itself is redrawn with the face that was picked
			HdUi::instance().applyFontOption();
		}
		if (i == &Options::oxceHdReticle)
		{
			_game->getMod()->applyHdReticle();         // takes effect at once, in battle too
		}
		if (i == &Options::oxceHdMode)
		{
			updateList();                             // the art version row shows the same option
			return;
		}
	}
	_lstOptions->setCellText(sel, 1, valueText(*setting));
}

/**
 * The whole description of a row: what the tooltip line shows, and the detail window in full.
 */
std::string OptionsHdState::rowDescription(size_t sel) const
{
	std::string desc;
	if (sel < _rows.size())
	{
		const Row row = _rows[sel];
		if (row.group == ROW_ART)
		{
			desc = tr("STR_HD_ART_VERSION_DESC");
			if (_adultShipped && _origin != OPT_MENU)
			{
				desc += " ";
				desc += tr("STR_HD_ART_MENU_ONLY");
			}
		}
		else if (row.group >= 0)
		{
			desc = tr(_groups[row.group].settings[row.index].description() + "_DESC");
		}
	}
	return desc;
}

void OptionsHdState::showDetail(size_t sel)
{
	const Row row = _rows[sel];
	if (row.group == ROW_NONE)
	{
		return;
	}
	const std::string name = row.group == ROW_ART ? tr("STR_HD_ART_VERSION") : tr(_groups[row.group].settings[row.index].description());
	_game->pushState(new OptionDetailState(_origin, name, rowDescription(sel),
		[this, sel, row](Uint8 b)
		{
			if (b != 0)
			{
				changeSetting(sel, b);
			}
			if (row.group == ROW_ART)
			{
				return std::make_pair(artText(), (Uint8)0);
			}
			const OptionInfo &info = _groups[row.group].settings[row.index];
			return std::make_pair(valueText(info), info.type() == OPTION_BOOL && !*info.asBool() ? _greyedOutColor : (Uint8)0);
		}));
}

void OptionsHdState::lstOptionsMouseOver(Action *)
{
	_txtTooltip->setText(rowDescription(_lstOptions->getSelectedRow()));
}

void OptionsHdState::lstOptionsMouseOut(Action *)
{
	_txtTooltip->setText("");
}

}
