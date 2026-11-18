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
#include "../Engine/CrossPlatform.h"
#include "../Engine/FileMap.h"
#include "../Engine/HdSprites.h"
#include "../Engine/HdGentle.h"
#include "../Engine/HdLab.h"
#include "../Engine/HdUi.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Logger.h"
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
#include "OptionsCustomColorState.h"
#include "OptionsButtonFaceState.h"
#include "OptionsButtonInkState.h"
#include "OptionsScreenThemesState.h"

namespace OpenXcom
{

/// Row markers in _rows: ROW_LAB asks for the lab's password, ROW_LAB_LOCK closes the lab again, ROW_BETTERAI opens the
/// BetterAI screen, ROW_BACK goes back from it.
/// ROW_CUSTOM opens the window of the player's own colour of the battle panel; ROW_FACE the window of the windows' buttons'
/// look, ROW_INK the window of their letters.
static const int ROW_NONE = -1, ROW_ART = -2, ROW_LAB = -3, ROW_LAB_LOCK = -4, ROW_BETTERAI = -5, ROW_BACK = -6, ROW_CUSTOM = -7, ROW_FACE = -8, ROW_INK = -9, ROW_WINCUSTOM = -10, ROW_SCREENS = -11, ROW_GUIDE = -13;
/// ROW_GUIDE opens the guide to this menu on the site in the player's browser.
static const char *const HD_GUIDE_URL = "https://x-piratez.mywire.org:8443/hd-wiki/index.html";
/// ROW_SCREENS opens the window of the themes by screen (XP-000484).
/// ROW_WINCUSTOM opens the window of the player's own colour of the windows' metal (XP-000479).
/// ROW_MERGED is a row over several options at once (HD_MERGED); its index in the row is the number in that table.
/// Every marker has its own number: ROW_GUIDE once had -12 too, and every merged row then told the guide's text.
static const int ROW_MERGED = -12;
/// What an entry of a group is: an option (its index in the group's settings), a special row (its marker) or a merged row.
static const int ITEM_OPTION = 0, ITEM_SPECIAL = 1, ITEM_MERGED = 2;

/// The menu, by hand (docs/HD_MENU.md): tabs over the list, three in a row; in each its groups; in each its rows in this
/// order. A row is the id of an option (Options.cpp), a "@" row of its own (HD_SPECIAL) or a merged one ("@m_", HD_MERGED).
/// An option that is in no row is not in the menu.
struct HdGroupDef { const char *title; std::vector<const char*> rows; };
struct HdTabDef { const char *title; std::vector<HdGroupDef> groups; };
static const HdTabDef HD_LAYOUT[] = {
	{ "STR_HD_T_GRAPHICS", {
		{ "STR_HD_G_01", { "@guide", "@art", "oxceAdultAsk", "@m_smooth", "oxceGentle" } },
		{ "STR_HD_G_02", { "@m_light", "@m_shadow" } },
		{ "STR_HD_G_03", { "@m_fire", "oxceHdVolumeSmoke", "oxceHdPlainSmoke" } },
		{ "STR_HD_G_04", { "@m_weather", "@m_tracks" } },
		{ "STR_HD_G_05", { "@m_edge", "oxceHdMapBorder" } } } },
	{ "STR_HD_T_BATTLE", {
		{ "STR_HD_G_06", { "oxceHdFx", "oxceHdHitFlash", "oxceHdClassicShots", "oxceHdQuickFlight", "oxceHdLooseHits", "oxceHdShotCut",
			"oxceHdKillCam", "oxceHdBlastFall", "@m_blood" } },
		{ "STR_HD_G_07", { "@m_enemyturn", "oxceHdEnemyNumber", "oxceHdWalkerTurn" } },
		{ "STR_HD_G_08", { "oxceCollapse", "oxceHdTrunkArmor" } },
		{ "STR_HD_G_25", { "oxceHdCtrlZoom" } } } },
	{ "STR_HD_T_AIM", {
		{ "STR_HD_G_09", { "oxceHdReticle", "oxceHdReticleArtillery", "oxceHdReticleExplosive", "oxceHdReticleDamageColor", "oxceHdAimArc",
			"oxceHdBlastArea", "oxceHdAimSkillBonus", "oxceHdAltInfo", "@m_nums", "oxceHdPathStretch" } },
		{ "STR_HD_G_10", { "@m_panel", "@custom", "oxceHdPanelHide" } },
		{ "STR_HD_G_11", { "oxceHdInvBackdrop", "oxceHdScrollSplit" } } } },
	{ "STR_HD_T_INTERFACE", {
		{ "STR_HD_G_12", { "@m_ui", "oxceHdUiSkin", "oxceHdUiFont", "oxceHdPictures", "oxceHdClassicDolls" } },
		{ "STR_HD_G_13", { "@m_wintheme", "@wincustom", "@screens", "@face", "@ink", "oxceHdButtonTextSize" } },
		{ "STR_HD_G_14", { "oxceHdUpdateNotice", "oxceHdChatNotice" } } } },
	{ "STR_HD_T_WORLD", {
		{ "STR_HD_G_15", { "oxceHdGlobeScale", "oxceHdCraftOutlines", "@m_radar", "oxceHdRadarCraft", "oxceHdCraftRoute", "oxceHdGlobeBox" } },
		{ "STR_HD_G_16", { "@m_craftweap", "oxceDogfightHitChance", "oxceHdPilotVoice" } },
		{ "STR_HD_G_17", { "@m_baseanim", "oxceHdCraftLaunch" } },
		{ "STR_HD_G_18", { "oxceSoldierListGroupBy", "oxceHdCraftFit", "oxceHdCraftMission", "oxceHdArmorSortCraft" } },
		{ "STR_HD_G_19", { "oxceTradeConfirm", "oxceTradeStay", "oxceTransferExchange", "oxceHdTransferConfirm" } },
		{ "STR_HD_G_20", { "oxceHdManufactureTop", "oxceManufactureDelivery", "oxceHdResearchEta" } } } },
	{ "STR_HD_T_GAME", {
		{ "STR_HD_G_21", { "@ai" } },
		{ "STR_HD_G_22", { "oxceNoBattleSaves", "oxceKnowledgeArmor", "oxceCatchThrown" } },
		{ "STR_HD_G_23", { "oxceHdGpu", "oxceHdThreads", "oxceCompactSave" } },
		{ "STR_HD_G_24", { "oxceHdMapRotation" } } } } };
static const int HD_TAB_COUNT = sizeof(HD_LAYOUT) / sizeof(HD_LAYOUT[0]);
/// The group of the HD lab (Engine/HdLab.h): its rows show only once the password was given.
static const std::string LAB_GROUP = "STR_HD_G_24";
/// The rows of their own: the marker they have in _rows.
static const struct { const char *key; int marker; } HD_SPECIAL[] = {
	{ "@art", ROW_ART }, { "@ai", ROW_BETTERAI }, { "@custom", ROW_CUSTOM }, { "@wincustom", ROW_WINCUSTOM },
	{ "@screens", ROW_SCREENS }, { "@face", ROW_FACE }, { "@ink", ROW_INK }, { "@guide", ROW_GUIDE } };

/// The merged rows: one row over several options, with a value list of its own. They only write the options' values (the
/// variables and the keys of options.cfg are as ever); none of these options had more to do on a change than the list built again.
enum { M_SMOOTH, M_UI, M_LIGHT, M_SHADOW, M_FIRE, M_WEATHER, M_BLOOD, M_TRACKS, M_EDGE, M_ENEMYTURN, M_PANEL, M_WINTHEME, M_NUMS,
	M_CRAFTWEAP, M_RADAR, M_BASEANIM };
static const struct { const char *key; const char *name; bool isBool; std::vector<const char*> options; } HD_MERGED[] = {
	{ "@m_smooth", "STR_HD_M_SMOOTH", true, { "oxceHdMode", "oxceHdUiSmooth" } },
	{ "@m_ui", "STR_HD_UI", true, { "oxceHdUi" } },
	{ "@m_light", "STR_HD_M_LIGHT", false, { "oxceHdLight", "oxceHdFlashLight" } },
	{ "@m_shadow", "STR_HD_M_SHADOW", false, { "oxceHdUnitShadow", "oxceHdItemShadow", "oxceHdFloorAo" } },
	{ "@m_fire", "STR_HD_M_FIRE", false, { "oxceHdFire", "oxceHdVolumeFire" } },
	{ "@m_weather", "STR_HD_M_WEATHER", false, { "oxceHdWeather", "oxceHdWeatherSound" } },
	{ "@m_blood", "STR_HD_M_BLOOD", false, { "oxceHdBloodColor", "oxceHdBloodSpray", "oxceHdBloodCloud" } },
	{ "@m_tracks", "STR_HD_M_TRACKS", false, { "oxceHdBloodSteps", "oxceHdSnowTracks" } },
	{ "@m_edge", "STR_HD_M_EDGE", false, { "oxceHdBackdrop", "oxceHdBeyondEdge", "oxceHdBeyondLook" } },
	{ "@m_enemyturn", "STR_HD_M_ENEMY_TURN", false, { "oxceHdEnemyTurn", "oxceHdHiddenMap" } },
	{ "@m_panel", "STR_HD_M_PANEL", false, { "oxceHdBattleHud", "oxceHdBattleHudColor" } },
	{ "@m_wintheme", "STR_HD_M_WINTHEME", false, { "oxceHdWindowTheme", "oxceHdWindowThemeColor" } },
	{ "@m_nums", "STR_HD_M_NUMS", false, { "oxceHdAimNumSize", "oxceHdPathNumSize" } },
	{ "@m_craftweap", "STR_HD_M_CRAFT_WEAPONS", false, { "oxceCraftWeaponIcons", "oxceHdCraftWeaponToggle" } },
	{ "@m_radar", "STR_HD_M_RADAR", false, { "oxceHdRadar", "oxceHdRadarWaves" } },
	{ "@m_baseanim", "STR_HD_M_BASE_ANIM", true, { "oxceHdBaseAnim", "oxceHdCraftLights" } } };
static const int HD_MERGED_COUNT = sizeof(HD_MERGED) / sizeof(HD_MERGED[0]);
/// How many values a merged row has.
static int mergedCount(int m)
{
	switch (m)
	{
	case M_SMOOTH: case M_UI: case M_BLOOD: case M_BASEANIM: return 2;
	case M_LIGHT: case M_SHADOW: case M_WEATHER: case M_CRAFTWEAP: return 3;
	case M_TRACKS: case M_ENEMYTURN: return 4;
	case M_FIRE: case M_EDGE: return 5;                  // fire: its four styles and the tongues of flame
	case M_RADAR: return 7;                              // the circles, the wash, the wash with the sweep, the waves in 4 paces
	case M_PANEL: return 11;                             // classic, then the panel's 10 colours
	case M_NUMS: return 11;                              // 50..100 percent in steps of 5
	case M_WINTHEME: return 12;                          // off, then the 11 values of the windows' colour
	}
	return 2;
}
/// Which value of a merged row the options are at now.
static int mergedCurrent(int m)
{
	using namespace Options;
	switch (m)
	{
	case M_SMOOTH: return oxceHdMode == 2 || (oxceHdMode == 0 && oxceHdUiSmooth) ? 1 : 0;
	case M_UI: return oxceHdUi > 0 ? 1 : 0;
	case M_LIGHT: return !oxceHdLight ? 0 : oxceHdFlashLight ? 2 : 1;
	case M_SHADOW: return oxceHdFloorAo && oxceHdUnitShadow ? 2 : (oxceHdUnitShadow || oxceHdItemShadow) ? 1 : 0;
	case M_FIRE: return oxceHdVolumeFire ? 4 : std::max(0, std::min(3, oxceHdFire));
	case M_WEATHER: return !oxceHdWeather ? 0 : oxceHdWeatherSound ? 2 : 1;
	case M_BLOOD: return (oxceHdBloodColor || oxceHdBloodSpray || oxceHdBloodCloud) ? 1 : 0;
	case M_TRACKS: return (oxceHdBloodSteps ? 1 : 0) + (oxceHdSnowTracks ? 2 : 0);
	case M_EDGE: return oxceHdBeyondEdge ? 2 + std::max(0, std::min(2, oxceHdBeyondLook)) : oxceHdBackdrop ? 1 : 0;
	case M_ENEMYTURN: return oxceHdEnemyTurn == 2 ? 2 : oxceHdEnemyTurn == 3 ? 3 : (oxceHdEnemyTurn == 1 || !oxceHdHiddenMap) ? 0 : 1;
	case M_PANEL: return !oxceHdBattleHud ? 0 : std::max(0, std::min(9, oxceHdBattleHudColor)) + 1;
	case M_WINTHEME: return !oxceHdWindowTheme ? 0 : std::max(0, std::min(10, oxceHdWindowThemeColor)) + 1;
	case M_NUMS: return (std::max(50, std::min(100, oxceHdAimNumSize)) - 50 + 2) / 5;
	case M_CRAFTWEAP: return !oxceCraftWeaponIcons ? 0 : oxceHdCraftWeaponToggle ? 2 : 1;
	case M_RADAR: return oxceHdRadar < 3 ? std::max(0, oxceHdRadar) : 3 + std::max(0, std::min(3, oxceHdRadarWaves));
	case M_BASEANIM: return (oxceHdBaseAnim || oxceHdCraftLights) ? 1 : 0;
	}
	return 0;
}
/// Puts the options of a merged row at its value v.
static void mergedSet(int m, int v)
{
	using namespace Options;
	switch (m)
	{
	case M_SMOOTH:
		oxceHdUiSmooth = v != 0;
		if (oxceHdMode != 0) oxceHdMode = v ? 2 : 1;
		if (oxceHdUi > 0) oxceHdUi = v ? 2 : 1;
		break;
	case M_UI:
		oxceHdUi = v == 0 ? 0 : mergedCurrent(M_SMOOTH) ? 2 : 1;
		break;
	case M_LIGHT:
		oxceHdLight = v > 0;
		if (v > 0) oxceHdFlashLight = v == 2;
		break;
	case M_SHADOW:
		oxceHdUnitShadow = oxceHdItemShadow = v > 0;
		oxceHdFloorAo = v == 2;
		break;
	case M_FIRE:
		if (v < 4)
		{
			oxceHdFire = v;
			oxceHdVolumeFire = false;
		}
		else
		{
			oxceHdVolumeFire = true;
		}
		break;
	case M_WEATHER:
		oxceHdWeather = v > 0;
		if (v > 0) oxceHdWeatherSound = v == 2;
		break;
	case M_BLOOD:
		oxceHdBloodColor = oxceHdBloodSpray = oxceHdBloodCloud = v != 0;
		break;
	case M_TRACKS:
		oxceHdBloodSteps = (v & 1) != 0;
		oxceHdSnowTracks = (v & 2) != 0;
		break;
	case M_EDGE:
		if (v < 2)
		{
			oxceHdBackdrop = v == 1;
			oxceHdBeyondEdge = false;
		}
		else
		{
			oxceHdBeyondEdge = true;                      // the backdrop stays as it is
			oxceHdBeyondLook = v - 2;
		}
		break;
	case M_ENEMYTURN:
		oxceHdHiddenMap = v > 0;
		oxceHdEnemyTurn = v >= 2 ? v : 0;
		break;
	case M_PANEL:
		oxceHdBattleHud = v > 0;
		if (v > 0) oxceHdBattleHudColor = v - 1;
		break;
	case M_WINTHEME:
		oxceHdWindowTheme = v > 0;
		if (v > 0) oxceHdWindowThemeColor = v - 1;
		break;
	case M_NUMS:
		oxceHdAimNumSize = oxceHdPathNumSize = 50 + v * 5;
		break;
	case M_CRAFTWEAP:
		oxceCraftWeaponIcons = v > 0;
		if (v > 0) oxceHdCraftWeaponToggle = v == 2;
		break;
	case M_RADAR:
		if (v < 3)
		{
			oxceHdRadar = v;
		}
		else
		{
			oxceHdRadar = 3;
			oxceHdRadarWaves = v - 3;
		}
		break;
	case M_BASEANIM:
		oxceHdBaseAnim = oxceHdCraftLights = v != 0;
		break;
	}
}
/// Is the special row grey (its window opens all the same)? The conditions are those of the rows it stood under.
static bool specialGrey(int marker)
{
	const bool skin = Options::oxceHdUi > 0 && Options::oxceHdUiSkin > 0;
	switch (marker)
	{
	case ROW_CUSTOM: return !skin;
	case ROW_WINCUSTOM: case ROW_FACE: case ROW_INK: return !skin || !Options::oxceHdWindowTheme;
	case ROW_SCREENS: return Options::oxceHdUi <= 0 || Options::oxceHdUiSkin <= 0;   // (the themes need the skin; the global switch of the theme they do not)
	}
	return false;
}
/// The label of the special row (the window it opens is marked by " >" after it).
static const char *specialLabel(int marker)
{
	switch (marker)
	{
	case ROW_CUSTOM: return "STR_HD_CUSTOM_COLOR";
	case ROW_WINCUSTOM: return "STR_HD_WIN_CUSTOM_COLOR";
	case ROW_SCREENS: return "STR_HD_SCREEN_THEMES";
	case ROW_FACE: return "STR_HD_BUTTON_FACE";
	case ROW_INK: return "STR_HD_BUTTON_INK";
	case ROW_GUIDE: return "STR_HD_GUIDE";
	}
	return "";
}
/// The tab open last: the window opens on it again, until the game is closed.
static int hdTab = 0;
/// The category of BetterAI (Battlescape/AiProbe.h): its rows are on the BetterAI screen, not in the main list.
static const std::string AI_CATEGORY = "STR_HD_AI";

/**
 * Initializes all the elements in the HD Options window.
 * @param origin Game section that originated this state.
 */
OptionsHdState::OptionsHdState(OptionsOrigin origin) : OptionsBaseState(origin), _betterAiView(false), _aiGroup(-1)
{
	setHdScreen("hdMenu");
	setCategory(_btnHd);

	for (int t = 0; t < HD_TAB_COUNT; ++t)
	{
		// a pixel apart both ways, as the categories on the left (they stood 4 apart across and 1 down), and the
		// label a step smaller than a category's: a tab is the lesser button
		_btnTabs.push_back(new TextButton(66, 12, 94 + (t % 3) * 67, 8 + (t / 3) * 13));
		_btnTabs.back()->setHdCapScale(0.85f);
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
		_btnTabs[t]->setText(tr(HD_LAYOUT[t].title));
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

	for (int t = 0; t < HD_TAB_COUNT; ++t)
	{
		for (const auto &def : HD_LAYOUT[t].groups)
		{
			Group group;
			group.title = def.title;
			group.tab = t;
			group.lab = group.title == LAB_GROUP;
			for (const char *row : def.rows)
			{
				const std::string key = row;
				bool found = false;
				if (key[0] == '@')
				{
					for (const auto &s : HD_SPECIAL)
					{
						if (key == s.key)
						{
							group.items.push_back(Item{ ITEM_SPECIAL, s.marker });
							found = true;
						}
					}
					for (int m = 0; m < HD_MERGED_COUNT; ++m)
					{
						if (key == HD_MERGED[m].key)
						{
							// a fire style without its pictures in the active mods would change nothing: the row is not offered
							if (m != M_FIRE || fireShipped)
							{
								group.items.push_back(Item{ ITEM_MERGED, m });
							}
							found = true;
						}
					}
					if (!found)
					{
						Log(LOG_WARNING) << "HD menu: no row " << key;
					}
					continue;
				}
				for (const auto& optionInfo : Options::getOptionInfo())
				{
					if (optionInfo.id() != key)
					{
						continue;
					}
					found = true;
					if (optionInfo.type() == OPTION_KEY || optionInfo.description().empty())
					{
						break;
					}
					// asking at every start only means something when there is an adult tree to choose
					// (asBool throws on an option of another type, so the type is checked first)
					if (optionInfo.type() == OPTION_BOOL && optionInfo.asBool() == &Options::oxceAdultAsk && !_adultShipped)
					{
						break;
					}
					if (optionInfo.type() == OPTION_INT && (optionInfo.asInt() == &Options::oxceHdReticle || optionInfo.asInt() == &Options::oxceHdReticleArtillery
						|| optionInfo.asInt() == &Options::oxceHdReticleExplosive) && !reticleShipped)
					{
						break;
					}
					group.items.push_back(Item{ ITEM_OPTION, (int)group.settings.size() });
					group.settings.push_back(optionInfo);
					break;
				}
				if (!found)
				{
					Log(LOG_WARNING) << "HD menu: no option " << key;
				}
			}
			_groups.push_back(group);
		}
	}
	// the rows of the BetterAI screen (the @ai row opens it): the options of its category, off every tab
	Group ai;
	ai.title = AI_CATEGORY;
	ai.tab = -1;
	ai.lab = false;
	for (const auto& optionInfo : Options::getOptionInfo())
	{
		if (optionInfo.category() == AI_CATEGORY && optionInfo.type() != OPTION_KEY && !optionInfo.description().empty())
		{
			ai.settings.push_back(optionInfo);
		}
	}
	if (!ai.settings.empty())
	{
		_aiGroup = (int)_groups.size();
		_groups.push_back(ai);
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
	addValueRow(group, index, label, valueText(info), valueColor(info), grey);
}

/**
 * The rows of a setting or of a merged row, whose value and its color are known (see addSettingRow).
 */
void OptionsHdState::addValueRow(int group, int index, const std::string &label, const std::string &value, Uint8 color, bool grey)
{
	if (!longValue(value))
	{
		addRow(group, index, label, value);
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 1, color);
	}
	else
	{
		addRow(group, index, label, "", 1);
		addRow(group, index, "   " + value, "", 2);
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 0, color);
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
	for (size_t g = 0; g < _groups.size(); ++g)
	{
		const Group &group = _groups[g];
		if (group.items.empty() || group.tab != tab)
		{
			continue;
		}
		if (!_rows.empty() && _rows.back().group != ROW_NONE)
		{
			addRow(ROW_NONE, 0, "", "");
		}
		addRow(ROW_NONE, 0, tr(group.title), "");
		_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 0, _colorGroup);
		if (group.lab && !HdLab::unlocked())
		{
			// the lab's rows stay hidden: one row asks for the password
			addRow(ROW_LAB, 0, tr("STR_HD_LAB_LOCKED"), tr("STR_HD_LAB_ENTER"));
			continue;
		}
		for (const Item &item : group.items)
		{
			if (item.kind == ITEM_OPTION)
			{
				const OptionInfo &info = group.settings[item.index];
				const bool gentle = HdGentle::locks(info);
				// grey out options a mod, the gentle mode or the battle in progress fixes
				addSettingRow((int)g, item.index, gentle ? std::string(tr(info.description())) + " " + std::string(tr("STR_GENTLE_LOCKED")) : std::string(tr(info.description())),
					gentle || battleLocks(info) || dependsOff(info) || fixeduserOptions.find(info.id()) != fixeduserOptions.end());
			}
			else if (item.kind == ITEM_MERGED)
			{
				addValueRow(ROW_MERGED, item.index, tr(HD_MERGED[item.index].name), mergedValue(item.index, mergedCurrent(item.index)),
					mergedColor(item.index), mergedGrey(item.index));
			}
			else if (item.index == ROW_ART)
			{
				addRow(ROW_ART, 0, tr("STR_HD_ART_VERSION"), artText());
			}
			else if (item.index == ROW_BETTERAI)
			{
				// BetterAI opens its own screen; the value is its switch's
				addRow(ROW_BETTERAI, 0, std::string(tr("STR_BETTER_AI")) + " >", Options::oxceBetterAi ? tr("STR_YES") : tr("STR_NO"));
				_lstOptions->setCellColor(_lstOptions->getLastRowIndex(), 1, Options::oxceBetterAi ? _lstOptions->getColor() : _greyedOutColor);
			}
			else
			{
				// a window of its own, opened by the row (the colour of the battle panel, of the windows, the themes by screen,
				// the buttons' look and letters)
				addRow(item.index, 0, std::string(tr(specialLabel(item.index))) + " >", "");
				if (specialGrey(item.index))
				{
					_lstOptions->setRowColor(_lstOptions->getLastRowIndex(), _greyedOutColor);
				}
			}
		}
		if (group.lab)
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
		if (p == &Options::oxceHdButtonTextSize) return !fonts;
		if (p == &Options::oxceHdWindowThemeColor) return !skin || !Options::oxceHdWindowTheme;
		if (p == &Options::oxceHdRadarWaves) return Options::oxceHdRadar != 3;
		if (p == &Options::oxceHdRadarCraft) return Options::oxceHdRadar == 0;
		if (p == &Options::oxceHdTrunkArmor) return !Options::oxceCollapse;
		if (p == &Options::oxceHdInvBackdrop) return !Options::oxceHdPictures || Options::oxceHdUi <= 0;
		if (p == &Options::oxceHdBloodStepsLife || p == &Options::oxceHdBloodStepsColor) return !Options::oxceHdBloodSteps;
	}
	else if (info.type() == OPTION_BOOL)
	{
		const bool *b = info.asBool();
		if (b == &Options::oxceHdBattleHud || b == &Options::oxceHdWindowTheme) return !skin;
		if (b == &Options::oxceHdInventoryKeys) return !skin || !Options::oxceHdBattleHud;
		if (b == &Options::oxceHdClassicDolls) return !Options::oxceHdPictures;
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

/**
 * The name of a value of a merged row.
 */
std::string OptionsHdState::mergedValue(int m, int v) const
{
	if (HD_MERGED[m].isBool)
	{
		return v ? tr("STR_YES") : tr("STR_NO");
	}
	const std::string n = std::to_string(v);
	switch (m)
	{
	case M_LIGHT: case M_SHADOW: case M_WEATHER: case M_BLOOD: case M_TRACKS: case M_EDGE: case M_ENEMYTURN: case M_CRAFTWEAP:
		return tr(std::string(HD_MERGED[m].name) + "_" + n);
	case M_FIRE:
		return v < 4 ? tr("STR_HD_FIRE_" + n) : tr("STR_HD_M_FIRE_TONGUES");
	case M_PANEL:
		return v == 0 ? tr("STR_HD_M_PANEL_CLASSIC") : tr("STR_HD_BATTLE_HUD_COLOR_" + std::to_string(v - 1));
	case M_WINTHEME:
		if (v == 0)
		{
			return tr("STR_HD_M_WINTHEME_OFF");
		}
		// the value of the windows' colour is v - 1: 0 as the battle panel's, then the panel's names (its value + 1)
		return v == 1 ? tr("STR_HD_WINDOW_THEME_COLOR_SAME") : tr("STR_HD_BATTLE_HUD_COLOR_" + std::to_string(std::min(v - 2, 9)));
	case M_NUMS:
		return std::to_string(50 + v * 5) + "%";
	case M_RADAR:
		if (v < 3)
		{
			return tr("STR_HD_RADAR_" + n);
		}
		return std::string(tr("STR_HD_M_RADAR_WAVES")) + ": " + std::string(tr("STR_HD_RADAR_WAVES_" + std::to_string(v - 3)));
	}
	return n;
}

/**
 * Is a merged row fixed by a mod: one of its options is among those the mod fixes?
 */
bool OptionsHdState::mergedFixed(int m) const
{
	auto& fixeduserOptions = _game->getMod()->getFixedUserOptions();
	for (const char *id : HD_MERGED[m].options)
	{
		if (fixeduserOptions.find(id) != fixeduserOptions.end())
		{
			return true;
		}
	}
	return false;
}

/**
 * Is a merged row grey? As the old row it took the place of was: the panel's and the windows' rows without the skin,
 * the numbers' without the HD font; or a mod fixes one of its options (such a row does not change).
 */
bool OptionsHdState::mergedGrey(int m) const
{
	const bool skin = Options::oxceHdUi > 0 && Options::oxceHdUiSkin > 0;
	const bool fonts = skin && Options::oxceHdUiFont > 0;
	return mergedFixed(m) || (m == M_PANEL && !skin) || (m == M_WINTHEME && !skin) || (m == M_NUMS && !fonts);
}

/**
 * The color of a merged row's value: grey when the row is, and a "no" of a yes-no row (as in valueColor).
 */
Uint8 OptionsHdState::mergedColor(int m) const
{
	if (mergedGrey(m) || (HD_MERGED[m].isBool && mergedCurrent(m) == 0))
	{
		return _greyedOutColor;
	}
	return _lstOptions->getColor();
}

/**
 * Steps a merged row to its next value (or the previous one), round the list; the list is built again, the other rows
 * can be changed by it (the interface row by the smooth one, the greys).
 */
void OptionsHdState::changeMerged(int m, int increment)
{
	if (mergedFixed(m))
	{
		return;
	}
	const int n = mergedCount(m);
	mergedSet(m, (mergedCurrent(m) + increment + n) % n);
	updateList();
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
	// the smoke: the pack's own, puffs, puffs over a veil (STR_HD_VOLUME_SMOKE_0..2)
	if (info.asInt() == &Options::oxceHdVolumeSmoke)
	{
		return tr("STR_HD_VOLUME_SMOKE_" + std::to_string(std::max(0, std::min(2, Options::oxceHdVolumeSmoke))));
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
	// how long the bloody soles last: the turns, 11 = always; their colour by name
	if (info.asInt() == &Options::oxceHdBloodStepsLife)
	{
		if (Options::oxceHdBloodStepsLife >= 11)
		{
			return tr("STR_HD_BLOOD_STEPS_LIFE_ALWAYS");
		}
		return std::to_string(std::max(1, Options::oxceHdBloodStepsLife));
	}
	if (info.asInt() == &Options::oxceHdBloodStepsColor)
	{
		return tr("STR_HD_BLOOD_STEPS_COLOR_" + std::to_string(Options::oxceHdBloodStepsColor));
	}
	if (info.asInt() == &Options::oxceHdEnemyTurn)
	{
		return tr("STR_HD_ENEMY_TURN_" + std::to_string(Options::oxceHdEnemyTurn));
	}
	if (info.asInt() == &Options::oxceHdBeyondLook)
	{
		return tr("STR_HD_BEYOND_LOOK_" + std::to_string(Options::oxceHdBeyondLook));
	}
	if (info.asInt() == &Options::oxceHdMapBorder)
	{
		return tr("STR_HD_MAP_BORDER_" + std::to_string(Options::oxceHdMapBorder));
	}
	if (info.asInt() == &Options::oxceHdInvBackdrop)
	{
		return tr("STR_HD_INV_BACKDROP_" + std::to_string(Options::oxceHdInvBackdrop));
	}
	if (info.asInt() == &Options::oxceHdRadar)
	{
		return tr("STR_HD_RADAR_" + std::to_string(Options::oxceHdRadar));
	}
	if (info.asInt() == &Options::oxceHdRadarWaves)
	{
		return tr("STR_HD_RADAR_WAVES_" + std::to_string(Options::oxceHdRadarWaves));
	}
	if (info.asInt() == &Options::oxceHdRadarCraft)
	{
		return tr("STR_HD_RADAR_CRAFT_" + std::to_string(Options::oxceHdRadarCraft));
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
	if (info.asInt() == &Options::oxceHdWindowThemeColor)
	{
		// 0 as the battle panel's, then the panel's names (its value + 1)
		const int v = Options::oxceHdWindowThemeColor;
		return v <= 0 ? tr("STR_HD_WINDOW_THEME_COLOR_SAME") : tr("STR_HD_BATTLE_HUD_COLOR_" + std::to_string(std::min(v - 1, 9)));
	}
	if (info.asInt() == &Options::oxceHdPathNumSize || info.asInt() == &Options::oxceHdPathNumWeight
		|| info.asInt() == &Options::oxceHdAimNumSize || info.asInt() == &Options::oxceHdAimNumWeight)
	{
		return std::to_string(std::max(50, std::min(100, *info.asInt()))) + "%";
	}
	if (info.asInt() == &Options::oxceHdButtonTextSize)
	{
		return std::to_string(std::max(60, std::min(100, *info.asInt()))) + "%";
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
		if (Options::oxceHdScale <= 1)
		{
			Options::oxceHdScale = 4;                 // the menu has no row of the scale: HD at the scale of 1 shows nothing new
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
	if (row.group == ROW_MERGED)
	{
		changeMerged(row.index, increment);
		return;
	}
	if (row.group == ROW_CUSTOM)
	{
		// the list is filled again when the window closes (init): the panel's colour row shows the own one
		_game->pushState(new OptionsCustomColorState(_origin));
		return;
	}
	if (row.group == ROW_WINCUSTOM)
	{
		_game->pushState(new OptionsCustomColorState(_origin, true));
		return;
	}
	if (row.group == ROW_SCREENS)
	{
		_game->pushState(new OptionsScreenThemesState(_origin));
		return;
	}
	if (row.group == ROW_GUIDE)
	{
		CrossPlatform::openExplorer(HD_GUIDE_URL);
		return;
	}
	if (row.group == ROW_FACE)
	{
		_game->pushState(new OptionsButtonFaceState(_origin));
		return;
	}
	if (row.group == ROW_INK)
	{
		_game->pushState(new OptionsButtonInkState(_origin));
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
		else if (i == &Options::oxceHdVolumeSmoke)
		{
			min = 0;                                  // 0 the pack's smoke, 1 puffs, 2 puffs over a veil
			max = 2;
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
		else if (i == &Options::oxceHdBloodStepsLife)
		{
			min = 1;                                  // bloody soles: 1..10 turns, 11 = always
			max = 11;
		}
		else if (i == &Options::oxceHdBloodStepsColor)
		{
			min = 0;                                  // 0 by the creature, 1 red
			max = 1;
		}
		else if (i == &Options::oxceHdBeyondLook || i == &Options::oxceHdMapBorder)
		{
			min = 0;                                  // beyond the edge: 0 as it is, 1 black and white, 2 fog; border: 0 off, 1 line, 2 fence
			max = 2;
		}
		else if (i == &Options::oxceHdInvBackdrop)
		{
			min = 0;                                  // inventory: 0 black, 1 armoury, 2 ship's hold, 3 canvas
			max = 3;
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
		else if (i == &Options::oxceHdRadarCraft)
		{
			min = 0;                                  // a craft out: 0 its circle, 1 a wave each cycle, 2 a beam
			max = 2;
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
			max = 9;                                  // 5 starship, 6 niello silver, 7 black iron and bone, 8 bronze of the deep, 9 the player's own
		}
		else if (i == &Options::oxceHdWindowThemeColor)
		{
			min = 0;                                  // 0 as the battle panel's, 1..10 the panel's colours 0..9 (10 the player's own)
			max = 10;
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
		else if (i == &Options::oxceHdButtonTextSize)
		{
			*i += increment * 4;                      // percent of the usual, in steps of 5
			min = 60;
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
		if (pb == &Options::oxceHdPathDigits || pb == &Options::oxceHdBloodSteps || pi == &Options::oxceHdUi || pi == &Options::oxceHdUiSkin
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
		else if (row.group == ROW_CUSTOM)
		{
			desc = tr("STR_HD_CUSTOM_COLOR_DESC");
		}
		else if (row.group == ROW_WINCUSTOM)
		{
			desc = tr("STR_HD_WIN_CUSTOM_COLOR_DESC");
		}
		else if (row.group == ROW_SCREENS)
		{
			desc = tr("STR_HD_SCREEN_THEMES_DESC");
		}
		else if (row.group == ROW_GUIDE)
		{
			desc = tr("STR_HD_GUIDE_DESC");
		}
		else if (row.group == ROW_FACE)
		{
			desc = tr("STR_HD_BUTTON_FACE_DESC");
		}
		else if (row.group == ROW_INK)
		{
			desc = tr("STR_HD_BUTTON_INK_DESC");
		}
		else if (row.group == ROW_MERGED)
		{
			desc = tr(std::string(HD_MERGED[row.index].name) + "_DESC");
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
	if (row.group == ROW_LAB || row.group == ROW_LAB_LOCK || row.group == ROW_BETTERAI || row.group == ROW_BACK || row.group == ROW_CUSTOM || row.group == ROW_WINCUSTOM || row.group == ROW_SCREENS || row.group == ROW_FACE || row.group == ROW_INK || row.group == ROW_GUIDE)
	{
		changeSetting(sel, SDL_BUTTON_LEFT);
		return;
	}
	const std::string name = row.group == ROW_ART ? tr("STR_HD_ART_VERSION") : row.group == ROW_MERGED ? tr(HD_MERGED[row.index].name)
		: tr(_groups[row.group].settings[row.index].description());
	_game->pushState(new OptionDetailState(_origin, name, rowDescription(sel),
		[this, sel, row](Uint8 b)
		{
			if (row.group == ROW_MERGED)
			{
				// (the list is built again by a change, so the row is told by its number, not by its place in the list)
				if (b != 0)
				{
					changeMerged(row.index, b == SDL_BUTTON_LEFT ? 1 : -1);
				}
				return std::make_pair(mergedValue(row.index, mergedCurrent(row.index)), mergedColor(row.index) == _greyedOutColor ? _greyedOutColor : (Uint8)0);
			}
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
