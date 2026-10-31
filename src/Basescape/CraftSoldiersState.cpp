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
#include "CraftSoldiersState.h"
#include <algorithm>
#include <functional>
#include <climits>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/ComboBox.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Menu/ErrorMessageState.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Craft.h"
#include "../Savegame/SavedGame.h"
#include "SoldierInfoState.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleInterface.h"
#include "../Engine/Unicode.h"
#include "../Battlescape/BattlescapeGenerator.h"
#include "../Battlescape/BriefingState.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Engine/Palette.h"
#include "../Mod/RuleStartingCondition.h"
#include "../Mod/AlienDeployment.h"
#include "../Mod/AlienRace.h"
#include "../Mod/RuleGlobe.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleSoldier.h"
#include "../Mod/Texture.h"
#include "../Mod/Polygon.h"
#include "../Geoscape/Globe.h"
#include "../Savegame/Base.h"
#include "../Savegame/Target.h"
#include "../Savegame/MissionSite.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/Ufo.h"

namespace OpenXcom
{

/**
 * OXCE-HD (oxceHdCraftFit): the plate of the seats between the sort box and the OK button. A button's look, but no mouse,
 * no key and no press: it only shows "seats used / seats in all".
 */
class CraftFitPlate : public TextButton
{
public:
	CraftFitPlate(int width, int height, int x, int y) : TextButton(width, height, x, y) { }
	void handle(Action *, State *) override { }
};

/**
 * OXCE-HD (oxceHdCraftMission): the starting condition of a target - the same chain as ConfirmLandingState::checkStartingCondition:
 * UFO: the deployment by the UFO type (type_UNDERWATER on a fake underwater texture); mission site: its deployment;
 * alien base: the race's base custom mission, else the base deployment. No condition in the deployment - the one of the
 * texture (mission site: the texture of the site, else the globe texture under it, as GeoscapeState hands it over;
 * UFO and base: the globe texture). Reads only, no random numbers.
 * @return The condition, or null if the landing would check nothing.
 */
static const RuleStartingCondition *findStartingCondition(const Mod *mod, const Target *target)
{
	const Ufo *u = dynamic_cast<const Ufo*>(target);
	const MissionSite *m = dynamic_cast<const MissionSite*>(target);
	const AlienBase *b = dynamic_cast<const AlienBase*>(target);
	if (!u && !m && !b)
	{
		return nullptr;
	}
	Polygon *poly = Globe::polygonAt(mod->getGlobe(), target->getLongitude(), target->getLatitude());
	Texture *globeTexture = mod->getGlobe()->getTexture(poly ? poly->getTexture() : -1);
	Texture *missionTexture = globeTexture;
	if (m)
	{
		if (globeTexture && globeTexture->isCosmeticOcean())
		{
			globeTexture = mod->getGlobe()->getTexture(-1);
		}
		missionTexture = mod->getGlobe()->getTexture(m->getTexture());
		if (!missionTexture)
		{
			missionTexture = globeTexture;
		}
	}

	const AlienDeployment *ruleDeploy = nullptr;
	if (u)
	{
		std::string name = u->getRules()->getType();
		if (missionTexture && missionTexture->isFakeUnderwater())
		{
			name += "_UNDERWATER";
		}
		ruleDeploy = mod->getDeployment(name);
	}
	else if (m)
	{
		ruleDeploy = mod->getDeployment(m->getDeployment()->getType());
	}
	else
	{
		const AlienRace *race = mod->getAlienRace(b->getAlienRace());
		ruleDeploy = race ? mod->getDeployment(race->getBaseCustomMission()) : nullptr;
		if (!ruleDeploy) ruleDeploy = mod->getDeployment(b->getDeployment()->getType());
	}
	if (!ruleDeploy)
	{
		return nullptr;
	}
	const RuleStartingCondition *rule = mod->getStartingCondition(ruleDeploy->getStartingCondition());
	if (!rule && missionTexture)
	{
		rule = mod->getStartingCondition(missionTexture->getStartingCondition());
	}
	return rule;
}

enum MissionFit { MF_OK, MF_CRAFT, MF_SOLDIER_TYPE };

/// OXCE-HD (oxceHdCraftMission): what the condition says about the craft as a whole - the same calls as the landing, one by one.
struct MissionCraftFit
{
	bool craftOk = true;        // RuleStartingCondition::isCraftPermitted
	bool needCommander = false; // requiresCommanderOnboard and no commander aboard
	bool needItems = false;     // the required items are not aboard
};

static MissionCraftFit missionCraftFit(const RuleStartingCondition *rule, const Craft *craft)
{
	MissionCraftFit r;
	if (rule)
	{
		r.craftOk = rule->isCraftPermitted(craft->getRules()->getType());
		r.needCommander = rule->requiresCommanderOnboard() && !craft->isCommanderOnboard();
		r.needItems = !craft->areRequiredItemsOnboard(rule->getRequiredItems());
	}
	return r;
}

/// OXCE-HD (oxceHdCraftMission): one soldier - the craft, then the soldier type (Craft::areOnlyPermittedSoldierTypesOnboard, per soldier).
static MissionFit missionSoldierFit(const RuleStartingCondition *rule, const Craft *craft, const Soldier *s)
{
	if (!rule)
	{
		return MF_OK;
	}
	if (!rule->isCraftPermitted(craft->getRules()->getType()))
	{
		return MF_CRAFT;
	}
	if (!rule->isSoldierTypePermitted(s->getRules()->getType()))
	{
		return MF_SOLDIER_TYPE;
	}
	return MF_OK;
}

/// OXCE-HD (oxceHdCraftMission): the armor is replaced at the start, it is no ban. The same membership test as
/// RuleStartingCondition::getArmorReplacement, but without its random pick (that would take a number from the generator).
static bool missionArmorWillChange(const RuleStartingCondition *rule, const Soldier *s)
{
	if (!rule)
	{
		return false;
	}
	const std::string &armor = s->getArmor()->getType();
	const auto &forbidden = rule->getForbiddenArmors();
	const auto &allowed = rule->getAllowedArmors();
	if (!forbidden.empty())
	{
		return std::find(forbidden.begin(), forbidden.end(), armor) != forbidden.end();
	}
	if (!allowed.empty())
	{
		return std::find(allowed.begin(), allowed.end(), armor) == allowed.end();
	}
	return false;
}

/**
 * Initializes all the elements in the Craft Soldiers screen.
 * @param game Pointer to the core game.
 * @param base Pointer to the base to get info from.
 * @param craft ID of the selected craft.
 */
CraftSoldiersState::CraftSoldiersState(Base *base, size_t craft)
		:  SortSoldiersMixin(base), _craft(craft), _otherCraftColor(0), _origSoldierOrder(*_base->getSoldiers()), _dynGetter(NULL)
{
	bool hidePreview = _game->getSavedGame()->getMonthsPassed() == -1;
	Craft *c = _base->getCrafts()->at(_craft);
	if (c && !c->getRules()->isForNewBattle())
	{
		// no battlescape map available
		hidePreview = true;
	}

	// Create objects
	_window = new Window(this, 320, 200, 0, 0);
	// OXCE-HD (oxceHdCraftFit): the sort box and (without the preview button) OK shorter, between them the plate of the seats
	const bool fit = Options::oxceHdCraftFit;
	const bool mission = Options::oxceHdCraftMission; // OXCE-HD: the box "For mission:" under the list, the list 13 rows
	_btnOk = new TextButton(hidePreview ? (fit ? 116 : 148) : 30, 16, hidePreview ? (fit ? 196 : 164) : 274, 176);
	_btnFit = fit ? new CraftFitPlate(hidePreview ? 64 : 44, 16, hidePreview ? 128 : 116, 176) : nullptr;
	_btnPreview = new TextButton(102, 16, 164, 176);
	_txtTitle = new Text(300, 17, 16, 7);
	_txtName = new Text(114, 9, 16, 32);
	_txtRank = new Text(102 - RANK_SHIFT, 9, 122 + RANK_SHIFT, 32);
	_txtCraft = new Text(84, 9, 220, 32);
	_txtAvailable = new Text(110, 9, 16, 24);
	_txtUsed = new Text(110, 9, 122, 24);
	_cbxSortBy = new ComboBox(this, fit ? (hidePreview ? 116 : 104) : 148, 16, 8, 176, true);
	_lstSoldiers = new TextList(288, mission ? 104 : 128, 8, 40);
	if (mission)
	{
		_txtMissionInfo = new Text(288, 9, 16, 145);
		// the box is half as wide, at the right edge (x 194..308), so that its button does not cover the open sort list;
		// the label ends right at the box
		_txtMissionLabel = new Text(100, 9, 92, 161);
		_cbxMission = new ComboBox(this, 114, 16, 194, 157, true);
	}

	touchComponentsCreate(_txtTitle, true);

	// Set palette
	setInterface("craftSoldiers");

	add(_window, "window", "craftSoldiers");
	add(_btnOk, "button", "craftSoldiers");
	add(_btnPreview, "button", "craftSoldiers");
	if (_btnFit)
	{
		add(_btnFit, "button", "craftSoldiers");
	}
	add(_txtTitle, "text", "craftSoldiers");
	add(_txtName, "text", "craftSoldiers");
	add(_txtRank, "text", "craftSoldiers");
	add(_txtCraft, "text", "craftSoldiers");
	add(_txtAvailable, "text", "craftSoldiers");
	add(_txtUsed, "text", "craftSoldiers");
	add(_lstSoldiers, "list", "craftSoldiers");
	if (_cbxMission)
	{
		// the texts go under the sort box, so its open list is drawn over them
		add(_txtMissionInfo, "text", "craftSoldiers");
		add(_txtMissionLabel, "text", "craftSoldiers");
	}
	add(_cbxSortBy, "button", "craftSoldiers");
	if (_cbxMission)
	{
		add(_cbxMission, "button", "craftSoldiers");
	}

	touchComponentsAdd("button2", "craftSoldiers", _window);

	_otherCraftColor = _game->getMod()->getInterface("craftSoldiers")->getElement("otherCraft")->color;

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "craftSoldiers");

