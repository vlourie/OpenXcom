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
#include "Screen.h"
#include "../resource.h"
#include "HdUiArt.h"
#include "Scalers/xbrz.h"
#include <algorithm>
#include <sstream>
#include <cmath>
#include <iomanip>
#include <climits>
#include <cstdio>
#include "../lodepng.h"
#include "Exception.h"
#include "Surface.h"
#include "Logger.h"
#include "Action.h"
#include "Options.h"
#include "CrossPlatform.h"
#include "FileMap.h"
#include "Zoom.h"
#include "Timer.h"
#include "HdTest.h"
#include "HdWorkers.h"
#include <chrono>
#include <SDL.h>

namespace OpenXcom
{

const int Screen::ORIGINAL_WIDTH = 320;
const int Screen::ORIGINAL_HEIGHT = 200;

static const int VIDEO_WINDOW_POS_LEN = 40;
static char VIDEO_WINDOW_POS[VIDEO_WINDOW_POS_LEN];

static const char* SDL_VIDEO_CENTERED_UNSET = "SDL_VIDEO_CENTERED=";
static const char* SDL_VIDEO_CENTERED_CENTER = "SDL_VIDEO_CENTERED=center";
static const char* SDL_VIDEO_WINDOW_POS_UNSET = "SDL_VIDEO_WINDOW_POS=";

/**
 * Sets up all the internal display flags depending on
 * the current video settings.
 */
void Screen::makeVideoFlags()
{
	_flags = SDL_HWSURFACE|SDL_DOUBLEBUF|SDL_HWPALETTE;
	if (Options::asyncBlit)
	{
		_flags |= SDL_ASYNCBLIT;
	}
	if (useOpenGL())
	{
		_flags = SDL_OPENGL;
		SDL_GL_SetAttribute( SDL_GL_RED_SIZE, 5 );
		SDL_GL_SetAttribute( SDL_GL_GREEN_SIZE, 5 );
		SDL_GL_SetAttribute( SDL_GL_BLUE_SIZE, 5 );
		SDL_GL_SetAttribute( SDL_GL_DEPTH_SIZE, 16 );
		SDL_GL_SetAttribute( SDL_GL_DOUBLEBUFFER, 1 );
	}
	if (Options::allowResize)
	{
		_flags |= SDL_RESIZABLE;
	}

	// Handle window positioning
	if (!Options::fullscreen && Options::rootWindowedMode)
	{
		snprintf(VIDEO_WINDOW_POS, VIDEO_WINDOW_POS_LEN, "SDL_VIDEO_WINDOW_POS=%d,%d", Options::windowedModePositionX, Options::windowedModePositionY);
		SDL_putenv(VIDEO_WINDOW_POS);
		SDL_putenv((char *)SDL_VIDEO_CENTERED_UNSET);
	}
	else if (Options::borderless)
	{
		SDL_putenv((char *)SDL_VIDEO_WINDOW_POS_UNSET);
		SDL_putenv((char *)SDL_VIDEO_CENTERED_CENTER);
	}
	else
	{
		SDL_putenv((char *)SDL_VIDEO_WINDOW_POS_UNSET);
		SDL_putenv((char *)SDL_VIDEO_CENTERED_UNSET);
	}

	// Handle display mode
	if (Options::fullscreen)
	{
		_flags |= SDL_FULLSCREEN;
	}
	if (Options::borderless)
	{
		_flags |= SDL_NOFRAME;
	}

	// the HD battlescape needs the layered (32-bit) output whatever the scaler
	_bpp = (use32bitScaler() || useOpenGL() || Options::oxceHdScale > 1 || Options::oxceHdPictures) ? 32 : 8;
	_layered = (_bpp == 32);
	_baseWidth = Options::baseXResolution;
	_baseHeight = Options::baseYResolution;
}


/**
 * Initializes a new display screen for the game to render contents to.
 * The screen is set up based on the current options.
 */
Screen *Screen::_current = nullptr;

Screen::Screen() : _baseWidth(ORIGINAL_WIDTH), _baseHeight(ORIGINAL_HEIGHT), _scaleX(1.0), _scaleY(1.0), _flags(0), _numColors(0), _firstColor(0), _pushPalette(false), _flickerFix(false), _layered(false), _worldScale(1)
{
	_current = this;
	_flickerFix = Options::oxceEnablePaletteFlickerFix;

	resetDisplay();
	memset(deferredPalette, 0, 256*sizeof(SDL_Color));
}

/**
 * Deletes the buffer from memory. The display screen itself
 * is automatically freed once SDL shuts down.
 */
Screen::~Screen()
{
	if (_current == this) _current = nullptr;
}

/**
 * Returns the screen's internal buffer surface. Any
 * contents that need to be shown will be blitted to this.
 * @return Pointer to the buffer surface.
 */
SDL_Surface *Screen::getSurface()
{
	_pushPalette = true;
	return _surface.get();
}

/**
 * Handles screen key shortcuts.
 * @param action Pointer to an action.
 */
void Screen::handle(Action *action)
{
	if (Options::debug)
	{
		if (action->getDetails()->type == SDL_KEYDOWN && action->getDetails()->key.keysym.sym == SDLK_F8 && (SDL_GetModState() & KMOD_ALT) != 0)
		{
			switch(Timer::gameSlowSpeed)
			{
				case 1: Timer::gameSlowSpeed = 5; break;
				case 5: Timer::gameSlowSpeed = 15; break;
				default: Timer::gameSlowSpeed = 1; break;
			}
		}
	}

	if (action->getDetails()->type == SDL_KEYDOWN && action->getDetails()->key.keysym.sym == SDLK_RETURN && (SDL_GetModState() & KMOD_ALT) != 0)
	{
		Options::fullscreen = !Options::fullscreen;
		resetDisplay();
	}
	else if (action->getDetails()->type == SDL_KEYDOWN && action->getDetails()->key.keysym.sym == Options::keyScreenshot)
	{
		std::ostringstream ss;
		int i = 0;
		do
		{
			ss.str("");
			ss << Options::getMasterUserFolder() << "screen" << std::setfill('0') << std::setw(3) << i << ".png";
			i++;
		}
		while (CrossPlatform::fileExists(ss.str()));
		screenshot(ss.str());
		return;
	}
}


/**
 * Renders the buffer's contents onto the screen, applying
 * any necessary filters or conversions in the process.
 * If the scaling factor is bigger than 1, the entire contents
 * of the buffer are resized by that factor (eg. 2 = doubled)
 * before being put on screen.
 */
void Screen::flip()
{
	// perform any requested palette update
	if (_flickerFix && _pushPalette && _numColors && _screen->format->BitsPerPixel == 8)
	{
		if (_screen->format->BitsPerPixel == 8 && SDL_SetColors(_screen, &(deferredPalette[_firstColor]), _firstColor, _numColors) == 0)
		{
			Log(LOG_DEBUG) << "Display palette doesn't match requested palette";
		}
		_numColors = 0;
		_pushPalette = false;
	}

	if (_layered)
	{
		// classic 8-bit layer over the world layer, then the world layer is what gets scaled to the display
		const auto t0 = std::chrono::steady_clock::now();
		composeInto(_world.get());
		if (getWidth() != _world->w || getHeight() != _world->h || useOpenGL())
		{
			Zoom::flipWithZoom(_world.get(), _screen, _topBlackBand, _bottomBlackBand, _leftBlackBand, _rightBlackBand, &glOutput);
		}
		else
		{
			SDL_BlitSurface(_world.get(), 0, _screen, 0);
		}
		_lastFlipMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
	}
	else if (getWidth() != _baseWidth || getHeight() != _baseHeight || useOpenGL())
	{
		Zoom::flipWithZoom(_surface.get(), _screen, _topBlackBand, _bottomBlackBand, _leftBlackBand, _rightBlackBand, &glOutput);
	}
	else
	{
		SDL_BlitSurface(_surface.get(), 0, _screen, 0);
	}

	// perform any requested palette update
	if (!_flickerFix && _pushPalette && _numColors && _screen->format->BitsPerPixel == 8)
	{
		if (_screen->format->BitsPerPixel == 8 && SDL_SetColors(_screen, &(deferredPalette[_firstColor]), _firstColor, _numColors) == 0)
		{
			Log(LOG_DEBUG) << "Display palette doesn't match requested palette";
		}
		_numColors = 0;
		_pushPalette = false;
	}



	if (SDL_Flip(_screen) == -1)
	{
		throw Exception(SDL_GetError());
	}
}

/**
 * Clears all the contents out of the internal buffer.
 */
void Screen::clear()
{
	Surface::CleanSdlSurface(_surface.get());
	if (_world)
	{
		Surface::CleanSdlSurface(_world.get());
	}
	Surface::CleanSdlSurface(_screen);
}

/**
 * The classic layer over the world layer through xBRZ: the 8-bit layer becomes
 * ARGB (index 0 transparent), is scaled k times by xBRZ in row slices on the
 * render threads, then alpha-blended over the world layer.
 */
void Screen::composeSmooth(SDL_Surface *dst, const Uint32 *lut, int srcW, int srcH, int k) const
{
	static std::vector<Uint32> src, big;
	src.resize((size_t)srcW * srcH);
	big.resize((size_t)srcW * k * srcH * k);
	const Uint8 *srcPixels = (const Uint8*)_surface->pixels;
	const int srcPitch = _surface->pitch;
	for (int y = 0; y < srcH; ++y)
	{
		const Uint8 *row = srcPixels + (size_t)y * srcPitch;
		Uint32 *out = &src[(size_t)y * srcW];
		for (int x = 0; x < srcW; ++x)
		{
			const Uint8 idx = row[x];
			out[x] = idx ? (lut[idx] | 0xFF000000u) : 0u;
		}
	}
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(srcH / 16, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		const int ya = (int)((long long)srcH * job / jobs);
		const int yb = (int)((long long)srcH * (job + 1) / jobs);
		xbrz::scale((size_t)k, src.data(), big.data(), srcW, srcH, xbrz::ARGB, xbrz::ScalerCfg(), ya, yb);
	});
	if (SDL_MUSTLOCK(dst)) SDL_LockSurface(dst);
	const int W = srcW * k, H = std::min(srcH * k, dst->h);
	Uint8 *dstPixels = (Uint8*)dst->pixels;
	const int dstPitch = dst->pitch;
	pool.run(jobs, [&](int job)
	{
		const int ya = (int)((long long)H * job / jobs);
		const int yb = (int)((long long)H * (job + 1) / jobs);
		for (int y = ya; y < yb; ++y)
		{
			const Uint32 *s = &big[(size_t)y * W];
			Uint32 *d = (Uint32*)(dstPixels + (size_t)y * dstPitch);
			for (int x = 0; x < W && x < dst->w; ++x)
			{
				const Uint32 p = s[x];
				const Uint32 a = p >> 24;
				if (!a) continue;
				if (a == 255)
				{
					d[x] = p;
					continue;
				}
				const Uint32 q = d[x];
				const Uint32 ia = 255 - a;
				const Uint32 r = (((p >> 16) & 0xFF) * a + ((q >> 16) & 0xFF) * ia) / 255;
				const Uint32 g = (((p >> 8) & 0xFF) * a + ((q >> 8) & 0xFF) * ia) / 255;
				const Uint32 b = ((p & 0xFF) * a + (q & 0xFF) * ia) / 255;
				d[x] = 0xFF000000u | (r << 16) | (g << 8) | b;
			}
		}
	});
	if (SDL_MUSTLOCK(dst)) SDL_UnlockSurface(dst);
}

