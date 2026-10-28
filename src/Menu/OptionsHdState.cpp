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
#include "../Engine/FileMap.h"
#include "../Engine/HdSprites.h"
#include "../Engine/HdGentle.h"
#include "../Engine/HdLab.h"
#include "../Engine/HdUi.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Battlescape/Map.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "AdultChoiceState.h"
#include "HdLabPasswordState.h"
#include "OptionDetailState.h"

namespace OpenXcom
{

/// The tabs over the list, three in a row: graphics, battle, interface, geoscape and base, AI and rules, speed.
static const char *const HD_TABS[] = { "STR_HD_TAB_GRAPHICS", "STR_HD_TAB_BATTLE", "STR_HD_TAB_INTERFACE", "STR_HD_TAB_WORLD", "STR_HD_TAB_AI", "STR_HD_TAB_SPEED" };
static const int HD_TAB_COUNT = sizeof(HD_TABS) / sizeof(HD_TABS[0]);
/// The groups of the list, in this order, each on its tab (a title can come twice: its graphics options on the first
/// tab, the rest on its own); the first one also holds the art version row. The title is a category of Options.cpp.
static const struct { const char *category; int tab; } HD_CATEGORIES[] = {
	{ "STR_HD_ART", 0 }, { "STR_HD_GENTLE", 0 }, { "STR_HD_GRAPHICS", 0 },
	{ "STR_HD_INTERFACE", 0 },
	{ "STR_HD_BATTLE", 1 }, { "STR_HD_BATTLE_UI", 1 }, { "STR_HD_PHYSICS", 1 },
	{ "STR_HD_INTERFACE", 2 },
	{ "STR_HD_GEOSCAPE", 3 }, { "STR_HD_BASE", 3 },
	{ "STR_HD_AI", 4 }, { "STR_HD_CHALLENGE", 4 }, { "STR_HD_RULES", 4 },
	{ "STR_HD_SPEED", 5 }, { "STR_HD_LAB", 5 } };
/// The options of how things look, wherever their category is: they all go on the graphics tab, to the group of their
/// category (the battle ones to "Graphics of the battle"). Options of the categories ART, GENTLE and GRAPHICS are there already.
static const char *const HD_GRAPHICS_OPTIONS[] = {
	"oxceHdBlastFall", "oxceHdKillCam", "oxceHdHiddenMap", "oxceHdBackdrop", "oxceHdEnemyNumber",
	"oxceHdUi", "oxceHdUiSkin", "oxceHdUiFont", "oxceHdPictures", "oxceHdUiSmooth" };
/// The tab open last: the window opens on it again, until the game is closed.
static int hdTab = 0;
/// The category of the HD lab (Engine/HdLab.h): its rows show only once the password was given.
static const std::string LAB_CATEGORY = "STR_HD_LAB";
/// The category of BetterAI (Battlescape/AiProbe.h): its rows are on the BetterAI screen, not in the main list.
static const std::string AI_CATEGORY = "STR_HD_AI";
/// Row markers in _rows: ROW_LAB asks for the lab's password, ROW_LAB_LOCK closes the lab again, ROW_BETTERAI opens the
/// BetterAI screen, ROW_BACK goes back from it.
static const int ROW_NONE = -1, ROW_ART = -2, ROW_LAB = -3, ROW_LAB_LOCK = -4, ROW_BETTERAI = -5, ROW_BACK = -6;

/**
 * Initializes all the elements in the HD Options window.
 * @param origin Game section that originated this state.
 */
OptionsHdState::OptionsHdState(OptionsOrigin origin) : OptionsBaseState(origin), _betterAiView(false), _aiGroup(-1)
{
	setCategory(_btnHd);

	for (int t = 0; t < HD_TAB_COUNT; ++t)
	{
		_btnTabs.push_back(new TextButton(64, 12, 94 + (t % 3) * 68, 8 + (t / 3) * 13));
	}
	_tab = _btnTabs[std::max(0, std::min(HD_TAB_COUNT - 1, hdTab))];
	_lstOptions = new TextList(200, 112, 94, 34);

	for (TextButton *btn : _btnTabs)
	{
		add(btn, "button", "advancedMenu");
	}
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

	for (int t = 0; t < HD_TAB_COUNT; ++t)
	{
		_btnTabs[t]->setSmall();
		_btnTabs[t]->setText(tr(HD_TABS[t]));
		_btnTabs[t]->setGroup(&_tab);
		_btnTabs[t]->onMousePress((ActionHandler)&OptionsHdState::btnTabPress, SDL_BUTTON_LEFT);
	}

	// the value column is as wide as the widest value it can show
	Text text = Text(100, 9, 0, 0);
	text.initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	int rightcol = 0;
	// (the short values: yes and no, the art versions, a few words of the short variants - what is longer goes under its label)
	for (const char *s : { "STR_YES", "STR_NO", "STR_HD_ART_ORIGINAL", "STR_HD_ART_HD", "STR_HD_ART_ADULT",
		"STR_HD_ENEMY_NUMBER_1", "STR_HD_ENEMY_NUMBER_2", "STR_HD_ENEMY_TURN_0", "STR_HD_ENEMY_TURN_2", "STR_HD_RETICLE_PACK",
		"STR_HD_RETICLE_STOCK", "STR_HD_FIRE_0", "STR_HD_ALT_INFO_1", "STR_HD_RADAR_0" })
	{
		text.setText(tr(s));
		rightcol = std::max(rightcol, text.getTextWidth());
	}
	rightcol += 2;
	_valueWidth = rightcol;

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
	_hdActive = _game->getMod()->hasHdArt();
	// a style row without its pictures in the active mods would change nothing: it is not offered, and
	// its value stays in options.cfg as it was (Options::save writes every option, shown or not).
	// Fire styles are the variants 2s and 2s + 1 of the fire frames (Map.cpp, UnitSprite.cpp)
	const bool fireShipped = FileMap::fileExists(HdSprites::artPath("SMOKE.PCK/0.v2.png"));
	bool reticleShipped = FileMap::fileExists(HdSprites::artPath("CURSOR.PCK/6.png"));
	for (const auto &style : Mod::HD_RETICLES)
	{
		reticleShipped = reticleShipped || FileMap::fileExists(HdSprites::artPath("CURSOR.PCK/reticle_" + style + "/6.png"));
	}

	for (const auto &c : HD_CATEGORIES)
	{
		const char *category = c.category;
		Group group;
		group.title = category;
		group.tab = c.tab;
		for (const auto& optionInfo : Options::getOptionInfo())
		{
			// the group an option is in: a graphics option on the first tab (the battle ones in the graphics group), the
			// others where their category is (a category on two tabs: its second entry)
			bool graphics = false;
			for (const char *id : HD_GRAPHICS_OPTIONS)
			{
				graphics = graphics || optionInfo.id() == id;
			}
			const std::string home = graphics && optionInfo.category() == "STR_HD_BATTLE" ? std::string("STR_HD_GRAPHICS") : optionInfo.category();
			int homeTab = -1;
			for (const auto &d : HD_CATEGORIES)
			{
				if (home == d.category && (homeTab < 0 || !graphics))
				{
					homeTab = d.tab;
				}
			}
			if (optionInfo.type() != OPTION_KEY && !optionInfo.description().empty() && home == category && homeTab == c.tab)
			{
				// asking at every start only means something when there is an adult tree to choose
				// (asBool throws on an option of another type, so the type is checked first)
				if (optionInfo.type() == OPTION_BOOL && optionInfo.asBool() == &Options::oxceAdultAsk && !_adultShipped)
				{
					continue;
				}
				if (optionInfo.type() == OPTION_INT && ((optionInfo.asInt() == &Options::oxceHdFire && !fireShipped) ||
					((optionInfo.asInt() == &Options::oxceHdReticle || optionInfo.asInt() == &Options::oxceHdReticleArtillery
					|| optionInfo.asInt() == &Options::oxceHdReticleExplosive) && !reticleShipped)))
				{
					continue;
				}
				group.settings.push_back(optionInfo);
			}
		}
		if (group.title == AI_CATEGORY && !group.settings.empty())
		{
			_aiGroup = (int)_groups.size();
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

void OptionsHdState::addRow(int group, int index, const std::string &name, const std::string &value, int pair)
{
	_lstOptions->addRow(2, name.c_str(), value.c_str());
	_rows.push_back(Row{ group, index, pair });
}

/**
 * Is the value wider than the column beside the label? Measured as the column itself was (base font).
 */
bool OptionsHdState::longValue(const std::string &value) const
{
	Text text = Text(200, 9, 0, 0);
	text.initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	text.setText(value);
	return text.getTextWidth() > _valueWidth;
}

/**
 * The rows of a setting. A short value (yes, no, a number, a few words) stands in the label's row, as ever; a long one
 * would be cut to pieces in that narrow column, so it gets a row under the label, indented, in the value's color.
 */
void OptionsHdState::addSettingRow(int group, int index, const std::string &label, bool grey)
{
	const OptionInfo &info = _groups[group].settings[index];
	const std::string value = valueText(info);
	if (!longValue(value))
	{
		addRow(group, index, label, value);
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 1, valueColor(info));
	}
	else
	{
		addRow(group, index, label, "", 1);
		addRow(group, index, "   " + value, "", 2);
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 0, valueColor(info));
	}
	if (grey)
	{
		_lstOptions->setRowColor(_lstOptions->getLastRowIndex(), _greyedOutColor);
		if (_rows.back().pair == 2)
		{
			_lstOptions->setRowColor(_lstOptions->getLastRowIndex() - 1, _greyedOutColor);
		}
	}
}

/**
 * Writes a setting's value in its row: the second column, or the row under the label when the value is long. A value
 * that is now of the other kind than its rows were made for (short to long, or back) builds the list again.
 */
void OptionsHdState::setValueCell(size_t sel, const std::string &value, Uint8 color)
{
	const Row row = _rows[sel];
	if ((row.pair == 0) == longValue(value))
	{
		updateList();
		return;
	}
	if (row.pair == 0)
	{
		_lstOptions->setCellText(sel, 1, value);
		_lstOptions->setCellColor(sel, 1, color);
	}
	else
	{
		const size_t at = row.pair == 1 ? sel + 1 : sel;
		_lstOptions->setCellText(at, 0, "   " + value);
		_lstOptions->setCellColor(at, 0, color);
	}
}

/**
 * Fills the settings list: a line about the mod when it is off, then the groups.
 */
void OptionsHdState::updateList()
{
	const size_t scroll = _lstOptions->getScroll(); // clearList() scrolls to the top
	_lstOptions->clearList();
	_rows.clear();

	if (!_hdActive)
	{
		addRow(ROW_NONE, 0, tr("STR_HD_MOD_OFF"), "");
		_lstOptions->setRowColor(_lstOptions->getLastRowIndex(), _greyedOutColor);
		addRow(ROW_NONE, 0, "", "");
	}

	auto& fixeduserOptions = _game->getMod()->getFixedUserOptions();
	if (_betterAiView && _aiGroup >= 0)
	{
		// the BetterAI screen: its switch first, the rows under it grey while it is off, the way back last
		addRow(ROW_NONE, 0, tr("STR_BETTER_AI"), "");
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 0, _colorGroup);
		const Group &group = _groups[_aiGroup];
		for (size_t i = 0; i < group.settings.size(); ++i)
		{
			const OptionInfo &info = group.settings[i];
			addRow(_aiGroup, (int)i, tr(info.description()), valueText(info));
			_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 1, valueColor(info));
			if (aiLocks(info) || fixeduserOptions.find(info.id()) != fixeduserOptions.end())
			{
				_lstOptions->setRowColor(_lstOptions->getLastRowIndex(), _greyedOutColor);
			}
		}
		addRow(ROW_NONE, 0, "", "");
		addRow(ROW_BACK, 0, tr("STR_BETTER_AI_BACK"), "");
		return;
	}
	const int tab = currentTab();
	if (_aiGroup >= 0 && _groups[_aiGroup].tab == tab)
	{
		// BetterAI opens its own screen from the first row of its tab; the value is its switch's
		addRow(ROW_BETTERAI, 0, std::string(tr("STR_BETTER_AI")) + " >", Options::oxceBetterAi ? tr("STR_YES") : tr("STR_NO"));
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 1, Options::oxceBetterAi ? _lstOptions->getColor() : _greyedOutColor);
	}
	for (size_t g = 0; g < _groups.size(); ++g)
	{
		const Group &group = _groups[g];
		const bool withArt = g == 0;
		const bool lab = group.title == LAB_CATEGORY;
		if ((group.settings.empty() && !withArt) || (int)g == _aiGroup || group.tab != tab)
		{
			continue;
		}
		if (!_rows.empty() && _rows.back().group != ROW_NONE)
		{
			addRow(ROW_NONE, 0, "", "");
		}
		// a group of one setting that is called as the group is (the gentle mode) is that row alone, without a header over it
		if (withArt || group.settings.size() != 1 || std::string(tr(group.settings[0].description())) != std::string(tr(group.title)))
		{
			addRow(ROW_NONE, 0, tr(group.title), "");
			_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 0, _colorGroup);
		}
		if (withArt)
		{
			addRow(ROW_ART, 0, tr("STR_HD_ART_VERSION"), artText());
		}
		if (lab && !HdLab::unlocked())
		{
			// the lab's rows stay hidden: one row asks for the password
			addRow(ROW_LAB, 0, tr("STR_HD_LAB_LOCKED"), tr("STR_HD_LAB_ENTER"));
			continue;
		}
		for (size_t i = 0; i < group.settings.size(); ++i)
		{
			const OptionInfo &info = group.settings[i];
			const bool gentle = HdGentle::locks(info);
			// grey out options a mod, the gentle mode or the battle in progress fixes
			addSettingRow((int)g, (int)i, gentle ? std::string(tr(info.description())) + " " + std::string(tr("STR_GENTLE_LOCKED")) : std::string(tr(info.description())),
				gentle || battleLocks(info) || dependsOff(info) || fixeduserOptions.find(info.id()) != fixeduserOptions.end());
		}
		if (lab)
		{
			addRow(ROW_LAB_LOCK, 0, tr("STR_HD_LAB_RELOCK"), "");
		}
	}
	_lstOptions->scrollTo(scroll); // the row just changed stays where the player looks at it
}

