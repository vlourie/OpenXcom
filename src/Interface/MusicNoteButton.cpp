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
#include "MusicNoteButton.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/HdPlateCanvas.h"
#include "../Engine/HdUi.h"
#include "../Mod/Mod.h"

namespace OpenXcom
{

MusicNoteButton::MusicNoteButton(Game *game, int x, int y) : InteractiveSurface(9, 9, x, y), _game(game), _classic(0), _down(false)
{
}

MusicNoteButton::~MusicNoteButton()
{
	delete _classic;
}

void MusicNoteButton::paint(PlateCanvas &c)
{
	c.fill(0, 0, 9, 9, 0xFF000000);
	c.gradient(1, 1, 7, 7, _down ? 0xFF8E8EA2 : 0xFFD4D4E0, _down ? 0xFFD4D4E0 : 0xFF8E8EA2);
	c.fill(1, 1, 7, 1, _down ? 0xFF404050 : 0xFFFFFFFF);
	c.fill(1, 1, 1, 7, _down ? 0xFF404050 : 0xFFFFFFFF);
	c.fill(1, 7, 7, 1, _down ? 0xFFFFFFFF : 0xFF404050);
	c.fill(7, 1, 1, 7, _down ? 0xFFFFFFFF : 0xFF404050);
	c.note(2.4f + (_down ? 1 : 0), 1.4f + (_down ? 1 : 0), 0xFF10101A, 0.62f);
}

void MusicNoteButton::draw()
{
	Surface::draw();
	if (HdUi::active() && HdUi::instance().hasFonts())
	{
		return;
	}
	if (!_classic)
	{
		Mod *mod = _game->getMod();
		_classic = new ClassicPlateCanvas(this, mod->getFont("FONT_BIG"), mod->getFont("FONT_SMALL"), _game->getLanguage());
	}
	_classic->begin();
	paint(*_classic);
}

void MusicNoteButton::hdMirror()
{
	if (!HdUi::instance().hasFonts())
	{
		Surface::hdMirror();
		return;
	}
	Mod *mod = _game->getMod();
	HdPlateCanvas canvas((float)getX(), (float)getY(), mod->getFont("FONT_BIG"), mod->getFont("FONT_SMALL"));
	paint(canvas);
}

void MusicNoteButton::mousePress(Action *action, State *state)
{
	if (action->getDetails()->button.button == SDL_BUTTON_LEFT)
	{
		_down = true;
		_redraw = true;
	}
	InteractiveSurface::mousePress(action, state);
}

void MusicNoteButton::mouseRelease(Action *action, State *state)
{
	if (action->getDetails()->button.button == SDL_BUTTON_LEFT)
	{
		_down = false;
		_redraw = true;
	}
	InteractiveSurface::mouseRelease(action, state);
}

}
