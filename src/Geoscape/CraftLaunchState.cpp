/*
 * Copyright 2010-2026 OpenXcom Developers.
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
#include "CraftLaunchState.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <utility>
#include "../Basescape/BaseView.h"
#include "../Engine/Action.h"
#include "../Engine/FileMap.h"
#include "../Engine/Game.h"
#include "../Engine/HdGpuWorld.h"
#include "../Engine/HdSprites.h"
#include "../Engine/HdUi.h"
#include "../Engine/HdVideo.h"
#include "../Engine/HdWorkers.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/Screen.h"
#include "../Engine/Sound.h"
#include "../Interface/Cursor.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleBaseFacility.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/Base.h"
#include "../Savegame/BaseFacility.h"
#include "../Savegame/Craft.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace
{
/// A key or a click this early is the tail of the order that sent the craft, not a skip.
const Uint32 SKIP_AFTER_MS = 300;
/// However long a clip claims to be, it never holds the game longer.
const double MAX_CLIP_SECONDS = 15.0;
/// Leaving: the whole base a moment, the camera comes down on the hangar, stays there, the picture goes black.
const Uint32 IN_LOOK_MS = 500;
const Uint32 IN_ZOOM_MS = 1800;
/// ... and there the order to start: the alarm (drawAlarm, hd/LAUNCH/start.wav)
const Uint32 IN_HOLD_MS = 1400;
/// Coming back: the hangar comes out of the black, stays a moment, the camera pulls back, the base stays.
const Uint32 OUT_HOLD_MS = 800;
const Uint32 OUT_ZOOM_MS = 1500;
const Uint32 OUT_REST_MS = 600;
const Uint32 FADE_MS = 300;
/// The base view: the stock 6 x 6 grid.
const int VIEW_SIZE = 192;
/// A cell of the base grid (BaseView::GRID_SIZE).
const int GRID = 32;
/// The whole base with a little black around it; the hangar with some of its neighbours.
const double WHOLE_MARGIN = 1.08;
const double HANGAR_MARGIN = 1.35;
/// Headless checks: OXCE_HD_DUMP_LAUNCH=<prefix> dumps the scene at these moments (ms from its
/// start) as <prefix>_0.png ...: leaving - the base, the way down, the hangar, the clip; coming
/// back - the clip, the hangar, the way back, the base.
const Uint32 TEST_MOMENTS[] = { 300, 1400, 2850, 3350, 6000, 7600, 8600, 9500 };
/// The alarm: the wash pulses, the stripes flash, the beacons turn (per second).
const double ALARM_PULSE_HZ = 2.2;
const Uint32 ALARM_STRIPES_MS = 250;
const double BEACON_TURNS = 1.5;
const double PI = 3.14159265358979323846;

/// Mixes a colour into a pixel: `a` of 1.
inline Uint32 blendRgb(Uint32 px, int r, int g, int b, double a)
{
	const int pr = (px >> 16) & 0xFF, pg = (px >> 8) & 0xFF, pb = px & 0xFF;
	const int nr = (int)(pr + (r - pr) * a), ng = (int)(pg + (g - pg) * a), nb = (int)(pb + (b - pb) * a);
	return (px & 0xFF000000u) | ((Uint32)nr << 16) | ((Uint32)ng << 8) | (Uint32)nb;
}

/// Adds light to a pixel, saturating.
inline Uint32 addRgb(Uint32 px, double r, double g, double b)
{
	const int nr = std::min(255, (int)(((px >> 16) & 0xFF) + r)), ng = std::min(255, (int)(((px >> 8) & 0xFF) + g)), nb = std::min(255, (int)((px & 0xFF) + b));
	return (px & 0xFF000000u) | ((Uint32)nr << 16) | ((Uint32)ng << 8) | (Uint32)nb;
}

double ease(double t)
{
	t = std::min(1.0, std::max(0.0, t));
	return t * t * (3.0 - 2.0 * t);
}

/// The brightness (of 256) of a phase `length` long at `t`: out of the black and back into it.
int fade(Uint32 t, Uint32 length, bool in, bool out)
{
	double b = 1.0;
	if (in)
	{
		b = std::min(b, t / (double)FADE_MS);
	}
	if (out)
	{
		b = std::min(b, (length > t ? length - t : 0) / (double)FADE_MS);
	}
	return (int)(256.0 * std::min(1.0, std::max(0.0, b)) + 0.5);
}

}

CraftLaunchState::CraftLaunchState(std::unique_ptr<HdVideo> video, const Craft *craft, Base *base, bool landing) :
	_video(std::move(video)), _craft(craft), _base(base), _landing(landing), _phase(PHASE_CLIP)
{
	if (_base)
	{
		// the base view in the middle of the screen, as the basescape draws it (the world layer is
		// k times the base resolution, so it is drawn at the same scale)
		Screen *screen = _game->getScreen();
		const int k = std::max(1, screen->getWorldScale());
		SDL_Surface *world = screen->getWorldSurface();
		const int baseW = world ? world->w / k : Screen::ORIGINAL_WIDTH, baseH = world ? world->h / k : Screen::ORIGINAL_HEIGHT;
		_view = new BaseView(VIEW_SIZE, VIEW_SIZE, std::max(0, (baseW - VIEW_SIZE) / 2), std::max(0, (baseH - VIEW_SIZE) / 2));
		setInterface("basescape");
		add(_view, "baseView", "basescape");
		auto *lights = _game->getMod()->getInterface("basescape")->getElementOptional("trafficLights");
		if (lights)
		{
			_view->setOtherColors(lights->color, lights->color2, lights->border, !lights->TFTDMode);
		}
		_view->setTexture(_game->getMod()->getSurfaceSet("BASEBITS.PCK"));
		_view->setBase(_base);
		_view->setHdTime(_game->getSavedGame()->getTime());
		if (!_landing)
		{
			// it is out already: the view draws it in its hangar all the same
			_view->setHdDeparting(_craft);
			// the order to start; no mixer (a headless run), no sound
			const std::string start = HdSprites::artPath("LAUNCH/start.wav");
			if (Mix_QuerySpec(nullptr, nullptr, nullptr) != 0 && FileMap::fileExists(start))
			{
				_alarm.reset(new Sound());
				_alarm->load(start);
			}
		}
	}
	else
	{
		// the geoscape palette stays, so nothing flickers in the frame the scene closes on
		setStatePalette(_game->getScreen()->getPalette());
	}
	_phase = (_view && !_landing) ? PHASE_BASE_IN : PHASE_CLIP;
}

CraftLaunchState::~CraftLaunchState()
{
}

State *CraftLaunchState::create(const Craft *craft, bool landing)
{
	if (!craft)
	{
		return nullptr;
	}
	return create(craft->getRules()->getType(), craft->getNumTotalSoldiers(), landing, craft);
}

State *CraftLaunchState::create(const std::string &craftType, int soldiers, bool landing)
{
	return create(craftType, soldiers, landing, nullptr);
}

/**
 * 0 off, 1 only a craft with soldiers aboard (the mission ones), 2 every craft that has a clip.
 */