/**
 * (Re)allocates the world layer: a true-color surface of k * base resolution.
 */
void Screen::allocateWorld()
{
	const int w = _baseWidth * _worldScale;
	const int h = _baseHeight * _worldScale;
	if (!_world || _world->w != w || _world->h != h)
	{
		std::tie(_worldBuffer, _world) = Surface::NewPair32Bit(w, h);
	}
	SDL_SetColorKey(_world.get(), 0, 0);
}

/**
 * Returns the world layer (only meaningful when the output is layered).
 */
SDL_Surface *Screen::getWorldSurface()
{
	if (!_world)
	{
		allocateWorld();
	}
	return _world.get();
}

/**
 * Changes the world layer scale factor and reallocates the layer.
 * @param scale k >= 1.
 */
void Screen::setWorldScale(int scale)
{
	if (scale < 1)
	{
		scale = 1;
	}
	_worldScaleFixed = true;
	if (scale != _worldScale)
	{
		_worldScale = scale;
		if (_layered)
		{
			resetDisplay(false);
		}
	}
}

/**
 * Composes the classic 8-bit layer over a true-color surface of world size:
 * every non-zero index is looked up in the layer's palette and written as an
 * opaque pixel, scaled by k with nearest neighbour; index 0 stays transparent
 * (exactly the SDL color-key convention every game surface already follows).
 * @param dst Surface of the world layer's size and format.
 */
