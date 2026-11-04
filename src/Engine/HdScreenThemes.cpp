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
#include "HdScreenThemes.h"
#include <algorithm>
#include <sstream>
#include <vector>
#include "CrossPlatform.h"
#include "HdBattleHud.h"
#include "Logger.h"
#include "Options.h"
#include "Yaml.h"

namespace OpenXcom
{

namespace
{

const char *FILE_NAME = "hd_screen_themes.yml";

/// The tree's top: the groups under "all" and the screens (the interface categories of the ruleset) in each. A name the table
/// does not know hangs straight under "all". The groups have the names of the main screens too (geoscape, basescape): that
/// screen is the group itself. The table of every screen is stage 4 of XP-000484.
struct Group
{
	const char *name;
	const char *screens;   ///< names, separated by spaces
};

const Group GROUPS[] = {
	{ "menu", "mainMenu newGameMenu newBattleMenu optionsMenu saveMenus modsMenu pauseMenu noteMenu oxceLinks endGameStatistics "
		"tests ufopaedia statsForNerds" },
	{ "geoscape", "intercept dogfight dogfightExperience dogfightInfo graphs fundingWindow monthlyReport ufoTracker geoCraft "
		"selectMusicTrack itemsArriving baseNaming baseDestroyed targetInfo multipleTargets" },
	{ "basescape", "baseInfo allocateManufacture allocateMartial allocatePsi allocateResearch buyMenu sellMenu costsInfo craftArmor "
		"craftEquipment craftEquipmentLoad craftEquipmentSave craftInfo craftPilots craftPilotsSelect craftSelect craftSoldiers "
		"craftWeapons dependencyTree dismantleFacility globalContainmentMenu globalManufactureMenu globalResearchDiary "
		"globalResearchMenu itemLocations manageContainment manufactureInfo manufactureMenu placeFacility researchMenu sackSoldier "
		"selectFacility selectNewManufacture selectNewResearch soldierArmor soldierAvatar soldierBonus soldierDiary "
		"soldierDiaryLight soldierDiaryMission soldierDiaryPerformance soldierInfo soldierList soldierMemorial soldierRank "
		"soldierTransform soldierTransformation soldierVoice storesInfo techTreeSelect techTreeViewer transferBaseSelect "
		"transferConfirm transferInfo transferMenu transformationList" },
	{ "battlescape", "debriefing commendations commendationsLate promotions cannotReequip" },
	{ "messages", "UFOInfo UFOLost alienBase terrorSite craftError craftPilotError craftPatrol lowFuel geoscapeEvent geoManufacture "
		"geoManufactureComplete geoNewCraft geoNewFacility geoNewItem geoResearch geoResearchComplete geoResearchRequired "
		"trainingFinished martialTraining psiTraining" },
	{ "landing", "confirmLanding confirmCydonia confirmDestination" },
};

const char *ALL = "all";

/// Screen -> its parent: every group and every screen of the table.
const std::unordered_map<std::string, std::string> &tree()
{
	static const std::unordered_map<std::string, std::string> t = []
	{
		std::unordered_map<std::string, std::string> m;
		m[ALL] = "";
		for (const Group &g : GROUPS)
		{
			m[g.name] = ALL;
			std::istringstream in(g.screens);
			std::string s;
			while (in >> s)
			{
				// (a screen named like its group, as geoscape and basescape are, is the group)
				if (m.find(s) == m.end())
				{
					m[s] = g.name;
				}
			}
		}
		return m;
	}();
	return t;
}

/// One value of a theme: its key in the file, its place in Values, its bounds and the option it is laid into.
struct Field
{
	const char *key;
	int HdScreenThemes::Values::*value;
	int lo, hi;
	int *option;      ///< nullptr for a value kept only (text) or a boolean option (boolOption)
	bool *boolOption;
	int unit;         ///< what the player edits together: 0 the colour, 1 the buttons' look, 2 their letters, 3 the plain text
};

/// The windows' skin (oxceHdUiSkin) is not here on purpose: more than a dozen places read it outside the blit of a state
/// (WarningMessage, Surface, HdUpdateNotice...), so it stays one common option. An old "skin" key in the file is not read.
const Field *fields(size_t &count)
{
	using V = HdScreenThemes::Values;
	static const Field F[] = {
		{ "windowTheme", &V::windowTheme, 0, 1, nullptr, &Options::oxceHdWindowTheme, 0 },
		{ "color", &V::color, 0, 10, &Options::oxceHdWindowThemeColor, nullptr, 0 },
		{ "hue", &V::hue, 0, 359, &Options::oxceHdWinKeyHue, nullptr, 0 },
		{ "sat", &V::sat, 0, 100, &Options::oxceHdWinKeySat, nullptr, 0 },
		{ "val", &V::val, 0, 100, &Options::oxceHdWinKeyVal, nullptr, 0 },
		{ "face", &V::face, 0, HdBattleHud::FACES - 1, &Options::oxceHdButtonFace, nullptr, 1 },
		{ "shape", &V::shape, 0, HdBattleHud::SHAPES - 1, &Options::oxceHdButtonShape, nullptr, 1 },
		{ "gloss", &V::gloss, 0, 100, &Options::oxceHdButtonGloss, nullptr, 1 },
		{ "inkTone", &V::inkTone, 0, 2, &Options::oxceHdButtonInkTone, nullptr, 2 },
		{ "inkHue", &V::inkHue, 0, 360, &Options::oxceHdButtonInkHue, nullptr, 2 },
		{ "inkLight", &V::inkLight, 0, 100, &Options::oxceHdButtonInkLight, nullptr, 2 },
		{ "inkSat", &V::inkSat, 0, 100, &Options::oxceHdButtonInkSat, nullptr, 2 },
		{ "textHue", &V::textHue, 0, 360, nullptr, nullptr, 3 },
		{ "textSat", &V::textSat, 0, 100, nullptr, nullptr, 3 },
	};
	count = sizeof(F) / sizeof(F[0]);
	return F;
}

}

bool HdScreenThemes::Values::any() const
{
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n; ++i)
	{
		if (this->*f[i].value >= 0) return true;
	}
	return false;
}

