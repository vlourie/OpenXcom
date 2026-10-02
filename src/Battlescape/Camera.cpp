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
#include "Camera.h"
#include "Map.h"
#include "../Engine/Action.h"
#include "../Engine/Options.h"
#include "../Engine/Timer.h"
#include "../Engine/HdGentle.h"
#include "../fmath.h"
#include <algorithm>
#include <cmath>

namespace OpenXcom
{

/**
 * Sets up a camera.
 * @param spriteWidth Width of map sprite.
 * @param spriteHeight Height of map sprite.
 * @param mapsize_x Current map size in X axis.
 * @param mapsize_y Current map size in Y axis.
 * @param mapsize_z Current map size in Z axis.
 * @param map Pointer to map surface.
 * @param visibleMapHeight Current height the view is at.
 */
Camera::Camera(int spriteWidth, int spriteHeight, int mapsize_x, int mapsize_y, int mapsize_z, Map *map, int visibleMapHeight) :
	_scrollMouseTimer(0), _scrollKeyTimer(0),
	_spriteWidth(spriteWidth), _spriteHeight(spriteHeight),
	_k(spriteWidth / 32 > 0 ? spriteWidth / 32 : 1),
	_mapsize_x(mapsize_x), _mapsize_y(mapsize_y), _mapsize_z(mapsize_z),
	_screenWidth(map->getWidth()), _screenHeight(map->getHeight()),
	_mapOffset(-250 * (spriteWidth / 32 > 0 ? spriteWidth / 32 : 1), 250 * (spriteWidth / 32 > 0 ? spriteWidth / 32 : 1), 0),
	_scrollMouseX(0), _scrollMouseY(0), _scrollKeyX(0), _scrollKeyY(0), _scrollTrigger(false),
	_visibleMapHeight(visibleMapHeight), _showAllLayers(false), _showSingleLayer(false),
	_map(map)
{
}

/**
 * Deletes the Camera.
 */
Camera::~Camera()
{

}

/**
 * Sets the camera's scrolling timer.
 * @param mouse Pointer to mouse timer.
 * @param key Pointer to key timer.
 */
void Camera::setScrollTimer(Timer *mouse, Timer *key)
{
	_scrollMouseTimer = mouse;
	_scrollKeyTimer = key;
}

/**
 * Handles camera mouse shortcuts.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Camera::mousePress(Action *action, State *)
{
	if (action->getDetails()->button.button == SDL_BUTTON_LEFT && Options::battleEdgeScroll == SCROLL_TRIGGER)
	{
		_scrollTrigger = true;
		mouseOver(action, 0);
	}
	else if (Options::battleDragScrollButton != SDL_BUTTON_MIDDLE || (SDL_GetMouseState(0,0)&SDL_BUTTON(Options::battleDragScrollButton)) == 0)
	{
		if (action->getDetails()->button.button == SDL_BUTTON_WHEELUP)
		{
			up();
		}
		else if (action->getDetails()->button.button == SDL_BUTTON_WHEELDOWN)
		{
			down();
		}
	}
}

/**
 * Handles camera mouse shortcuts.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Camera::mouseRelease(Action *action, State *)
{
	if (action->getDetails()->button.button == SDL_BUTTON_LEFT && Options::battleEdgeScroll == SCROLL_TRIGGER)
	{
		_scrollMouseX = 0;
		_scrollMouseY = 0;
		_scrollMouseTimer->stop();
		_scrollTrigger = false;
		int posX = action->getXMouse();
		int posY = action->getYMouse();
		if ((posX < (SCROLL_BORDER * action->getXScale()) && posX > 0)
			|| (posX > (_screenWidth / _k - SCROLL_BORDER) * action->getXScale())
			|| (posY < (SCROLL_BORDER * action->getYScale()) && posY > 0)
			|| (posY > (_screenHeight / _k - SCROLL_BORDER) * action->getYScale()))
			// A cheap hack to avoid handling this event as a click
			// on the map when the mouse is on the scroll-border
			action->getDetails()->button.button = 0;
	}
}

/**
 * Handles mouse over events.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Camera::mouseOver(Action *action, State *)
{
	if (_map->getCursorType() == CT_NONE)
	{
		return;
	}

	if (Options::battleEdgeScroll == SCROLL_AUTO || _scrollTrigger)
	{
		int posX = action->getXMouse();
		int posY = action->getYMouse();
		int scrollSpeed = Options::battleScrollSpeed;

		//left scroll
		if (posX < (SCROLL_BORDER * action->getXScale()) && posX >= 0)
		{
			_scrollMouseX = scrollSpeed;
			// if close to top or bottom, also scroll diagonally
			//downleft
			if (posY < (SCROLL_DIAGONAL_EDGE * action->getYScale()) && posY >= 0)
			{
				_scrollMouseY = scrollSpeed/2;
			}
			//upleft
			else if (posY > (_screenHeight / _k - SCROLL_DIAGONAL_EDGE) * action->getYScale())
			{
				_scrollMouseY = -scrollSpeed/2;
			}
			else _scrollMouseY = 0;
		}
		//right scroll
		else if (posX > (_screenWidth / _k - SCROLL_BORDER) * action->getXScale())
		{
			_scrollMouseX = -scrollSpeed;
			// if close to top or bottom, also scroll diagonally
			//downright
			if (posY <= (SCROLL_DIAGONAL_EDGE * action->getYScale()) && posY >= 0)
			{
				_scrollMouseY = scrollSpeed/2;
			}
			//upright
			else if (posY > (_screenHeight / _k - SCROLL_DIAGONAL_EDGE) * action->getYScale())
			{
				_scrollMouseY = -scrollSpeed/2;
			}
			else _scrollMouseY = 0;
		}
		else if (posX)
		{
			_scrollMouseX = 0;
		}

		//up
		if (posY < (SCROLL_BORDER * action->getYScale()) && posY >= 0)
		{
			_scrollMouseY = scrollSpeed;
			// if close to left or right edge, also scroll diagonally
			//up left
			if (posX < (SCROLL_DIAGONAL_EDGE * action->getXScale()) && posX >= 0)
			{
				_scrollMouseX = scrollSpeed;
				_scrollMouseY /=2;
			}
			//up right
			else if (posX > (_screenWidth / _k - SCROLL_DIAGONAL_EDGE) * action->getXScale())
			{
				_scrollMouseX = -scrollSpeed;
				_scrollMouseY /=2;
			}
		}
		//down
		else if (posY > (_screenHeight / _k - SCROLL_BORDER) * action->getYScale())
		{
			_scrollMouseY = -scrollSpeed;
			// if close to left or right edge, also scroll diagonally
			//down left
			if (posX < (SCROLL_DIAGONAL_EDGE * action->getXScale()) && posX >= 0)
			{
				_scrollMouseX = scrollSpeed;
				_scrollMouseY /=2;
			}
			//down right
			else if (posX > (_screenWidth / _k - SCROLL_DIAGONAL_EDGE) * action->getXScale())
			{
				_scrollMouseX = -scrollSpeed;
				_scrollMouseY /=2;
			}
		}
		else if (posY && _scrollMouseX == 0)
		{
			_scrollMouseY = 0;
		}

		if ((_scrollMouseX || _scrollMouseY) && !_scrollMouseTimer->isRunning() && !_scrollKeyTimer->isRunning() && 0==(SDL_GetMouseState(0,0)&SDL_BUTTON(Options::battleDragScrollButton)))
		{
			_scrollMouseTimer->start();
		}
		else if ((!_scrollMouseX && !_scrollMouseY) && _scrollMouseTimer->isRunning())
		{
			_scrollMouseTimer->stop();
		}
	}
}

/**
 * Handles camera keyboard shortcuts.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Camera::keyboardPress(Action *action, State *)
{
	if (_map->getCursorType() == CT_NONE)
	{
		return;
	}

	int key = action->getDetails()->key.keysym.sym;
	int scrollSpeed = Options::battleScrollSpeed;
	if (key == Options::keyBattleLeft)
	{
		_scrollKeyX = scrollSpeed;
	}
	else if (key == Options::keyBattleRight)
	{
		_scrollKeyX = -scrollSpeed;
	}
	else if (key == Options::keyBattleUp)
	{
		_scrollKeyY = scrollSpeed;
	}
	else if (key == Options::keyBattleDown)
	{
		_scrollKeyY = -scrollSpeed;
	}

	if ((_scrollKeyX || _scrollKeyY) && !_scrollKeyTimer->isRunning() && !_scrollMouseTimer->isRunning() && 0==(SDL_GetMouseState(0,0)&SDL_BUTTON(Options::battleDragScrollButton)))
	{
		_scrollKeyTimer->start();
	}
	else if ((!_scrollKeyX && !_scrollKeyY) && _scrollKeyTimer->isRunning())
	{
		_scrollKeyTimer->stop();
	}
}

/**
 * Handles camera keyboard shortcuts.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Camera::keyboardRelease(Action *action, State *)
{
	if (_map->getCursorType() == CT_NONE)
	{
		return;
	}

	int key = action->getDetails()->key.keysym.sym;
	if (key == Options::keyBattleLeft)
	{
		_scrollKeyX = 0;
	}
	else if (key == Options::keyBattleRight)
	{
		_scrollKeyX = 0;
	}
	else if (key == Options::keyBattleUp)
	{
		_scrollKeyY = 0;
	}
	else if (key == Options::keyBattleDown)
	{
		_scrollKeyY = 0;
	}

	if ((_scrollKeyX || _scrollKeyY) && !_scrollKeyTimer->isRunning() && !_scrollMouseTimer->isRunning() && 0==(SDL_GetMouseState(0,0)&SDL_BUTTON(Options::battleDragScrollButton)))
	{
		_scrollKeyTimer->start();
	}
	else if ((!_scrollKeyX && !_scrollKeyY) && _scrollKeyTimer->isRunning())
	{
		_scrollKeyTimer->stop();
	}
}

/**
 * Handles mouse-scrolling.
 */
void Camera::scrollMouse()
{
	// scroll speeds are kept in base pixels, the camera moves in world pixels
	scrollXY(_scrollMouseX * _k, _scrollMouseY * _k, true);
}

/**
 * Handles keyboard-scrolling.
 */
void Camera::scrollKey()
{
	scrollXY(_scrollKeyX * _k, _scrollKeyY * _k, true);
}

/**
 * Handles scrolling with given deviation.
 * @param x X deviation.
 * @param y Y deviation.
 * @param redraw Redraw map or not.
 */
void Camera::scrollXY(int x, int y, bool redraw)
{
	_mapOffset.x += x;
	_mapOffset.y += y;

	do
	{
		int xx = 0;
		int yy = 0;
		convertScreenToMap(halfWorld(_screenWidth), halfWorld(_visibleMapHeight), &xx, &yy);
		_center.x = xx;
		_center.y = yy;

		// Handling map bounds...
		// Ok, this is a prototype, it should be optimized.
		// Actually this should be calculated instead of slow-approximation.
		// (steps of k world pixels = 1 base pixel, keeping the offset a multiple of k)
		if (_center.x < 0)             { _mapOffset.x -= _k; _mapOffset.y -= _k; continue; }
		if (_center.x > _mapsize_x -1) { _mapOffset.x += _k; _mapOffset.y += _k; continue; }
		if (_center.y < 0)             { _mapOffset.x += _k; _mapOffset.y -= _k; continue; }
		if (_center.y > _mapsize_y -1) { _mapOffset.x -= _k; _mapOffset.y += _k; continue; }
		break;
	}
	while (true);

	_map->refreshSelectorPosition();
	if (redraw) _map->invalidate();
}


/**
 * Handles jumping with given deviation.
 * @param x X deviation.
 * @param y Y deviation.
 */
void Camera::jumpXY(int x, int y)
{
	_mapOffset.x += x;
	_mapOffset.y += y;
	int xx = 0;
	int yy = 0;
	convertScreenToMap(halfWorld(_screenWidth), halfWorld(_visibleMapHeight), &xx, &yy);
	_center.x = xx;
	_center.y = yy;
}


/**
 * Goes one level up.
 */
void Camera::up()
{
	if (_mapOffset.z < _mapsize_z - 1)
	{
		_mapOffset.z++;
		_mapOffset.y += _spriteHeight * 3 / 5;
		_map->draw();
	}
}

/**
 * Goes one level down.
 */
void Camera::down()
{
	if (_mapOffset.z > 0)
	{
		_mapOffset.z--;
		_mapOffset.y -= _spriteHeight * 3 / 5;
		_map->draw();
	}
}

/**
 * Sets the view level.
 * @param viewlevel New view level.
 */
void Camera::setViewLevel(int viewlevel)
{
	_mapOffset.z = Clamp(viewlevel, 0, _mapsize_z - 1);
	_map->draw();
}


/**
 * Centers map on a certain position.
 * @param mapPos Position to center on.
 * @param redraw Redraw map or not.
 */
void Camera::centerOnPosition(Position mapPos, bool redraw)
{
	Position screenPos;
	_center = mapPos;
	_center.x = Clamp<int>(_center.x, -1, _mapsize_x);
	_center.y = Clamp<int>(_center.y, -1, _mapsize_y);
	convertMapToScreen(_center, &screenPos);

	_mapOffset.x = -(screenPos.x - halfWorld(_screenWidth));
	_mapOffset.y = -(screenPos.y - halfWorld(_visibleMapHeight));

	_mapOffset.z = _center.z;
	_glideNext = true;
	if (redraw) _map->draw();
}

/**
 * Is a tile well inside the visible part of the map (above the icons) at the logical offset?
 * The unit standing on it fits whole: its floor point is half a tile in from the sides and the
 * bottom, and a tile's height below the top.
 * @param mapPos Position to check.
 */
bool Camera::inView(Position mapPos) const
{
	Position screenPos;
	convertMapToScreen(mapPos, &screenPos);
	const int x = screenPos.x + _mapOffset.x + _spriteWidth / 2;
	const int y = screenPos.y + _mapOffset.y + _spriteHeight - _spriteWidth / 4;
	return x >= _spriteWidth / 2 && x <= _screenWidth - _spriteWidth / 2
		&& y >= _spriteHeight && y <= _visibleMapHeight - _spriteWidth / 4;
}

/**
 * Centers map on a position for a unit picked or an event, unless in gentle mode the position
 * is in view already: then the camera stays and only goes to its level. Without the mode it is
 * centerOnPosition exactly.
 * @param mapPos Position to center on.
 * @param redraw Redraw map or not.
 */
void Camera::focusOn(Position mapPos, bool redraw)
{
	if (HdGentle::on() && mapPos.x >= 0 && mapPos.y >= 0 && mapPos.z >= 0 && mapPos.z < _mapsize_z && inView(mapPos))
	{
		_mapOffset.z = mapPos.z;
		if (redraw) _map->draw();
		return;
	}
	centerOnPosition(mapPos, redraw);
}

/// Gentle mode: how fast the picture catches up with the camera, s (a critically damped spring:
/// about 0.3 s to 95 % of the way, no overshoot; a new target turns it from where it is now).
static const double GLIDE_TIME = 0.13;
/// Gentle mode: a centering further than this many screens is cut, not glided: a fast sweep of
/// the whole screen is just what the mode is for avoiding.
static const double GLIDE_FAR = 1.5;
/// Gentle mode: frames further apart than this, ms (a message or a dialog over the map), stop
/// counting as a glide for clicks into the map.
static const unsigned GLIDE_GAP = 250;
/// Gentle mode: one frame moves the picture by at most this much time of its way, ms: after a pause
/// (the AI thinking, a dialog) the picture goes on from where it stood instead of jumping ahead.
/// About one frame at 50-60 fps: a slower game glides longer, never in bigger steps.
static const unsigned GLIDE_STEP = 20;

/**
 * Gentle mode: puts the shown offset in place of the logical one for drawing the map. A centering
 * (centerOnPosition) since the last frame glides there; any other move (scrolling, a level up or
 * down) moves the picture along at once, a glide on its way included. Does nothing without the mode.
 */
void Camera::beginShown()
{
	_gliding = false;
	if (!HdGentle::on())
	{
		_shownValid = false;
		_glideNext = false;
		return;
	}
	const unsigned now = SDL_GetTicks();
	const Position logical = _mapOffset;
	if (!_shownValid)
	{
		_shownX = logical.x;
		_shownY = logical.y;
		_shownVX = _shownVY = 0;
		_shownValid = true;
	}
	else if (logical.x != _lastLogical.x || logical.y != _lastLogical.y)
	{
		if (!_glideNext)
		{
			_shownX += logical.x - _lastLogical.x;
			_shownY += logical.y - _lastLogical.y;
		}
		else if (std::abs(logical.x - _shownX) > GLIDE_FAR * _screenWidth || std::abs(logical.y - _shownY) > GLIDE_FAR * _visibleMapHeight)
		{
			_shownX = logical.x;
			_shownY = logical.y;
			_shownVX = _shownVY = 0;
		}
		else if (_shownX == _lastLogical.x && _shownY == _lastLogical.y && _shownVX == 0 && _shownVY == 0)
		{
			_shownTicks = now; // a glide from rest starts with this frame
		}
	}
	_glideNext = false;
	_lastLogical = logical;

	if (_shownX != logical.x || _shownY != logical.y)
	{
		const unsigned ms = std::min(now - _shownTicks, GLIDE_STEP);
		const double dt = ms / 1000.0;
		const double omega = 2.0 / GLIDE_TIME;
		const double x = omega * dt;
		const double decay = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x);
		auto spring = [&](double &cur, double &vel, double target)
		{
			const double change = cur - target;
			const double temp = (vel + omega * change) * dt;
			vel = (vel - omega * temp) * decay;
			cur = target + (change + temp) * decay;
		};
		spring(_shownX, _shownVX, logical.x);
		spring(_shownY, _shownVY, logical.y);
		if (std::abs(_shownX - logical.x) < _k && std::abs(_shownY - logical.y) < _k)
		{
			_shownX = logical.x;
			_shownY = logical.y;
			_shownVX = _shownVY = 0;
		}
	}
	else
	{
		_shownVX = _shownVY = 0;
	}
	_shownTicks = now;
	_gliding = _shownX != logical.x || _shownY != logical.y;

