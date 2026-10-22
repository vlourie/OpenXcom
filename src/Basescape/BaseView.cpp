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
#include "BaseView.h"
#include <algorithm>
#include <sstream>
#include <cmath>
#include "../Engine/SurfaceSet.h"
#include "../Engine/Action.h"
#include "../Savegame/Base.h"
#include "../Savegame/BaseFacility.h"
#include "../Mod/RuleBaseFacility.h"
#include "../Savegame/Craft.h"
#include "../Interface/Text.h"
#include "../Engine/Timer.h"
#include "../Engine/Options.h"
#include <climits>
#include <cstdlib>
#include <map>
#include "../Mod/Texture.h"
#include "../Engine/HdBase.h"
#include "../Engine/HdBaseLife.h"
#include "../Engine/HdCraftLights.h"
#include "../Engine/HdSmooth.h"
#include "../Engine/HdUi.h"
#include "../Engine/HdUiArt.h"
#include "../Engine/Screen.h"
#include "../Savegame/GameTime.h"

namespace
{

/// The base screen draws its HD pictures when the option is on and the screen has a world layer of 2x or more.
bool hdBaseActive()
{
	OpenXcom::Screen *screen = OpenXcom::Screen::current();
	return OpenXcom::Options::oxceHdPictures && screen && screen->isLayered() && screen->getWorldScale() >= 2;
}

/// The living base (HdBaseScene): the pack lights its pictures, so the whole view - the rock of every
/// cell too - lies in the world layer under that light. Comes with the HD pictures (read once per run).
bool hdScenes()
{
	static const bool pictures = OpenXcom::Options::oxceHdBaseAnim;
	return pictures && hdBaseActive() && OpenXcom::HdBase::scenes();
}

/// A classic BASEBITS frame k times bigger (xBRZ, or nearest with the nearest HD interface), made once.
const OpenXcom::HdFrame *classicHd(OpenXcom::SurfaceSet *texture, int index, int k, const SDL_Color *colors)
{
	static std::map<std::pair<int, int>, OpenXcom::HdFrame> cache;
	static const SDL_Color *cachedColors = nullptr;
	static OpenXcom::SurfaceSet *cachedTexture = nullptr;
	if (colors != cachedColors || texture != cachedTexture)
	{
		cache.clear();
		cachedColors = colors;
		cachedTexture = texture;
	}
	const bool smooth = OpenXcom::HdUi::mode() != 1;
	const std::pair<int, int> key(index, k * 2 + (smooth ? 1 : 0));
	auto it = cache.find(key);
	if (it != cache.end())
	{
		return it->second.empty() ? nullptr : &it->second;
	}
	OpenXcom::HdFrame &out = cache[key];
	OpenXcom::Surface *frame = texture ? texture->getFrame(index) : nullptr;
	if (!frame || !colors)
	{
		return nullptr;
	}
	const Uint8 *pixels = (const Uint8*)frame->getBuffer();
	const int w = frame->getWidth(), h = frame->getHeight(), pitch = frame->getPitch();
	if (smooth && OpenXcom::HdSmooth::smoothPalette(pixels, w, h, pitch, colors, k, out))
	{
		return &out;
	}
	out.width = w * k;
	out.height = h * k;
	out.pixels.assign((size_t)out.width * out.height, 0u);
	for (int y = 0; y < out.height; ++y)
	{
		for (int x = 0; x < out.width; ++x)
		{
			const Uint8 i = pixels[(size_t)(y / k) * pitch + x / k];
			if (i)
			{
				out.pixels[(size_t)y * out.width + x] = 0xFF000000u | ((Uint32)colors[i].r << 16) | ((Uint32)colors[i].g << 8) | colors[i].b;
			}
		}
	}
	out.buildSpans();
	return &out;
}

}

namespace OpenXcom
{

/**
 * Sets up a base view with the specified size and position.
 * @param width Width in pixels.
 * @param height Height in pixels.
 * @param x X position in pixels.
 * @param y Y position in pixels.
 */
BaseView::BaseView(int width, int height, int x, int y) : InteractiveSurface(width, height, x, y),
	_base(0), _texture(0), _selFacility(0), _big(0), _small(0), _lang(0),
	_gridX(0), _gridY(0), _selSizeX(0), _selSizeY(0),
	_selector(0), _blink(true),
	_redColor(0), _yellowColor(0), _greenColor(0), _highContrast(true),
	_cellColor(0), _selectorColor(0), _animPhase(0), _animTick(0), _hdNextChange(0), _hdNumbersKept(false)
{
	// Clear grid
	for (int i = 0; i < BASE_SIZE; ++i)
	{
		for (int j = 0; j < BASE_SIZE; ++j)
		{
			_facilities[i][j] = 0;
		}
	}

	_timer = new Timer(100);
	_timer->onTimer((SurfaceHandler)&BaseView::blink);
	_timer->start();
}

/**
 * Deletes contents.
 */
BaseView::~BaseView()
{
	delete _selector;
	delete _timer;
	for (auto* text : _hdNumbers)
	{
		delete text;
	}
}

/**
 * Is the HD interface going to draw the numbers over the facilities with its own fonts? Then they
 * are kept out of the classic layer: it reaches the HD layer through the upscaler, which smears
 * letters (R-022).
 */
bool BaseView::hdNumbers() const
{
	return HdUi::skin() && HdUi::instance().hasFonts();
}

/**
 * A number over a facility, laid out: blitted into the classic layer and dropped, or kept for
 * the HD interface to draw with its own fonts (blit).
 */
void BaseView::keepNumber(Text *text)
{
	if (_hdNumbersKept)
	{
		text->draw();   // lays the string out; hdDrawAt reads that layout
		_hdNumbers.push_back(text);
		return;
	}
	text->blit(this->getSurface());
	delete text;
}

/**
 * Changes the various resources needed for text rendering.
 * The different fonts need to be passed in advance since the
 * text size can change mid-text, and the language affects
 * how the text is rendered.
 * @param big Pointer to large-size font.
 * @param small Pointer to small-size font.
 * @param lang Pointer to current language.
 */
void BaseView::initText(Font *big, Font *small, Language *lang)
{
	_big = big;
	_small = small;
	_lang = lang;
}

/**
 * Changes the current base to display and
 * initializes the internal base grid.
 * @param base Pointer to base to display.
 */
void BaseView::setBase(Base *base)
{
	_base = base;
	_selFacility = 0;

	// Clear grid
	for (int x = 0; x < BASE_SIZE; ++x)
	{
		for (int y = 0; y < BASE_SIZE; ++y)
		{
			_facilities[x][y] = 0;
		}
	}

	// Fill grid with base facilities
	for (auto* fac : *_base->getFacilities())
	{
		for (int y = fac->getY(); y < fac->getY() + fac->getRules()->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + fac->getRules()->getSizeX(); ++x)
			{
				_facilities[x][y] = fac;
			}
		}
	}