	touchComponentsConfigure();

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&CraftSoldiersState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&CraftSoldiersState::btnOkClick, Options::keyCancel);
	_btnOk->onKeyboardPress((ActionHandler)&CraftSoldiersState::btnDeassignAllSoldiersClick, Options::keyRemoveSoldiersFromAllCrafts);
	_btnOk->onKeyboardPress((ActionHandler)&CraftSoldiersState::btnDeassignCraftSoldiersClick, Options::keyRemoveSoldiersFromCraft);

	_btnPreview->setText(tr("STR_CRAFT_DEPLOYMENT_PREVIEW"));
	_btnPreview->setVisible(!hidePreview);
	_btnPreview->onMouseClick((ActionHandler)&CraftSoldiersState::btnPreviewClick);

	_txtTitle->setBig();
	if (Options::oxceBaseTouchButtons)
	{
		_txtTitle->setAlign(ALIGN_CENTER);
		_txtTitle->setText(c->getName(_game->getLanguage()));
	}
	else
	{
		_txtTitle->setAlign(ALIGN_LEFT);
		_txtTitle->setText(tr("STR_SELECT_SQUAD_FOR_CRAFT").arg(c->getName(_game->getLanguage())));
	}

	_txtName->setText(tr("STR_NAME_UC"));

	_txtRank->setText(tr("STR_RANK"));

	_txtCraft->setText(tr("STR_CRAFT"));

	if (_cbxMission)
	{
		// OXCE-HD (oxceHdCraftMission): item 0 = no target (the list is as it was), then the detected targets
		_txtMissionLabel->setAlign(ALIGN_RIGHT);
		_txtMissionLabel->setText(tr("STR_CRAFT_FOR_MISSION"));
		std::vector<std::string> names;
		names.push_back(tr("STR_CRAFT_FOR_MISSION_NONE"));
		buildMissionTargets(names);
		{
			// the box is narrow: a long name is cut with "..." to the width of the box, the list of targets itself is not touched
			Text probe(300, 9, 0, 0);
			probe.initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
			probe.setSmall();
			const int maxWidth = _cbxMission->getWidth() - 24;
			for (size_t i = 1; i < names.size(); ++i)
			{
				UString name = Unicode::convUtf8ToUtf32(names[i]);
				probe.setText(names[i]);
				if (probe.getTextWidth() <= maxWidth)
				{
					continue;
				}
				while (name.size() > 1)
				{
					name.pop_back();
					probe.setText(Unicode::convUtf32ToUtf8(name) + "...");
					if (probe.getTextWidth() <= maxWidth)
					{
						break;
					}
				}
				names[i] = Unicode::convUtf32ToUtf8(name) + "...";
			}
		}
		_cbxMission->setOptions(names);
		// XP-000376: the rows are coloured as in the UFO tracker (T): mission sites in the second colour (yellow of the
		// basescape palette: the tracker's own index belongs to the geoscape palette), UFOs and alien bases in the box's colour
		for (size_t i = 0; i < _missionTargets.size(); ++i)
		{
			if (dynamic_cast<const MissionSite*>(_missionTargets[i]))
			{
				_cbxMission->setRowColor(i + 1, 144);
			}
		}
		_cbxMission->setSelected(0);
		_cbxMission->onChange((ActionHandler)&CraftSoldiersState::cbxMissionChange);
		_lstSoldiers->onMouseOver((ActionHandler)&CraftSoldiersState::lstSoldiersMouseOver);
		_lstSoldiers->onMouseOut((ActionHandler)&CraftSoldiersState::lstSoldiersMouseOut);
	}

	// populate sort options
	FillSorters(_sortFunctors, *_cbxSortBy, (ActionHandler)&CraftSoldiersState::cbxSortByChange);
	ChangeDynSorter(_dynGetter);
	// OXCE 8.7: default info column (Alt+select remembers it); sorting stays with our QOL default sorter
	{
		size_t selIdx = Options::oxceBaseSoldierInfoColumnDefault;
		if (selIdx >= _sortFunctors.size())
		{
			selIdx = 0;
			Options::oxceBaseSoldierInfoColumnDefault = 0;
		}
		if (selIdx != 0)
		{
			_cbxSortBy->setSelected(selIdx);
			if (_sortFunctors[selIdx] && selIdx != 2 && selIdx != 3)
			{
				_dynGetter = _sortFunctors[selIdx]->getGetter();
			}
		}
	}

	_lstSoldiers->setArrowColumn(188, ARROW_VERTICAL);
	_lstSoldiers->setColumns(3, 106, 98, 76);
	_lstSoldiers->setAlign(ALIGN_RIGHT, 3);
	_lstSoldiers->setSelectable(true);
	_lstSoldiers->setBackground(_window);
	_lstSoldiers->setMargin(8);
	_lstSoldiers->onLeftArrowClick((ActionHandler)&CraftSoldiersState::lstItemsLeftArrowClick);
	_lstSoldiers->onRightArrowClick((ActionHandler)&CraftSoldiersState::lstItemsRightArrowClick);
	_lstSoldiers->onMouseClick((ActionHandler)&CraftSoldiersState::lstSoldiersClick, 0);
	_lstSoldiers->onMousePress((ActionHandler)&CraftSoldiersState::lstSoldiersMousePress);
}