	_savedOffset = logical;
	_mapOffset.x = (int)std::lround(_shownX / _k) * _k;
	_mapOffset.y = (int)std::lround(_shownY / _k) * _k;
	_drawnOffset = _mapOffset;
	_inShown = true;
}

/**
 * Gentle mode: is the picture still on its way to the logical offset? A glide whose frames
 * stopped coming (a message over the map) does not count: it ends at the next frame anyway.
 */
bool Camera::isGliding() const
{
	return _gliding && SDL_GetTicks() - _shownTicks <= GLIDE_GAP;
}

/**
 * Gentle mode: brings the logical offset back after drawing the map. If the drawing moved the
 * camera itself (following a projectile, which the mode turns off), that place is taken as is.
 */
void Camera::endShown()
{
	if (!_inShown)
	{
		return;
	}
	_inShown = false;
	if (_mapOffset.x == _drawnOffset.x && _mapOffset.y == _drawnOffset.y)
	{
		_mapOffset.x = _savedOffset.x;
		_mapOffset.y = _savedOffset.y;
	}
	else
	{
		_shownX = _mapOffset.x;
		_shownY = _mapOffset.y;
		_shownVX = _shownVY = 0;
		_lastLogical = _mapOffset;
		_gliding = false;
	}
}

/**
 * Gets map's center position.
 * @return Map's center position.
 */
