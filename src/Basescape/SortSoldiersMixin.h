#pragma once
#include <vector>
#include <string>
#include <functional>
#include "../Engine/State.h"
#include "SoldierSortUtil.h"
#include "../Engine/Options.h"
#include "../Engine/SurfaceSet.h"
#include "../Interface/ComboBox.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Mod/RuleSoldier.h"

namespace OpenXcom
{
	template<typename StateType = State>
	class SortSoldiersMixin : public StateType
	{
	public:
		SortSoldiersMixin(Base* base)
			: _base(base), _sortFirst(-1), _sortFirstReversed(false)
		{}

	protected:
		/// OXCE-HD: how far the soldier lists' rank column (and its header) stands right of where OXCE has it,
		/// near the arrows, with the rank badge in front of it
		static const int RANK_SHIFT = 12;

		void FillSorters(std::vector<SortFunctor*>& sorters, ComboBox& sortingCombobox, ActionHandler comboBoxChangeHandler)
		{
			std::map<Options::QOL::DefaultSoldiersSorter, size_t> sortersToIndexes;
			std::vector<std::string> sortingNames;

			sortingNames.push_back(State::tr("STR_ORIGINAL_ORDER"));
			sorters.push_back(nullptr);
			sortersToIndexes[Options::QOL::DefaultSoldiersSorter::Original] = sorters.size() - 1;
			
#define PUSH_IN(strId, functor) \
		sortingNames.push_back(State::tr(strId)); \
		sorters.push_back(new SortFunctor(State::_game, functor));

			PUSH_IN("STR_ID", idStat);
			PUSH_IN("STR_NAME_UC", nameStat);
			PUSH_IN("STR_CRAFT", craftIdStat);
			PUSH_IN("STR_SOLDIER_TYPE", typeStat);
			PUSH_IN("STR_RANK", rankStat);
			PUSH_IN("STR_IDLE_DAYS", idleDaysStat);
			PUSH_IN("STR_MISSIONS2", missionsStat);
			PUSH_IN("STR_KILLS2", killsStat);
			sortersToIndexes[Options::QOL::DefaultSoldiersSorter::KillCount] = sorters.size() - 1;

			PUSH_IN("STR_WOUND_RECOVERY2", woundRecoveryStat);
			if (State::_game->getMod()->isManaFeatureEnabled() && !State::_game->getMod()->getReplenishManaAfterMission())
			{
				PUSH_IN("STR_MANA_CURRENT", currentManaStat);
				sortersToIndexes[Options::QOL::DefaultSoldiersSorter::CurrentMana] = sorters.size() - 1;

				PUSH_IN("STR_MANA_MISSING", manaMissingStat);
			}

			PUSH_IN("STR_TIME_UNITS", tuStat);
			PUSH_IN("STR_STAMINA", staminaStat);
			PUSH_IN("STR_HEALTH", healthStat);
			PUSH_IN("STR_BRAVERY", braveryStat);
			PUSH_IN("STR_REACTIONS", reactionsStat);
			PUSH_IN("STR_FIRING_ACCURACY", firingStat);
			sortersToIndexes[Options::QOL::DefaultSoldiersSorter::FiringAccuracy] = sorters.size() - 1;

			PUSH_IN("STR_THROWING_ACCURACY", throwingStat);
			PUSH_IN("STR_MELEE_ACCURACY", meleeStat);
			PUSH_IN("STR_STRENGTH", strengthStat);
			if (State::_game->getMod()->isManaFeatureEnabled())
			{
				// "unlock" is checked later
				PUSH_IN("STR_MANA_POOL", manaStat);
			}
			PUSH_IN("STR_PSIONIC_STRENGTH", psiStrengthStat);
			PUSH_IN("STR_PSIONIC_SKILL", psiSkillStat);

#undef PUSH_IN

			_sortNames = sortingNames;
			const auto defaultSorter = static_cast<Options::QOL::DefaultSoldiersSorter>(Options::QOL::defaultSoldiersSorter);
			auto it = sortersToIndexes.find(defaultSorter);

			size_t index = 0;
			if (it != sortersToIndexes.end())
				index = it->second;

			DoSort(index, sorters[index]);

			sortingCombobox.setOptions(sortingNames);
			sortingCombobox.setSelected(0);
			sortingCombobox.onChange(comboBoxChangeHandler);
			sortingCombobox.setText(State::tr("STR_SORT_BY"));
		}

		void DoSort(int sortIndex, const SortFunctor* sortFunctor, int secondIndex = -1, const SortFunctor* second = nullptr)
		{
			// OXCE-HD: no sorter (original order) still gets the groups below
			if (sortFunctor && sortFunctor->_getStatFn && second && second->_getStatFn)
			{
				// OXCE-HD: two criteria (SortSecond): the second one first, then the first one over it - the
				// sort is stable, so among soldiers equal by the first the second one's order stays. Each keeps
				// the direction it was picked with (Shift)
				SortBy(secondIndex, second, State::_game->isShiftPressed());
				SortBy(sortIndex, sortFunctor, _sortFirstReversed);
			}
			else if (sortFunctor && sortFunctor->_getStatFn)
			{
				_sortFirst = sortIndex;
				_sortFirstReversed = State::_game->isShiftPressed();
				if (sortIndex == 2)
				{
					std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(),
									 [](const Soldier* a, const Soldier* b)
									 {
										 return Unicode::naturalCompare(a->getName(), b->getName());
									 });
				}
				else if (sortIndex == 3)
				{
					std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(), craftLess);
				}
				else
				{
					std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(), *sortFunctor);
				}