void Screen::composeInto(SDL_Surface *dst) const
{
	if (!dst || !_surface || _surface->format->BitsPerPixel != 8)
	{
		return;
	}
	const SDL_Palette *pal = _surface->format->palette;
	Uint32 lut[256];
	for (int i = 0; i < 256; ++i)
	{
		SDL_Color c = { 0, 0, 0, 0 };
		if (pal && i < pal->ncolors)
		{
			c = pal->colors[i];
		}
		lut[i] = SDL_MapRGB(dst->format, c.r, c.g, c.b);
	}

	const int k = _worldScale;
	const int srcW = std::min(_surface->w, dst->w / k);
	const int srcH = std::min(_surface->h, dst->h / k);
	if (k >= 2 && k <= 6 && !_worldScaleFixed && Options::oxceHdUiSmooth)
	{
		// outside the battlescape the classic layer goes over the world with xBRZ (the look of the xBRZ
		// display filter), index 0 transparent: the HD pictures underneath show through
		composeSmooth(dst, lut, srcW, srcH, k);
		return;
	}
	if (SDL_MUSTLOCK(dst)) SDL_LockSurface(dst);
	const Uint8 *srcPixels = (const Uint8*)_surface->pixels;
	Uint8 *dstPixels = (Uint8*)dst->pixels;
	const int srcPitch = _surface->pitch;
	const int dstPitch = dst->pitch;
	// bands of base rows, on the render threads
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(srcH / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		const int ya = (int)((long long)srcH * job / jobs);
		const int yb = (int)((long long)srcH * (job + 1) / jobs);
		for (int y = ya; y < yb; ++y)
		{
			const Uint8 *srcRow = srcPixels + (size_t)y * srcPitch;
			for (int ky = 0; ky < k; ++ky)
			{
				Uint32 *dstRow = (Uint32*)(dstPixels + (size_t)(y * k + ky) * dstPitch);
				for (int x = 0; x < srcW; ++x)
				{
					const Uint8 idx = srcRow[x];
					if (idx)
					{
						const Uint32 value = lut[idx];
						Uint32 *d = dstRow + (size_t)x * k;
						for (int kx = 0; kx < k; ++kx)
						{
							d[kx] = value;
						}
					}
				}
			}
		}
	});
	if (SDL_MUSTLOCK(dst)) SDL_UnlockSurface(dst);
}