Position Camera::getCenterPosition()
{
	_center.z = _mapOffset.z;
	return _center;
}

/**
 * Converts screen coordinates to map coordinates.
 * @param screenX Screen x position.
 * @param screenY Screen y position.
 * @param mapX Map x position.
 * @param mapY Map y position.
 */
void Camera::convertScreenToMap(int screenX, int screenY, int *mapX, int *mapY) const
{
	// HD render: the original integer arithmetic is not scale invariant (the "/ 4" truncates),
	// so the conversion is done in base pixels: world coordinates are always k times base ones.
	const int spriteWidth = _spriteWidth / _k;
	const int spriteHeight = _spriteHeight / _k;
	const int offsetX = _mapOffset.x / _k;
	const int offsetY = _mapOffset.y / _k;
	screenX /= _k;
	screenY /= _k;

	// add half a tile height to the mouse position per layer we are above the floor
	screenY += (-spriteWidth/2) + (_mapOffset.z) * ((spriteHeight + spriteWidth / 4) / 2);

	// calculate the actual x/y pixel position on a diamond shaped map
	// taking the view offset into account
	*mapY = - screenX + offsetX + 2 * screenY - 2 * offsetY;
	*mapX = screenY - offsetY - *mapY / 4 - (spriteWidth/4);

	// to get the row & column itself, divide by the size of a tile
	*mapX /= (spriteWidth / 4);
	*mapY /= spriteWidth;

	*mapX = Clamp(*mapX, -1, _mapsize_x);
	*mapY = Clamp(*mapY, -1, _mapsize_y);
}

