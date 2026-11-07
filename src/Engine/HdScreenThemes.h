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
#include <vector>

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
 * "all" is the options themselves (the common ones): it is not kept in the file (an "all" there is skipped with one line
 * in the log), so a state with no screen of its own (the start, the loading) is never under a theme. The windows' skin
 * (oxceHdUiSkin) is not a part of a theme either: more than a dozen places read it outside the drawing of a state.
 *
 * The theme is put to work by Scope: for the blit of one state it lays the values into the options the drawing reads at
 * drawing time (the windows' theme, colour, relief, letters), and gives the previous ones back after. The colour of the plain
 * texts (textHue, textSat: the hue and saturation replaced, the brightness of every shade kept) is the two statics
 * activeTextHue/Sat that Text's drawing reads; the battle map ("battleMap") never gets it. No file, or no values for the
 * screen: Scope writes nothing, the frame is as it was.
 */
class HdScreenThemes
{
public:
	/// What a theme sets; -1 = not set (taken from the parent). The values are those of the options of the same name.
	struct Values
	{
		int windowTheme = -1;   ///< oxceHdWindowTheme (0, 1)
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
		int textHue = -1;       ///< the hue of the plain texts (labels, lists), 0..359; -1 the palette's own
		int textSat = -1;       ///< their saturation, 0..100; -1 the palette's own (the brightness of every shade is always kept)

		bool any() const;
		/// Takes from `parent` what this one does not set.
		void inherit(const Values &parent);
	};

	static HdScreenThemes &instance();

	/// The text theme in force now (the Scope of the state being drawn, or the edit of a screen's theme); -1 = the palette's own.
	/// The plain texts' drawing (HdUi::textTint) reads them; the buttons' labels have their own letters and do not.
	static int activeTextHue, activeTextSat;
	static bool textActive() { return activeTextHue >= 0 || activeTextSat >= 0; }

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
		bool _textCut = false;   ///< the text theme was taken off for this blit (the battle map under an edit)
		int _textWas[2] = { -1, -1 };
		int _was[16];
	};

	/// The menu "Themes of the screens" (OptionsScreenThemesState): the groups, and what the tree puts under a group or a screen
	/// (the screens of a room's window, of the production...), in the table's order.
	static const std::vector<std::string> &groups();
	static const std::vector<std::string> &childrenOf(const std::string &parent);
	/// Whether the screen has no interface category in the ruleset (a window that names itself by State::setHdScreen): the menu lists it always.
	static bool hasNoCategory(const std::string &screen);

	/**
	 * Editing the theme of one screen. The windows the player edits it in (the colour, the buttons' look and letters) read and
	 * write the options directly, so for the time of the edit the options hold the screen's values (the screen's own, then its
	 * parents', then what the options were), and Scope does nothing: every window on the stack shows the values being edited.
	 * endEdit puts the options back as they were, so options.cfg is never changed by it; only the screen's record is.
	 */
	/// Starts: remembers the options, puts the screen's resolved values in them. False when an edit is already open.
	bool beginEdit(const std::string &screen);
	bool editing() const { return _editing; }
	const std::string &editScreen() const { return _editScreen; }
	/// "As the parent": the options take the parent's values (and what the options were), the screen's own are dropped on commit.
	void editAsParent();
	/// The text colour the screen's parent has (-1, -1: none): what the window "Text colour" sets back.
	void editParentText(int &hue, int &sat);
	/// What the screen's record would be now (an empty one: as the parent).
	Values editResult() const;
	/// Ends: with `commit` the record is set and the file written; the options come back either way. Does nothing if no edit is open.
	void endEdit(bool commit);

private:
	HdScreenThemes() = default;
	/// Puts the values (nullptr: none) over what the options were before the edit, into the options.
	void loadEdit(const Values *v);
	std::unordered_map<std::string, Values> _own;       ///< what the file says
	std::unordered_map<std::string, Values> _cache;     ///< the screen -> its values with the parents' put in (any() false = none)
	bool _editing = false;
	bool _editParent = false;                           ///< "as the parent" was pressed: the record starts empty
	std::string _editScreen;
	int _editWas[16] = {};                              ///< the options before the edit (by the fields of the table)
	int _editStart[16] = {};                            ///< the options as the edit set them: a unit changed from these is the player's
};

}