/**
 * Changes the 8bpp palette used to render the screen's contents.
 * @param colors Pointer to the set of colors.
 * @param firstcolor Offset of the first color to replace.
 * @param ncolors Amount of colors to replace.
 * @param immediately Apply palette changes immediately, otherwise wait for next blit.
 */
void Screen::setPalette(const SDL_Color* colors, int firstcolor, int ncolors, bool immediately)
{
	if (_numColors && (_numColors != ncolors) && (_firstColor != firstcolor))
	{
		// an initial palette setup has not been committed to the screen yet
		// just update it with whatever colors are being sent now
		memmove(&(deferredPalette[firstcolor]), colors, sizeof(SDL_Color)*ncolors);
		_numColors = 256; // all the use cases are just a full palette with 16-color follow-ups
		_firstColor = 0;
	}
	else
	{
		memmove(&(deferredPalette[firstcolor]), colors, sizeof(SDL_Color) * ncolors);
		_numColors = ncolors;
		_firstColor = firstcolor;
	}

	SDL_SetColors(_surface.get(), const_cast<SDL_Color *>(colors), firstcolor, ncolors);

	// defer actual update of screen until SDL_Flip()
	if (immediately && _screen->format->BitsPerPixel == 8 && SDL_SetColors(_screen, const_cast<SDL_Color *>(colors), firstcolor, ncolors) == 0)
	{
		Log(LOG_DEBUG) << "Display palette doesn't match requested palette";
	}

	// Sanity check
	/*
	SDL_Color *newcolors = _screen->format->palette->colors;
	for (int i = firstcolor, j = 0; i < firstcolor + ncolors; i++, j++)
	{
		Log(LOG_DEBUG) << (int)newcolors[i].r << " - " << (int)newcolors[i].g << " - " << (int)newcolors[i].b;
		Log(LOG_DEBUG) << (int)colors[j].r << " + " << (int)colors[j].g << " + " << (int)colors[j].b;
		if (newcolors[i].r != colors[j].r ||
			newcolors[i].g != colors[j].g ||
			newcolors[i].b != colors[j].b)
		{
			Log(LOG_ERROR) << "Display palette doesn't match requested palette";
			break;
		}
	}
	*/
}