void HdScreenThemes::Values::inherit(const Values &parent)
{
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n; ++i)
	{
		if (this->*f[i].value < 0) this->*f[i].value = parent.*f[i].value;
	}
}

HdScreenThemes &HdScreenThemes::instance()
{
	static HdScreenThemes themes;
	return themes;
}

std::string HdScreenThemes::path()
{
	return Options::getConfigFolder() + FILE_NAME;
}

std::string HdScreenThemes::parentOf(const std::string &screen)
{
	if (screen == ALL) return "";
	const auto &t = tree();
	const auto found = t.find(screen);
	return found == t.end() ? ALL : found->second;
}

bool HdScreenThemes::known(const std::string &name)
{
	return tree().find(name) != tree().end();
}

void HdScreenThemes::load()
{
	_own.clear();
	_cache.clear();
	const std::string file = path();
	if (!CrossPlatform::fileExists(file))
	{
		return;
	}
	try
	{
		YAML::YamlRootNodeReader reader(file);
		size_t n;
		const Field *f = fields(n);
		std::unordered_map<std::string, Values> read;
		const YAML::YamlNodeReader screens = reader["screens"];
		bool allSkipped = false;
		for (const auto &screen : screens.isValid() && screens.isMap() ? screens.children() : std::vector<YAML::YamlNodeReader>())
		{
			if (std::string(screen.key()) == ALL)
			{
				// "all" is the common options themselves: a theme there would put every state with no screen (the start,
				// the loading) under it. It is not kept in the file.
				allSkipped = true;
				continue;
			}
			Values v;
			for (size_t i = 0; i < n; ++i)
			{
				if (f[i].boolOption)
				{
					bool b;
					if (screen.tryRead(f[i].key, b)) v.*f[i].value = b ? 1 : 0;
				}
				else
				{
					int x;
					if (screen.tryRead(f[i].key, x)) v.*f[i].value = std::min(std::max(x, f[i].lo), f[i].hi);
				}
			}
			if (v.any())
			{
				read[std::string(screen.key())] = v;
			}
		}
		_own.swap(read);
		if (allSkipped)
		{
			Log(LOG_WARNING) << "HD screen themes: " << file << ": the entry \"all\" is skipped, the common options are set in the options window";
		}
	}
	catch (const std::exception &e)
	{
		_own.clear();
		Log(LOG_WARNING) << "HD screen themes: " << file << " is not read, no themes by screen: " << e.what();
	}
	if (!_own.empty())
	{
		Log(LOG_INFO) << "HD screen themes: " << _own.size() << " screens in " << file;
	}
}