	_redraw = true;
}

/**
 * Changes the texture to use for drawing
 * the various base elements.
 * @param texture Pointer to SurfaceSet to use.
 */
void BaseView::setTexture(SurfaceSet *texture)
{
	_texture = texture;
}

/**
 * Returns the facility the mouse is currently over.
 * @return Pointer to base facility (0 if none).
 */
BaseFacility *BaseView::getSelectedFacility() const
{
	return _selFacility;
}

/**
 * Prevents any mouseover bugs on dismantling base facilities before setBase has had time to update the base.
 */
void BaseView::resetSelectedFacility()
{
	_facilities[_selFacility->getX()][_selFacility->getY()] = 0;
	_selFacility = 0;
}


/**
 * Returns the X position of the grid square
 * the mouse is currently over.
 * @return X position on the grid.
 */
int BaseView::getGridX() const
{
	return _gridX;
}

/**
 * Returns the Y position of the grid square
 * the mouse is currently over.
 * @return Y position on the grid.
 */
int BaseView::getGridY() const
{
	return _gridY;
}

/**
 * If enabled, the base view will respond to player input,
 * highlighting the selected facility.
 * @param size Facility length (0 disables it).
 */
void BaseView::setSelectable(int sizeX, int sizeY)
{
	_selSizeX = sizeX;
	_selSizeY = sizeY;
	if (_selSizeX > 0 && _selSizeY > 0)
	{
		_selector = new Surface(sizeX * GRID_SIZE, sizeY * GRID_SIZE, _x, _y);
		_selector->setPalette(getPalette());
		SDL_Rect r;
		r.w = _selector->getWidth();
		r.h = _selector->getHeight();
		r.x = 0;
		r.y = 0;
		_selector->drawRect(&r, _selectorColor);
		r.w -= 2;
		r.h -= 2;
		r.x++;
		r.y++;
		_selector->drawRect(&r, 0);
		_selector->setVisible(false);
	}
	else
	{
		delete _selector;
	}
}

/**
 * Returns if a certain facility can be successfully
 * placed on the currently selected square.
 * @param rule Facility type.
 * @param facilityBeingMoved Selected facility.
 * @param isStartFacility Is this a start facility?
 * @return 0 if placeable, otherwise error code for why we couldn't place it
 * 1: not connected to lift or on top of another facility (standard OXC behavior)
 * 2: trying to upgrade over existing facility, but it's in use
 * 3: trying to upgrade over existing facility, but it's already being upgraded
 * 4: trying to upgrade over existing facility, but size/placement mismatch
 * 5: trying to upgrade over existing facility, but ruleset of new facility requires a specific existing facility
 * 6: trying to upgrade over existing facility, but ruleset disallows it
 * 7: trying to upgrade over existing facility, but all buildings next to it are under construction and build queue is off
 */
BasePlacementErrors BaseView::getPlacementError(const RuleBaseFacility *rule, BaseFacility *facilityBeingMoved, bool isStartFacility) const
{
	// We'll need to know for the final check if we're upgrading an existing facility
	bool buildingOverExisting = false;

	// Area where we want to place a new building
	const BaseAreaSubset placementArea = BaseAreaSubset(rule->getSizeX(), rule->getSizeY()).offset(_gridX, _gridY);
	// Whole base
	const BaseAreaSubset baseArea = BaseAreaSubset(BASE_SIZE, BASE_SIZE);

	// Check if the facility fits inside the base boundaries
	if (BaseAreaSubset::intersection(placementArea, baseArea) != placementArea)
	{
		return BPE_NotConnected;
	}

	// Check usage of facilites in the area that will be replaced by a new building
	if (facilityBeingMoved == nullptr)
	{
		BasePlacementErrors areaUseError = _base->isAreaInUse(placementArea, rule);
		if (areaUseError != BPE_None)
		{
			return areaUseError;
		}
	}

	// Check if all squares are occupied already (for facilities that can be built only as upgrades)
	if (rule->isUpgradeOnly())
	{
		for (int y = placementArea.beg_y; y < placementArea.end_y; ++y)
		{
			for (int x = placementArea.beg_x; x < placementArea.end_x; ++x)
			{
				BaseFacility* facility = _facilities[x][y];
				if (!facility)
				{
					return BPE_UpgradeOnly;
				}
			}
		}
	}

	// Check if square isn't occupied
	for (int y = placementArea.beg_y; y < placementArea.end_y; ++y)
	{
		for (int x = placementArea.beg_x; x < placementArea.end_x; ++x)
		{
			BaseFacility* facility = _facilities[x][y];
			if (facility != 0)
			{
				if (isStartFacility)
				{
					return BPE_NotConnected;
				}
				// when moving an existing facility, it should not block itself
				if (facilityBeingMoved == nullptr)
				{
					// Further check to see if the facility already there can be built over and we're not removing an important base function
					BasePlacementErrors canBuildOverError = rule->getCanBuildOverOtherFacility(facility->getRules());
					if (canBuildOverError != BPE_None)
					{
						return canBuildOverError;
					}

					// Make sure the facility we're building over is entirely within the size of the one we're checking
					const BaseAreaSubset removedArea = facility->getPlacement();
					if (BaseAreaSubset::intersection(placementArea, removedArea) != removedArea)
					{
						return BPE_UpgradeSizeMismatch;
					}

					// Make sure this facility is not already being upgraded
					if (facility->getIfHadPreviousFacility() && facility->getBuildTime() != 0)
					{
						return BPE_Upgrading;
					}

					buildingOverExisting = true;
				}
				else if (facility != facilityBeingMoved)
				{
					return BPE_NotConnected;
				}
			}
		}
	}

	bool bq=Options::allowBuildingQueue;
	bool hasConnectingFacility = false;

	// Check for another facility to connect to
	for (int i = 0; i < rule->getSizeX(); ++i)
	{
		// top
		if (_gridY > 0 && _facilities[_gridX + i][_gridY - 1] != 0)
		{
			hasConnectingFacility = true;
			if ((!buildingOverExisting && bq) || _facilities[_gridX + i][_gridY - 1]->isBuiltOrHadPreviousFacility())
				return BPE_None;
		}
		// bottom
		if (_gridY + rule->getSizeY() < BASE_SIZE && _facilities[_gridX + i][_gridY + rule->getSizeY()] != 0)
		{
			hasConnectingFacility = true;
			if ((!buildingOverExisting && bq) || _facilities[_gridX + i][_gridY + rule->getSizeY()]->isBuiltOrHadPreviousFacility())
				return BPE_None;
		}
	}
	for (int i = 0; i < rule->getSizeY(); ++i)
	{
		// left
		if (_gridX > 0 && _facilities[_gridX - 1][_gridY + i] != 0)
		{
			hasConnectingFacility = true;
			if ((!buildingOverExisting && bq) || _facilities[_gridX - 1][_gridY + i]->isBuiltOrHadPreviousFacility())
				return BPE_None;
		}
		// right
		if (_gridX + rule->getSizeX() < BASE_SIZE && _facilities[_gridX + rule->getSizeX()][_gridY + i] != 0)
		{
			hasConnectingFacility = true;
			if ((!buildingOverExisting && bq) || _facilities[_gridX + rule->getSizeX()][_gridY + i]->isBuiltOrHadPreviousFacility())
				return BPE_None;
		}
	}

	// We can assume if we've reached this point that none of the connecting facilities are finished!
	if (hasConnectingFacility && (!bq || buildingOverExisting))
		return BPE_Queue;

	return BPE_NotConnected;
}

