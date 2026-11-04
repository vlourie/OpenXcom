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
#include <string>
#include <unordered_map>

namespace OpenXcom
{

/**
 * Themes by screen (XP-000484, docs/research/screen-themes-xp484-2026-11-04.md): every screen may have its own colour,
 * relief and letters of the windows' buttons and frames. The player's choices lie in hd_screen_themes.yml next to
 * options.cfg; only what the player set is there.
 *
 * A screen (State::_hdScreen) has a parent in a tree: the screen -> a group (menu, geoscape, basescape, battlescape,
 * messages, landing) -> all. A screen the table does not know (another mod's) hangs straight under all. Each value is
 * taken separately: the screen's own, else its parent's and so on up to "all"; what no one set stays as the options say.
 *
 * The theme is put to work by Scope: for the blit of one state it lays the values into the options the drawing reads at
 * drawing time (the windows' theme, colour, relief, letters), and gives the previous ones back after. No file, or no
 * values for the screen: Scope writes nothing, the frame is as it was.
 */
class HdScreenThemes
{
public:
	/// What a theme sets; -1 = not set (taken from the parent). The values are those of the options of the same name.
	struct Values
	{
		int windowTheme = -1;   ///< oxceHdWindowTheme (0, 1)
		int skin = -1;          ///< oxceHdUiSkin
		int color = -1;         ///< oxceHdWindowThemeColor (0 the panel's, 1..10; 10 = the own colour of hue, sat, val)
		int hue = -1;           ///< oxceHdWinKeyHue
		int sat = -1;           ///< oxceHdWinKeySat
		int val = -1;           ///< oxceHdWinKeyVal
		int face = -1;          ///< oxceHdButtonFace
		int shape = -1;         ///< oxceHdButtonShape
		int gloss = -1;         ///< oxceHdButtonGloss
		int inkTone = -1;       ///< oxceHdButtonInkTone
		int inkHue = -1;        ///< oxceHdButtonInkHue
		int inkLight = -1;      ///< oxceHdButtonInkLight
		int inkSat = -1;        ///< oxceHdButtonInkSat
		int textHue = -1;       ///< read and kept only (the colour of plain text, stage 3)
		int textSat = -1;       ///< the same

		bool any() const;
		/// Takes from `parent` what this one does not set.
		void inherit(const Values &parent);
	};

	static HdScreenThemes &instance();

	/// Reads the file (at start and on leaving the options window). No file, or a bad one: no themes; a bad one makes one line in the log.
	void load();
	/// Writes the file with the themes as they are now (and no file at all while there are none).
	bool save() const;
	/// The full path of the file, next to options.cfg.
	static std::string path();

	/// No theme anywhere: the engine does nothing per frame.
	bool empty() const { return _own.empty(); }

	/// The values a player set for exactly this screen (nullptr: none), to change them (the menu).
	const Values *own(const std::string &screen) const;
	/// Sets (or, with nothing set in `v`, clears) the player's values of a screen; the caches go.
	void setOwn(const std::string &screen, const Values &v);

	/// The parent of a screen in the tree: a group's is "all", "all" has none (""), a name not in the table has "all".
	static std::string parentOf(const std::string &screen);
	/// Whether the table knows the name (a group, or a screen listed in it).
	static bool known(const std::string &name);

	/// The values of a screen with the parents' put in; nullptr when not one is set along the whole chain. Cached.
	const Values *resolved(const std::string &screen);

	/// For the blit of one state: the screen's values go into the options, the previous ones come back in the destructor.
	class Scope
	{
	public:
		/// `screen` = nullptr, or no values for it: does nothing.
		explicit Scope(const std::string *screen);
		~Scope();
		Scope(const Scope &) = delete;
		Scope &operator=(const Scope &) = delete;
	private:
		bool _on = false;
		int _was[13];
	};

private:
	HdScreenThemes() = default;
	std::unordered_map<std::string, Values> _own;       ///< what the file says
	std::unordered_map<std::string, Values> _cache;     ///< the screen -> its values with the parents' put in (any() false = none)
};

}
