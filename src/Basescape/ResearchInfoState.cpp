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
#include "ResearchInfoState.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Savegame/Base.h"
#include "../Mod/RuleResearch.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/ResearchProject.h"
#include "../Savegame/SavedGame.h"
#include "../Interface/ArrowButton.h"
#include "../Engine/Timer.h"
#include "../Engine/RNG.h"
#include <climits>
#include <sstream>

namespace OpenXcom
{

/**
 * Initializes all the elements in the ResearchProject screen.
 * @param game Pointer to the core game.
 * @param base Pointer to the base to get info from.
 * @param rule A RuleResearch which will be used to create a new ResearchProject
 */
ResearchInfoState::ResearchInfoState(Base *base, RuleResearch *rule) : _base(base), _project(nullptr), _rule(rule)
{
	int rng = RNG::generate(50, 150);
	int randomizedCost = rule->getCost() * rng / 100;
	if (rule->getCost() > 0)
	{
		randomizedCost = std::max(1, randomizedCost);
	}
	_project = new ResearchProject(rule, randomizedCost);

	buildUi();
}

/**
 * Initializes all the elements in the ResearchProject screen.
 * @param game Pointer to the core game.
 * @param base Pointer to the base to get info from.
 * @param project A ResearchProject to modify
 */
ResearchInfoState::ResearchInfoState(Base *base, ResearchProject *project) : _base(base), _project(project), _rule(0)
{
	buildUi();
}

/**
 * Builds dialog.
 */
void ResearchInfoState::buildUi()
{
	_screen = false;

	// the option "approximate term" (XP-000491) makes the window 14 px taller for one more line: the upper part
	// goes 7 px up, the buttons 7 px down; with the option off every number is as it was
	// (XP-000493: two lines now, the range and the "expected about N days", so 22 px taller: dy = 11)
	const int dy = Options::oxceHdResearchEta ? 11 : 0;

	_window = new Window(this, 230, 140 + 2 * dy, 45, 30 - dy);
	_txtTitle = new Text(210, 17, 61, 40 - dy);

	_txtAvailableScientist = new Text(210, 9, 61, 60 - dy);
	_txtAvailableSpace = new Text(210, 9, 61, 70 - dy);
	_txtAllocatedScientist = new Text(210, 17, 61, 80 - dy);
	_txtMore = new Text(110, 17, 85, 100 - dy);
	_txtLess = new Text(110, 17, 85, 120 - dy);
	_btnCancel = new TextButton(90, 16, 61, 145 + dy);
	_btnOk = new TextButton(90, 16, 169, 145 + dy);

	_btnMore = new ArrowButton(ARROW_BIG_UP, 13, 14, 195, 100 - dy);
	_btnLess = new ArrowButton(ARROW_BIG_DOWN, 13, 14, 195, 120 - dy);

	_surfaceScientists = new InteractiveSurface(230, 140 + 2 * dy, 45, 30 - dy);
	_surfaceScientists->onMouseClick((ActionHandler)&ResearchInfoState::handleWheel, 0);

	if (dy)
	{
		_txtEta = new Text(210, 9, 61, 132);
		_txtEtaExpected = new Text(210, 9, 61, 141);
	}

	touchComponentsCreate(_txtTitle, false, -45, +30 - dy, true);

	// Set palette
	setInterface("allocateResearch");

	add(_surfaceScientists);
	add(_window, "window", "allocateResearch");
	add(_btnOk, "button2", "allocateResearch");
	add(_btnCancel, "button2", "allocateResearch");
	add(_txtTitle, "text", "allocateResearch");
	add(_txtAvailableScientist, "text", "allocateResearch");
	add(_txtAvailableSpace, "text", "allocateResearch");
	add(_txtAllocatedScientist, "text", "allocateResearch");
	if (_txtEta)
	{
		add(_txtEta, "text", "allocateResearch");
		add(_txtEtaExpected, "text", "allocateResearch");
	}
	add(_txtMore, "text", "allocateResearch");
	add(_txtLess, "text", "allocateResearch");
	add(_btnMore, "button1", "allocateResearch");
	add(_btnLess, "button1", "allocateResearch");

	touchComponentsAdd("button3", "allocateResearch", _window);

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "allocateResearch");