State *CraftLaunchState::create(const std::string &craftType, int soldiers, bool landing, const Craft *craft)
{
	if (Options::oxceHdCraftLaunch <= 0 || (Options::oxceHdCraftLaunch == 1 && soldiers <= 0))
	{
		return nullptr;
	}
	Screen *screen = Screen::current();
	if (!screen || !screen->isLayered() || screen->getWorldScale() < 2)
	{
		return nullptr;
	}
	const std::string path = HdSprites::artPath("LAUNCH/" + craftType + (landing ? ".land.mpg" : ".mpg"));
	if (!FileMap::fileExists(path))
	{
		return nullptr;
	}
	std::unique_ptr<HdVideo> video(new HdVideo());
	if (!video->open(path))
	{
		Log(LOG_WARNING) << "HD craft launch: cannot play " << path;
		return nullptr;
	}
	Log(LOG_INFO) << "HD craft launch: " << path << (craft && craft->getBase() ? " from the base" : "");
	return new CraftLaunchState(std::move(video), craft, craft ? craft->getBase() : nullptr, landing);
}

void CraftLaunchState::init()
{
	State::init();
	_cursorWasVisible = _game->getCursor()->getVisible();
	_game->getCursor()->setVisible(false);
	_startTicks = _lastTicks = SDL_GetTicks();
	enter(_phase);
}