bool HdScreenThemes::save() const
{
	const std::string file = path();
	if (_own.empty() && !CrossPlatform::fileExists(file))
	{
		return true;
	}
	std::string yaml;
	try
	{
		YAML::YamlRootNodeWriter writer;
		writer.setAsMap();
		auto screens = writer["screens"];
		screens.setAsMap();
		size_t n;
		const Field *f = fields(n);
		// in a fixed order, so the file does not shuffle between two savings
		std::vector<std::string> names;
		for (const auto &s : _own) names.push_back(s.first);
		std::sort(names.begin(), names.end());
		for (const std::string &name : names)
		{
			auto node = screens[screens.saveString(name)];
			node.setAsMap();
			node.setFlowStyle();
			const Values &v = _own.at(name);
			for (size_t i = 0; i < n; ++i)
			{
				if (v.*f[i].value < 0) continue;
				if (f[i].boolOption) node.write(f[i].key, v.*f[i].value != 0);
				else node.write(f[i].key, v.*f[i].value);
			}
		}
		yaml = writer.emit().yaml;
	}
	catch (const std::exception &e)
	{
		Log(LOG_WARNING) << "HD screen themes: " << e.what();
		return false;
	}
	const std::string head = "# OXCE-HD themes by screen. What a screen does not set comes from its parent (group, then all).\n";
	if (!CrossPlatform::writeFile(file, head + yaml + "\n"))
	{
		Log(LOG_WARNING) << "Failed to save " << file;
		return false;
	}
	return true;
}

const HdScreenThemes::Values *HdScreenThemes::own(const std::string &screen) const
{
	const auto found = _own.find(screen);
	return found == _own.end() ? nullptr : &found->second;
}

void HdScreenThemes::setOwn(const std::string &screen, const Values &v)
{
	if (screen.empty() || screen == ALL) return;
	if (v.any()) _own[screen] = v;
	else _own.erase(screen);
	_cache.clear();
}

const HdScreenThemes::Values *HdScreenThemes::resolved(const std::string &screen)
{
	const std::string &key = screen.empty() ? std::string(ALL) : screen;
	auto found = _cache.find(key);
	if (found == _cache.end())
	{
		Values r;
		std::string cur = key;
		// (the chain is short; the bound keeps a table gone wrong from looping)
		for (int depth = 0; depth < 8 && !cur.empty(); ++depth)
		{
			const auto o = _own.find(cur);
			if (o != _own.end()) r.inherit(o->second);
			cur = parentOf(cur);
		}
		found = _cache.emplace(key, r).first;
	}
	return found->second.any() ? &found->second : nullptr;
}

const std::vector<std::string> &HdScreenThemes::groups()
{
	static const std::vector<std::string> g = []
	{
		std::vector<std::string> v;
		for (const Group &group : GROUPS) v.push_back(group.name);
		return v;
	}();
	return g;
}

const std::vector<std::string> &HdScreenThemes::screensOf(const std::string &group)
{
	static const std::unordered_map<std::string, std::vector<std::string>> m = []
	{
		std::unordered_map<std::string, std::vector<std::string>> r;
		for (const Group &g : GROUPS)
		{
			std::vector<std::string> &list = r[g.name];
			std::istringstream in(g.screens);
			std::string s;
			while (in >> s)
			{
				// (only the screens the tree puts under this group: a name that is a group itself, or one listed twice, is not repeated)
				const auto t = tree().find(s);
				if (t != tree().end() && t->second == g.name && std::find(list.begin(), list.end(), s) == list.end())
				{
					list.push_back(s);
				}
			}
		}
		return r;
	}();
	static const std::vector<std::string> none;
	const auto found = m.find(group);
	return found == m.end() ? none : found->second;
}

namespace
{

int optionValue(const Field &f)
{
	return f.boolOption ? (*f.boolOption ? 1 : 0) : f.option ? *f.option : -1;
}

void setOption(const Field &f, int v)
{
	if (f.boolOption) *f.boolOption = v != 0;
	else if (f.option) *f.option = v;
}

bool isOption(const Field &f)
{
	return f.option || f.boolOption;
}

}

