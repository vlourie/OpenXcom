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

#include <locale>
#include <algorithm>
#include <cmath>
#include "Ufopaedia.h"
#include "UfopaediaSelectState.h"
#include "../Mod/ArticleDefinition.h"
#include "../Engine/Game.h"
#include "../Engine/Options.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Unicode.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextEdit.h"
#include "../Interface/TextButton.h"
#include "../Interface/ComboBox.h"
#include "../Interface/TextList.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace
{

/**
 * How far apart two palette entries look, as plain distance in RGB.
 */
int colorDistance(const SDL_Color &a, const SDL_Color &b)
{
	const int dr = (int)a.r - (int)b.r, dg = (int)a.g - (int)b.g, db = (int)a.b - (int)b.b;
	return (int)(std::sqrt((double)(dr * dr + dg * dg + db * db)) + 0.5);
}

/**
 * The colour of an unread article, in a shade the eye can tell from a read one.
 * X-Piratez paints both with neighbouring shades of the same cyan - 81 against 134, forty units
 * of RGB apart - so opening an article changed nothing anyone could see. When the mod's two
 * colours come out that close, the list's own palette is searched for a shade that is as far from
 * the normal one as it gets while staying about as bright, and whose five shades still darken one
 * after another: the font draws a letter as colour + 1 down to colour + 5, so a colour that runs
 * off the end of its ramp gets a shadow brighter than the letter itself. Nothing suitable in the
 * palette - the mod's own colour is kept.
 */
Uint8 visibleNewColor(const SDL_Color *pal, Uint8 normal, Uint8 fromMod)
{
	const int CLOSE = 96;
	if (!pal || normal + 5 > 255 || fromMod + 5 > 255 || colorDistance(pal[normal + 1], pal[fromMod + 1]) >= CLOSE)
	{
		return fromMod;
	}
	auto lum = [&](int i) { return pal[i].r * 2 + pal[i].g * 5 + pal[i].b; };
	const int want = lum(normal + 1);
	Uint8 best = fromMod;
	int bestDistance = colorDistance(pal[normal + 1], pal[fromMod + 1]);
	for (int base = 0; base + 5 < 256; ++base)
	{
		const int face = lum(base + 1);
		if (face < want * 3 / 4 || face > want * 5 / 4)
		{
			continue;
		}
		bool ramp = true;
		for (int shade = 2; shade <= 5 && ramp; ++shade)
		{
			ramp = lum(base + shade) < lum(base + shade - 1);
		}
		const int d = ramp ? colorDistance(pal[normal + 1], pal[base + 1]) : 0;
		if (ramp && d > bestDistance)
		{
			bestDistance = d;
			best = (Uint8)base;
		}
	}
	return best;
}

}

	UfopaediaSelectState::UfopaediaSelectState(const std::string &section, int heightOffset, int windowOffset) : _section(section), _lstScroll(0)
	{
		_isCommendationsSection = (_section == UFOPAEDIA_COMMENDATIONS);
		_screen = false;

		// set background window
		_window = new Window(this, 256, 180 + heightOffset, 32, 10 - windowOffset, POPUP_NONE);
		_window->setInnerColor(239); // almost black = darkest index from backpals.dat
		_btnQuickSearch = new TextEdit(this, 48, 9, 48, 30 - windowOffset);

		// set title
		_txtTitle = new Text(224, 17, 48, 26 - windowOffset);

		// set buttons
		_btnOk = new TextButton(108, 16, 164, 166 - windowOffset + heightOffset);
		_cbxFilter = new ComboBox(this, 108, 16, 48, 166 - windowOffset + heightOffset, true);
		int listHeightOffset = (heightOffset / 8) * 8; // multiple of 8
		_lstSelection = new TextList(224, 104 + listHeightOffset, 40, 50 - windowOffset);

		// Set palette
		setInterface("ufopaedia");

		add(_window, "window", "ufopaedia");
		add(_btnQuickSearch, "button2", "ufopaedia");
		add(_txtTitle, "text", "ufopaedia");
		add(_btnOk, "button2", "ufopaedia");
		add(_lstSelection, "list", "ufopaedia");
		add(_cbxFilter, "button2", "ufopaedia");

		_colorNormal = _lstSelection->getColor();
		_colorNew = Options::oxceHighlightNewTopics
			? visibleNewColor(_lstSelection->getPalette(), _colorNormal, _lstSelection->getSecondaryColor())
			: _colorNormal;
		_colorHidden = _game->getMod()->getInterface("ufopaedia")->getElement("listExtended")->color;

		centerAllSurfaces();

		setWindowBackground(_window, "ufopaedia");

		_txtTitle->setBig();
		_txtTitle->setAlign(ALIGN_CENTER);
		_txtTitle->setText(tr("STR_SELECT_ITEM"));

		_btnOk->setText(tr("STR_OK"));
		_btnOk->onMouseClick((ActionHandler)&UfopaediaSelectState::btnOkClick);
		_btnOk->onKeyboardPress((ActionHandler)&UfopaediaSelectState::btnOkClick,Options::keyCancel);
		_btnOk->onKeyboardPress((ActionHandler)&UfopaediaSelectState::btnMarkAllAsSeenClick, Options::keyMarkAllAsSeen);

		_lstSelection->setColumns(1, 206);
		_lstSelection->setSelectable(true);
		_lstSelection->setBackground(_window);
		_lstSelection->setMargin(18);
		_lstSelection->setAlign(ALIGN_CENTER);
		_lstSelection->onMouseClick((ActionHandler)&UfopaediaSelectState::lstSelectionClick, SDL_BUTTON_LEFT);
		_lstSelection->onMouseClick((ActionHandler)&UfopaediaSelectState::lstSelectionClickRight, SDL_BUTTON_RIGHT);

		std::vector<std::string> filterOptions;
		filterOptions.push_back("STR_FILTER_DEFAULT");
		filterOptions.push_back(_isCommendationsSection ? "STR_NOT_AWARDED_YET" : "STR_SHOW_ONLY_NEW");
		filterOptions.push_back("STR_FILTER_HIDDEN");
		_cbxFilter->setOptions(filterOptions, true);
		_cbxFilter->onChange((ActionHandler)&UfopaediaSelectState::cbxFilterChange);

		_btnQuickSearch->setText(""); // redraw
		_btnQuickSearch->onEnter((ActionHandler)&UfopaediaSelectState::btnQuickSearchApply);
		_btnQuickSearch->setVisible(Options::oxceQuickSearchButton);

		_btnOk->onKeyboardRelease((ActionHandler)&UfopaediaSelectState::btnQuickSearchToggle, Options::keyToggleQuickSearch);
	}

	UfopaediaSelectState::~UfopaediaSelectState()
	{}

	/**
	 * Initializes the state.
	 */
	void UfopaediaSelectState::init()
	{
		State::init();
		loadSelectionList(false);
	}

	/**
	 * Returns to the previous screen.
	 * @param action Pointer to an action.
	 */
	void UfopaediaSelectState::btnOkClick(Action *)
	{
		_game->popState();
	}

	/**
	 *
	 * @param action Pointer to an action.
	 */
	void UfopaediaSelectState::lstSelectionClick(Action *)
	{
		_lstScroll = _lstSelection->getScroll();
		Ufopaedia::openArticle(_game, _filtered_article_list[_lstSelection->getSelectedRow()]);
	}

	/**
	 * Toggles the topic status.
	 * @param action Pointer to an action.
	 */
	void UfopaediaSelectState::lstSelectionClickRight(Action *)
	{
		// change status
		const std::string rule = _filtered_article_list[_lstSelection->getSelectedRow()]->id;
		int oldState = _game->getSavedGame()->getUfopediaRuleStatus(rule);
		int newState = (oldState + 1) % ArticleDefinition::PEDIA_STATUSES;
		if (!Options::oxceHighlightNewTopics)
		{
			// only switch between hidden and not hidden
			newState = (oldState == ArticleDefinition::PEDIA_STATUS_HIDDEN) ? ArticleDefinition::PEDIA_STATUS_NORMAL : ArticleDefinition::PEDIA_STATUS_HIDDEN;
		}
		_game->getSavedGame()->setUfopediaRuleStatus(rule, newState);

		if (newState == ArticleDefinition::PEDIA_STATUS_HIDDEN)
		{
			_lstSelection->setRowColor(_lstSelection->getSelectedRow(), _colorHidden);
		}
		else if (newState == ArticleDefinition::PEDIA_STATUS_NEW)
		{
			_lstSelection->setRowColor(_lstSelection->getSelectedRow(), _colorNew);
		}
		else
		{
			_lstSelection->setRowColor(_lstSelection->getSelectedRow(), _colorNormal);
		}
	}

	/**
	* Quick search toggle.
	* @param action Pointer to an action.
	*/
	void UfopaediaSelectState::btnQuickSearchToggle(Action *action)
	{
		if (_btnQuickSearch->getVisible())
		{
			_btnQuickSearch->setText("");
			_btnQuickSearch->setVisible(false);
			btnQuickSearchApply(action);
		}
		else
		{
			_btnQuickSearch->setVisible(true);
			_btnQuickSearch->setFocus(true);
		}
	}

	/**
	* Quick search.
	* @param action Pointer to an action.
	*/
	void UfopaediaSelectState::btnQuickSearchApply(Action *)
	{
		loadSelectionList(false);
	}

	/**
	* Updates the list to match the filter.
	* @param action Pointer to an action.
	*/
	void UfopaediaSelectState::cbxFilterChange(Action *)
	{
		loadSelectionList(false);
	}

	/**
	* Marks all items as seen
	* @param action Pointer to an action.
	*/
	void UfopaediaSelectState::btnMarkAllAsSeenClick(Action *)
	{
		loadSelectionList(true);
	}

	void UfopaediaSelectState::loadSelectionList(bool markAllAsSeen)
	{
		std::string searchString = _btnQuickSearch->getText();
		Unicode::upperCase(searchString);

		_lstSelection->clearList();
		_article_list.clear();
		Ufopaedia::list(_game->getSavedGame(), _game->getMod(), _section, _article_list);
		// by the title the player reads: the mod's listOrder groups articles by topic, which in a
		// section of two hundred entries is no help at all when looking for one by name
		std::sort(_article_list.begin(), _article_list.end(), [&](ArticleDefinition *a, ArticleDefinition *b)
			{ return Unicode::naturalCompare(tr(a->getMainTitle()), tr(b->getMainTitle())); });
		_filtered_article_list.clear();
		size_t selectedFilter = _cbxFilter->getSelected();

		int row = 0;
		bool hasUnseen = false;
		int ruleStatus = 0;
		for (auto* articleDef : _article_list)
		{
			ruleStatus = _game->getSavedGame()->getUfopediaRuleStatus(articleDef->id);

			// filter
			if (selectedFilter == 0)
			{
				if (ruleStatus == ArticleDefinition::PEDIA_STATUS_HIDDEN)
				{
					continue;
				}
			}
			else if (selectedFilter == 2)
			{
				if (ruleStatus != ArticleDefinition::PEDIA_STATUS_HIDDEN)
				{
					continue;
				}
			}
			else if (selectedFilter == 1)
			{
				if (_isCommendationsSection)
				{
					if (Ufopaedia::isAwardedCommendation(_game->getSavedGame(), articleDef))
					{
						continue;
					}
				}
				else
				{
					if (ruleStatus != ArticleDefinition::PEDIA_STATUS_NEW)
					{
						continue;
					}
				}
			}

			// quick search
			if (!searchString.empty())
			{
				std::string projectName = tr(articleDef->getMainTitle());
				Unicode::upperCase(projectName);
				if (projectName.find(searchString) == std::string::npos)
				{
					continue;
				}
			}

			_filtered_article_list.push_back(articleDef);
			_lstSelection->addRow(1, tr(articleDef->getMainTitle()).c_str());

			if (markAllAsSeen)
			{
				// remember all listed articles as seen/normal
				_game->getSavedGame()->setUfopediaRuleStatus(articleDef->id, ArticleDefinition::PEDIA_STATUS_NORMAL);
			}
			else
			{
				if (ruleStatus == ArticleDefinition::PEDIA_STATUS_NEW)
				{
					_lstSelection->setCellColor(row, 0, _colorNew);
					hasUnseen = true;
				}
				else if (ruleStatus == ArticleDefinition::PEDIA_STATUS_HIDDEN)
				{
					_lstSelection->setCellColor(row, 0, _colorHidden);
				}
			}
			row++;
		}

		if (!_isCommendationsSection)
		{
			std::string label = tr("STR_OK");
			_btnOk->setText((hasUnseen ? "* " : "") + label);
		}
		if (_lstScroll > 0)
		{
			_lstSelection->scrollTo(_lstScroll);
			_lstScroll = 0;
		}
	}

}