/**
 * cleans up dynamic state
 */
CraftSoldiersState::~CraftSoldiersState()
{
	for (auto* sortFunctor : _sortFunctors)
	{
		delete sortFunctor;
	}
}

/**
 * Sorts the soldiers list by the selected criterion
 * @param action Pointer to an action.
 */
void CraftSoldiersState::cbxSortByChange(Action *)
{
	bool ctrlPressed = _game->isCtrlPressed(true);
	size_t selIdx = _cbxSortBy->getSelected();
	if (selIdx == (size_t)-1)
	{
		return;
	}
	if (_game->isAltPressed(true))
	{
		Options::oxceBaseSoldierInfoColumnDefault = selIdx;
	}

	SortFunctor *compFunc = _sortFunctors[selIdx];
	_dynGetter = NULL;
	if (compFunc)
	{
		if (selIdx != 2 && selIdx != 3)
		{
			_dynGetter = compFunc->getGetter();
		}

		// if CTRL is pressed, we only want to show the dynamic column, without actual sorting
		if (!ctrlPressed)
		{
			DoSort(selIdx, compFunc);
		}
		else
		{
			SortSecond(selIdx, _sortFunctors, *_cbxSortBy); // OXCE-HD: second criterion inside the first
		}
	}
	else
	{
		// restore original ordering, ignoring (of course) those
		// soldiers that have been sacked since this state started
		for (const auto* origSoldier : _origSoldierOrder)
		{
			auto soldierIt = std::find(_base->getSoldiers()->begin(), _base->getSoldiers()->end(), origSoldier);
			if (soldierIt != _base->getSoldiers()->end())
			{
				Soldier *s = *soldierIt;
				_base->getSoldiers()->erase(soldierIt);
				_base->getSoldiers()->insert(_base->getSoldiers()->end(), s);
			}
		}
		DoSort(selIdx, nullptr); // OXCE-HD: the groups over the original order
	}

	size_t originalScrollPos = _lstSoldiers->getScroll();
	initList(originalScrollPos);
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Shows the battlescape preview.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::btnPreviewClick(Action *)
{
	Craft* c = _base->getCrafts()->at(_craft);
	if (c->getSpaceUsed() <= 0)
	{
		// at least one unit must be onboard
		return;
	}

	SavedBattleGame* bgame = new SavedBattleGame(_game->getMod(), _game->getLanguage(), true);
	_game->getSavedGame()->setBattleGame(bgame);
	BattlescapeGenerator bgen = BattlescapeGenerator(_game);
	bgame->setMissionType(c->getRules()->getCustomPreviewType());
	bgame->setCraftForPreview(c);
	bgen.setCraft(c);
	bgen.run();

	// needed for preview of craft deployment tiles
	bgame->setCraftPos(bgen.getCraftPos());
	bgame->setCraftZ(bgen.getCraftZ());
	bgame->calculateCraftTiles();

	_game->pushState(new BriefingState(c));
}

/**
 * Shows the soldiers in a list at specified offset/scroll.
 */
void CraftSoldiersState::initList(size_t scrl)
{
	int row = 0;
	_lstSoldiers->clearList();
	_fitGrey.clear();

	// OXCE-HD: the race picture of the soldier info screen before the name and the rank badge before the rank
	// (Options::oxceBaseSoldierTypeIcon): 32x20 fits the row as 13x8. The rank stands RANK_SHIFT to the right,
	// near the arrows (the header too); the craft column stays where it was
	const int icon = Options::oxceBaseSoldierTypeIcon ? 13 : 0;
	SurfaceSet *badges = icon ? _game->getMod()->getSurfaceSet("BASEBITS.PCK") : nullptr;
	_lstSoldiers->setIconColumn(8, icon);
	_lstSoldiers->setIconColumn(106 + RANK_SHIFT - 3, badges ? 10 : 0, 1);
	_lstSoldiers->setMargin(8 + icon);
	if (_dynGetter != NULL)
	{
		// OXCE-HD: the stat column wider (22, not 16) - kills in thousands (X-Piratez) ran over the craft name
		_lstSoldiers->setColumns(4, 106 - icon + RANK_SHIFT, 98 - RANK_SHIFT, 54, 22);
	}
	else
	{
		_lstSoldiers->setColumns(3, 106 - icon + RANK_SHIFT, 98 - RANK_SHIFT, 76);
	}

	Craft *c = _base->getCrafts()->at(_craft);
	BaseSumDailyRecovery recovery = _base->getSumRecoveryPerDay();
	for (const auto* soldier : *_base->getSoldiers())
	{
		if (_dynGetter != NULL)
		{
			// call corresponding getter
			int dynStat = (*_dynGetter)(_game, soldier);
			std::ostringstream ss;
			ss << dynStat;
			_lstSoldiers->addRow(4, soldier->getName(true, 19).c_str(), tr(soldier->getRankString()).c_str(), soldier->getCraftString(_game->getLanguage(), recovery).c_str(), ss.str().c_str());
		}
		else
		{
			_lstSoldiers->addRow(3, soldier->getName(true, 19).c_str(), tr(soldier->getRankString()).c_str(), soldier->getCraftString(_game->getLanguage(), recovery).c_str());
		}

		Uint8 color;
		if (soldier->getCraft() == c)
		{
			color = _lstSoldiers->getSecondaryColor();
		}
		else if (soldier->getCraft() != 0)
		{
			color = _otherCraftColor;
		}
		else
		{
			color = _lstSoldiers->getColor();
		}
		setListRowColor(*_lstSoldiers, row, color, *soldier);
		if (icon)
		{
			_lstSoldiers->setRowIcon(row, SoldierFlag(soldier));
			_lstSoldiers->setRowIcon(row, badges->getFrame(soldier->getRankSprite()), 1);
		}

		row++;
	}
	if (scrl)
		_lstSoldiers->scrollTo(scrl);
	_lstSoldiers->draw();

	_txtAvailable->setText(tr("STR_SPACE_AVAILABLE").arg(c->getSpaceAvailable()));
	_txtUsed->setText(tr("STR_SPACE_USED").arg(c->getSpaceUsed()));
	fitRefresh();
	missionRefresh();
}

/**
 * OXCE-HD (oxceHdCraftFit): would the click on this soldier meet a craft limit - the same test (and the same Craft calls)
 * as the click handler, which for those cases opens the "not enough space" window? Only the display asks it:
 * the rules of the assignment are as they were.
 * @param s The soldier of a row.
 * @param c The craft being filled.
 * @return True if the soldier can be taken to the craft by the click in principle, but a limit of the craft stops him.
 */
bool CraftSoldiersState::doesNotFit(const Soldier *s, const Craft *c) const
{
	if (s->getCraft() == c)
	{
		return false;
	}
	if (s->getCraft() && s->getCraft()->getStatus() == "STR_OUT")
	{
		return false;
	}
	if (!s->hasFullHealth())
	{
		return false;
	}
	CraftPlacementErrors err = c->validateAddingSoldier(c->getSpaceAvailable(), s);
	return err != CPE_None && err != CPE_SoldierGroupNotAllowed && err != CPE_SoldierGroupNotSame && err != CPE_ArmorGroupNotAllowed;
}

/**
 * OXCE-HD (oxceHdWoundedRed): the row colours as the base sets them (the mana highlight too), and then, with the option on,
 * the name and the "WOUNDED>days" text of a wounded soldier red - a colour of the interface palette. Display only.
 */
void CraftSoldiersState::setListRowColor(TextList& list, size_t row, Uint8 color, const Soldier& soldier)
{
	HighlightLowManaSoldiersMixin<TouchState>::setListRowColor(list, row, color, soldier);
	if (Options::oxceHdWoundedRed && soldier.isWounded())
	{
		const Uint8 red = Palette::blockOffset(2) + 2;
		list.setCellColor(row, 0, red);
		list.setCellColor(row, 2, red);
	}
}

/**
 * OXCE-HD (oxceHdCraftFit): the plate with "seats used / seats in all" (the same Craft::getSpaceUsed and
 * Craft::getSpaceAvailable as the two texts above) and the rows of the soldiers who no longer fit in grey.
 */
void CraftSoldiersState::fitRefresh()
{
	if (!_btnFit)
	{
		return;
	}
	Craft *c = _base->getCrafts()->at(_craft);
	const int used = c->getSpaceUsed();
	_btnFit->setText(std::to_string(used) + "/" + std::to_string(used + c->getSpaceAvailable()));

	const Uint8 grey = Palette::blockOffset(0) + 8;
	_fitGrey.resize(_base->getSoldiers()->size(), 0);
	size_t row = 0;
	for (const auto* soldier : *_base->getSoldiers())
	{
		const bool g = doesNotFit(soldier, c);
		if (g)
		{
			_lstSoldiers->setRowColor(row, grey);
		}
		else if (_fitGrey[row])
		{
			Uint8 color = _lstSoldiers->getColor();
			if (soldier->getCraft() == c)
			{
				color = _lstSoldiers->getSecondaryColor();
			}
			else if (soldier->getCraft() != 0)
			{
				color = _otherCraftColor;
			}
			setListRowColor(*_lstSoldiers, row, color, *soldier);
		}
		_fitGrey[row] = g;
		++row;
	}
}

/**
 * Shows the soldiers in a list.
 */
void CraftSoldiersState::init()
{
	State::init();
	_base->prepareSoldierStatsWithBonuses(); // refresh stats for sorting
	initList(_lstSoldiers->getScroll());

	// update the label to indicate presence of a saved craft deployment
	Craft* c = _base->getCrafts()->at(_craft);
	if (c->hasCustomDeployment())
		_btnPreview->setText(tr("STR_CRAFT_DEPLOYMENT_PREVIEW_SAVED"));
	else
		_btnPreview->setText(tr("STR_CRAFT_DEPLOYMENT_PREVIEW"));

	touchComponentsRefresh();
}

/**
 * Reorders a soldier up.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::lstItemsLeftArrowClick(Action *action)
{
	unsigned int row = _lstSoldiers->getSelectedRow();
	if (row > 0)
	{
		if (_game->isLeftClick(action, true))
		{
			moveSoldierUp(action, row);
		}
		else if (_game->isRightClick(action, true))
		{
			moveSoldierUp(action, row, true);
		}
	}
	_cbxSortBy->setText(tr("STR_SORT_BY"));
	_cbxSortBy->setSelected(-1);
	ForgetSort();
}

/**
 * Moves a soldier up on the list.
 * @param action Pointer to an action.
 * @param row Selected soldier row.
 * @param max Move the soldier to the top?
 */
void CraftSoldiersState::moveSoldierUp(Action *action, unsigned int row, bool max)
{
	Soldier *s = _base->getSoldiers()->at(row);
	if (max)
	{
		_base->getSoldiers()->erase(_base->getSoldiers()->begin() + row);
		_base->getSoldiers()->insert(_base->getSoldiers()->begin(), s);
	}
	else
	{
		_base->getSoldiers()->at(row) = _base->getSoldiers()->at(row - 1);
		_base->getSoldiers()->at(row - 1) = s;
		if (row != _lstSoldiers->getScroll())
		{
			SDL_WarpMouse(action->getLeftBlackBand() + action->getXMouse(), action->getTopBlackBand() + action->getYMouse() - static_cast<Uint16>(8 * action->getYScale()));
		}
		else
		{
			_lstSoldiers->scrollUp(false);
		}
	}
	initList(_lstSoldiers->getScroll());
}

/**
 * Reorders a soldier down.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::lstItemsRightArrowClick(Action *action)
{
	unsigned int row = _lstSoldiers->getSelectedRow();
	size_t numSoldiers = _base->getSoldiers()->size();
	if (0 < numSoldiers && INT_MAX >= numSoldiers && row < numSoldiers - 1)
	{
		if (_game->isLeftClick(action, true))
		{
			moveSoldierDown(action, row);
		}
		else if (_game->isRightClick(action, true))
		{
			moveSoldierDown(action, row, true);
		}
	}
	_cbxSortBy->setText(tr("STR_SORT_BY"));
	_cbxSortBy->setSelected(-1);
	ForgetSort();
}

/**
 * Moves a soldier down on the list.
 * @param action Pointer to an action.
 * @param row Selected soldier row.
 * @param max Move the soldier to the bottom?
 */
void CraftSoldiersState::moveSoldierDown(Action *action, unsigned int row, bool max)
{
	Soldier *s = _base->getSoldiers()->at(row);
	if (max)
	{
		_base->getSoldiers()->erase(_base->getSoldiers()->begin() + row);
		_base->getSoldiers()->insert(_base->getSoldiers()->end(), s);
	}
	else
	{
		_base->getSoldiers()->at(row) = _base->getSoldiers()->at(row + 1);
		_base->getSoldiers()->at(row + 1) = s;
		if (row != _lstSoldiers->getVisibleRows() - 1 + _lstSoldiers->getScroll())
		{
			SDL_WarpMouse(action->getLeftBlackBand() + action->getXMouse(), action->getTopBlackBand() + action->getYMouse() + static_cast<Uint16>(8 * action->getYScale()));
		}
		else
		{
			_lstSoldiers->scrollDown(false);
		}
	}
	initList(_lstSoldiers->getScroll());
}

/**
 * Shows the selected soldier's info.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::lstSoldiersClick(Action *action)
{
	double mx = action->getAbsoluteXMouse();
	if (mx >= _lstSoldiers->getArrowsLeftEdge() && mx < _lstSoldiers->getArrowsRightEdge())
	{
		return;
	}
	int row = _lstSoldiers->getSelectedRow();
	if (_game->isLeftClick(action, true))
	{
		Craft *c = _base->getCrafts()->at(_craft);
		Soldier *s = _base->getSoldiers()->at(_lstSoldiers->getSelectedRow());
		Uint8 color = _lstSoldiers->getColor();
		if (s->getCraft() == c)
		{
			s->setCraftAndMoveEquipment(0, _base, _game->getSavedGame()->getMonthsPassed() == -1);
			_lstSoldiers->setCellText(row, 2, tr("STR_NONE_UC"));
		}
		else if (s->getCraft() && s->getCraft()->getStatus() == "STR_OUT")
		{
			color = _otherCraftColor;
		}
		else if (s->hasFullHealth())
		{
			int space = c->getSpaceAvailable();
			CraftPlacementErrors err = c->validateAddingSoldier(space, s);
			if (err == CPE_None)
			{
				s->setCraftAndMoveEquipment(c, _base, _game->getSavedGame()->getMonthsPassed() == -1, true);
				_lstSoldiers->setCellText(row, 2, c->getName(_game->getLanguage()));
				color = _lstSoldiers->getSecondaryColor();

				// update the label to indicate absence of a saved craft deployment
				_btnPreview->setText(tr("STR_CRAFT_DEPLOYMENT_PREVIEW"));
			}
			else if (err == CPE_SoldierGroupNotAllowed)
			{
				_game->pushState(new ErrorMessageState(tr("STR_SOLDIER_GROUP_NOT_ALLOWED"), _palette, _game->getMod()->getInterface("soldierInfo")->getElement("errorMessage")->color, "BACK01.SCR", _game->getMod()->getInterface("soldierInfo")->getElement("errorPalette")->color));
			}
			else if (err == CPE_SoldierGroupNotSame)
			{
				_game->pushState(new ErrorMessageState(tr("STR_SOLDIER_GROUP_NOT_SAME"), _palette, _game->getMod()->getInterface("soldierInfo")->getElement("errorMessage")->color, "BACK01.SCR", _game->getMod()->getInterface("soldierInfo")->getElement("errorPalette")->color));
			}
			else if (err == CPE_ArmorGroupNotAllowed)
			{
				_game->pushState(new ErrorMessageState(tr("STR_ARMOR_GROUP_NOT_ALLOWED"), _palette, _game->getMod()->getInterface("soldierInfo")->getElement("errorMessage")->color, "BACK01.SCR", _game->getMod()->getInterface("soldierInfo")->getElement("errorPalette")->color));
			}
			else if (space > 0 && !Options::oxceHdCraftFit) // oxceHdCraftFit: no window, the row is grey instead
			{
				_game->pushState(new ErrorMessageState(tr("STR_NOT_ENOUGH_CRAFT_SPACE"), _palette, _game->getMod()->getInterface("soldierInfo")->getElement("errorMessage")->color, "BACK01.SCR", _game->getMod()->getInterface("soldierInfo")->getElement("errorPalette")->color));
			}
		}
		setListRowColor(*_lstSoldiers, row, color, *s);

		_txtAvailable->setText(tr("STR_SPACE_AVAILABLE").arg(c->getSpaceAvailable()));
		_txtUsed->setText(tr("STR_SPACE_USED").arg(c->getSpaceUsed()));
		fitRefresh();
		missionRefresh();
	}
	else if (_game->isRightClick(action, true))
	{
		_game->pushState(new SoldierInfoState(_base, row, false));
	}
}

/**
 * Handles the mouse-wheels on the arrow-buttons.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::lstSoldiersMousePress(Action *action)
{
	if (Options::changeValueByMouseWheel == 0)
		return;
	unsigned int row = _lstSoldiers->getSelectedRow();
	size_t numSoldiers = _base->getSoldiers()->size();
	if (action->getDetails()->button.button == SDL_BUTTON_WHEELUP &&
		row > 0)
	{
		if (action->getAbsoluteXMouse() >= _lstSoldiers->getArrowsLeftEdge() &&
			action->getAbsoluteXMouse() <= _lstSoldiers->getArrowsRightEdge())
		{
			moveSoldierUp(action, row);
		}
	}
	else if (action->getDetails()->button.button == SDL_BUTTON_WHEELDOWN &&
			 0 < numSoldiers && INT_MAX >= numSoldiers && row < numSoldiers - 1)
	{
		if (action->getAbsoluteXMouse() >= _lstSoldiers->getArrowsLeftEdge() &&
			action->getAbsoluteXMouse() <= _lstSoldiers->getArrowsRightEdge())
		{
			moveSoldierDown(action, row);
		}
	}
}

/**
 * De-assign all soldiers from all craft located in the base (i.e. not out on a mission).
 * @param action Pointer to an action.
 */
void CraftSoldiersState::btnDeassignAllSoldiersClick(Action *action)
{
	int row = 0;
	for (auto* soldier : *_base->getSoldiers())
	{
		auto color = _lstSoldiers->getColor();
		if (soldier->getCraft() && soldier->getCraft()->getStatus() != "STR_OUT")
		{
			soldier->setCraftAndMoveEquipment(0, _base, _game->getSavedGame()->getMonthsPassed() == -1);
			_lstSoldiers->setCellText(row, 2, tr("STR_NONE_UC"));
		}
		else if (soldier->getCraft() && soldier->getCraft()->getStatus() == "STR_OUT")
		{
			color = _otherCraftColor;
		}
		setListRowColor(*_lstSoldiers, row, color, *soldier);

		row++;
	}

	Craft *c = _base->getCrafts()->at(_craft);
	_txtAvailable->setText(tr("STR_SPACE_AVAILABLE").arg(c->getSpaceAvailable()));
	_txtUsed->setText(tr("STR_SPACE_USED").arg(c->getSpaceUsed()));
	fitRefresh();
	missionRefresh();
}

/**
 * De-assign all soldiers from the current craft.
 * @param action Pointer to an action.
 */
void CraftSoldiersState::btnDeassignCraftSoldiersClick(Action *action)
{
	Craft *c = _base->getCrafts()->at(_craft);
	int row = 0;
	for (auto* soldier : *_base->getSoldiers())
	{
		if (soldier->getCraft() == c)
		{
			soldier->setCraftAndMoveEquipment(0, _base, _game->getSavedGame()->getMonthsPassed() == -1);
			_lstSoldiers->setCellText(row, 2, tr("STR_NONE_UC"));
			setListRowColor(*_lstSoldiers, row, _lstSoldiers->getColor(), *soldier);
		}
		row++;
	}

	_txtAvailable->setText(tr("STR_SPACE_AVAILABLE").arg(c->getSpaceAvailable()));
	_txtUsed->setText(tr("STR_SPACE_USED").arg(c->getSpaceUsed()));
	fitRefresh();
	missionRefresh();
}

/**
 * OXCE-HD (oxceHdCraftMission): the detected targets, the sources and the filters of the UFO tracker (UfoTrackerState):
 * mission sites, UFOs, alien bases (in the order of the tracker) - the UFOs only as they stand on the ground or have crashed (a flying one is not landed on;
 * the landing check is made for those two). Item 0 of the box (none) is already in the names.
 */
void CraftSoldiersState::buildMissionTargets(std::vector<std::string> &names)
{
	SavedGame *save = _game->getSavedGame();
	for (const auto *site : *save->getMissionSites())
	{
		if (site->getDetected())
		{
			_missionTargets.push_back(site);
			names.push_back(site->getName(_game->getLanguage()));
		}
	}
	// the order of the UFO tracker (T): sites, then UFOs and crashes, then alien bases (XP-000376)
	for (const auto *ufo : *save->getUfos())
	{
		if (ufo->getDetected() && (ufo->getStatus() == Ufo::LANDED || ufo->getStatus() == Ufo::CRASHED))
		{
			_missionTargets.push_back(ufo);
			names.push_back(ufo->getName(_game->getLanguage()));
		}
	}
	for (const auto *ab : *save->getAlienBases())
	{
		if (ab->isDiscovered())
		{
			_missionTargets.push_back(ab);
			names.push_back(ab->getName(_game->getLanguage()));
		}
	}
}

/**
 * OXCE-HD (oxceHdCraftMission): another target chosen (or none): the condition is looked up, the rows repainted.
 * Nothing is stored in the save, the order of the soldiers is not touched.
 */
void CraftSoldiersState::cbxMissionChange(Action *)
{
	const size_t sel = _cbxMission->getSelected();
	_missionActive = sel >= 1 && sel <= _missionTargets.size();
	_missionRule = _missionActive ? findStartingCondition(_game->getMod(), _missionTargets[sel - 1]) : nullptr;
	if (!_missionActive)
	{
		_txtMissionInfo->setText("");
	}
	initList(_lstSoldiers->getScroll()); // all the rows as the base paints them, then missionRefresh()
}

/**
 * OXCE-HD (oxceHdCraftMission): the colour of a row by the craft of the soldier, as initList sets it.
 */
Uint8 CraftSoldiersState::rowBaseColor(const Soldier *s, const Craft *c) const
{
	if (s->getCraft() == c)
	{
		return _lstSoldiers->getSecondaryColor();
	}
	if (s->getCraft() != 0)
	{
		return _otherCraftColor;
	}
	return _lstSoldiers->getColor();
}

/**
 * OXCE-HD (oxceHdCraftMission): with a target chosen, the name of every soldier who can fly there is green, and the line
 * under the list says how many, or what the craft lacks. Called after every fitRefresh(). Display only: the green name is a
 * soldier with full health, not on a craft that is out, whose row is not grey (does not fit), and whom the starting condition
 * of the target lets in (the craft and the soldier type - the checks of the landing). The rest keep their colours.
 * Nothing chosen - nothing is done.
 */
void CraftSoldiersState::missionRefresh()
{
	if (!_cbxMission || !_missionActive)
	{
		return;
	}
	Craft *c = _base->getCrafts()->at(_craft);
	const Uint8 green = Palette::blockOffset(3) + 2;
	size_t row = 0, fit = 0;
	for (const auto *soldier : *_base->getSoldiers())
	{
		const bool grey = row < _fitGrey.size() && _fitGrey[row];
		if (!grey)
		{
			setListRowColor(*_lstSoldiers, row, rowBaseColor(soldier, c), *soldier);
			const bool away = soldier->getCraft() && soldier->getCraft() != c && soldier->getCraft()->getStatus() == "STR_OUT";
			if (soldier->hasFullHealth() && !away && missionSoldierFit(_missionRule, c, soldier) == MF_OK)
			{
				_lstSoldiers->setCellColor(row, 0, green);
				++fit;
			}
		}
		++row;
	}
	const MissionCraftFit cf = missionCraftFit(_missionRule, c);
	if (!cf.craftOk)
	{
		_missionLine = tr("STR_CRAFT_MISSION_NO_CRAFT");
	}
	else if (cf.needCommander)
	{
		_missionLine = tr("STR_CRAFT_MISSION_NEED_COMMANDER");
	}
	else if (cf.needItems)
	{
		_missionLine = tr("STR_CRAFT_MISSION_NEED_ITEMS");
	}
	else
	{
		_missionLine = tr("STR_CRAFT_MISSION_FIT_COUNT").arg(fit).arg(_base->getSoldiers()->size());
	}
	_txtMissionInfo->setText(_missionLine);
}

/**
 * OXCE-HD (oxceHdCraftMission): the mouse over a row - the line says why this soldier does or does not fit the target.
 */
void CraftSoldiersState::lstSoldiersMouseOver(Action *)
{
	if (!_missionActive)
	{
		return;
	}
	const size_t row = _lstSoldiers->getSelectedRow();
	if (row >= _base->getSoldiers()->size())
	{
		return;
	}
	const Soldier *s = _base->getSoldiers()->at(row);
	const Craft *c = _base->getCrafts()->at(_craft);
	switch (missionSoldierFit(_missionRule, c, s))
	{
	case MF_CRAFT:
		_txtMissionInfo->setText(tr("STR_CRAFT_MISSION_NO_CRAFT"));
		break;
	case MF_SOLDIER_TYPE:
		_txtMissionInfo->setText(tr("STR_CRAFT_MISSION_NO_TYPE"));
		break;
	default:
		if (!s->hasFullHealth() || (s->getCraft() && s->getCraft() != c && s->getCraft()->getStatus() == "STR_OUT"))
		{
			_txtMissionInfo->setText(tr("STR_CRAFT_MISSION_UNAVAILABLE")); // wounded or on a craft that is out: not green
		}
		else
		{
			_txtMissionInfo->setText(tr(missionArmorWillChange(_missionRule, s) ? "STR_CRAFT_MISSION_FITS_ARMOR" : "STR_CRAFT_MISSION_FITS"));
		}
		break;
	}
}

/**
 * OXCE-HD (oxceHdCraftMission): the mouse left the list - the line is the summary again.
 */
void CraftSoldiersState::lstSoldiersMouseOut(Action *)
{
	if (_missionActive)
	{
		_txtMissionInfo->setText(_missionLine);
	}
}
}