/**
 * Returns the screen's 8bpp palette.
 * @return Pointer to the palette's colors.
 */
SDL_Color *Screen::getPalette() const
{
	return (SDL_Color*)deferredPalette;
}

/**
 * Returns the width of the screen.
 * @return Width in pixels.
 */
int Screen::getWidth() const
{
	return _screen->w;
}

/**
 * Returns the height of the screen.
 * @return Height in pixels
 */
int Screen::getHeight() const
{
	return _screen->h;
}

/**
 * Resets the screen surfaces based on the current display options,
 * as they don't automatically take effect.
 * @param resetVideo Reset display surface.
 */
void Screen::resetDisplay(bool resetVideo, bool noShaders)
{
#if defined __linux__ || defined _WIN32 || defined  __CYGWIN__
	Uint32 oldFlags = _flags;
#endif

	int width = Options::displayWidth;
	int height = Options::displayHeight;
	makeVideoFlags();

	// when layered, the internal buffer is the 8-bit classic layer whatever the display depth
	const int bufferBpp = _layered ? 8 : _bpp;
	if (!_surface || (_surface->format->BitsPerPixel != bufferBpp ||
		_surface->w != _baseWidth ||
		_surface->h != _baseHeight)) // don't reallocate _surface if not necessary, it's a waste of CPU cycles
	{
		if (bufferBpp == 32)
		{
			std::tie(_buffer, _surface) = Surface::NewPair32Bit(_baseWidth, _baseHeight);
		}
		else
		{
			std::tie(_buffer, _surface) = Surface::NewPair8Bit(_baseWidth, _baseHeight);
		}

		if (_surface->format->BitsPerPixel == 8)
		{
			SDL_SetColors(_surface.get(), deferredPalette, 0, 255);
		}
	}
	SDL_SetColorKey(_surface.get(), 0, 0); // turn off color key! (composeInto() handles transparency itself)
	if (_layered)
	{
		// outside the battlescape (which sets its own scale) the world layer follows the display: the HD
		// pictures of the interface are drawn into it at the display's resolution
		if (!_worldScaleFixed && _baseHeight > 0)
		{
			_worldScale = Options::oxceHdPictures ? std::max(1, std::min(6, (int)std::lround((double)height / _baseHeight))) : 1;
		}
		allocateWorld();
		HdUiArt::clearPrepared();
	}
	else
	{
		_world.reset();
		_worldBuffer.reset();
	}

	if (resetVideo || _screen->format->BitsPerPixel != _bpp)
	{
		Log(LOG_INFO) << "Attempting to set display to " << width << "x" << height << "x" << _bpp << "...";

#if defined __linux__ || defined _WIN32 || defined  __CYGWIN__
		// Workaround for segfault when switching to opengl
		if ((oldFlags & SDL_OPENGL) != (_flags & SDL_OPENGL))
		{
			Uint8 cursor = 0;
			char *_oldtitle = 0;
			SDL_WM_GetCaption(&_oldtitle, NULL);
			std::string title(_oldtitle);
			SDL_QuitSubSystem(SDL_INIT_VIDEO);
			SDL_InitSubSystem(SDL_INIT_VIDEO);

			// recreate operations done by `Game::Game` constructor
			SDL_ShowCursor(SDL_ENABLE);
			SDL_EnableUNICODE(1);
			CrossPlatform::setWindowIcon(IDI_ICON1, "openxcom.png");
			SDL_WM_SetCaption(title.c_str(), 0);
			SDL_WM_GrabInput(Options::captureMouse);
			SDL_SetCursor(SDL_CreateCursor(&cursor, &cursor, 1,1,0,0));
		}
#endif
		_screen = SDL_SetVideoMode(width, height, _bpp, _flags);
		if (_screen == 0)
		{
			Log(LOG_ERROR) << SDL_GetError();
			Log(LOG_INFO) << "Attempting to set display to default resolution...";
			_screen = SDL_SetVideoMode(640, 400, _bpp, _flags);
			if (_screen == 0)
			{
				if (_flags & SDL_OPENGL)
				{
					Options::useOpenGL = false;
				}
				throw Exception(SDL_GetError());
			}
		}
		Log(LOG_INFO) << "Display set to " << getWidth() << "x" << getHeight() << "x" << (int)_screen->format->BitsPerPixel << ".";
	}
	else
	{
		clear();
	}

	Options::displayWidth = getWidth();
	Options::displayHeight = getHeight();
	_scaleX = getWidth() / (double)_baseWidth;
	_scaleY = getHeight() / (double)_baseHeight;

	double pixelRatioY = 1.0;
	if (Options::nonSquarePixelRatio && !Options::allowResize)
	{
		pixelRatioY = 1.2;
	}
	bool cursorInBlackBands;
	if (!Options::keepAspectRatio)
	{
		cursorInBlackBands = false;
	}
	else if (Options::fullscreen)
	{
		cursorInBlackBands = Options::cursorInBlackBandsInFullscreen;
	}
	else if (!Options::borderless)
	{
		cursorInBlackBands = Options::cursorInBlackBandsInWindow;
	}
	else
	{
		cursorInBlackBands = Options::cursorInBlackBandsInBorderlessWindow;
	}

	if (_scaleX > _scaleY && Options::keepAspectRatio)
	{
		int targetWidth = (int)floor(_scaleY * (double)_baseWidth);
		_topBlackBand = _bottomBlackBand = 0;
		_leftBlackBand = (getWidth() - targetWidth) / 2;
		if (_leftBlackBand < 0)
		{
			_leftBlackBand = 0;
		}
		_rightBlackBand = getWidth() - targetWidth - _leftBlackBand;
		_cursorTopBlackBand = 0;

		if (cursorInBlackBands)
		{
			_scaleX = _scaleY;
			_cursorLeftBlackBand = _leftBlackBand;
		}
		else
		{
			_cursorLeftBlackBand = 0;
		}
	}
	else if (_scaleY > _scaleX && Options::keepAspectRatio)
	{
		int targetHeight = (int)floor(_scaleX * (double)_baseHeight * pixelRatioY);
		_topBlackBand = (getHeight() - targetHeight) / 2;
		if (_topBlackBand < 0)
		{
			_topBlackBand = 0;
		}
		_bottomBlackBand = getHeight() - targetHeight - _topBlackBand;
		if (_bottomBlackBand < 0)
		{
			_bottomBlackBand = 0;
		}
		_leftBlackBand = _rightBlackBand = 0;
		_cursorLeftBlackBand = 0;

		if (cursorInBlackBands)
		{
			_scaleY = _scaleX;
			_cursorTopBlackBand = _topBlackBand;
		}
		else
		{
			_cursorTopBlackBand = 0;
		}
	}
	else
	{
		_topBlackBand = _bottomBlackBand = _leftBlackBand = _rightBlackBand = _cursorTopBlackBand = _cursorLeftBlackBand = 0;
	}

	if (useOpenGL())
	{
#ifndef __NO_OPENGL
		OpenGL::checkErrors = Options::checkOpenGLErrors;
		if (_layered)
		{
			glOutput.init(_world->w, _world->h);
		}
		else
		{
			glOutput.init(_baseWidth, _baseHeight);
		}
		glOutput.linear = Options::useOpenGLSmoothing; // setting from shader file will override this, though
		if (!noShaders && FileMap::fileExists(Options::useOpenGLShader))
		{
			if (!glOutput.set_shader(Options::useOpenGLShader.c_str()))
			{
				Options::useOpenGLShader = "";
			}
		}
		glOutput.setVSync(Options::vSyncForOpenGL);
#endif
	}

	if (_screen->format->BitsPerPixel == 8)
	{
		setPalette(getPalette());
	}
}