/**
 * The index of the tab pressed last.
 */
int OptionsHdState::currentTab() const
{
	for (int t = 0; t < (int)_btnTabs.size(); ++t)
	{
		if (_btnTabs[t] == _tab)
		{
			return t;
		}
	}
	return 0;
}

/**
 * Shows the groups of the tab just pressed (the group pointer is already moved by the button).
 */
void OptionsHdState::btnTabPress(Action *)
{
	hdTab = currentTab();
	_betterAiView = false;
	_lstOptions->scrollTo(0);                             // the other list starts at its top
	updateList();
}

/**
 * A "no" reads apart from a "yes" at a glance: in the color of a disabled option.
 */
Uint8 OptionsHdState::valueColor(const OptionInfo &info) const
{
	if (HdGentle::locks(info) || battleLocks(info) || aiLocks(info) || dependsOff(info))
	{
		return _greyedOutColor;
	}
	return info.type() == OPTION_BOOL && !*info.asBool() ? _greyedOutColor : _lstOptions->getColor();
}

/**
 * Is the main option of this setting off, so the setting does nothing for now? Its row is grey, but it can be changed.
 */
bool OptionsHdState::dependsOff(const OptionInfo &info) const
{
	const bool skin = Options::oxceHdUi > 0 && Options::oxceHdUiSkin > 0;
	const bool fonts = skin && Options::oxceHdUiFont > 0;
	if (info.type() == OPTION_INT)
	{
		const int *p = info.asInt();
		if (p == &Options::oxceHdPathNumSize || p == &Options::oxceHdPathNumWeight) return !Options::oxceHdPathDigits || !fonts;
		if (p == &Options::oxceHdAimNumSize || p == &Options::oxceHdAimNumWeight) return !fonts;
		if (p == &Options::oxceHdBattleHudColor) return !skin;
		if (p == &Options::oxceHdRadarWaves) return Options::oxceHdRadar != 3;
		if (p == &Options::oxceHdTrunkArmor) return !Options::oxceCollapse;
	}
	else if (info.type() == OPTION_BOOL)
	{
		const bool *b = info.asBool();
		if (b == &Options::oxceHdBattleHud) return !skin;
		if (b == &Options::oxceHdRadarBeam) return Options::oxceHdRadar != 3;
	}
	return false;
}