void CraftLaunchState::enter(Phase phase)
{
	_phase = phase;
	_phaseStart = SDL_GetTicks();
}

void CraftLaunchState::close()
{
	if (_done)
	{
		return;
	}
	_done = true;
	_game->getCursor()->setVisible(_cursorWasVisible);
	_game->popState();
}

void CraftLaunchState::handle(Action *action)
{
	const Uint8 type = action->getDetails()->type;
	if ((type == SDL_KEYDOWN || type == SDL_MOUSEBUTTONDOWN) && SDL_GetTicks() - _startTicks >= SKIP_AFTER_MS)
	{
		close();
	}
}

void CraftLaunchState::think()
{
	const Uint32 now = SDL_GetTicks();
	const Uint32 t = now - _phaseStart;
	switch (_phase)
	{
	case PHASE_BASE_IN:
		if (_hangarKnown && t >= IN_LOOK_MS + IN_ZOOM_MS && !_alarmSounded)
		{
			// the order to start
			_alarmSounded = true;
			if (_alarm)
			{
				_alarm->play();
			}
		}
		if (t >= IN_LOOK_MS + IN_ZOOM_MS + IN_HOLD_MS)
		{
			enter(PHASE_CLIP);
		}
		break;
	case PHASE_CLIP:
		// a stall longer than a few frames (loading, a dragged window) does not jump the clip ahead
		_video->advance(std::min(now - _lastTicks, 100u) / 1000.0);
		if (_video->ended() || _video->time() >= MAX_CLIP_SECONDS)
		{
			if (_view && _landing)
			{
				enter(PHASE_BASE_OUT);
			}
			else
			{
				close();
			}
		}
		break;
	case PHASE_BASE_OUT:
		if (t >= OUT_HOLD_MS + OUT_ZOOM_MS + OUT_REST_MS)
		{
			close();
		}
		break;
	}
	_lastTicks = now;
}

void CraftLaunchState::blit()
{
	Screen *screen = _game->getScreen();
	if (!screen->isLayered() || _done)
	{
		return;
	}
	const Uint32 t = SDL_GetTicks() - _phaseStart;
	switch (_phase)
	{
	case PHASE_BASE_IN:
		if (!_hangarKnown)
		{
			// the first frame of the base loads its HD pictures (seconds, the first time in a game):
			// it is drawn black, and the scene's clock starts after it
			drawBase(0.0, 0);
			_startTicks = _lastTicks = SDL_GetTicks();
			enter(PHASE_BASE_IN);
			break;
		}
		drawBase(ease((t - std::min(t, IN_LOOK_MS)) / (double)IN_ZOOM_MS), fade(t, IN_LOOK_MS + IN_ZOOM_MS + IN_HOLD_MS, true, true),
			t >= IN_LOOK_MS + IN_ZOOM_MS ? (int)(t - IN_LOOK_MS - IN_ZOOM_MS) : -1);
		break;
	case PHASE_CLIP:
		_video->draw(screen->getWorldSurface());
		break;
	case PHASE_BASE_OUT:
		if (!_hangarKnown)
		{
			drawBase(1.0, 0);
			enter(PHASE_BASE_OUT);
			break;
		}
		drawBase(1.0 - ease((t - std::min(t, OUT_HOLD_MS)) / (double)OUT_ZOOM_MS), fade(t, OUT_HOLD_MS + OUT_ZOOM_MS + OUT_REST_MS, true, true));
		break;
	}
	static const char *testPrefix = getenv("OXCE_HD_DUMP_LAUNCH");
	if (testPrefix && *testPrefix && _testNext < sizeof(TEST_MOMENTS) / sizeof(TEST_MOMENTS[0])
		&& SDL_GetTicks() - _startTicks >= TEST_MOMENTS[_testNext] && !screen->hasHdTestDumpRequest())
	{
		Log(LOG_INFO) << "HD craft launch: dump " << _testNext << " at " << (SDL_GetTicks() - _startTicks) << " ms, phase " << (int)_phase << " at " << t << " ms";
		screen->requestHdTestDump(std::string(testPrefix) + "_" + std::to_string(_testNext++) + ".png");
	}
}

