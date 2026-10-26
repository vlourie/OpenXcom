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
#include <chrono>
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
#include <string>
#include "../Mod/Texture.h"
#include "../Engine/HdBase.h"
#include "../Engine/HdBaseLife.h"
#include "../Engine/HdCraftLights.h"
#include "../Engine/HdSmooth.h"
#include "../Engine/HdUi.h"
#include "../Engine/HdUiArt.h"
#include "../Engine/Logger.h"
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

/// The rock of the living base as the preview drew it (hd/BASEBITS.PCK/ground.png, the whole base in one
/// picture), read once; nullptr without it: the cells keep the classic rock.
const OpenXcom::HdFrame *hdGround()
{
	static OpenXcom::HdFrame frame;
	static bool read = false;
	if (!read)
	{
		read = true;
		if (!OpenXcom::HdSprites::loadPng(OpenXcom::HdSprites::artPath("BASEBITS.PCK/ground.png"), frame))
		{
			frame = OpenXcom::HdFrame();
		}
	}
	return frame.empty() ? nullptr : &frame;
}

/// The living base made by BaseView::hdLayout: the view and what it was made for.
struct HdLayout
{
	std::string key;
	OpenXcom::HdBaseScene::View view;
};
HdLayout hdLayoutMade;

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
	const auto frameStart = std::chrono::steady_clock::now();
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
	// ... and with the pack's rock it is the preview's: the rock with the facilities' shadows, one picture
	const HdBaseScene::View *view = lit ? hdLayout(k) : nullptr;
	if (view)
	{
		HdUiArt::drawFrame(world, view->ground, view->x, view->y);
	}
	else if (lit)
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
				const HdFrame *ground = view ? nullptr : classicHd(_texture, rock, k, getPalette());
				if (ground)
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
	const auto sceneStart = std::chrono::steady_clock::now();
	if (lit)
	{
		drawHdScene(world, k, now);
	}
	if (std::getenv("OXCE_HD_BASE_PERF"))
	{
		static double pictures = 0, scene = 0;
		static int frames = 0;
		const auto end = std::chrono::steady_clock::now();
		pictures += std::chrono::duration<double, std::milli>(sceneStart - frameStart).count();
		scene += std::chrono::duration<double, std::milli>(end - sceneStart).count();
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base frame: pictures and rock " << pictures / frames << " ms + scene " << scene / frames << " ms per frame";
			pictures = scene = 0;
			frames = 0;
		}
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
	// the fits of the facilities (tickets 237-245): which run now, their turrets, glows and bursts below
	const HdBaseScene::View *view = hdLayout(k);
	if (view)
	{
		HdBaseScene::tick(hdLayoutMade.view, now);
	}
	int number = 0;
	for (const auto* fac : *_base->getFacilities())
	{
		++number;
		const int fit = view && number - 1 < (int)view->facilityFit.size() ? view->facilityFit[number - 1] : -1;
		const float fitAt = fit >= 0 ? HdBaseScene::fitTime(*view, fit, now) : 0.0f;
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
					// all floor unless the tile's scene tells where the furniture stands (below)
					for (int sx = 0; sx < HdBaseLife::SUB; ++sx)
					{
						for (int sy = 0; sy < HdBaseLife::SUB; ++sy)
						{
							plan.walk[x * HdBaseLife::SUB + sx][y * HdBaseLife::SUB + sy] = 1;
						}
					}
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
				if (scene->walkSize > 0 && x >= 0 && y >= 0 && x < HdBaseLife::SIZE && y < HdBaseLife::SIZE)
				{
					const int n = scene->walkSize;
					for (int sx = 0; sx < HdBaseLife::SUB; ++sx)
					{
						for (int sy = 0; sy < HdBaseLife::SUB; ++sy)
						{
							plan.walk[x * HdBaseLife::SUB + sx][y * HdBaseLife::SUB + sy] =
								scene->walk[(sy * n / HdBaseLife::SUB) * n + sx * n / HdBaseLife::SUB];
						}
					}
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
					if (light.kind == HdBaseScene::BURST)
					{
						// burns only in the facility's fit, its period the pulses of a fit
						if (fit < 0 || fitAt < 0)
						{
							continue;
						}
						p.level *= HdBaseScene::fitWave(fitAt, view->fits[fit].length, std::max(1, (int)light.period));
					}
					p.home = scene->gate == HdBaseScene::GATE_HOME;
					p.seed = (seed = seed * 1103515245u + 12345u) >> 8;
					lights.push_back(p);
				}
				for (const HdBaseScene::Emit &emit : scene->emits)
				{
					if (fit >= 0 && fitAt < 0 &&
						(emit.kind == HdBaseScene::SWEEP || emit.kind == HdBaseScene::ORBIT || emit.kind == HdBaseScene::BEAM))
					{
						continue;           // the turret's beam sweeps only in its fit
					}
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
	// the hangars (OXCE_HD_HANGAR_LIFE=1, the pilot of 26.10): the hands at the craft by its state, the vent breathing,
	// the exhaust of a craft back from a flight and a floodlight over it at night - the craft is only read
	static const bool hangarLife = std::getenv("OXCE_HD_HANGAR_LIFE") && std::atoi(std::getenv("OXCE_HD_HANGAR_LIFE")) != 0;
	if (hangarLife)
	{
		auto emit = [&](HdBaseScene::EmitKind kind, float x, float y, float w, float h, float r, float g, float b, float level)
		{
			HdBaseScene::PlacedEmit e;
			e.emit.kind = kind;
			e.emit.x = x;
			e.emit.y = y;
			e.emit.w = w;
			e.emit.h = h;
			e.emit.r = r;
			e.emit.g = g;
			e.emit.b = b;
			e.scale = site;
			e.level = level;
			e.seed = (Uint32)(x * 7 + y * 31) * 2654435761u;
			emits.push_back(e);
		};
		for (const auto* fac : *_base->getFacilities())
		{
			// the vent grate in the top right of the pack's hangar picture (BASEBITS 10, pack pixels 93-111, 18-40)
			if (fac->getRules()->getCrafts() > 0 && isHdFacility(fac) && hdTileIndex(fac, 1) == 10)
			{
				emit(HdBaseScene::STEAM, (getX() + (fac->getX() + 1) * GRID_SIZE) * k + 93 * site, (getY() + fac->getY() * GRID_SIZE) * k + 18 * site,
					18 * site, 22 * site, 0.85f, 0.88f, 0.90f, 0.35f);
			}
		}
		for (const HdCraft &craft : _hdCrafts)
		{
			Surface *frame = _texture->getFrame(craft.index);
			if (!frame)
			{
				continue;
			}
			HdBaseLife::Plan::Craft c;
			c.status = craft.status;
			c.fuelX = (float)craft.fuelX / GRID_SIZE;
			c.fuelY = (float)craft.fuelY / GRID_SIZE;
			plan.crafts.push_back(c);
			const unsigned char mine = (unsigned char)plan.crafts.size();
			const int sq = GRID_SIZE / HdBaseLife::SUB;
			int x0 = INT_MAX, x1 = -1, y1 = -1;
			for (int py = 0; py < frame->getHeight(); ++py)
			{
				for (int px = 0; px < frame->getWidth(); ++px)
				{
					const int gx = (craft.x + px) / sq, gy = (craft.y + py) / sq;
					if (frame->getPixel(px, py) && craft.x + px >= 0 && craft.y + py >= 0 && gx < HdBaseLife::SIZE * HdBaseLife::SUB && gy < HdBaseLife::SIZE * HdBaseLife::SUB)
					{
						plan.hull[gx][gy] = mine;
						x0 = std::min(x0, craft.x + px);
						x1 = std::max(x1, craft.x + px);
						y1 = std::max(y1, craft.y + py);
					}
				}
			}
			if (x1 < 0)
			{
				continue;
			}
			const float midX = (getX() + (x0 + x1 + 1) / 2.0f) * k;
			// back from a flight: a grey haze off its tail while it refuels
			if (craft.status == HdBaseLife::CRAFT_BUSY)
			{
				emit(HdBaseScene::STEAM, midX - 8 * site, (getY() + y1) * k - 6 * site, 16 * site, 10 * site, 0.55f, 0.55f, 0.58f, 0.5f);
			}
			// at night a floodlight from above falls on the craft
			if (night > 0.3f)
			{
				HdBaseScene::Placed p;
				p.light.x = midX;
				p.light.y = (getY() + craft.y + frame->getHeight() / 2.0f) * k;
				p.light.radius = 1.1f * cellPx;
				p.light.kind = HdBaseScene::STEADY;
				p.light.r = 1.0f;
				p.light.g = 0.95f;
				p.light.b = 0.85f;
				p.scale = site;
				p.level = 0.9f * night;
				lights.push_back(p);
			}
		}
	}
	const SDL_Rect area = { (Sint16)(getX() * k), (Sint16)(getY() * k), (Uint16)(getWidth() * k), (Uint16)(getHeight() * k) };
	// OXCE_HD_BASE_PERF: what each part of the living base costs, an average every 60 frames into the log
	static const bool perf = std::getenv("OXCE_HD_BASE_PERF") != nullptr;
	typedef std::chrono::steady_clock Clock;
	const auto t0 = Clock::now();
	// the water ripples and the dishes turn under the crew; the lamps fall on the relief of the pictures
	if (view)
	{
		HdBaseScene::drawMotion(world, *view, now);
	}
	const auto t1 = Clock::now();
	// the crew before the light: it darkens with the rooms at night, and its lanterns light them
	static const bool noCrew = HdBaseScene::measuredOff("crew");
	if (!noCrew)
	{
		HdBaseLife::draw(world, plan, getX() * k, getY() * k, GRID_SIZE * k, night, now, lights);
	}
	const auto t2 = Clock::now();
	HdBaseScene::draw(world, area, lights, night, now, view);
	const auto t3 = Clock::now();
	HdBaseScene::drawParticles(world, area, emits, night, now);
	if (perf)
	{
		static double sum[5] = { 0, 0, 0, 0, 0 };
		static int frames = 0;
		const auto t4 = Clock::now();
		auto ms = [](Clock::time_point a, Clock::time_point b) { return std::chrono::duration<double, std::milli>(b - a).count(); };
		sum[0] += ms(t0, t1);
		sum[1] += ms(t1, t2);
		sum[2] += ms(t2, t3);
		sum[3] += ms(t3, t4);
		sum[4] += ms(t0, t4);
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base scene: " << sum[4] / frames << " ms per frame = motion " << sum[0] / frames << " + crew "
				<< sum[1] / frames << " + light " << sum[2] / frames << " + particles " << sum[3] / frames << " | "
				<< lights.size() << " lights, " << emits.size() << " emitters, k=" << k << ", " << area.w << "x" << area.h << " px";
			std::fill(sum, sum + 5, 0.0);
			frames = 0;
		}
	}
}