/**
 * Returns if the placed facility is placed in queue or not.
 * @param rule Facility type.
 * @return True if queued, False otherwise.
 */
bool BaseView::isQueuedBuilding(const RuleBaseFacility *rule) const
{
	for (int i = 0; i < rule->getSizeX(); ++i)
	{
		if ((_gridY > 0 && _facilities[_gridX + i][_gridY - 1] != 0 && _facilities[_gridX + i][_gridY - 1]->isBuiltOrHadPreviousFacility()) ||
			(_gridY + rule->getSizeY() < BASE_SIZE && _facilities[_gridX + i][_gridY + rule->getSizeY()] != 0 && _facilities[_gridX + i][_gridY + rule->getSizeY()]->isBuiltOrHadPreviousFacility()))
		{
			return false;
		}
	}
	for (int i = 0; i < rule->getSizeY(); ++i)
	{
		if ((_gridX > 0 && _facilities[_gridX - 1][_gridY + i] != 0 && _facilities[_gridX - 1][_gridY + i]->isBuiltOrHadPreviousFacility()) ||
			(_gridX + rule->getSizeX() < BASE_SIZE && _facilities[_gridX + rule->getSizeX()][_gridY + i] != 0 && _facilities[_gridX + rule->getSizeX()][_gridY + i]->isBuiltOrHadPreviousFacility()))
		{
			return false;
		}
	}
	return true;
}

/**
 * ReCalculates the remaining build-time of all queued buildings.
 */
void BaseView::reCalcQueuedBuildings()
{
	setBase(_base);
	std::vector<BaseFacility*> facilities;
	for (auto* fac : *_base->getFacilities())
	{
		if (fac->getAdjustedBuildTime() > 0)
		{
			// Set all queued buildings to infinite.
			if (fac->getAdjustedBuildTime() > fac->getRules()->getBuildTime())
			{
				fac->setBuildTime(INT_MAX);
			}
			facilities.push_back(fac);
		}
	}

	// Applying a simple Dijkstra Algorithm
	while (!facilities.empty())
	{
		auto min = facilities.begin();
		for (auto it = facilities.begin(); it != facilities.end(); ++it)
		{
			if ((*it)->getAdjustedBuildTime() < (*min)->getAdjustedBuildTime())
			{
				min = it;
			}
		}
		BaseFacility* facility=(*min);
		facilities.erase(min);
		const RuleBaseFacility *rule=facility->getRules();
		int x=facility->getX(), y=facility->getY();
		for (int i = 0; i < rule->getSizeX(); ++i)
		{
			if (y > 0) updateNeighborFacilityBuildTime(facility,_facilities[x + i][y - 1]);
			if (y + rule->getSizeY() < BASE_SIZE) updateNeighborFacilityBuildTime(facility,_facilities[x + i][y + rule->getSizeY()]);
		}
		for (int i = 0; i < rule->getSizeY(); ++i)
		{
			if (x > 0) updateNeighborFacilityBuildTime(facility, _facilities[x - 1][y + i]);
			if (x + rule->getSizeX() < BASE_SIZE) updateNeighborFacilityBuildTime(facility, _facilities[x + rule->getSizeX()][y + i]);
		}
	}
}

/**
 * Updates the neighborFacility's build time. This is for internal use only (reCalcQueuedBuildings()).
 * @param facility Pointer to a base facility.
 * @param neighbor Pointer to a neighboring base facility.
 */
void BaseView::updateNeighborFacilityBuildTime(BaseFacility* facility, BaseFacility* neighbor)
{
	if (facility != 0 && neighbor != 0
	&& neighbor->getAdjustedBuildTime() > neighbor->getRules()->getBuildTime()
	&& facility->getAdjustedBuildTime() + neighbor->getRules()->getBuildTime() < neighbor->getAdjustedBuildTime())
		neighbor->setBuildTime(facility->getAdjustedBuildTime() + neighbor->getRules()->getBuildTime());
}

