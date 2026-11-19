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
#include "ReequipManufactureState.h"
#include <algorithm>
#include <climits>
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleManufacture.h"
#include "../Savegame/Base.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/Production.h"
#include "../Savegame/SavedGame.h"
#include "../Basescape/ManufactureInfoState.h"
#include "../Basescape/ManufactureStartState.h"

namespace OpenXcom
{

/**
 * Initializes the elements of the screen.
 * @param item The type of the missing item.
 * @param home The base the craft is at.
 */
ReequipManufactureState::ReequipManufactureState(const std::string &item, Base *home) : _item(item), _home(home)
{
	_window = new Window(this, 320, 200, 0, 0);
	_txtTitle = new Text(300, 17, 10, 9);
	_txtBase = new Text(120, 9, 10, 34);
	_txtState = new Text(168, 9, 130, 34);
	_lstBases = new TextList(288, 128, 8, 44);
	_txtNone = new Text(280, 40, 20, 80);
	_btnCancel = new TextButton(120, 14, 100, 178);

	setInterface("cannotReequip");

	add(_window, "window", "cannotReequip");
	add(_txtTitle, "heading", "cannotReequip");
	add(_txtBase, "text", "cannotReequip");
	add(_txtState, "text", "cannotReequip");
	add(_lstBases, "list", "cannotReequip");
	add(_txtNone, "text", "cannotReequip");
	add(_btnCancel, "button", "cannotReequip");

	centerAllSurfaces();

	setWindowBackground(_window, "cannotReequip");

	_txtTitle->setText(tr("STR_REEQUIP_WHERE_TO_MAKE").arg(tr(_item)));
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();

	_txtBase->setText(tr("STR_REEQUIP_BASE"));
	_txtState->setText(tr("STR_REEQUIP_STATE"));

	_txtNone->setText(tr("STR_REEQUIP_CANNOT_MAKE"));
	_txtNone->setAlign(ALIGN_CENTER);
	_txtNone->setWordWrap(true);
	_txtNone->setVisible(false);

	_lstBases->setColumns(2, 122, 164);
	_lstBases->setSelectable(true);
	_lstBases->setBackground(_window);
	_lstBases->setMargin(2);
	_lstBases->onMouseClick((ActionHandler)&ReequipManufactureState::lstBasesClick);

	_btnCancel->setText(tr("STR_CANCEL_UC"));
	_btnCancel->onMouseClick((ActionHandler)&ReequipManufactureState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&ReequipManufactureState::btnCancelClick, Options::keyCancel);
}

ReequipManufactureState::~ReequipManufactureState()
{
}

/**
 * Lists the bases for each researched project that makes the item: the craft's base first, then those that can
 * make it, then the others with the reason. Read only: nothing is changed here.
 */
void ReequipManufactureState::init()
{
	State::init();

	_lstBases->clearList();
	_choices.clear();

	SavedGame *save = _game->getSavedGame();
	const Mod *mod = _game->getMod();
	std::vector<RuleManufacture*> rules;
	for (const auto &name : mod->getManufactureList())
	{
		RuleManufacture *rule = mod->getManufacture(name);
		if (!rule || !save->isResearched(rule->getRequirements()))
		{
			continue;
		}
		for (const auto &produced : rule->getProducedItems())
		{
			if (produced.first && produced.first->getType() == _item)
			{
				rules.push_back(rule);
				break;
			}
		}
	}
	_txtNone->setVisible(rules.empty());
	if (rules.empty())
	{
		return;
	}

	struct Row { Choice choice; int order; std::string state; };
	std::vector<Row> rows;
	for (auto *rule : rules)
	{
		for (auto *base : *save->getBases())
		{
			Production *running = nullptr;
			for (auto *p : base->getProductions())
			{
				if (p->getRules() == rule)
				{
					running = p;
					break;
				}
			}
			const bool facility = !(~base->getProvidedBaseFunc({}) & rule->getRequireBaseFunc()).any();
			bool materials = true;
			for (const auto &need : rule->getRequiredItems())
			{
				if (base->getStorageItems()->getItem(need.first) < need.second)
				{
					materials = false;
					break;
				}
			}
			const bool space = running || base->getFreeWorkshops() >= rule->getRequiredSpace();
			std::string state;
			int order;
			if (!facility)
			{
				state = tr("STR_REEQUIP_NO_FACILITY");
				order = 3;
			}
			else if (running)
			{
				state = tr("STR_REEQUIP_RUNNING");
				order = 1;
			}
			else if (!materials)
			{
				state = tr("STR_REEQUIP_NO_MATERIALS");
				order = 2;
			}
			else
			{
				state = space ? tr("STR_REEQUIP_CAN").arg(base->getAvailableEngineers()) : tr("STR_REEQUIP_NO_SPACE").arg(base->getAvailableEngineers());
				order = space ? 0 : 1;
			}
			if (base == _home)
			{
				order = facility ? -1 : order;
			}
			rows.push_back(Row{ Choice{ base, rule, running, facility }, order, state });
		}
	}
	std::stable_sort(rows.begin(), rows.end(), [](const Row &a, const Row &b) { return a.order < b.order; });

	// the rows a base can't take: the list's second colour (not every mod gives one - then the text's, else the list's own)
	const RuleInterface *ui = _game->getMod()->getInterface("cannotReequip");
	const Element *listUi = ui->getElement("list"), *textUi = ui->getElementOptional("text");
	const Uint8 grey = (Uint8)(listUi->color2 != INT_MAX ? listUi->color2 : textUi && textUi->color != INT_MAX ? textUi->color : listUi->color);
	for (const auto &row : rows)
	{
		std::string name = row.choice.base->getName(_game->getLanguage());
		if (rules.size() > 1)
		{
			name += " - " + std::string(tr(row.choice.rule->getName()));
		}
		_lstBases->addRow(2, name.c_str(), row.state.c_str());
		if (!row.choice.open)
		{
			_lstBases->setRowColor(_lstBases->getLastRowIndex(), grey);
		}
		_choices.push_back(row.choice);
	}
}

/**
 * Returns to the list of missing items.
 * @param action Pointer to an action.
 */
void ReequipManufactureState::btnCancelClick(Action *)
{
	_game->popState();
}

/**
 * Opens the usual production screens of the clicked base: a running project of it to change, else the start of a new one.
 * @param action Pointer to an action.
 */
void ReequipManufactureState::lstBasesClick(Action *)
{
	const size_t row = _lstBases->getSelectedRow();
	if (row >= _choices.size() || !_choices[row].open)
	{
		return;
	}
	const Choice &c = _choices[row];
	if (c.running)
	{
		_game->pushState(new ManufactureInfoState(c.base, c.running));
	}
	else
	{
		_game->pushState(new ManufactureStartState(c.base, c.rule));
	}
}

}