	touchComponentsConfigure();

	_txtTitle->setBig();

	_txtTitle->setText(_rule ? tr(_rule->getName()) : tr(_project->getRules()->getName()));

	_txtAllocatedScientist->setBig();

	_txtMore->setText(tr("STR_INCREASE"));
	_txtLess->setText(tr("STR_DECREASE"));

	_txtMore->setBig();
	_txtLess->setBig();

	if (_rule)
	{
		_base->addResearch(_project);
		if (_rule->isHoldingNeededItem())
		{
			_base->getStorageItems()->removeItem(_rule->getNeededItem(), 1);
		}
	}
	setAssignedScientist();
	_btnMore->onMousePress((ActionHandler)&ResearchInfoState::morePress);
	_btnMore->onMouseRelease((ActionHandler)&ResearchInfoState::moreRelease);
	_btnMore->onMouseClick((ActionHandler)&ResearchInfoState::moreClick, 0);
	_btnLess->onMousePress((ActionHandler)&ResearchInfoState::lessPress);
	_btnLess->onMouseRelease((ActionHandler)&ResearchInfoState::lessRelease);
	_btnLess->onMouseClick((ActionHandler)&ResearchInfoState::lessClick, 0);

	_timerMore = new Timer(250);
	_timerMore->onTimer((StateHandler)&ResearchInfoState::more);
	_timerLess = new Timer(250);
	_timerLess->onTimer((StateHandler)&ResearchInfoState::less);

	_btnOk->onMouseClick((ActionHandler)&ResearchInfoState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&ResearchInfoState::btnOkClick, Options::keyOk);
	if (_rule)
	{
		_btnOk->setText(tr("STR_START_PROJECT"));
		_btnCancel->setText(tr("STR_CANCEL_UC"));
		_btnCancel->onKeyboardPress((ActionHandler)&ResearchInfoState::btnCancelClick, Options::keyCancel);
	}
	else
	{
		_btnOk->setText(tr("STR_OK"));
		_btnCancel->setText(tr("STR_CANCEL_PROJECT"));
		_btnOk->onKeyboardPress((ActionHandler)&ResearchInfoState::btnOkClick, Options::keyCancel);
	}
	_btnCancel->onMouseClick((ActionHandler)&ResearchInfoState::btnCancelClick);

	if (_rule)
	{
		// mark new/hidden as normal
		_game->getSavedGame()->setResearchRuleStatus(_rule->getName(), RuleResearch::RESEARCH_STATUS_NORMAL);
	}
}

/**
 * Frees up memory that's not automatically cleaned on exit
 */
ResearchInfoState::~ResearchInfoState()
{
	delete _timerLess;
	delete _timerMore;
}

/**
 * Resets stuff when coming back from other screens.
 */