/**
 * The frame whose HD picture stands for a tile of the facility: its graphic, or its shape
 * when the graphic is not drawn (a big facility without spriteEnabled keeps it all in the shape).
 */
int BaseView::hdTileIndex(const BaseFacility *facility, int num)
{
	const RuleBaseFacility *rules = facility->getRules();
	return (rules->getSpriteEnabled() ? rules->getSpriteFacility() : rules->getSpriteShape()) + num;
}

/**
 * A facility with an HD picture of every one of its tiles is not drawn on the classic
 * layer at all - neither its shape nor its graphic - so that the picture in the world
 * layer under it is what is seen (see BaseView::blit).
 * The pictures come with the facility animations: with them off the base is drawn from the
 * classic sprites, as before the pictures were made. The option is read once per run, so it
 * applies after a restart.
 * @param facility The facility.
 * @return True when the mod has a picture of every tile of the facility.
 */
bool BaseView::isHdFacility(const BaseFacility *facility) const
{
	static const bool pictures = Options::oxceHdBaseAnim;
	if (!pictures || !facility || facility->getBuildTime() != 0)
	{
		return false;
	}
	const int tiles = facility->getRules()->getSizeX() * facility->getRules()->getSizeY();
	for (int num = 0; num < tiles; ++num)
	{
		if (HdBase::phases(hdTileIndex(facility, num)) == 0)
		{
			return false;
		}
	}
	return true;
}

/**
 * A facility being built in the living base (HdBaseScene::drawBuilding): with the lit pictures, one
 * whose tiles all have a picture leaves the classic layer like a built one; its number of days stays.
 * @param facility The facility.
 * @return True when it is drawn in the world layer as a blueprint growing into its picture.
 */
bool BaseView::isHdBuilding(const BaseFacility *facility) const
{
	if (!facility || facility->getBuildTime() == 0 || !hdScenes())
	{
		return false;
	}
	const int tiles = facility->getRules()->getSizeX() * facility->getRules()->getSizeY();
	for (int num = 0; num < tiles; ++num)
	{
		if (HdBase::phases(hdTileIndex(facility, num)) == 0)
		{
			return false;
		}
	}
	return true;
}

/**
 * Draws the HD pictures of the facilities into the true-color world layer, where
 * the holes left in the classic layer (see draw) show them.
 */
void BaseView::drawHd()
{
	if (!_visible || _hidden || !_base || !_texture || !hdBaseActive())
	{
		return;
	}
	Screen *screen = Screen::current();
	SDL_Surface *world = screen ? screen->getWorldSurface() : 0;
	const int k = screen ? screen->getWorldScale() : 1;
	if (!world || k < 2)
	{
		return;
	}
	const int rock = _base->getGlobeTexture() ? _base->getGlobeTexture()->getBaseGridSprite() : 0;
	// every phase of the base's tiles at once, before the first of them is drawn
	std::vector<HdBase::Want> want;
	for (const auto* fac : *_base->getFacilities())
	{
		if (!isHdFacility(fac) && !isHdBuilding(fac))
		{
			continue;
		}
		const int tiles = fac->getRules()->getSizeX() * fac->getRules()->getSizeY();
		for (int num = 0; num < tiles; ++num)
		{
			const int index = hdTileIndex(fac, num);
			// a facility picture fills its grid cell: a mod's frame may be 32x40 with the bottom rows empty
			if (_texture->getFrame(index))
			{
				want.push_back({ index, GRID_SIZE, GRID_SIZE });
			}
		}
	}
	HdBase::preload(want, k, Options::oxceHdBaseAnim);
	// the pictures run on the display clock, never the game's: a still picture, a loop, a burst now and then
	const Uint32 now = SDL_GetTicks();
	Uint32 next = 0xFFFFFFFFu;
	// the living base: the rock of the cells without an HD picture is lit with the rest (see draw)
	const bool lit = hdScenes();
	if (lit)
	{
		if (const HdFrame *ground = classicHd(_texture, rock, k, getPalette()))
		{
			for (int x = 0; x < BASE_SIZE; ++x)
			{
				for (int y = 0; y < BASE_SIZE; ++y)
				{
					if (!isHdFacility(_facilities[x][y]))
					{
						HdUiArt::drawFrame(world, *ground, (getX() + x * GRID_SIZE) * k, (getY() + y * GRID_SIZE) * k);
					}
				}
			}
		}
	}
	for (const auto* fac : *_base->getFacilities())
	{
		const bool building = isHdBuilding(fac);
		if (!isHdFacility(fac) && !building)
		{
			continue;
		}
		// every tile of a facility bursts at once, facilities one after another
		const Uint32 seed = (Uint32)(fac->getX() * 7 + fac->getY() * 31 + 1);
		int num = 0;
		for (int y = fac->getY(); y < fac->getY() + fac->getRules()->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + fac->getRules()->getSizeX(); ++x)
			{
				// the rock the classic layer leaves out under the picture (it shows through its holes)
				if (const HdFrame *ground = classicHd(_texture, rock, k, getPalette()))
				{
					HdUiArt::drawFrame(world, *ground, (getX() + x * GRID_SIZE) * k, (getY() + y * GRID_SIZE) * k);
				}
				const int index = hdTileIndex(fac, num);
				if (_texture->getFrame(index))
				{
					next = std::min(next, HdBase::draw(world, index, (getX() + x * GRID_SIZE) * k, (getY() + y * GRID_SIZE) * k,
						k, GRID_SIZE, GRID_SIZE, Options::oxceHdBaseAnim, now, seed));
				}
				++num;
			}
		}
		if (building)
		{
			// the share of the build time gone by (only read); a little of it shows from the first day
			const int total = fac->getRules()->getBuildTime();
			float progress = total > 0 ? 1.0f - (float)fac->getBuildTime() / total : 0.5f;
			// OXCE_HD_BASE_BUILD=0..1: every site that far on (a test of the look, as OXCE_HD_BASE_NIGHT)
			if (const char *env = std::getenv("OXCE_HD_BASE_BUILD"))
			{
				progress = (float)std::atof(env);
			}
			const SDL_Rect rect = { (Sint16)((getX() + fac->getX() * GRID_SIZE) * k), (Sint16)((getY() + fac->getY() * GRID_SIZE) * k),
				(Uint16)(fac->getRules()->getSizeX() * GRID_SIZE * k), (Uint16)(fac->getRules()->getSizeY() * GRID_SIZE * k) };
			HdBaseScene::drawBuilding(world, rect, std::min(0.97f, std::max(0.04f, progress)), GRID_SIZE * k / 128.0f,
				seed * 2654435761u, now);
		}
	}
	// the craft over its HD hangar (a classic hangar keeps its craft on the classic layer)
	for (const HdCraft &craft : _hdCrafts)
	{
		Surface *classic = _texture->getFrame(craft.index);
		if (!craft.inWorld || !classic)
		{
			continue;
		}
		const HdFrame *picture = HdBase::phases(craft.index) > 0
			? HdBase::frame(craft.index, Options::oxceHdCraftLights ? _animPhase : 0, k, classic->getWidth(), classic->getHeight())
			: classicHd(_texture, craft.index, k, getPalette());
		if (picture)
		{
			HdUiArt::drawFrame(world, *picture, (getX() + craft.x) * k, (getY() + craft.y) * k);
		}
		if (Options::oxceHdCraftLights && HdBase::phases(craft.index) > 1)
		{
			next = now;         // a craft picture with phases steps with _animPhase
		}
	}
	_hdNextChange = next;
	if (lit)
	{
		drawHdScene(world, k, now);
	}
}