/**
 * Returns the screen's X scale.
 * @return Scale factor.
 */
double Screen::getXScale() const
{
	return _scaleX;
}

/**
 * Returns the screen's Y scale.
 * @return Scale factor.
 */
double Screen::getYScale() const
{
	return _scaleY;
}

/**
 * Returns the screen's top black forbidden to cursor band's height.
 * @return Height in pixel.
 */
int Screen::getCursorTopBlackBand() const
{
	return _cursorTopBlackBand;
}

/**
 * Returns the screen's left black forbidden to cursor band's width.
 * @return Width in pixel.
 */
int Screen::getCursorLeftBlackBand() const
{
	return _cursorLeftBlackBand;
}

/**
 * Saves a screenshot of the screen's contents.
 * @param filename Filename of the PNG file.
 */
void Screen::screenshot(const std::string &filename) const
{
	SDL_Surface *screenshot = SDL_AllocSurface(0, getWidth() - getWidth()%4, getHeight(), 24, 0xff, 0xff00, 0xff0000, 0);

	if (useOpenGL())
	{
#ifndef __NO_OPENGL
		GLenum format = GL_RGB;

		for (int y = 0; y < getHeight(); ++y)
		{
			glReadPixels(0, getHeight()-(y+1), getWidth() - getWidth()%4, 1, format, GL_UNSIGNED_BYTE, ((Uint8*)screenshot->pixels) + y*screenshot->pitch);
		}
		glErrorCheck();
#endif
	}
	else
	{
		SDL_BlitSurface(_screen, 0, screenshot, 0);
	}
	std::vector<unsigned char> out;
	if (_screen->format->BitsPerPixel == 8 && Options::oxceRawScreenShots)
	{
		SDL_Color *palette = getPalette();
		lodepng::State state;
		for (size_t i = 0; i < 256; ++i)
		{
			SDL_Color color = palette[i];
			lodepng_palette_add(&state.info_png.color, color.r, color.g, color.b, 255);
			lodepng_palette_add(&state.info_raw, color.r, color.g, color.b, 255);
		}
		state.info_png.color.colortype = LCT_PALETTE; //if you comment this line, and create the above palette in info_raw instead, then you get the same image in a RGBA PNG.
		state.info_png.color.bitdepth = 8;
		state.info_raw.colortype = LCT_PALETTE;
		state.info_raw.bitdepth = 8;
		state.encoder.auto_convert = 0; //we specify ourselves exactly what output PNG color mode we want
		unsigned error = lodepng::encode(out, (const unsigned char *)(_surface->pixels), _surface->w, _surface->h, state);
		if (error)
		{
			Log(LOG_ERROR) << "Saving to PNG failed: " << lodepng_error_text(error);
		}
	}
	else
	{
		unsigned error = lodepng::encode(out, (const unsigned char *)(screenshot->pixels), getWidth() - getWidth()%4, getHeight(), LCT_RGB);
		if (error)
		{
			Log(LOG_ERROR) << "Saving to PNG failed: " << lodepng_error_text(error);
		}
	}

	SDL_FreeSurface(screenshot);

	CrossPlatform::writeFile(filename, out);
}