/**
 * Converts map coordinates X,Y,Z to screen positions X, Y.
 * @param mapPos X,Y,Z coordinates on the map.
 * @param screenPos Screen position.
 */
void Camera::convertMapToScreen(Position mapPos, Position *screenPos) const
{
	screenPos->z = 0; // not used
	screenPos->x = mapPos.x * (_spriteWidth / 2) - mapPos.y * (_spriteWidth / 2);
	screenPos->y = mapPos.x * (_spriteWidth / 4) + mapPos.y * (_spriteWidth / 4) - mapPos.z * ((_spriteHeight + _spriteWidth / 4) / 2);
}

/**
 * Converts voxel coordinates X,Y,Z to screen positions X, Y.
 * @param voxelPos X,Y,Z coordinates of the voxel.
 * @param screenPos Screen position.
 */
void Camera::convertVoxelToScreen(Position voxelPos, Position *screenPos) const
{
	Position mapPosition = voxelPos.toTile();
	convertMapToScreen(mapPosition, screenPos);
	double dx = voxelPos.x - (mapPosition.x * 16);
	double dy = voxelPos.y - (mapPosition.y * 16);
	double dz = voxelPos.z - (mapPosition.z * 24);
	// HD render: one voxel is k screen pixels; computed exactly as k times the original integer result
	const double baseSpriteHeight = _spriteHeight / (double)_k;
	screenPos->x += (int)(dx - dy) * _k + (_spriteWidth/2);
	screenPos->y += (int)(((baseSpriteHeight / 2.0)) + (dx / 2.0) + (dy / 2.0) - dz) * _k;
	screenPos->x += _mapOffset.x;
	screenPos->y += _mapOffset.y;
}

