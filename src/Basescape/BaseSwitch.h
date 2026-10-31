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
#include <algorithm>
#include <functional>
#include <string>
#include "../Engine/Game.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Savegame/Base.h"

namespace OpenXcom
{

class State;

namespace BaseSwitch
{
	/// Which bases a screen can switch to (a research screen needs laboratories, and so on).
	typedef std::function<bool(const Base*)> Filter;
	/// The neighbouring base in the given direction (-1 previous, +1 next), round the list; nullptr if none fits.
	Base *neighbour(Game *game, const Base *base, int dir, const Filter &fits);
	/// Replaces the top screen with the same screen of another base; the base screens right below it show that base too.
	void replace(Game *game, State *next, Base *base);
}

/**
 * Base name line under the title of a base screen, with the previous/next base buttons
 * (also the left/right keys): the same screen of the neighbouring base without going back
 * to the basescape. Switching is off until the opener calls allowBaseSwitch() - forced
 * screens (after a battle, prison or stores overflow, "cannot re-equip") never switch.
 */
template<typename State_t>
class BaseSwitchMixin : public State_t
{
private:
	/// Height of the line; everything below it moves this much lower.
	static const int LINE = 10;
	/// Top of the bottom buttons: they and anything lower stay in place.
	static const int BUTTONS_Y = 176;

	TextButton *_btnPrevBase = nullptr, *_btnNextBase = nullptr;
	Text *_txtBaseName = nullptr;
	Base *_switchBase = nullptr;
	bool _switchAllowed = false;
	BaseSwitch::Filter _switchFits;
	std::function<State*(Base*)> _switchOpen;
	std::function<bool()> _switchBlocked;

	void switchBase(int dir)
	{
		if (!_switchAllowed || (_switchBlocked && _switchBlocked()))
			return;
		Base *base = BaseSwitch::neighbour(this->_game, _switchBase, dir, _switchFits);
		if (base)
		{
			BaseSwitch::replace(this->_game, _switchOpen(base), base);
		}
	}
protected:
	using State_t::State_t;
	/**
	 * Makes room under the title and creates the base name line and the arrows;
	 * call after adding the screen's own elements, before centerAllSurfaces().
	 * @param base Base shown on the screen.
	 * @param category Interface category of the screen.
	 * @param textId, buttonId Interface elements whose colours the line and the arrows take.
	 * @param y Top of the line; the screen's elements from here down to the bottom buttons move one line lower, lists get one line shorter.
	 * @param fits Bases the screen can switch to (empty - any base).
	 * @param open Opens the same screen for another base.
	 * @param blocked Unconfirmed changes or a forced situation: no switching while it is true.
	 */
	void addBaseSwitch(Base *base, const std::string &category, const std::string &textId, const std::string &buttonId, int y,
		BaseSwitch::Filter fits, std::function<State*(Base*)> open, std::function<bool()> blocked = {})
	{
		for (Surface *surface : this->_surfaces)
		{
			if (surface->getY() < y || surface->getY() >= BUTTONS_Y || dynamic_cast<Window*>(surface))
				continue;
			surface->setY(surface->getY() + LINE);
			if (auto *list = dynamic_cast<TextList*>(surface))
			{
				// whole rows only, down to just above the bottom buttons: a half row would show cut
				int row = std::max(list->getRowHeight(), 1);
				int height = std::min(list->getHeight(), BUTTONS_Y - 2 - list->getY());
				list->setHeight(std::max(height - height % row, row));
			}
		}

		_switchBase = base;
		_switchFits = std::move(fits);
		_switchOpen = std::move(open);
		_switchBlocked = std::move(blocked);
		_btnPrevBase = new TextButton(14, LINE, 10, y);
		_btnNextBase = new TextButton(14, LINE, 296, y);
		_txtBaseName = new Text(268, 9, 26, y + 1);
		this->add(_txtBaseName, textId, category);
		this->add(_btnPrevBase, buttonId, category);
		this->add(_btnNextBase, buttonId, category);

		_txtBaseName->setAlign(ALIGN_CENTER);
		_txtBaseName->setText(base->getName());
		_btnPrevBase->setText("<");
		_btnPrevBase->onMouseClick((ActionHandler)&BaseSwitchMixin::btnPrevBaseClick);
		_btnPrevBase->onKeyboardPress((ActionHandler)&BaseSwitchMixin::btnPrevBaseClick, Options::keyGeoLeft);
		_btnNextBase->setText(">");
		_btnNextBase->onMouseClick((ActionHandler)&BaseSwitchMixin::btnNextBaseClick);
		_btnNextBase->onKeyboardPress((ActionHandler)&BaseSwitchMixin::btnNextBaseClick, Options::keyGeoRight);
		updateBaseSwitch();
	}
	/// Shows the arrows only while there is a base to switch to and nothing holds the screen.
	void updateBaseSwitch()
	{
		if (!_btnPrevBase)
			return;
		bool show = _switchAllowed && !(_switchBlocked && _switchBlocked())
			&& BaseSwitch::neighbour(this->_game, _switchBase, 1, _switchFits) != nullptr;
		_btnPrevBase->setVisible(show);
		_btnNextBase->setVisible(show);
	}
public:
	/// Lets the screen switch bases (the opener decides).
	void allowBaseSwitch()
	{
		_switchAllowed = true;
		updateBaseSwitch();
	}
	/// Whether the opener let the screen switch bases (not a forced screen).
	bool baseSwitchAllowed() const { return _switchAllowed; }
	/// Handler for the previous base button and key.
	void btnPrevBaseClick(Action *) { switchBase(-1); }
	/// Handler for the next base button and key.
	void btnNextBaseClick(Action *) { switchBase(1); }
};

/// Opens a base screen that may switch bases: pushState(withBaseSwitch(new ResearchState(base))).
template<typename T>
T *withBaseSwitch(T *state)
{
	state->allowBaseSwitch();
	return state;
}

}