/**
 * HD test: writes the internal (base resolution, unscaled) buffer as an RGB PNG
 * and clears the pending request. Called by the game loop after all states
 * have been blitted, but before the FPS counter and the mouse cursor.
 */
void Screen::writeHdTestDump()
{
	if (_hdTestDumpPath.empty())
	{
		return;
	}
	if (_layered && _world)
	{
		// the frame as the player will see it: world layer with the classic layer composed on top
		Surface::UniqueBufferPtr tmpBuffer;
		Surface::UniqueSurfacePtr tmp;
		std::tie(tmpBuffer, tmp) = Surface::NewPair32Bit(_world->w, _world->h);
		SDL_SetColorKey(tmp.get(), 0, 0);
		SDL_BlitSurface(_world.get(), 0, tmp.get(), 0);
		composeInto(tmp.get());
		HdTest::savePngRgb(_hdTestDumpPath, tmp.get());
	}
	else
	{
		HdTest::savePngRgb(_hdTestDumpPath, _surface.get());
	}
	_hdTestDumpPath.clear();
}


/**
 * Check whether a 32bpp scaler has been selected.
 * @return if it is enabled with a compatible resolution.
 */
bool Screen::use32bitScaler()
{
	int w = Options::displayWidth;
	int h = Options::displayHeight;
	int baseW = Options::baseXResolution;
	int baseH = Options::baseYResolution;
	int maxScale = 0;

	if (Options::useHQXFilter)
	{
		maxScale = 4;
	}
	else if (Options::useXBRZFilter)
	{
		maxScale = 6;
	}

	for (int i = 2; i <= maxScale; i++)
	{
		if (w == baseW * i && h == baseH * i)
		{
			return true;
		}
	}
	return false;
}