/**
 * The rows under the BetterAI switch do nothing while it is off: grey, and a click does not change them.
 */
bool OptionsHdState::aiLocks(const OptionInfo &info) const
{
	return !Options::oxceBetterAi && info.category() == AI_CATEGORY
		&& !(info.type() == OPTION_BOOL && info.asBool() == &Options::oxceBetterAi);
}

/**
 * The battle saves rule holds for the whole battle: from a battle the tab shows it but does not change it.
 */
bool OptionsHdState::battleLocks(const OptionInfo &info) const
{
	return _origin == OPT_BATTLESCAPE && info.type() == OPTION_BOOL && info.asBool() == &Options::oxceNoBattleSaves;
}

std::string OptionsHdState::valueText(const OptionInfo &info) const
{
	if (info.type() == OPTION_BOOL)
	{
		// a setting the gentle mode holds shows the value it is held at, not the player's own
		const bool value = HdGentle::locks(info) ? HdGentle::lockedValue(info.asBool()) != 0 : *info.asBool();
		return value ? tr("STR_YES") : tr("STR_NO");
	}
	// the HD font is picked by name: the number alone says nothing about which face it is
	if (info.asInt() == &Options::oxceHdUiFont)
	{
		return HdUi::instance().fontSetName(Options::oxceHdUiFont);
	}
	if (info.asInt() == &Options::oxceHdReticle || info.asInt() == &Options::oxceHdReticleArtillery || info.asInt() == &Options::oxceHdReticleExplosive)
	{
		// the reticles of a kind of shot: 0 is the main one (the throw cursor for explosives), v the main one's v - 1
		int r = *info.asInt();
		if (info.asInt() != &Options::oxceHdReticle)
		{
			if (r <= 0)
			{
				return tr(info.asInt() == &Options::oxceHdReticleExplosive ? "STR_HD_RETICLE_THROW" : "STR_HD_RETICLE_SAME");
			}
			--r;
		}
		if (r >= 2 && r - 2 < (int)Mod::HD_RETICLES.size())
		{
			return tr("STR_HD_RETICLE_" + Mod::HD_RETICLES[r - 2]);
		}
		return tr(r == 1 ? "STR_HD_RETICLE_STOCK" : "STR_HD_RETICLE_PACK");
	}
	// the fire styles by name (strings in the hd mod, Ruleset/fire.rul)
	if (info.asInt() == &Options::oxceHdFire)
	{
		return tr("STR_HD_FIRE_" + std::to_string(Options::oxceHdFire));
	}
	// the pace of fire and smoke as the speed it gives, percent of the stock one
	if (info.asInt() == &Options::oxceHdFirePace || info.asInt() == &Options::oxceHdSmokePace)
	{
		return std::to_string(Map::hdEnviPercent(*info.asInt())) + "%";
	}
	if (info.asInt() == &Options::oxceHdEnemyNumber)
	{
		return tr("STR_HD_ENEMY_NUMBER_" + std::to_string(Options::oxceHdEnemyNumber));
	}
	if (info.asInt() == &Options::oxceHdEnemyTurn)
	{
		return tr("STR_HD_ENEMY_TURN_" + std::to_string(Options::oxceHdEnemyTurn));
	}
	if (info.asInt() == &Options::oxceHdRadar)
	{
		return tr("STR_HD_RADAR_" + std::to_string(Options::oxceHdRadar));
	}
	if (info.asInt() == &Options::oxceHdRadarWaves)
	{
		return tr("STR_HD_RADAR_WAVES_" + std::to_string(Options::oxceHdRadarWaves));
	}
	if (info.asInt() == &Options::oxceHdTrunkArmor)
	{
		return tr("STR_HD_TRUNK_ARMOR_" + std::to_string(Options::oxceHdTrunkArmor));
	}
	if (info.asInt() == &Options::oxceHdMapRotation)
	{
		return tr("STR_HD_MAP_ROTATION_" + std::to_string(((Options::oxceHdMapRotation % 4) + 4) % 4));
	}
	if (info.asInt() == &Options::oxceHdCraftLaunch)
	{
		return tr("STR_HD_CRAFT_LAUNCH_" + std::to_string(Options::oxceHdCraftLaunch));
	}
	if (info.asInt() == &Options::oxceHdAltInfo)
	{
		return tr("STR_HD_ALT_INFO_" + std::to_string(Options::oxceHdAltInfo));
	}
	if (info.asInt() == &Options::oxceHdBattleHudColor)
	{
		return tr("STR_HD_BATTLE_HUD_COLOR_" + std::to_string(Options::oxceHdBattleHudColor));
	}
	if (info.asInt() == &Options::oxceHdPathNumSize || info.asInt() == &Options::oxceHdPathNumWeight
		|| info.asInt() == &Options::oxceHdAimNumSize || info.asInt() == &Options::oxceHdAimNumWeight)
	{
		return std::to_string(std::max(50, std::min(100, *info.asInt()))) + "%";
	}
	// the same names as the geoscape scale in the video options: "3x" = a globe pixel is 3 display pixels
	if (info.asInt() == &Options::oxceHdGlobeScale)
	{
		if (Options::oxceHdGlobeScale > 0)
		{
			return std::to_string(Options::oxceHdGlobeScale) + "x";
		}
		return tr("STR_HD_GLOBE_SCALE_SAME");
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
	if (row.group == ROW_LAB)
	{
		// the list is filled again when the tab comes back on top (init)
		_game->pushState(new HdLabPasswordState(_origin, nullptr));
		return;
	}
	if (row.group == ROW_LAB_LOCK)
	{
		HdLab::lock();
		updateList();
		return;
	}
	if (row.group == ROW_BETTERAI || row.group == ROW_BACK)
	{
		_betterAiView = row.group == ROW_BETTERAI;
		_lstOptions->scrollTo(0);                     // the other list starts at its top
		updateList();
		return;
	}
	if (row.group < 0)
	{
		return;
	}
	OptionInfo *setting = &_groups[row.group].settings[row.index];

	// greyed out options are fixed, cannot be changed by the user
	auto& fixeduserOptions = _game->getMod()->getFixedUserOptions();
	if (fixeduserOptions.find(setting->id()) != fixeduserOptions.end() || HdGentle::locks(*setting) || battleLocks(*setting) || aiLocks(*setting))
	{
		return;
	}

	if (setting->type() == OPTION_BOOL)
	{
		bool *b = setting->asBool();
		*b = !*b;
		if (b == &Options::oxceGentle || b == &Options::oxceBetterAi)
		{
			updateList();                             // the rows the mode or the switch holds change with it
			return;
		}
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
		else if (i == &Options::oxceHdReticleArtillery || i == &Options::oxceHdReticleExplosive)
		{
			min = 0;                                  // 0 = the main reticle (the throw cursor), then as oxceHdReticle + 1
			max = 2 + (int)Mod::HD_RETICLES.size();
		}
		else if (i == &Options::oxceHdFire)
		{
			min = 0;                                  // 0 = the pack's own fire
			max = 3;
		}
		else if (i == &Options::oxceHdFirePace || i == &Options::oxceHdSmokePace)
		{
			min = 0;                                  // 0 = the stock speed, higher = slower
			max = Map::HD_ENVI_PACES - 1;
		}
		else if (i == &Options::oxceHdEnemyNumber)
		{
			min = 0;                                  // 0 none, 1 blinking, 2 steady
			max = 2;
		}
		else if (i == &Options::oxceHdEnemyTurn)
		{
			min = 0;                                  // 0 as it was, 1 hidden screen with a strip, 2 frame and the panel down, 3 frame with a progress bar
			max = 3;
		}
		else if (i == &Options::oxceHdRadar)
		{
			min = 0;                                  // 0 circles, 1 joint wash, 2 wash with the sweep, 3 waves
			max = 3;
		}
		else if (i == &Options::oxceHdRadarWaves)
		{
			min = 0;                                  // 0 all at once each hour, in turn each 1, 3, 6 hours
			max = 3;
		}
		else if (i == &Options::oxceHdMapRotation)
		{
			min = 0;                                  // quarter turns of the battle map
			max = 3;
		}
		else if (i == &Options::oxceHdTrunkArmor)
		{
			min = 0;                                  // 0 as in the game, 1 armor x2, 2 x3, 3 mixed
			max = 3;
		}
		else if (i == &Options::oxceHdBattleHudColor)
		{
			min = 0;                                  // 0 dark slate, 1 gold as the original, 2 Consul's hull, 3 Cruiser's, 4 ship's brass,
			max = 8;                                  // 5 starship, 6 niello silver, 7 black iron and bone, 8 bronze of the deep
		}
		else if (i == &Options::oxceHdCraftLaunch)
		{
			min = 0;                                  // 0 off, 1 crafts with soldiers aboard, 2 every craft
			max = 2;
		}
		else if (i == &Options::oxceHdAltInfo)
		{
			min = 0;                                  // what Alt shows, always: 0 nothing, 1 facing,
			max = 3;                                  // 2 damage and psi in the aim, 3 both
		}
		else if (i == &Options::oxceHdPathNumSize || i == &Options::oxceHdPathNumWeight
			|| i == &Options::oxceHdAimNumSize || i == &Options::oxceHdAimNumWeight)
		{
			*i += increment * 4;                      // percent of the usual, in steps of 5
			min = 50;
			max = 100;
		}
		else if (i == &Options::oxceHdGlobeScale)
		{
			min = 0;                                  // 0 = as the geoscape
			max = 6;
		}
		else if (i == &Options::oxceBaseSoldierGroupBy)
		{
			min = 0;                                  // 0 no groups, 1 race, 2 rank, 3 craft (as on the advanced screen)
			max = 3;
		}
		else if (i == &Options::oxceTradeConfirm)
		{
			min = 0;                                  // confirm from this many lines, 0 never (as on the advanced screen)
			max = 20;
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
	{
		// the main option of dependent rows changed: they turn grey, or back
		const bool *pb = setting->type() == OPTION_BOOL ? setting->asBool() : nullptr;
		const int *pi = setting->type() == OPTION_INT ? setting->asInt() : nullptr;
		if (pb == &Options::oxceHdPathDigits || pi == &Options::oxceHdUi || pi == &Options::oxceHdUiSkin
			|| pi == &Options::oxceHdUiFont || pi == &Options::oxceHdRadar)
		{
			updateList();
			return;
		}
	}
	setValueCell(sel, valueText(*setting), valueColor(*setting));
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
		if (row.group == ROW_LAB)
		{
			desc = tr("STR_HD_LAB_LOCKED_DESC");
		}
		else if (row.group == ROW_LAB_LOCK)
		{
			desc = tr("STR_HD_LAB_RELOCK_DESC");
		}
		else if (row.group == ROW_BETTERAI)
		{
			desc = tr("STR_BETTER_AI_DESC");
		}
		else if (row.group == ROW_ART)
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
			const OptionInfo &info = _groups[row.group].settings[row.index];
			desc = tr(info.description() + "_DESC");
			if (HdGentle::locks(info))
			{
				desc += " ";
				desc += tr("STR_GENTLE_LOCKED_DESC");
			}
			if (battleLocks(info))
			{
				desc += " ";
				desc += tr("STR_HD_NO_BATTLE_SAVES_LOCKED");
			}
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
	if (row.group == ROW_LAB || row.group == ROW_LAB_LOCK || row.group == ROW_BETTERAI || row.group == ROW_BACK)
	{
		changeSetting(sel, SDL_BUTTON_LEFT);
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
			return std::make_pair(valueText(info), HdGentle::locks(info) || battleLocks(info) || aiLocks(info) || dependsOff(info) || (info.type() == OPTION_BOOL && !*info.asBool()) ? _greyedOutColor : (Uint8)0);
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