				if (State::_game->isShiftPressed())
				{
					std::reverse(_base->getSoldiers()->begin(), _base->getSoldiers()->end());
				}
			}
			else
			{
				_sortFirst = -1;
			}

			// OXCE-HD: the groups (Options::oxceBaseSoldierGroupBy) over the order just made: the sort is
			// stable, so inside a group the soldiers stay in the chosen order (reversed with Shift too).
			// Sorting by the grouping criterion itself keeps its own direction
			const int groupBy = Options::oxceBaseSoldierGroupBy;
			if (groupBy == 1 && sortIndex != 4)
			{
				// by race, and inside a race by the chosen criterion alone. The race is the set of pictures
				// (flagOffset): in X-Piratez a race has several types (the synths with dolls and killbots),
				// and by the type the list went race - type - criterion. In vanilla the offset is 0 for all
				std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(),
								 [](const Soldier* a, const Soldier* b)
								 {
									 return a->getRules()->getFlagOffset() < b->getRules()->getFlagOffset();
								 });
			}
			else if (groupBy == 2 && sortIndex != 5)
			{
				std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(),
								 [](const Soldier* a, const Soldier* b)
								 {
									 return a->getRank() > b->getRank();
								 });
			}
			else if (groupBy == 3 && sortIndex != 3)
			{
				std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(), craftLess);
			}
		}

		/// OXCE-HD: one stable sort by the criterion; reversed turns the criterion around, soldiers equal by it
		/// keep their order (unlike reversing the whole list, which would turn a second criterion around too).
		void SortBy(int sortIndex, const SortFunctor* sortFunctor, bool reversed)
		{
			std::function<bool(Soldier*, Soldier*)> less;
			if (sortIndex == 2)
			{
				less = [](Soldier* a, Soldier* b) { return Unicode::naturalCompare(a->getName(), b->getName()); };
			}
			else if (sortIndex == 3)
			{
				less = craftLess;
			}
			else
			{
				less = *sortFunctor;
			}
			if (reversed)
			{
				std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(),
								 [&less](Soldier* a, Soldier* b) { return less(b, a); });
			}
			else
			{
				std::stable_sort(_base->getSoldiers()->begin(), _base->getSoldiers()->end(), less);
			}
		}

		/// OXCE-HD: Ctrl + a criterion in the sort list while the list is sorted by another one - the new one
		/// becomes the second criterion, inside the first (Type, then Firing accuracy), and the list button
		/// names both. False when there is no first criterion (original order, hand-moved list, the same one):
		/// then Ctrl keeps its OXCE meaning - show the column without sorting.
		bool SortSecond(size_t selIdx, const std::vector<SortFunctor*>& sorters, ComboBox& sortingCombobox)
		{
			const int first = _sortFirst;
			if (first <= 0 || (size_t)first >= sorters.size() || !sorters[first] || (int)selIdx == first ||
				selIdx >= sorters.size() || !sorters[selIdx] || (size_t)first >= _sortNames.size())
			{
				return false;
			}
			DoSort(first, sorters[first], selIdx, sorters[selIdx]);
			sortingCombobox.setText(_sortNames[first] + " > " + _sortNames[selIdx]);
			return true;
		}

		/// OXCE-HD: the list was reordered by hand - Ctrl has no first criterion to add to.
		void ForgetSort()
		{
			_sortFirst = -1;
		}

		/// The craft order: soldiers on a craft first, by the craft's type, then by its number.
		static bool craftLess(const Soldier* a, const Soldier* b)
		{
			if (a->getCraft())
			{
				if (b->getCraft())
				{
					if (a->getCraft()->getRules() == b->getCraft()->getRules())
					{
						return a->getCraft()->getId() < b->getCraft()->getId();
					}
					else
					{
						return a->getCraft()->getRules() < b->getCraft()->getRules();
					}
				}
				else
				{
					return true; // a < b
				}
			}

			return false; // b > a
		}

		/// OXCE-HD: the soldier's picture from the soldier info screen (soldierFlag in SoldierSortUtil).
		Surface *SoldierFlag(const Soldier *soldier) const
		{
			return soldierFlag(State::_game->getMod(), soldier);
		}

		void ChangeDynSorter(getStatFn_t& getter)
		{
			const auto defaultSorter = static_cast<Options::QOL::DefaultSoldiersSorter>(Options::QOL::defaultSoldiersSorter);
			if (defaultSorter == Options::QOL::DefaultSoldiersSorter::Original)
				getter = nullptr;
			else if (defaultSorter == Options::QOL::DefaultSoldiersSorter::KillCount)
				getter = killsStat;
			else if (defaultSorter == Options::QOL::DefaultSoldiersSorter::FiringAccuracy)
				getter = firingStat;
			else if (defaultSorter == Options::QOL::DefaultSoldiersSorter::CurrentMana)
				getter = currentManaStat;
		}

	protected:
		Base* _base;
		/// OXCE-HD: the first criterion (-1 - none) and its direction, and the list's names, for SortSecond
		int _sortFirst;
		bool _sortFirstReversed;
		std::vector<std::string> _sortNames;
	};

}