/**
 * Check if OpenGL is enabled.
 * @return if it is enabled.
 */
bool Screen::useOpenGL()
{
#ifdef __NO_OPENGL
	return false;
#else
	return Options::useOpenGL;
#endif
}

/**
 * Gets the Horizontal offset from the mid-point of the screen, in pixels.
 * @return the horizontal offset.
 */
int Screen::getDX() const
{
	return (_baseWidth - ORIGINAL_WIDTH) / 2;
}

/**
 * Gets the Vertical offset from the mid-point of the screen, in pixels.
 * @return the vertical offset.
 */
int Screen::getDY() const
{
	return (_baseHeight - ORIGINAL_HEIGHT) / 2;
}

/**
 * Changes a given scale, and if necessary, switch the current base resolution.
 * @param type the new scale level.
 * @param width reference to which x scale to adjust.
 * @param height reference to which y scale to adjust.
 * @param change should we change the current scale.
 */
void Screen::updateScale(int type, int &width, int &height, bool change)
{
	// a new kind of screen: its world scale is derived from the display again (until a state sets one)
	if (_current) _current->_worldScaleFixed = false;
	double pixelRatioY = 1.0;

	if (Options::nonSquarePixelRatio)
	{
		pixelRatioY = 1.2;
	}

	switch (type)
	{
	case SCALE_15X:
		width = Screen::ORIGINAL_WIDTH * 1.5;
		height = Screen::ORIGINAL_HEIGHT * 1.5;
		break;
	case SCALE_2X:
		width = Screen::ORIGINAL_WIDTH * 2;
		height = Screen::ORIGINAL_HEIGHT * 2;
		break;
	case SCALE_SCREEN_DIV_10:
		width = Options::displayWidth / 10.0;
		height = Options::displayHeight / pixelRatioY / 10.0;
		break;
	case SCALE_SCREEN_DIV_8:
		width = Options::displayWidth / 8.0;
		height = Options::displayHeight / pixelRatioY / 8.0;
		break;
	case SCALE_SCREEN_DIV_6:
		width = Options::displayWidth / 6.0;
		height = Options::displayHeight / pixelRatioY / 6.0;
		break;
	case SCALE_SCREEN_DIV_5:
		width = Options::displayWidth / 5.0;
		height = Options::displayHeight / pixelRatioY / 5.0;
		break;
	case SCALE_SCREEN_DIV_4:
		width = Options::displayWidth / 4.0;
		height = Options::displayHeight / pixelRatioY / 4.0;
		break;
	case SCALE_SCREEN_DIV_3:
		width = Options::displayWidth / 3.0;
		height = Options::displayHeight / pixelRatioY / 3.0;
		break;
	case SCALE_SCREEN_DIV_2:
		width = Options::displayWidth / 2.0;
		height = Options::displayHeight / pixelRatioY  / 2.0;
		break;
	case SCALE_SCREEN:
		width = Options::displayWidth;
		height = Options::displayHeight / pixelRatioY;
		break;
	case SCALE_ORIGINAL:
	default:
		width = Screen::ORIGINAL_WIDTH;
		height = Screen::ORIGINAL_HEIGHT;
		break;
	}

	// don't go under minimum resolution... it's bad, mmkay?
	width = std::max(width, Screen::ORIGINAL_WIDTH);
	height = std::max(height, Screen::ORIGINAL_HEIGHT);

	if (change && (Options::baseXResolution != width || Options::baseYResolution != height))
	{
		Options::baseXResolution = width;
		Options::baseYResolution = height;
	}
}

}
