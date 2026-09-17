	#pragma once
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
#include <SDL.h>
#include <string>
#include "OpenGL.h"
#include "Surface.h"

namespace OpenXcom
{

class Surface;
class Action;

/**
 * A display screen, handles rendering onto the game window.
 * In SDL a Screen is treated like a Surface, so this is just
 * a specialized version of a Surface with functionality more
 * relevant for display screens. Contains a Surface buffer
 * where all the contents are kept, so any filters or conversions
 * can be applied before rendering the screen.
 */
class Screen
{
private:
	SDL_Surface *_screen;
	int _bpp;
	int _baseWidth, _baseHeight;
	double _scaleX, _scaleY;
	int _topBlackBand, _bottomBlackBand, _leftBlackBand, _rightBlackBand, _cursorTopBlackBand, _cursorLeftBlackBand;
	Uint32 _flags;
	SDL_Color deferredPalette[256];
	int _numColors, _firstColor;
	bool _pushPalette;
	bool _flickerFix;
	OpenGL glOutput;
	Surface::UniqueBufferPtr _buffer;
	Surface::UniqueSurfacePtr _surface;
	std::string _hdTestDumpPath;
	double _lastFlipMs = 0.0;
	/// Layered output (see getWorldSurface): the classic 8-bit layer is composed over a true-color world layer.
	bool _layered;
	bool _worldScaleFixed = false;        ///< the world scale was set by a state (the battlescape), not derived from the display
	static Screen *_current;
	/// World layer scale factor k: the world layer is k * base resolution.
	int _worldScale;
	Surface::UniqueBufferPtr _worldBuffer;
	Surface::UniqueSurfacePtr _world;
	/// (Re)allocates the world layer to match the base resolution and scale.
	void allocateWorld();
	/// Draws the classic 8-bit layer (index 0 = transparent) over a true-color surface of world size.
	void composeInto(SDL_Surface *dst) const;
	/// The classic layer over the world layer with xBRZ (see composeInto).
	void composeSmooth(SDL_Surface *dst, const Uint32 *lut, int srcW, int srcH, int k) const;
	/// Sets the _flags and _bpp variables based on game options; needed in more than one place now
	void makeVideoFlags();
public:
	static const int ORIGINAL_WIDTH;
	static const int ORIGINAL_HEIGHT;

	/// Creates a new display screen.
	Screen();
	/// Cleans up the display screen.
	~Screen();
	/// Get horizontal offset.
	int getDX() const;
	/// Get vertical offset.
	int getDY() const;
	/// Gets the internal buffer.
	SDL_Surface *getSurface();
	/// Handles keyboard events.
	void handle(Action *action);
	/// Renders the screen onto the game window.
	void flip();
	/// Clears the screen.
	void clear();
	/// Sets the screen's 8bpp palette.
	void setPalette(const SDL_Color *colors, int firstcolor = 0, int ncolors = 256, bool immediately = false);
	/// Gets the screen's 8bpp palette.
	SDL_Color *getPalette() const;
	/// Gets the screen's width.
	int getWidth() const;
	/// Gets the screen's height.
	int getHeight() const;
	/// Resets the screen display.
	void resetDisplay(bool resetVideo = true, bool noShaders = false);
	/// Gets the screen's X scale.
	double getXScale() const;
	/// Gets the screen's Y scale.
	double getYScale() const;
	/// Gets the screen's top black forbidden to cursor band's height.
	int getCursorTopBlackBand() const;
	/// Gets the screen's left black forbidden to cursor band's width.
	int getCursorLeftBlackBand() const;
	/// Takes a screenshot.
	void screenshot(const std::string &filename) const;
	/// HD test: asks for the next composed base-resolution frame (before scaling and cursor) to be written as PNG.
	void requestHdTestDump(const std::string &filename) { _hdTestDumpPath = filename; }
	/// HD test: true while a dump request is pending.
	bool hasHdTestDumpRequest() const { return !_hdTestDumpPath.empty(); }
	/// Time the last layered flip took (compose + scale/upload + swap), milliseconds (HD render profiling).
	double getLastFlipMs() const { return _lastFlipMs; }
	/// HD test: writes the pending dump of the internal buffer and clears the request.
	void writeHdTestDump();
	/// Gets the base (unscaled) width of the internal buffer.
	int getBaseWidth() const { return _baseWidth; }
	/// Gets the base (unscaled) height of the internal buffer.
	int getBaseHeight() const { return _baseHeight; }
	/// Gets the bit depth of the display output (the classic layer itself is 8-bit when layered).
	int getBpp() const { return _bpp; }
	/// Is the output layered? True whenever the display is 32-bit (OpenGL or a 32-bit scaler).
	/// Then the internal buffer is an 8-bit "classic" layer (index 0 = transparent) that is composed
	/// over the world layer at flip time; in plain 8-bit display mode there is no world layer at all.
	bool isLayered() const { return _layered; }
	/// Gets the world layer: a true-color surface of k * base resolution that the battlescape map draws into.
	/// Only valid when isLayered().
	SDL_Surface *getWorldSurface();
	/// Gets the world layer scale factor k.
	int getWorldScale() const { return _worldScale; }
	/// The screen (for drawing code without a Game at hand); null before it exists.
	static Screen *current() { return _current; }
	/// Sets the world layer scale factor k (reallocates the world layer).
	void setWorldScale(int scale);
	/// Checks whether a 32bit scaler is requested and works for the selected resolution
	static bool use32bitScaler();
	/// Checks whether OpenGL output is requested
	static bool useOpenGL();
	/// update the game scale as required.
	static void updateScale(int type, int &width, int &height, bool change);
};

}
