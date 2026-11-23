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
#include "ActionMenuItem.h"
#include <algorithm>
#include "../Interface/Text.h"
#include "../Interface/Frame.h"
#include "../Engine/Game.h"
#include "../Engine/HdUi.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"

namespace OpenXcom
{

/**
 * Sets up an Action menu item.
 * @param id The unique identifier of the menu item.
 * @param game Pointer to the game.
 * @param x Position on the x-axis.
 * @param y Position on the y-axis.
 */
ActionMenuItem::ActionMenuItem(int id, Game *game, int x, int y) : InteractiveSurface(272, 40, x + 24, y - (id*40)), _highlighted(false), _action(BA_NONE), _skill(nullptr), _tu(0)
{
	Font *big = game->getMod()->getFont("FONT_BIG"), *small = game->getMod()->getFont("FONT_SMALL");
	Language *lang = game->getLanguage();

	const Element *actionMenu = game->getMod()->getInterface("battlescape")->getElement("actionMenu");

	_highlightModifier = actionMenu->TFTDMode ? 12 : 3;

	_frame = new Frame(getWidth(), getHeight(), 0, 0);
	_frame->setHighContrast(true);
	_frame->setColor(actionMenu->border);
	_frame->setSecondaryColor(actionMenu->color2);
	_frame->setThickness(8);

	_txtDescription = new Text(200, 20, 10, 13);
	_txtDescription->initText(big, small, lang);
	_txtDescription->setBig();
	_txtDescription->setHighContrast(true);
	_txtDescription->setColor(actionMenu->color);
	_txtDescription->setVisible(true);

	_txtAcc = new Text(100, 20, 140, 13);
	_txtAcc->initText(big, small, lang);
	_txtAcc->setBig();
	_txtAcc->setHighContrast(true);
	_txtAcc->setColor(actionMenu->color);

	_txtTU = new Text(80, 20, 210, 13);
	_txtTU->initText(big, small, lang);
	_txtTU->setBig();
	_txtTU->setHighContrast(true);
	_txtTU->setColor(actionMenu->color);
}

/**
 * Deletes the ActionMenuItem.
 */
ActionMenuItem::~ActionMenuItem()
{
	delete _frame;
	delete _txtDescription;
	delete _txtAcc;
	delete _txtTU;
}

/**
 * Links with an action and fills in the text fields.
 * @param action The battlescape action.
 * @param description The actions description.
 * @param accuracy The actions accuracy, including the Acc> prefix.
 * @param timeunits The timeunits string, including the TUs> prefix.
 * @param tu The timeunits value.
 */
void ActionMenuItem::setAction(BattleActionType action, const std::string &description, const std::string &accuracy, const std::string &timeunits, int tu)
{
	_action = action;
	_txtDescription->setText(description);
	_txtAcc->setText(accuracy);
	_txtTU->setText(timeunits);
	_tu = tu;
	_redraw = true;
}

/**
 * Links with a skill.
 * @param skill The linked skill.
 */
void ActionMenuItem::setSkill(const RuleSkill *skill)
{
	_skill = skill;
}

/**
 * Gets the action that was linked to this menu item.
 * @return Action that was linked to this menu item.
 */
BattleActionType ActionMenuItem::getAction() const
{
	return _action;
}

/**
 * Gets the skill that was linked to this menu item.
 * @return Skill that was linked to this menu item.
 */
const RuleSkill* ActionMenuItem::getSkill() const
{
	return _skill;
}

/**
 * Gets the action tus that were linked to this menu item.
 * @return The timeunits that were linked to this menu item.
 */
int ActionMenuItem::getTUs() const
{
	return _tu;
}

/**
 * Replaces a certain amount of colors in the surface's palette.
 * @param colors Pointer to the set of colors.
 * @param firstcolor Offset of the first color to replace.
 * @param ncolors Amount of colors to replace.
 */
void ActionMenuItem::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	Surface::setPalette(colors, firstcolor, ncolors);
	_frame->setPalette(colors, firstcolor, ncolors);
	_txtDescription->setPalette(colors, firstcolor, ncolors);
	_txtAcc->setPalette(colors, firstcolor, ncolors);
	_txtTU->setPalette(colors, firstcolor, ncolors);
}

/**
 * Draws the bordered box.
 */
void ActionMenuItem::draw()
{
	_frame->blit(this->getSurface());
	_txtDescription->blit(this->getSurface());
	_txtAcc->blit(this->getSurface());
	_txtTU->blit(this->getSurface());
}

/**
 * The modern skin's menu item: a rounded panel in the frame's fill colour
 * (lighter while highlighted) with the frame's border, and the texts.
 */
void ActionMenuItem::hdMirror()
{
	if (!HdUi::skin())
	{
		Surface::hdMirror();
		return;
	}
	HdUi &ui = HdUi::instance();
	const SDL_Color *pal = HdUi::paletteOf(this);
	const int k = HdUi::scale();
	const float x0 = (float)getX() * k, y0 = (float)getY() * k, x1 = (float)(getX() + getWidth()) * k, y1 = (float)(getY() + getHeight()) * k;
	const float r = 1.5f * k, edge = std::max(1.0f, k * 0.5f);
	const Uint32 fill = HdUi::rgba(pal[_frame->getSecondaryColor()]);
	ui.fillRoundRect(x0, y0, x1, y1, r, (HdUi::scaled(fill, 1.1f) & 0x00FFFFFFu) | 0xF0000000u, (HdUi::scaled(fill, 0.85f) & 0x00FFFFFFu) | 0xF0000000u);
	if (_highlighted)
	{
		ui.fillRoundRect(x0 + edge, y0 + edge, x1 - edge, y0 + (y1 - y0) * 0.5f, std::max(r - edge, 0.0f), 0x24FFFFFFu, 0x06FFFFFFu);
	}
	ui.strokeRoundRect(x0, y0, x1, y1, r, edge, HdUi::rgba(pal[(Uint8)(_frame->getColor() + 2)], 220));
	// the three columns overlap on paper (10..210, 140..240, 210..290) and the classic layout gets away
	// with it because the bitmap letters are narrow: a name ending at 149 is simply overpainted by the
	// accuracy. The TrueType face is about half again as wide at the same cap height, so a long action
	// name ran straight through the accuracy number. Every column gets the room up to the next one and
	// the line condenses into it.
	Text *columns[] = { _txtDescription, _txtAcc, _txtTU };
	const int count = (int)(sizeof(columns) / sizeof(columns[0]));
	for (int i = 0; i < count; ++i)
	{
		Text *text = columns[i];
		const int left = text->getX();
		const int next = i + 1 < count ? columns[i + 1]->getX() : getWidth();
		const int room = std::max(1, std::min(left + text->getWidth(), next) - left);
		text->hdDrawAt(getX() + left, getY() + text->getY(), getX() + left, getY(), room, getHeight());
	}
}

/**
 * Processes a mouse hover in event.
 * @param action Pointer to an action.
 * @param state Pointer to a state.
 */
void ActionMenuItem::mouseIn(Action *action, State *state)
{
	_highlighted = true;
	_frame->setSecondaryColor(_frame->getSecondaryColor() - _highlightModifier);
	draw();
	InteractiveSurface::mouseIn(action, state);
}


/**
 * Processes a mouse hover out event.
 * @param action Pointer to an action.
 * @param state Pointer to a state.
 */
void ActionMenuItem::mouseOut(Action *action, State *state)
{
	_highlighted = false;
	_frame->setSecondaryColor(_frame->getSecondaryColor() + _highlightModifier);
	draw();
	InteractiveSurface::mouseOut(action, state);
}


}