/**
 * The living base's light over everything drawHd has put into the world layer: the night of the
 * base's longitude and the lamps of the lit pictures (HdBaseScene). It only reads the game: the
 * clock, and whether the base researches and builds - a lab's screens dim when nobody works there.
 */
void BaseView::drawHdScene(SDL_Surface *world, int k, Uint32 now)
{
	const float night = _hdTime
		? HdBaseScene::nightAt(_base->getLongitude(), _hdTime->getHour(), _hdTime->getMinute(), _hdTime->getSecond())
		: 0.0f;
	const float labs = _base->getUsedLaboratories() > 0 ? 1.0f : 0.25f;
	const float works = _base->getUsedWorkshops() > 0 ? 1.0f : 0.25f;
	std::vector<HdBaseScene::Placed> lights;
	std::vector<HdBaseScene::PlacedEmit> emits;
	// the crew's view of the base (HdBaseLife): where to walk, work and sleep, and how many hands
	HdBaseLife::Plan plan;
	plan.scientists = _base->getTotalScientists();
	plan.engineers = _base->getTotalEngineers();
	plan.soldiers = (int)_base->getSoldiers()->size();
	plan.researching = _base->getUsedLaboratories() > 0;
	plan.producing = _base->getUsedWorkshops() > 0;
	plan.seed = (Uint32)std::lround(_base->getLongitude() * 1000) * 31u + (Uint32)std::lround(_base->getLatitude() * 1000);
	const float cellPx = (float)(GRID_SIZE * k);
	const float site = cellPx / 128.0f;           // world pixels per pack pixel, for the building sites
	int number = 0;
	for (const auto* fac : *_base->getFacilities())
	{
		++number;
		const bool building = isHdBuilding(fac);
		if (!isHdFacility(fac) && !building)
		{
			continue;
		}
		const RuleBaseFacility *rules = fac->getRules();
		int bits = 0;
		if (building)
		{
			bits = HdBaseLife::BUILD;
		}
		else if (!fac->getDisabled())
		{
			bits |= rules->getLaboratories() > 0 ? HdBaseLife::LAB : 0;
			bits |= rules->getWorkshops() > 0 ? HdBaseLife::WORK : 0;
			bits |= rules->getPersonnel() > 0 ? HdBaseLife::HOME : 0;
			bits |= rules->getAliens() > 0 ? HdBaseLife::PRISON : 0;
			bits |= rules->getSickBayAbsoluteBonus() > 0 || rules->getSickBayRelativeBonus() > 0 ? HdBaseLife::MED : 0;
			bits |= rules->getTrainingFacilities() > 0 ? HdBaseLife::GYM : 0;
			bits |= rules->getCrafts() > 0 ? HdBaseLife::HANGAR : 0;
			bits |= rules->getStorage() > 0 ? HdBaseLife::STORE : 0;
		}
		for (int y = fac->getY(); y < fac->getY() + rules->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + rules->getSizeX(); ++x)
			{
				if (x >= 0 && y >= 0 && x < HdBaseLife::SIZE && y < HdBaseLife::SIZE)
				{
					plan.facility[x][y] = number;
					plan.place[x][y] = bits ? bits : (int)HdBaseLife::OTHER;
				}
			}
		}
		if (building)
		{
			// the site: a work lamp over it, sparks of welding and dust
			const float fx = (float)((getX() + fac->getX() * GRID_SIZE) * k), fy = (float)((getY() + fac->getY() * GRID_SIZE) * k);
			const float fw = rules->getSizeX() * cellPx, fh = rules->getSizeY() * cellPx;
			HdBaseScene::Placed lamp;
			lamp.light.x = fx + fw / 2;
			lamp.light.y = fy + fh / 2;
			lamp.light.radius = 0.6f * std::max(fw, fh);
			lamp.light.kind = HdBaseScene::STEADY;
			lamp.light.r = 1.0f;
			lamp.light.g = 0.9f;
			lamp.light.b = 0.7f;
			lamp.scale = site;
			lamp.level = 0.7f;
			lights.push_back(lamp);
			HdBaseScene::PlacedEmit sparks;
			sparks.emit.kind = HdBaseScene::SPARKS;
			sparks.emit.x = fx + fw * 0.2f;
			sparks.emit.y = fy + fh * 0.2f;
			sparks.emit.w = fw * 0.6f;
			sparks.emit.h = fh * 0.6f;
			sparks.emit.r = 1.0f;
			sparks.emit.g = 0.75f;
			sparks.emit.b = 0.35f;
			sparks.scale = site;
			sparks.seed = (Uint32)number * 7919u;
			emits.push_back(sparks);
			HdBaseScene::PlacedEmit dust = sparks;
			dust.emit.kind = HdBaseScene::STEAM;
			dust.emit.x = fx + fw * 0.1f;
			dust.emit.y = fy + fh * 0.15f;
			dust.emit.w = fw * 0.8f;
			dust.emit.h = fh * 0.8f;
			dust.emit.r = 0.62f;
			dust.emit.g = 0.54f;
			dust.emit.b = 0.44f;
			dust.seed = (Uint32)number * 104729u;
			emits.push_back(dust);
			continue;
		}
		int num = 0;
		for (int y = fac->getY(); y < fac->getY() + fac->getRules()->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + fac->getRules()->getSizeX(); ++x)
			{
				const HdBaseScene::TileScene *scene = HdBase::scene(hdTileIndex(fac, num));
				++num;
				if (!scene)
				{
					continue;
				}
				const float s = (float)(GRID_SIZE * k) / scene->width;
				const float ox = (float)((getX() + x * GRID_SIZE) * k), oy = (float)((getY() + y * GRID_SIZE) * k);
				float level = scene->gate == HdBaseScene::GATE_LAB ? labs : scene->gate == HdBaseScene::GATE_WORK ? works : 1.0f;
				if (fac->getDisabled())
				{
					level = 0.1f;
				}
				Uint32 seed = (Uint32)(x * 7 + y * 31 + 1) * 2654435761u;
				for (const HdBaseScene::Light &light : scene->lights)
				{
					HdBaseScene::Placed p;
					p.light = light;
					p.light.x = ox + light.x * s;
					p.light.y = oy + light.y * s;
					p.light.radius = light.radius * s;
					p.scale = s;
					p.level = level;
					p.home = scene->gate == HdBaseScene::GATE_HOME;
					p.seed = (seed = seed * 1103515245u + 12345u) >> 8;
					lights.push_back(p);
				}
				for (const HdBaseScene::Emit &emit : scene->emits)
				{
					HdBaseScene::PlacedEmit e;
					e.emit = emit;
					e.emit.x = ox + emit.x * s;
					e.emit.y = oy + emit.y * s;
					e.emit.w = emit.w * s;
					e.emit.h = emit.h * s;
					e.scale = s;
					e.level = level;
					e.seed = (seed = seed * 1103515245u + 12345u) >> 8;
					emits.push_back(e);
				}
			}
		}
	}
	const SDL_Rect area = { (Sint16)(getX() * k), (Sint16)(getY() * k), (Uint16)(getWidth() * k), (Uint16)(getHeight() * k) };
	// the crew before the light: it darkens with the rooms at night, and its lanterns light them
	HdBaseLife::draw(world, plan, getX() * k, getY() * k, GRID_SIZE * k, night, now, lights);
	HdBaseScene::draw(world, area, lights, night, now);
	HdBaseScene::drawParticles(world, area, emits, night, now);
}