/**
 * The base view drawn as the basescape draws it (HD pictures into the world layer, the classic
 * layer over them), read back and enlarged over the whole world layer.
 */
void CraftLaunchState::drawBase(double zoom, int bright, int alarmMs)
{
	Screen *screen = _game->getScreen();
	SDL_Surface *world = screen->getWorldSurface();
	SDL_Surface *classic = screen->getSurface();
	const int k = screen->getWorldScale();
	if (!world || !_view || k < 1)
	{
		return;
	}
	// a writer the video card does not take (HdGpuWorld)
	HdGpuWorld::instance().cpu(world, "the craft launch");
	// the view writes the craft of each hangar into the facilities while it draws, and a hangar lost
	// in a base defence takes its craft with it (Base::destroyFacility): what it wrote is put back
	std::vector<std::pair<BaseFacility*, Craft*>> held;
	for (auto *fac : *_base->getFacilities())
	{
		held.push_back(std::make_pair(fac, fac->getCraftForDrawing()));
	}
	_view->blit(classic);
	if (!_hangarKnown)
	{
		Log(LOG_INFO) << "HD craft launch: world " << world->w << "x" << world->h << " k " << k << ", view at " << _view->getX() << "," << _view->getY() << " " << _view->getWidth() << "x" << _view->getHeight();
		for (const auto *fac : *_base->getFacilities())
		{
			if (fac->getCraftForDrawing() == _craft && _craft)
			{
				_hangarX = fac->getX() * GRID;
				_hangarY = fac->getY() * GRID;
				_hangarW = fac->getRules()->getSizeX() * GRID;
				_hangarH = fac->getRules()->getSizeY() * GRID;
				_hangarKnown = true;
				break;
			}
		}
		if (!_hangarKnown)
		{
			// no hangar holds it (a mod's craft without one): the middle of the base
			_hangarW = _hangarH = 2 * GRID;
			_hangarX = _hangarY = (VIEW_SIZE - _hangarW) / 2;
			_hangarKnown = true;
		}
	}
	for (const auto &h : held)
	{
		h.first->setCraftForDrawing(h.second);
	}
	// the classic layer goes into the world layer now (as Screen::flip would), so the enlargement
	// takes both; with the HD interface every blit was mirrored there already
	if (!HdUi::active())
	{
		screen->composeInto(world);
	}
	SDL_FillRect(classic, nullptr, 0);

	// the view, read back from the world layer
	const int vx = _view->getX() * k, vy = _view->getY() * k, vs = VIEW_SIZE * k;
	_shot.assign((size_t)vs * vs, SDL_MapRGB(world->format, 0, 0, 0));
	for (int y = 0; y < vs; ++y)
	{
		const int wy = vy + y;
		if (wy < 0 || wy >= world->h)
		{
			continue;
		}
		const int x0 = std::max(0, -vx), x1 = std::min(vs, world->w - vx);
		if (x0 < x1)
		{
			const Uint32 *row = (const Uint32*)((const Uint8*)world->pixels + (size_t)wy * world->pitch) + vx;
			std::copy(row + x0, row + x1, _shot.begin() + (size_t)y * vs + x0);
		}
	}

	drawAlarm(alarmMs, k);

	// the area shown: the whole base at 0, the hangar at 1, the size eased on a log scale so the
	// camera comes down at an even pace; the screen's aspect, so it fills the screen
	const double aspect = world->w / (double)world->h;
	const double h0 = VIEW_SIZE * WHOLE_MARGIN;
	const double h1 = std::max(_hangarH, _hangarW / aspect) * HANGAR_MARGIN;
	const double rh = std::exp(std::log(h0) + (std::log(h1) - std::log(h0)) * zoom);
	const double cx = VIEW_SIZE / 2.0 + (_hangarX + _hangarW / 2.0 - VIEW_SIZE / 2.0) * zoom;
	const double cy = VIEW_SIZE / 2.0 + (_hangarY + _hangarH / 2.0 - VIEW_SIZE / 2.0) * zoom;
	const double rw = rh * aspect;
	HdVideo::drawFitted(_shot.data(), vs, vs, (cx - rw / 2.0) * k, (cy - rh / 2.0) * k, rw * k, rh * k, world, bright);
}