/**
 * Gets the displayed level.
 * @return The displayed layer.
 */
int Camera::getViewLevel() const
{
	return _mapOffset.z;
}

/**
 * Gets the map size x.
 * @return The map size x.
 */
int Camera::getMapSizeX() const
{
	return _mapsize_x;
}

/**
 * Gets the map size y.
 * @return The map size y.
 */
int Camera::getMapSizeY() const
{
	return _mapsize_y;
}

/**
 * Gets the map offset.
 * @return The map offset.
 */
Position Camera::getMapOffset() const
{
	return _mapOffset;
}

/**
 * Sets the map offset.
 * @param pos The map offset.
 */
void Camera::setMapOffset(const Position& pos)
{
	_mapOffset = pos;
}

/**
 * Toggles showing all map layers.
 * @return New layer setting.
 */
int Camera::toggleShowAllLayers()
{
	_showAllLayers = !_showAllLayers;
	return _showAllLayers?2:1;
}

/**
 * Checks if the camera is showing all map layers.
 * @return Current layer setting.
 */
bool Camera::getShowAllLayers() const
{
	return _showAllLayers;
}

/**
 * Checks if map coordinates X,Y,Z are on screen.
 * @param mapPos Coordinates to check.
 * @param unitWalking True to offset coordinates for a unit walking.
 * @param unitSize size of unit (0 - single, 1 - 2x2, etc, used for walking only
 * @param boundary True if it's for caching calculation
 * @return True if the map coordinates are on screen.
 */