/**
 * Draws the lights of the crafts into the world layer. Called after the classic layer has been
 * mirrored there: a classic hangar and its craft come with the mirror and would cover them.
 */
void BaseView::drawHdLights()
{
	if (!_visible || _hidden || !_base || _hdCrafts.empty() || !hdBaseActive() || !Options::oxceHdCraftLights)
	{
		return;
	}
	Screen *screen = Screen::current();
	SDL_Surface *world = screen ? screen->getWorldSurface() : 0;
	const int k = screen ? screen->getWorldScale() : 1;
	if (!world || k < 2)
	{
		return;
	}
	const Uint32 ticks = SDL_GetTicks();
	for (const HdCraft &craft : _hdCrafts)
	{
		HdCraftLights::draw(world, craft.index, (getX() + craft.x) * k, (getY() + craft.y) * k, k,
			(HdCraftLights::Status)craft.status, craft.seed, ticks);
		if (craft.fuel >= 0)
		{
			HdCraftLights::drawFuel(world, (getX() + craft.fuelX) * k, (getY() + craft.fuelY) * k, k,
				craft.fuel, craft.seed, ticks);
		}
	}
}

/**
 * Keeps the animation timers running.
 */
void BaseView::think()
{
	_timer->think(0, this);
}

/**
 * Makes the facility selector blink.
 */
void BaseView::blink()
{
	_blink = !_blink;

	// HD pictures of facilities change on their own clock (HdBase::draw, steps of 200 ms): the classic
	// layer, which holds the craft and numbers over them, is drawn again only when one of them does
	if (HdBase::animated() && hdBaseActive() && (Options::oxceHdBaseAnim || Options::oxceHdCraftLights))
	{
		if (++_animTick >= 2)
		{
			_animTick = 0;
			++_animPhase;       // phases of the craft pictures
		}
		if (SDL_GetTicks() >= _hdNextChange)
		{
			_hdNextChange = 0xFFFFFFFFu;   // drawHd sets it again
			_redraw = true;
		}
	}

	if (_selSizeX > 0 && _selSizeY > 0)
	{
		SDL_Rect r;
		if (_blink)
		{
			r.w = _selector->getWidth();
			r.h = _selector->getHeight();
			r.x = 0;
			r.y = 0;
			_selector->drawRect(&r, _selectorColor);
			r.w -= 2;
			r.h -= 2;
			r.x++;
			r.y++;
			_selector->drawRect(&r, 0);
		}
		else
		{
			r.w = _selector->getWidth();
			r.h = _selector->getHeight();
			r.x = 0;
			r.y = 0;
			_selector->drawRect(&r, 0);
		}
	}
}

/**
 * Draws the view of all the facilities in the base, connectors
 * between them and crafts landed in hangars.
 */