/**
 * The order to start, over the hangar in the shot of the base (`ms` since it was given, below 0 none):
 * a red wash pulsing, yellow and black stripes flashing along the hangar's edge, a turning beacon
 * in each corner.
 */
void CraftLaunchState::drawAlarm(int ms, int k)
{
	const int vs = VIEW_SIZE * k;
	if (ms < 0 || !_hangarKnown || _shot.size() != (size_t)vs * vs)
	{
		return;
	}
	const int x0 = std::max(0, (int)std::floor(_hangarX * k)), y0 = std::max(0, (int)std::floor(_hangarY * k));
	const int x1 = std::min(vs, (int)std::ceil((_hangarX + _hangarW) * k)), y1 = std::min(vs, (int)std::ceil((_hangarY + _hangarH) * k));
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	const double t = ms / 1000.0;
	const double come = std::min(1.0, ms / (double)ALARM_STRIPES_MS);
	const double wash = 0.35 * come * (0.5 + 0.5 * std::sin(t * 2.0 * PI * ALARM_PULSE_HZ));
	const bool stripes = (ms / ALARM_STRIPES_MS) % 2 == 0;
	const int band = 3 * k, half = 4 * k;
	const double inset = 6.0 * k, radius = 24.0 * k, core = 2.5 * k;
	const double bx[4] = { x0 + inset, x1 - inset, x1 - inset, x0 + inset };
	const double by[4] = { y0 + inset, y0 + inset, y1 - inset, y1 - inset };
	double rc[4], rs[4];
	for (int i = 0; i < 4; ++i)
	{
		const double rot = t * 2.0 * PI * BEACON_TURNS + i * PI / 2.0;
		rc[i] = std::cos(rot);
		rs[i] = std::sin(rot);
	}

	HdWorkers &pool = HdWorkers::instance();
	const int rows = y1 - y0;
	const int jobs = std::max(1, std::min(rows / 16, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		const int ya = y0 + (int)((long long)rows * job / jobs);
		const int yb = y0 + (int)((long long)rows * (job + 1) / jobs);
		for (int y = ya; y < yb; ++y)
		{
			Uint32 *row = _shot.data() + (size_t)y * vs;
			for (int x = x0; x < x1; ++x)
			{
				Uint32 px = blendRgb(row[x], 255, 30, 20, wash);
				if (stripes && (x - x0 < band || x1 - 1 - x < band || y - y0 < band || y1 - 1 - y < band))
				{
					const bool yellow = ((x + y) / half) % 2 == 0;
					px = yellow ? blendRgb(px, 255, 200, 0, 0.85 * come) : blendRgb(px, 20, 20, 20, 0.85 * come);
				}
				for (int i = 0; i < 4; ++i)
				{
					const double dx = x + 0.5 - bx[i], dy = y + 0.5 - by[i];
					const double d2 = dx * dx + dy * dy;
					if (d2 >= radius * radius)
					{
						continue;
					}
					const double d = std::sqrt(d2);
					double beam;
					if (d < core)
					{
						beam = 1.0;
					}
					else
					{
						const double c = std::max(0.0, (dx * rc[i] + dy * rs[i]) / d);
						// a narrow beam and a faint glow all round
						const double c2 = c * c;
						beam = (c2 * c2 * 1.3 + 0.12 * core / d) * (1.0 - d / radius);
					}
					beam *= come;
					px = addRgb(px, 255.0 * beam, 190.0 * beam, 110.0 * beam);
				}
				row[x] = px;
			}
		}
	});
}

}