bool HdScreenThemes::beginEdit(const std::string &screen)
{
	if (_editing || screen.empty() || screen == ALL)
	{
		return false;
	}
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		_editWas[i] = optionValue(f[i]);
	}
	_editing = true;
	_editParent = false;
	_editScreen = screen;
	loadEdit(resolved(screen));
	return true;
}

void HdScreenThemes::loadEdit(const Values *v)
{
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		if (!isOption(f[i])) continue;
		setOption(f[i], v && v->*f[i].value >= 0 ? v->*f[i].value : _editWas[i]);
	}
	// the windows show the theme only with the switch on: the player edits what he then sees (the record turns it on)
	Options::oxceHdWindowTheme = true;
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		_editStart[i] = optionValue(f[i]);
	}
}

void HdScreenThemes::editAsParent()
{
	if (!_editing) return;
	_editParent = true;
	loadEdit(resolved(parentOf(_editScreen)));
}

HdScreenThemes::Values HdScreenThemes::editResult() const
{
	Values r;
	if (!_editing)
	{
		return r;
	}
	const Values *base = _editParent ? nullptr : own(_editScreen);
	size_t n;
	const Field *f = fields(n);
	// a unit (the colour, the look, the letters) is the screen's own once the player changed any of it, or if it was before
	bool wanted[4] = { false, false, false, false };
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		if (!isOption(f[i]) || f[i].boolOption) continue;   // (the switch of the theme is not the player's choice here)
		if (optionValue(f[i]) != _editStart[i] || (base && base->*f[i].value >= 0))
		{
			wanted[f[i].unit] = true;
		}
	}
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		if (!isOption(f[i]) || f[i].boolOption) continue;
		if (wanted[f[i].unit]) r.*f[i].value = optionValue(f[i]);
	}
	if (wanted[0] || wanted[1] || wanted[2])
	{
		r.windowTheme = 1;
	}
	else if (base && base->windowTheme >= 0)
	{
		r.windowTheme = base->windowTheme;   // (the switch alone, written by hand, stays)
	}
	if (base)
	{
		// what the menu does not edit (the text, stage 3) stays as it was
		for (size_t i = 0; i < n; ++i)
		{
			if (!isOption(f[i]) && base->*f[i].value >= 0) r.*f[i].value = base->*f[i].value;
		}
	}
	return r;
}

void HdScreenThemes::endEdit(bool commit)
{
	if (!_editing)
	{
		return;
	}
	const Values r = commit ? editResult() : Values();
	const std::string screen = _editScreen;
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		if (isOption(f[i])) setOption(f[i], _editWas[i]);
	}
	_editing = false;
	_editParent = false;
	_editScreen.clear();
	_cache.clear();
	if (commit)
	{
		setOwn(screen, r);
		save();
	}
}

HdScreenThemes::Scope::Scope(const std::string *screen)
{
	if (!screen)
	{
		return;
	}
	HdScreenThemes &themes = instance();
	if (themes.empty() || themes._editing)
	{
		// (while a screen's theme is being edited the options are the edited values for every window on the stack)
		return;
	}
	const Values *v = themes.resolved(*screen);
	if (!v)
	{
		return;
	}
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		if (f[i].boolOption)
		{
			_was[i] = *f[i].boolOption ? 1 : 0;
			if (v->*f[i].value >= 0) *f[i].boolOption = v->*f[i].value != 0;
		}
		else if (f[i].option)
		{
			_was[i] = *f[i].option;
			if (v->*f[i].value >= 0) *f[i].option = v->*f[i].value;
		}
	}
	_on = true;
	// the windows' own ramp, if the colour is the own one, is built here, on the main thread, before the render threads read it
	HdBattleHud::windowThemeKey();
}

HdScreenThemes::Scope::~Scope()
{
	if (!_on)
	{
		return;
	}
	size_t n;
	const Field *f = fields(n);
	for (size_t i = 0; i < n && i < 16; ++i)
	{
		if (f[i].boolOption) *f[i].boolOption = _was[i] != 0;
		else if (f[i].option) *f[i].option = _was[i];
	}
	HdBattleHud::windowThemeKey();
}

}