void BaseView::draw()
{
	Surface::draw();

	const bool hdTiles = hdBaseActive();
	_hdCrafts.clear();
	for (auto* text : _hdNumbers)
	{
		delete text;
	}
	_hdNumbers.clear();
	_hdNumbersKept = hdNumbers();

	// Draw grid squares (under an HD facility the rock goes to the world layer with it, and all of it
	// with the living base's light, see drawHd)
	const bool lit = hdTiles && hdScenes();
	for (int x = 0; x < BASE_SIZE; ++x)
	{
		for (int y = 0; y < BASE_SIZE; ++y)
		{
			if (lit || (hdTiles && isHdFacility(_facilities[x][y])))
			{
				continue;
			}
			Surface *frame = _texture->getFrame(_base->getGlobeTexture() ? _base->getGlobeTexture()->getBaseGridSprite() : 0);
			int fx = (x * GRID_SIZE);
			int fy = (y * GRID_SIZE);
			frame->blitNShade(this, fx, fy);
		}
	}

	auto craftIt = _base->getCrafts()->begin();

	for (const auto* fac : *_base->getFacilities())
	{
		// Draw facility shape (an HD facility is drawn in the world layer instead, see blit)
		if (hdTiles && (isHdFacility(fac) || isHdBuilding(fac)))
		{
			continue;
		}
		int num = 0;
		for (int y = fac->getY(); y < fac->getY() + fac->getRules()->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + fac->getRules()->getSizeX(); ++x)
			{
				Surface *frame;

				int outline = fac->getRules()->isSmall() ? 3 : fac->getRules()->getSizeX() * fac->getRules()->getSizeY();
				if (fac->getBuildTime() == 0)
					frame = _texture->getFrame(fac->getRules()->getSpriteShape() + num);
				else
					frame = _texture->getFrame(fac->getRules()->getSpriteShape() + num + outline);

				int fx = (x * GRID_SIZE);
				int fy = (y * GRID_SIZE);
				frame->blitNShade(this, fx, fy);

				num++;
			}
		}
	}

	// a connector into an HD facility: the classic door leaf (Piratez Door1/Door2, x and y 19..21 of the frame)
	// would lie over the picture's furniture, so only the tube on the seam is drawn (frame columns/rows < 18)
	auto hdJoin = [&](const BaseFacility *to) { return hdTiles && (isHdFacility(to) || isHdBuilding(to)); };
	for (const auto* fac : *_base->getFacilities())
	{
		// Draw connectors
		if (fac->isBuiltOrHadPreviousFacility() && !fac->getRules()->connectorsDisabled())
		{
			// Facilities to the right
			int x = fac->getX() + fac->getRules()->getSizeX();
			if (x < BASE_SIZE)
			{
				for (int y = fac->getY(); y < fac->getY() + fac->getRules()->getSizeY(); ++y)
				{
					if (_facilities[x][y] != 0 && _facilities[x][y]->isBuiltOrHadPreviousFacility() && !_facilities[x][y]->getRules()->connectorsDisabled())
					{
						Surface *frame = _texture->getFrame(7);
						int fx = (x * GRID_SIZE - GRID_SIZE / 2);
						int fy = (y * GRID_SIZE);
						if (hdJoin(_facilities[x][y]))
						{
							// the tube on the seam only: the HD picture has its own doorway where the door leaf stood
							frame->blitNShade(this, fx, fy, 0, GraphSubset(GRID_SIZE / 2 + 2, GRID_SIZE).offset(fx, fy));
						}
						else
						{
							frame->blitNShade(this, fx, fy);
						}
					}
				}
			}

			// Facilities to the bottom
			int y = fac->getY() + fac->getRules()->getSizeY();
			if (y < BASE_SIZE)
			{
				for (int subX = fac->getX(); subX < fac->getX() + fac->getRules()->getSizeX(); ++subX)
				{
					if (_facilities[subX][y] != 0 && _facilities[subX][y]->isBuiltOrHadPreviousFacility() && !_facilities[subX][y]->getRules()->connectorsDisabled())
					{
						Surface *frame = _texture->getFrame(8);
						int fx = (subX * GRID_SIZE);
						int fy = (y * GRID_SIZE - GRID_SIZE / 2);
						if (hdJoin(_facilities[subX][y]))
						{
							frame->blitNShade(this, fx, fy, 0, GraphSubset(GRID_SIZE, GRID_SIZE / 2 + 2).offset(fx, fy));
						}
						else
						{
							frame->blitNShade(this, fx, fy);
						}
					}
				}
			}
		}
	}

	// TODO: make const in the future
	for (auto* fac : *_base->getFacilities())
	{
		// Draw facility graphic (an HD facility is drawn in the world layer instead, see blit)
		const bool hdFacility = hdTiles && isHdFacility(fac);
		const bool hdBuilding = hdTiles && isHdBuilding(fac);
		int num = 0;
		for (int y = fac->getY(); y < fac->getY() + fac->getRules()->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + fac->getRules()->getSizeX(); ++x)
			{
				if (fac->getRules()->getSpriteEnabled() && !hdFacility && !hdBuilding)
				{
					Surface *frame = _texture->getFrame(fac->getRules()->getSpriteFacility() + num);
					int fx = (x * GRID_SIZE);
					int fy = (y * GRID_SIZE);
					frame->blitNShade(this, fx, fy);
				}

				num++;
			}
		}

		// Draw crafts
		fac->setCraftForDrawing(0);
		if (fac->getBuildTime() == 0 && fac->getRules()->getCrafts() > 0)
		{
			if (craftIt != _base->getCrafts()->end())
			{
				if ((*craftIt)->getStatus() != "STR_OUT")
				{
					const int index = (*craftIt)->getSkinSprite() + 33;
					Surface *frame = _texture->getFrame(index);
					int fx = (fac->getX() * GRID_SIZE + (fac->getRules()->getSizeX() - 1) * GRID_SIZE / 2 + 2);
					int fy = (fac->getY() * GRID_SIZE + (fac->getRules()->getSizeY() - 1) * GRID_SIZE / 2 - 4);
					// an HD picture of the craft goes to the world layer over an HD hangar (a classic
					// hangar comes with the mirror of this layer and would cover it); its lights go
					// over everything (see drawHdLights)
					const bool inWorld = hdFacility && HdBase::phases(index) > 0;
					// every craft in an HD hangar: its fuel garland is drawn even without lights
					if (hdTiles)
					{
						HdCraft craft;
						craft.index = index;
						craft.x = fx;
						craft.y = fy;
						craft.status = HdCraftLights::statusOf(*craftIt);
						craft.seed = (Uint32)(fac->getX() * 7 + fac->getY() * 31);
						craft.inWorld = inWorld;
						// the garland along the bottom edge of the hangar, under the craft
						craft.fuel = (*craftIt)->getFuelMax() > 0 ? (*craftIt)->getFuelPercentage() : -1;
						craft.fuelX = fac->getX() * GRID_SIZE + fac->getRules()->getSizeX() * GRID_SIZE / 2;
						craft.fuelY = (fac->getY() + fac->getRules()->getSizeY()) * GRID_SIZE - 7;						_hdCrafts.push_back(craft);
					}
					if (!inWorld)
					{
						frame->blitNShade(this, fx, fy);
					}
					fac->setCraftForDrawing(*craftIt);
				}
				++craftIt;
			}
		}

		// Draw time remaining
		if (fac->getBuildTime() > 0 || fac->getDisabled())
		{
			Text *text = new Text(GRID_SIZE * fac->getRules()->getSizeX(), 16, 0, 0);
			text->setPalette(getPalette());
			text->initText(_big, _small, _lang);
			text->setX(fac->getX() * GRID_SIZE);
			text->setY(fac->getY() * GRID_SIZE + (GRID_SIZE * fac->getRules()->getSizeY() - 16) / 2);
			text->setBig();
			std::ostringstream ss;
			if (fac->getDisabled())
				ss << "X";
			else
				ss << fac->getBuildTime();
			if (fac->getIfHadPreviousFacility()) // Indicate that this facility still counts for connectivity
				ss << "*";
			text->setAlign(ALIGN_CENTER);
			text->setColor(_cellColor);
			text->setText(ss.str());
			keepNumber(text);
		}

		// Draw ammo indicator
		if (fac->getBuildTime() == 0 && fac->getRules()->getAmmoMax() > 0)
		{
			Text* text = new Text(GRID_SIZE * fac->getRules()->getSizeX(), 9, 0, 0);
			text->setPalette(getPalette());
			text->initText(_big, _small, _lang);
			text->setX(fac->getX() * GRID_SIZE);
			text->setY(fac->getY() * GRID_SIZE);
			text->setHighContrast(_highContrast);
			if (fac->getAmmo() >= fac->getRules()->getAmmoMax())
				text->setColor(_greenColor); // 100%
			else if (fac->getAmmo() <= fac->getRules()->getAmmoMax() / 2)
				text->setColor(_redColor); // 0-50%
			else
				text->setColor(_yellowColor); // 51-99%
			std::ostringstream ss;
			ss << fac->getAmmo() << "/" << fac->getRules()->getAmmoMax();
			text->setText(ss.str());
			keepNumber(text);
		}
	}
}