void ResearchInfoState::init()
{
	State::init();

	touchComponentsRefresh();
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void ResearchInfoState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Returns to the previous screen, removing the current project from the active
 * research list.
 * @param action Pointer to an action.
 */
void ResearchInfoState::btnCancelClick(Action *)
{
	_base->removeResearch(_project);
	_game->popState();
}

/**
 * Updates count of assigned/free scientists and available lab space.
 */
void ResearchInfoState::setAssignedScientist()
{
	_txtAvailableScientist->setText(tr("STR_SCIENTISTS_AVAILABLE_UC").arg(_base->getAvailableScientists()));
	_txtAvailableSpace->setText(tr("STR_LABORATORY_SPACE_AVAILABLE_UC").arg(_base->getFreeLaboratories()));
	_txtAllocatedScientist->setText(tr("STR_SCIENTISTS_ALLOCATED").arg(_project->getAssigned()));
	if (_txtEta)
	{
		_txtEta->setText(etaText());
		_txtEtaExpected->setText(etaExpectedText());
	}
}

/**
 * The approximate term of the project, "from and to" in days (option oxceHdResearchEta, XP-000491).
 * Display only. It is counted from what the player can know: the ruleset cost R, the man-days already spent
 * and the scientists assigned now. The real cost of the project (hidden, RNG 50-150 % of R, see the constructor
 * above) is never read here: the bounds are the bounds of that RNG, not its result.
 * The project is stepped once a day (spent += assigned, then done when spent >= cost), so the term is at least a day;
 * and a project still on the list is not finished, i.e. its cost is above the spent.
 * Once the spent passes the lower bound the range narrows from below: this follows from the project not being done yet.
 */
std::string ResearchInfoState::etaText() const
{
	long long fromDays = 0, toDays = 0, expectedDays = 0;
	if (!etaDays(_project, fromDays, toDays, expectedDays))
	{
		return tr("STR_HD_RESEARCH_ETA_NONE");
	}
	if (fromDays >= toDays)
	{
		return tr("STR_HD_RESEARCH_ETA_ONE").arg(std::string(tr("STR_DAY", (unsigned)toDays)));
	}
	return tr("STR_HD_RESEARCH_ETA_RANGE").arg((int)fromDays).arg(std::string(tr("STR_DAY", (unsigned)toDays)));
}

/**
 * The second line, "expected about N days" (XP-000493): the term if the cost were the ruleset cost itself.
 * Empty when there is no scientists or the range is a single number.
 */
std::string ResearchInfoState::etaExpectedText() const
{
	long long fromDays = 0, toDays = 0, expectedDays = 0;
	if (!etaDays(_project, fromDays, toDays, expectedDays) || fromDays >= toDays)
	{
		return "";
	}
	return tr("STR_HD_RESEARCH_ETA_EXPECTED").arg(std::string(tr("STR_DAY", (unsigned)expectedDays)));
}

/**
 * The days to the end of a project counted from the ruleset cost, the spent and the scientists assigned now
 * (the same numbers for the assign window and for the research list, XP-000493, XP-000494).
 * The real cost of the project (_cost, the hidden RNG result) and the RNG are never touched: the bounds are the bounds
 * of the RNG (rule cost * 50..150 / 100, as the constructor above makes it) and "expected" is the term at the ruleset
 * cost itself, clamped to the bounds.
 * @param project The project.
 * @param fromDays Out: the least term, a day at least.
 * @param toDays Out: the longest term.
 * @param expectedDays Out: the term at the ruleset cost, between the two.
 * @return False if there are no scientists (no term).
 */
bool ResearchInfoState::etaDays(const ResearchProject *project, long long &fromDays, long long &toDays, long long &expectedDays)
{
	const long long cost = project->getRules()->getCost();
	const long long spent = project->getSpent();
	const long long assigned = project->getAssigned();
	if (cost <= 0)
	{
		// a project of no cost is finished by the next daily step, whoever works on it
		fromDays = toDays = expectedDays = 1;
		return true;
	}
	if (assigned <= 0)
	{
		return false;
	}
	const long long lowCost = std::max(1LL, cost * 50 / 100);
	const long long highCost = std::max(lowCost, cost * 150 / 100);
	const long long lowGoal = std::max(lowCost, spent + 1);
	const long long highGoal = std::max(highCost, spent + 1);
	fromDays = (lowGoal - spent + assigned - 1) / assigned;
	toDays = (highGoal - spent + assigned - 1) / assigned;
	const long long midGoal = std::max(cost, spent + 1);
	expectedDays = std::min(toDays, std::max(fromDays, (midGoal - spent + assigned - 1) / assigned));
	return true;
}

/**
 * The short term for a cell of the research list, e.g. "(2-5d)" (option oxceHdResearchEta, XP-000494).
 * @param state The state whose language is used.
 * @param project The project.
 * @return The text, empty if no scientists are assigned.
 */
std::string ResearchInfoState::etaShort(const State *state, const ResearchProject *project)
{
	long long fromDays = 0, toDays = 0, expectedDays = 0;
	if (!etaDays(project, fromDays, toDays, expectedDays))
	{
		return "";
	}
	std::ostringstream range;
	range << fromDays;
	if (toDays > fromDays)
	{
		range << "-" << toDays;
	}
	std::string text = state->tr("STR_HD_RESEARCH_ETA_SHORT").arg(range.str());
	if (text.compare(0, 4, "STR_") == 0)
	{
		// a language without the new string: the existing short day
		text = state->tr("STR_DAY_SHORT").arg(range.str());
	}
	return text;
}

/**
 * Increases or decreases the scientists according the mouse-wheel used.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::handleWheel(Action *action)
{
	if (action->getDetails()->button.button == SDL_BUTTON_WHEELUP) moreByValue(Options::changeValueByMouseWheel);
	else if (action->getDetails()->button.button == SDL_BUTTON_WHEELDOWN) lessByValue(Options::changeValueByMouseWheel);
}

/**
 * Starts the timeMore timer.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::morePress(Action *action)
{
	if (_game->isLeftClick(action, true)) _timerMore->start();
}

/**
 * Stops the timeMore timer.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::moreRelease(Action *action)
{
	if (_game->isLeftClick(action, true))
	{
		_timerMore->setInterval(250);
		_timerMore->stop();
	}
}

/**
 * Allocates scientists to the current project;
 * one scientist on left-click, all scientists on right-click.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::moreClick(Action *action)
{
	if (_game->isRightClick(action, true))
		moreByValue(INT_MAX);
	if (_game->isLeftClick(action, true))
		moreByValue(_game->getScrollStep());
}

/**
 * Starts the timeLess timer.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::lessPress(Action *action)
{
	if (_game->isLeftClick(action, true)) _timerLess->start();
}

/**
 * Stops the timeLess timer.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::lessRelease(Action *action)
{
	if (_game->isLeftClick(action, true))
	{
		_timerLess->setInterval(250);
		_timerLess->stop();
	}
}

/**
 * Removes scientists from the current project;
 * one scientist on left-click, all scientists on right-click.
 * @param action Pointer to an Action.
 */
void ResearchInfoState::lessClick(Action *action)
{
	if (_game->isRightClick(action, true))
		lessByValue(INT_MAX);
	if (_game->isLeftClick(action, true))
		lessByValue(_game->getScrollStep());
}

/**
 * Adds one scientist to the project if possible.
 */
void ResearchInfoState::more()
{
	_timerMore->setInterval(50);
	moreByValue(_game->getScrollStep());
}

/**
 * Adds the given number of scientists to the project if possible.
 * @param change Number of scientists to add.
 */
void ResearchInfoState::moreByValue(int change)
{
	if (0 >= change) return;
	int freeScientist = _base->getAvailableScientists();
	int freeSpaceLab = _base->getFreeLaboratories();
	if (freeScientist > 0 && freeSpaceLab > 0)
	{
		change = std::min(std::min(freeScientist, freeSpaceLab), change);
		_project->setAssigned(_project->getAssigned()+change);
		_base->setScientists(_base->getScientists()-change);
		setAssignedScientist();
	}
}

/**
 * Removes one scientist from the project if possible.
 */
void ResearchInfoState::less()
{
	_timerLess->setInterval(50);
	lessByValue(_game->getScrollStep());
}

/**
 * Removes the given number of scientists from the project if possible.
 * @param change Number of scientists to subtract.
 */
void ResearchInfoState::lessByValue(int change)
{
	if (0 >= change) return;
	int assigned = _project->getAssigned();
	if (assigned > 0)
	{
		change = std::min(assigned, change);
		_project->setAssigned(assigned-change);
		_base->setScientists(_base->getScientists()+change);
		setAssignedScientist();
	}
}

/**
 * Runs state functionality every cycle (used to update the timer).
 */
void ResearchInfoState::think()
{
	State::think();

	_timerLess->think (this, 0);
	_timerMore->think (this, 0);
}

}