/**
 * The living base for the layout now: the pictures over the pack's rock (the connectors stay the classic
 * tube, Vitali 22.10 «переходы такие НЕ ДЕЛАТЬ... лучше просто с оригинала взять»),
 * baked once (HdBaseScene::bake) and kept till a facility is built, moved or pulled down, or k changes.
 */
const HdBaseScene::View *BaseView::hdLayout(int k)
{
	const HdFrame *rock = hdGround();
	if (!rock || !_base || !_texture)
	{
		return nullptr;
	}
	std::ostringstream key;
	key << k << ' ' << getX() << ' ' << getY();
	for (const auto *fac : *_base->getFacilities())
	{
		key << ';' << fac->getRules()->getType() << ' ' << fac->getX() << ' ' << fac->getY() << ' '
			<< (isHdFacility(fac) ? 1 : isHdBuilding(fac) ? 2 : 0) << (fac->isBuiltOrHadPreviousFacility() ? 1 : 0);
	}
	HdLayout &made = hdLayoutMade;
	if (made.key == key.str())
	{
		return &made.view;
	}
	made = HdLayout();
	made.key = key.str();
	HdBaseScene::View &view = made.view;
	const int cell = GRID_SIZE * k;
	view.x = getX() * k;
	view.y = getY() * k;
	view.w = view.h = BASE_SIZE * cell;
	view.scale = cell / 128.0f;
	view.albedo.assign((size_t)view.w * view.h, 0u);
	auto put = [&view](const HdFrame &frame, int x0, int y0)
	{
		for (int y = 0; y < frame.height; ++y)
		{
			for (int x = 0; x < frame.width; ++x)
			{
				const int vx = x0 + x, vy = y0 + y;
				const Uint32 px = frame.pixels[(size_t)y * frame.width + x];
				if (vx >= 0 && vy >= 0 && vx < view.w && vy < view.h && (px >> 24))
				{
					view.albedo[(size_t)vy * view.w + vx] = px;
				}
			}
		}
	};
	std::vector<SDL_Rect> empty;
	for (int x = 0; x < BASE_SIZE; ++x)
	{
		for (int y = 0; y < BASE_SIZE; ++y)
		{
			if (!_facilities[x][y])
			{
				empty.push_back({ (Sint16)(x * cell), (Sint16)(y * cell), (Uint16)cell, (Uint16)cell });
			}
		}
	}
	std::vector<HdBaseScene::PlacedWater> waters;
	int number = 0;
	for (const auto *fac : *_base->getFacilities())
	{
		const RuleBaseFacility *rules = fac->getRules();
		view.facilityFit.push_back(-1);
		++number;
		if (isHdBuilding(fac))
		{
			continue;               // the site: bare rock under the blueprint (drawBuilding)
		}
		const bool hd = isHdFacility(fac);
		bool water = false;
		int num = 0;
		int fit = -1;
		for (int y = fac->getY(); y < fac->getY() + rules->getSizeY(); ++y)
		{
			for (int x = fac->getX(); x < fac->getX() + rules->getSizeX(); ++x)
			{
				const int index = hdTileIndex(fac, num++);
				if (!hd)
				{
					// a classic facility covers its cell on the classic layer: here it only casts its shadow
					HdFrame solid;
					solid.width = solid.height = cell;
					solid.pixels.assign((size_t)cell * cell, 0xFF505050u);
					put(solid, x * cell, y * cell);
					continue;
				}
				// a piece turning on its own: the picture without it is what lies under it
				const HdFrame *under = HdBase::layer(index, false, k, GRID_SIZE, GRID_SIZE);
				if (const HdFrame *picture = under ? under : HdBase::frame(index, 0, k, GRID_SIZE, GRID_SIZE))
				{
					put(*picture, x * cell, y * cell);
				}
				const HdBaseScene::TileScene *scene = HdBase::scene(index);
				if (!scene)
				{
					continue;
				}
				const float s = (float)cell / scene->width;
				// the facility moves in fits (tickets 237-245): one fit for all its tiles
				if (scene->cycle > 0 && fit < 0)
				{
					HdBaseScene::Fit F;
					F.period = scene->cycle;
					F.length = scene->fit;
					F.seed = (Uint32)number * 2654435761u ^ (Uint32)(fac->getX() * 31 + fac->getY());
					fit = (int)view.fits.size();
					view.fits.push_back(F);
					view.facilityFit.back() = fit;
				}
				const float tx = (float)(view.x + x * cell), ty = (float)(view.y + y * cell);
				for (const HdBaseScene::Glow &glow : scene->glows)
				{
					HdBaseScene::PlacedGlow p;
					p.glow = glow;
					p.glow.x = tx + glow.x * s;
					p.glow.y = ty + glow.y * s;
					p.glow.w = glow.w * s;
					p.glow.h = glow.h * s;
					p.fit = fit;
					if (fit >= 0)
					{
						view.glows.push_back(p);
					}
				}
				for (const HdBaseScene::Lid &lid : scene->lids)
				{
					HdBaseScene::PlacedLid p;
					p.lid = lid;
					p.lid.x = tx + lid.x * s;
					p.lid.y = ty + lid.y * s;
					p.lid.rx = lid.rx * s;
					p.lid.ry = lid.ry * s;
					p.fit = fit;
					p.scale = s;
					if (fit >= 0)
					{
						view.lids.push_back(p);
					}
				}
				for (const HdBaseScene::Sink &sink : scene->sinks)
				{
					HdBaseScene::PlacedSink p;
					p.sink = sink;
					p.sink.x = tx + sink.x * s;
					p.sink.y = ty + sink.y * s;
					p.sink.w = sink.w * s;
					p.sink.h = sink.h * s;
					p.sink.ix = tx + sink.ix * s;
					p.sink.iy = ty + sink.iy * s;
					p.sink.iw = sink.iw * s;
					p.sink.ih = sink.ih * s;
					p.fit = fit;
					if (fit >= 0)
					{
						view.sinks.push_back(p);
					}
				}
				if (scene->water && !water)
				{
					water = true;
					HdBaseScene::PlacedWater w;
					w.box = { (Sint16)(view.x + fac->getX() * cell), (Sint16)(view.y + fac->getY() * cell),
						(Uint16)(rules->getSizeX() * cell), (Uint16)(rules->getSizeY() * cell) };
					w.kind = scene->water;
					std::copy(scene->glint, scene->glint + 3, w.glint);
					w.least = scene->waterLeast;
					waters.push_back(w);
				}
				// light running along the pipes (23.10): the map of this tile's pipes at the size of its picture
				const HdFrame *pipes = scene->flow.mode != HdBaseScene::Flow::NONE ? HdBase::flow(index, k, GRID_SIZE, GRID_SIZE) : nullptr;
				if (pipes && pipes->width == cell && pipes->height == cell && (scene->flow.mode == HdBaseScene::Flow::STEADY || fit >= 0))
				{
					HdBaseScene::PlacedFlow p;
					p.flow = scene->flow;
					p.box = { (Sint16)(view.x + x * cell), (Sint16)(view.y + y * cell), (Uint16)cell, (Uint16)cell };
					p.map = pipes->pixels;
					p.fit = fit;
					view.flows.push_back(std::move(p));
				}
				for (const HdBaseScene::Spin &spin : scene->spins)
				{
					HdBaseScene::PlacedSpin p;
					p.spin = spin;
					p.spin.x = view.x + x * cell + spin.x * s;
					p.spin.y = view.y + y * cell + spin.y * s;
					p.spin.radius = spin.radius * s;
					p.phase = (float)((x * 7 + y * 13) % 17) / 17.0f;
					p.fit = fit;
					if (const HdFrame *piece = under ? HdBase::layer(index, true, k, GRID_SIZE, GRID_SIZE) : nullptr)
					{
						p.piece = *piece;
						p.px = view.x + x * cell;
						p.py = view.y + y * cell;
					}
					view.spins.push_back(p);
				}
			}
		}
	}
	const Uint32 t0 = SDL_GetTicks();
	HdBaseScene::bake(view, rock, empty, waters);
	Log(LOG_INFO) << "HdBaseScene: the living base baked " << view.w << "x" << view.h << " in " << SDL_GetTicks() - t0
		<< " ms, " << view.waters.size() << " waters, " << view.spins.size() << " spins, " << view.flows.size() << " flows";
	return &made.view;
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
				if ((*craftIt)->getStatus() != "STR_OUT" || *craftIt == _hdDeparting)
				{
					const int index = (*craftIt)->getSkinSprite() + 33;
					Surface *frame = _texture->getFrame(index);
					int fx = (fac->getX() * GRID_SIZE + (fac->getRules()->getSizeX() - 1) * GRID_SIZE / 2 + 2);
					int fy = (fac->getY() * GRID_SIZE + (fac->getRules()->getSizeY() - 1) * GRID_SIZE / 2 - 4);
					// over an HD hangar picture the craft sits on its pad: the classic offset above puts it about
					// 2 px right and 1 down of it, and each craft frame draws off its own centre - the drawn part
					// of the frame goes to the middle of the pad, 1 px above the middle of the hangar (BASEBITS 9-12
					// of the HD pack); a classic hangar keeps the classic place
					if (hdFacility)
					{
						int x0 = frame->getWidth(), y0 = frame->getHeight(), x1 = -1, y1 = -1;
						for (int py = 0; py < frame->getHeight(); ++py)
						{
							for (int px = 0; px < frame->getWidth(); ++px)
							{
								if (frame->getPixel(px, py))
								{
									x0 = std::min(x0, px);
									x1 = std::max(x1, px);
									y0 = std::min(y0, py);
									y1 = std::max(y1, py);
								}
							}
						}
						if (x1 >= 0)
						{
							fx = fac->getX() * GRID_SIZE + fac->getRules()->getSizeX() * GRID_SIZE / 2 - (x0 + x1 + 1) / 2;
							fy = fac->getY() * GRID_SIZE + fac->getRules()->getSizeY() * GRID_SIZE / 2 - 1 - (y0 + y1 + 1) / 2;
						}
					}
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
						// OXCE_HD_HANGAR_STATUS=0..4: every craft shown in that state (HdCraftLights::Status) - a test of
						// the hangar pictures, the craft itself unchanged
						static const char *shown = std::getenv("OXCE_HD_HANGAR_STATUS");
						if (shown && *shown >= '0' && *shown <= '4')
						{
							craft.status = *shown - '0';
						}
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