/**
 * Blits the base view and selector.
 * @param surface Pointer to surface to blit onto.
 */
void BaseView::blit(SDL_Surface *surface)
{
	// first: with the HD interface the classic layer is mirrored into the world layer by
	// Surface::blit, and its connectors, numbers and craft must stay over the pictures
	// (draw first: it decides which crafts go to the world layer)
	if (_visible && !_hidden && _redraw)
	{
		draw();
	}
	drawHd();
	Surface::blit(surface);
	if (_hdNumbersKept && HdUi::isScreen(surface) && HdUi::active())
	{
		// the numbers lie on the facilities' pictures, light ones too: an outline, as on any HD picture,
		// in place of the thin drop shadow (the classic big font has its dark edge drawn in)
		HdUi::instance().notePicture(getX(), getY(), getWidth(), getHeight());
		for (auto* text : _hdNumbers)
		{
			text->hdDrawAt(getX() + text->getX(), getY() + text->getY());
		}
	}
	else if (_hdNumbersKept != hdNumbers())
	{
		// the option was switched while the base stood still: lay the numbers out the other way round
		_redraw = true;
	}
	drawHdLights();
	if (_selector != 0)
	{
		_selector->blit(surface);
	}
}

/**
 * Selects the facility the mouse is over.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void BaseView::mouseOver(Action *action, State *state)
{
	_gridX = (int)floor(action->getRelativeXMouse() / (GRID_SIZE * action->getXScale()));
	_gridY = (int)floor(action->getRelativeYMouse() / (GRID_SIZE * action->getYScale()));
	if (_gridX >= 0 && _gridX < BASE_SIZE && _gridY >= 0 && _gridY < BASE_SIZE)
	{
		_selFacility = _facilities[_gridX][_gridY];
		if (_selSizeX > 0 && _selSizeY > 0)
		{
			if (_gridX + _selSizeX - 1 < BASE_SIZE && _gridY + _selSizeY - 1 < BASE_SIZE)
			{
				_selector->setX(_x + _gridX * GRID_SIZE);
				_selector->setY(_y + _gridY * GRID_SIZE);
				_selector->setVisible(true);
			}
			else
			{
				_selector->setVisible(false);
			}
		}
	}
	else
	{
		_selFacility = 0;
		if (_selSizeX > 0 && _selSizeY > 0)
		{
			_selector->setVisible(false);
		}
	}

	InteractiveSurface::mouseOver(action, state);
}

/**
 * Deselects the facility.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void BaseView::mouseOut(Action *action, State *state)
{
	_selFacility = 0;
	if (_selSizeX > 0 && _selSizeY > 0)
	{
		_selector->setVisible(false);
	}

	InteractiveSurface::mouseOut(action, state);
}

void BaseView::setColor(Uint8 color)
{
	_cellColor = color;
}
void BaseView::setSecondaryColor(Uint8 color)
{
	_selectorColor = color;
}
void BaseView::setOtherColors(Uint8 red, Uint8 yellow, Uint8 green, bool highContrast)
{
	_redColor = red;
	_yellowColor = yellow;
	_greenColor = green;
	_highContrast = highContrast;
}

}