bool Camera::isOnScreen(Position mapPos, const bool unitWalking, const int unitSize, const bool boundary) const
{
	Position screenPos;
	convertMapToScreen(mapPos, &screenPos);
	int posx = _spriteWidth/2, posy = _spriteHeight - _spriteWidth/4;
	int sizex = _spriteWidth/2, sizey = _spriteHeight/2;
	if (unitSize > 0)
	{
		posy -= _spriteWidth /4;
		sizex = _spriteWidth*unitSize;
		sizey = _spriteWidth*unitSize/2;
	}
	screenPos.x += _mapOffset.x + posx;
	screenPos.y += _mapOffset.y + posy;
	if (unitWalking)
	{
/* pretty hardcoded hack to handle overlapping by icons
(they are always in the center at the bottom of the screen)
Free positioned icons would require more complex workaround.
__________
|________|
||      ||
|| ____ ||
||_|XX|_||
|________|
 */
		if (boundary) //to make sprite updates even being slightly outside of screen
		{
			sizex += _spriteWidth;
			sizey += _spriteWidth/2;
		}
		if ( screenPos.x < 0 - sizex
			|| screenPos.x >= _screenWidth + sizex
			|| screenPos.y < 0 - sizey
			|| screenPos.y >= _screenHeight + sizey ) return false; //totally outside
		int side = ( _screenWidth - _map->getIconWidth() * _k ) / 2;
		if ( (screenPos.y < (_screenHeight - _map->getIconHeight() * _k) + sizey) ) return true; //above icons
		if ( (side > 1) && ( (screenPos.x < side + sizex) || (screenPos.x >= (_screenWidth - side - sizex)) ) ) return true; //at sides (if there are any)
		return false;
	}
	else
	{
		return screenPos.x >= 0
			&& screenPos.x <= _screenWidth - 10 * _k
			&& screenPos.y >= 0
			&& screenPos.y <= _screenHeight - 10 * _k;
	}
}

/**
 * Resizes the viewable window of the camera.
 */
void Camera::resize()
{
	_screenWidth = _map->getWidth();
	_screenHeight = _map->getHeight();
	_visibleMapHeight = _map->getHeight() - _map->getIconHeight() * _k;
}

void Camera::stopKeyScrolling()
{
	_scrollKeyTimer->stop();
}

void Camera::stopMouseScrolling()
{
	_scrollMouseTimer->stop();
}

}
