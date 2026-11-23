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
#include "Map.h"
#include "MapHd.h"
#include "Camera.h"
#include "CollapsePilot.h"
#include "UnitSprite.h"
#include "ItemSprite.h"
#include "Pathfinding.h"
#include "TileEngine.h"
#include "Projectile.h"
#include "ProjectileFlyBState.h"
#include "Explosion.h"
#include "BattlescapeState.h"
#include "Particle.h"
#include "../Mod/Mod.h"
#include "../Engine/Action.h"
#include "../Engine/SurfaceSet.h"
#include "../Engine/Timer.h"
#include "../Engine/Language.h"
#include "../Engine/Palette.h"
#include "../Engine/Game.h"
#include "../Engine/Screen.h"
#include "../Engine/HdTest.h"
#include "../Engine/HdBattleHud.h"
#include "../Engine/HdBlit.h"
#include "../Engine/HdCanvas.h"
#include "../Engine/HdFx.h"
#include "../Engine/HdGentle.h"
#include "../Engine/HdGpuWorld.h"
#include "../Engine/HdKillCam.h"
#include "../Engine/HdLab.h"
#include "../Engine/HdSmoke.h"
#include "../Engine/HdShots.h"
#include "../Engine/HdFire.h"
#include "../Engine/HdSprites.h"
#include "../Engine/HdTurn.h"
#include "../Engine/HdTurnGroups.h"
#include "../Engine/HdUi.h"
#include "../Engine/HdWorkers.h"
#include <chrono>
#include <climits>
#include <cmath>
#include <map>
#include <sstream>
#include <unordered_set>
#include "../Engine/FileMap.h"
#include "../Engine/ShaderDraw.h"
#include "../Engine/ShaderMove.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/BattleItem.h"
#include "../Ufopaedia/Ufopaedia.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleInterface.h"
#include "../Mod/MapDataSet.h"
#include "../Mod/MapData.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleEnviroEffects.h"
#include "BattlescapeMessage.h"
#include "AiProbe.h"
#include "../Savegame/SavedGame.h"
#include "../Interface/NumberText.h"
#include "../Interface/Text.h"
#include "../fmath.h"

namespace OpenXcom
{

/// Bloody footprints (Options::oxceHdBloodSteps, XP-000421): how many tiles after the blood a unit leaves them, how many prints the map keeps and
/// one tile keeps, the looks of a print (HD_STEP_PATTERNS), the opacity of a fresh, a middle and an old one (the age spread over the time they last,
/// Options::oxceHdBloodStepsLife: 1..10 turns, HD_STEP_ALWAYS = they do not go by time), the red when the blood has no colour of its own (or the player
/// wants red), and the kind of a print that is not a sole: the drops of a wounded unit on the move.
const int HD_STEP_TILES = 2, HD_STEP_MAX = 240, HD_STEP_PER_TILE = 3, HD_STEP_PATTERNS = 4, HD_STEP_ALPHA[3] = { 200, 150, 105 }, HD_STEP_RED = 0x8E1212,
	HD_STEP_ALWAYS = 11, HD_STEP_DROPS = 8, HD_STEP_FRAMES_MAX = 1200;

/// Turns a print lasts by the setting (the slider's 11 = always: 0).
int hdStepLife()
{
	const int life = Options::oxceHdBloodStepsLife;
	return life >= HD_STEP_ALWAYS ? 0 : std::max(1, life);
}

/// A hash of numbers for the looks of the prints (Map::hdStepFrame, hdObserveSteps): its own state, the battle's random numbers are not touched.
static Uint32 hdStepMix(Uint32 x)
{
	x ^= x >> 16;
	x *= 0x7FEB352DU;
	x ^= x >> 15;
	x *= 0x846CA68BU;
	x ^= x >> 16;
	return x;
}

/// The age of a print in turns -> 0 fresh, 1 middle, 2 old; the time it lasts is spread in three (a print that is always there ages over ten turns).
int hdStepTier(int age)
{
	const int life = hdStepLife() > 0 ? hdStepLife() : 10;
	return std::max(0, std::min(2, age * 3 / life));
}

/**
 * One print on a floor diamond (the bottom 32x16 of a 32x40 frame, k times), by the look of the walker (`kind`, HdFx::Track), turned to the way of the
 * step (one of eight). `variant` 0/1: one foot of a unit of one tile, left or right of the middle; 2..5: the quarter (x + 2 y) of the four tiles
 * of a 2x2 body. A boot is three ovals (forefoot, arch, heel); a bare foot is a heel, an arch, a ball and five toes (the big one inside); a paw
 * is a pad, four toe pads and four claws; a wheel is two ruts with a cross tread, a track is two wide bands with plates. A big walker (a 2x2 body)
 * leaves a print on each of its four tiles, 1.35 times bigger; wheels and tracks run on all four, two lanes a tile apart, so the ruts join at the tile edges.
 * Edges are smooth (a signed distance with a pixel of grace), the print is cut by the diamond itself. Drawn once for the key and kept for the battle.
 * `pattern` (HD_STEP_PATTERNS looks of one print): 0 plain, the others turned, shifted, larger or smaller and worn in patches; the kind HD_STEP_DROPS
 * is the blood of a wounded unit on the move: round drops along its way (`variant` 1: more and larger).
 */
const HdFrame &Map::hdStepFrame(int dx, int dy, int variant, int kind, int rgb, int tier, int pattern)
{
	const unsigned long long key = ((unsigned long long)kind << 48) | ((unsigned long long)(rgb & 0xFFFFFF) << 24) | ((unsigned long long)pattern << 20)
		| ((unsigned long long)_k << 12) | ((unsigned long long)((dx + 1) * 3 + (dy + 1)) << 8) | ((unsigned long long)variant << 4) | (unsigned long long)tier;
	auto it = _hdStepFrames.find(key);
	if (it != _hdStepFrames.end())
	{
		return it->second;
	}
	HdFrame &f = _hdStepFrames[key];
	// a dent in snow (the flag is in the key already): the look is the kind's, the edge is softer and the opacity its own
	const bool snow = (kind & HD_STEP_SNOW) != 0;
	kind &= ~HD_STEP_SNOW;
	const int k = _k;
	f.width = 32 * k;
	f.height = 16 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	// the cell is the square u, v in [-0.5, 0.5] (u along the map's x, v along its y); screen X = u - v, Y = u + v
	const double len = std::sqrt((double)(dx * dx + dy * dy));
	const double hx0 = dx / len, hy0 = dy / len;
	const bool drops = kind == HD_STEP_DROPS;
	const bool lanes = kind == HdFx::TRACK_WHEEL || kind == HdFx::TRACK_CRAWLER;
	// the looks of one print (HD_STEP_PATTERNS): 0 as it is drawn plain; the others turn it a little, shift it, make it a bit larger or smaller and wear
	// it in places (patches of the noise below); the ruts of wheels and tracks must join at the tile's edges, so they only wear; drops have their own scatter
	static const double PAT_ANGLE[HD_STEP_PATTERNS] = { 0.0, 0.2, -0.17, 0.09 }, PAT_SHIFT_S[HD_STEP_PATTERNS] = { 0.0, 0.035, -0.04, 0.015 },
		PAT_SHIFT_T[HD_STEP_PATTERNS] = { 0.0, -0.045, 0.035, 0.05 }, PAT_SCALE[HD_STEP_PATTERNS] = { 1.0, 0.94, 1.07, 0.98 }, PAT_WEAR[HD_STEP_PATTERNS] = { 0.0, 0.85, 0.6, 0.75 };
	const int pat = std::max(0, std::min(HD_STEP_PATTERNS - 1, pattern));
	const bool moves = !lanes && !drops;
	const double ang = moves ? PAT_ANGLE[pat] : 0.0, pscale = moves ? PAT_SCALE[pat] : 1.0;
	const double hx = hx0 * std::cos(ang) - hy0 * std::sin(ang), hy = hx0 * std::sin(ang) + hy0 * std::cos(ang), qx = -hy, qy = hx;
	const double shiftU = moves ? PAT_SHIFT_S[pat] * hx + PAT_SHIFT_T[pat] * qx : 0.0, shiftV = moves ? PAT_SHIFT_S[pat] * hy + PAT_SHIFT_T[pat] * qy : 0.0;
	const bool body = variant >= 2 && !drops;
	const int quarter = body ? variant - 2 : 0;
	const bool right = body ? (((quarter & 1) + (quarter >> 1)) & 1) != 0 : variant != 0;
	double sg = right ? 1.0 : -1.0, sc = drops ? 1.0 : (body ? 1.35 : 1.0) * (kind == HdFx::TRACK_BARE || kind == HdFx::TRACK_PAW ? 1.3 : 1.0),
		off = drops ? 0.0 : sg * (body ? 0.1 : 0.12), lead = 0.0;
	// a dent in snow of a one-tile walker (XP-000574, Vitali 14.11): two feet a tile, half the size, one ahead of the other; `variant` says which
	// foot leads. The blood's prints and the 2x2 bodies keep one print a tile.
	const bool pair = snow && moves && !body;
	const double sc1 = sc;
	struct Oval { double ahead, across, a, b; };
	Oval ovals[24];
	int count = 0;
	auto add = [&](double ahead, double across, double a, double b) { if (count < 24) ovals[count++] = Oval{ lead + ahead * sc, off + across * sc, a * sc, b * sc }; };
	// value noise on a grid of a quarter of a tile (the pattern's own), smooth between the nodes
	auto node = [pat](int ix, int iy) { return (hdStepMix((Uint32)ix * 374761393U + (Uint32)iy * 668265263U + (Uint32)pat * 1274126177U) & 0xFFFF) / 65535.0; };
	auto wear = [&](double u, double v)
	{
		const double gu = (u + 0.5) * 4.0 + 8.0, gv = (v + 0.5) * 4.0 + 8.0;
		const int iu = (int)std::floor(gu), iv = (int)std::floor(gv);
		double fu = gu - iu, fv = gv - iv;
		fu = fu * fu * (3.0 - 2.0 * fu);
		fv = fv * fv * (3.0 - 2.0 * fv);
		const double n = (node(iu, iv) * (1 - fu) + node(iu + 1, iv) * fu) * (1 - fv) + (node(iu, iv + 1) * (1 - fu) + node(iu + 1, iv + 1) * fu) * fv;
		double w = std::min(1.0, std::max(0.0, (n - 0.5) / 0.17));
		w = w * w * (3.0 - 2.0 * w);
		return 1.0 - PAT_WEAR[pat] * w;
	};
	if (drops)
	{
		// the drops of a wounded unit on the move: along its way through the tile, a few round ones, some pulled out along the way, some with a small one beside;
		// the heavy variant (many wounds) has more and larger ones
		const Uint32 seed = hdStepMix((Uint32)(pat * 7919 + variant * 104729 + (dx + 1) * 3 + (dy + 1) + 17));
		auto rnd = [seed](int i) { return (hdStepMix(seed * 2654435761U + (Uint32)i * 40503U) & 0xFFFF) / 65535.0; };
		const int n = 4 + (pat & 1) + 3 * (variant ? 1 : 0);
		for (int i = 0; i < n; ++i)
		{
			const double ahead = -0.36 + 0.72 * (i + 0.2 + 0.6 * rnd(i * 5)) / n, across = (rnd(i * 5 + 1) - 0.5) * 0.30,
				rad = (variant ? 0.045 : 0.03) * (0.6 + 0.8 * rnd(i * 5 + 2)), stretch = 1.1 + 0.5 * rnd(i * 5 + 3);
			add(ahead, across, rad * stretch, rad);
			if (rnd(i * 5 + 4) > 0.5 && count < 16)
			{
				add(ahead + 0.05 + rad, across + (rnd(i * 5 + 4) > 0.75 ? 0.05 : -0.05), 0.012, 0.012);
			}
		}
	}
	else for (int foot = 0; foot < (pair ? 2 : 1); ++foot)
	{
	if (pair)
	{
		sg = (foot == 0) == right ? 1.0 : -1.0;
		sc = sc1 * 0.5;
		off = sg * 0.07;
		lead = foot == 0 ? 0.2 : -0.2;
	}
	if (kind == HdFx::TRACK_BARE)
	{
		const double inner[5] = { 0.068, 0.033, 0.002, -0.030, -0.058 }, ahead[5] = { 0.19, 0.18, 0.168, 0.152, 0.132 },
			r[5] = { 0.04, 0.03, 0.028, 0.025, 0.022 };
		add(-0.17, 0, 0.075, 0.065);
		add(-0.065, sg * 0.022, 0.075, 0.04);
		add(0.04, 0, 0.078, 0.082);
		for (int i = 0; i < 5; ++i)
		{
			add(ahead[i], -sg * inner[i], r[i], r[i]);
		}
	}
	else if (kind == HdFx::TRACK_PAW)
	{
		const double across[4] = { -0.108, -0.037, 0.037, 0.108 }, ahead[4] = { 0.045, 0.098, 0.098, 0.045 };
		add(-0.05, 0, 0.085, 0.10);
		for (int i = 0; i < 4; ++i)
		{
			add(ahead[i], across[i], 0.036, 0.032);
			add(ahead[i] + 0.052, across[i], 0.028, 0.009);
		}
	}
	else if (!lanes)
	{
		add(0.13, 0, 0.21, 0.115);
		add(-0.04, 0, 0.09, 0.06);
		add(-0.19, 0, 0.11, 0.095);
	}
	}
	// the lanes of a wheeled or tracked body: two, a body's track apart (one tile for a 2x2 body), seen from this tile's middle
	const bool wheel = kind == HdFx::TRACK_WHEEL;
	const double laneHalf = body ? 0.5 : 0.2, laneWidth = wheel ? (body ? 0.09 : 0.055) : (body ? 0.17 : 0.1);
	const double lateral = body ? ((quarter & 1) - 0.5) * qx + ((quarter >> 1) - 0.5) * qy : 0.0;
	// the cross tread: bars along the way, whole to the tile (so they meet at its edges), dark bars and paler gaps
	const double pass = std::fabs(hx) > 0.9 || std::fabs(hy) > 0.9 ? 1.0 : std::sqrt(2.0);
	const double period = pass / (wheel ? 6 : 8), duty = wheel ? 0.55 : 0.8, gap = wheel ? 0.25 : 0.5;
	const double soft = (snow ? HD_SNOW_SOFT : 1.0) / (16.0 * k);
	const double alphaScale = snow ? HD_SNOW_ALPHA : 1.0;
	const Uint32 rgbPart = (Uint32)rgb & 0xFFFFFF;
	auto grace = [soft](double distance) { return std::min(1.0, std::max(0.0, 0.5 - distance / soft)); };
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			const double X = (x + 0.5) / (16.0 * k) - 1.0, Y = (y + 0.5) / (8.0 * k) - 1.0;
			const double u = (X + Y) / 2, v = (Y - X) / 2;
			if (std::fabs(u) > 0.5 || std::fabs(v) > 0.5)
			{
				continue;
			}
			const double pu = (u - shiftU) / pscale, pv = (v - shiftV) / pscale;
			const double s = pu * hx + pv * hy, t = pu * qx + pv * qy;
			double cover = 0.0;
			for (int i = 0; i < count; ++i)
			{
				const double ds = s - ovals[i].ahead, dt = t - ovals[i].across;
				const double e = std::sqrt((ds / ovals[i].a) * (ds / ovals[i].a) + (dt / ovals[i].b) * (dt / ovals[i].b));
				cover = std::max(cover, grace((e - 1.0) * std::min(ovals[i].a, ovals[i].b)));
			}
			if (lanes)
			{
				double across = 1e9;
				for (int lane = -1; lane <= 1; lane += 2)
				{
					const double d = std::fabs(t - (lane * laneHalf - lateral));
					across = std::min(across, d);
					cover = std::max(cover, grace(d - laneWidth));
				}
				if (cover > 0.0)
				{
					// a wheel's tread is a chevron (the bars lean back from the middle of the rut), a track's plates lie square
					const double at = (s + (wheel ? across * 1.1 : 0.0)) / period + duty / 2;
					const double w = at - std::floor(at);
					const double bar = grace(w < duty ? -std::min(w, duty - w) * period : std::min(w - duty, 1.0 - w) * period);
					cover *= gap + (1.0 - gap) * bar;
				}
			}
			if (cover > 0.0 && pat > 0 && !drops)
			{
				cover *= wear(u, v);
			}
			const int alpha = (int)std::lround(HD_STEP_ALPHA[std::max(0, std::min(2, tier))] * alphaScale * cover);
			if (alpha > 0)
			{
				f.pixels[(size_t)y * f.width + x] = ((Uint32)alpha << 24) | rgbPart;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
	return f;
}

/**
 * Puts a print on tile `index`: a tile keeps HD_STEP_PER_TILE at most (the oldest of the tile goes), the map HD_STEP_MAX (the oldest of the map goes).
 */
template <class Steps, class Order>
static void hdLayInto(Steps &steps, Order &order, size_t &count, size_t perTile, size_t maxCount, int index, const typename Steps::mapped_type::value_type &step)
{
	auto &prints = steps[index];
	if (prints.size() >= perTile)
	{
		prints.erase(prints.begin());
		--count;
	}
	prints.push_back(step);
	++count;
	order.push_back(std::make_pair(index, step.seq));
	while (count > maxCount || order.size() > maxCount * 4)
	{
		auto old = steps.find(order.front().first);
		if (old != steps.end())
		{
			auto &list = old->second;
			for (auto p = list.begin(); p != list.end(); ++p)
			{
				if (p->seq == order.front().second)
				{
					list.erase(p);
					--count;
					break;
				}
			}
			if (list.empty())
			{
				steps.erase(old);
			}
		}
		order.pop_front();
	}
}

void Map::hdLayStep(int index, const HdStep &step)
{
	hdLayInto(_hdSteps, _hdStepOrder, _hdStepCount, (size_t)HD_STEP_PER_TILE, (size_t)HD_STEP_MAX, index, step);
}

/**
 * Options::oxceHdSnowTracks: is the floor of `tile` snow? By the picture of the floor: the diamond (the bottom 16 of 40 rows of the HD frame) is snow
 * when at least half of its pixels are light and nearly grey (HD_SNOW_LIGHT, HD_SNOW_SPREAD). The set's name does not tell (XP-000563): the snow sets
 * have dirt, ice-water and wooden floors, MOUNTSNOW2 and POLAR mix them, and the floors of metal, asphalt and buildings never come out white-grey.
 * Found once for each floor sprite (by its buffer) and kept; no HD frame - not snow (nothing is asked again of a sprite that has none yet).
 */
bool Map::hdSnowFloor(const Tile *tile)
{
	const SurfaceRaw<const Uint8> sprite = tile->getSprite(O_FLOOR);
	if (!sprite)
	{
		return false;
	}
	const void *key = sprite.getBuffer();
	auto it = _hdSnowFloors.find(key);
	if (it != _hdSnowFloors.end())
	{
		return it->second;
	}
	const HdFrame *frame = _canvas->frameOf(sprite);
	if (!frame || frame->empty() || frame->height < 40)
	{
		return false;
	}
	size_t seen = 0, snow = 0;
	for (int y = frame->height * 24 / 40; y < frame->height; ++y)
	{
		for (int x = 0; x < frame->width; ++x)
		{
			const Uint32 p = frame->pixels[(size_t)y * frame->width + x];
			if ((p >> 24) <= 200)
			{
				continue;
			}
			const int r = (p >> 16) & 255, g = (p >> 8) & 255, b = p & 255;
			++seen;
			if (std::min(r, std::min(g, b)) >= HD_SNOW_LIGHT && std::max(r, std::max(g, b)) - std::min(r, std::min(g, b)) <= HD_SNOW_SPREAD)
			{
				++snow;
			}
		}
	}
	const bool result = seen > 0 && snow * 2 >= seen;
	_hdSnowFloors[key] = result;
	return result;
}

/**
 * The same for a dent in snow (Options::oxceHdSnowTracks): a tile keeps HD_SNOW_PER_TILE, the map HD_SNOW_MAX - their own, so the snow never pushes the blood out.
 */
void Map::hdLaySnow(int index, const HdStep &step)
{
	hdLayInto(_hdSnowSteps, _hdSnowOrder, _hdSnowCount, (size_t)HD_SNOW_PER_TILE, (size_t)HD_SNOW_MAX, index, step);
}

/**
 * Options::oxceHdBloodSteps: before a frame, looks at every unit the player sees (or all in the debug mode) that has moved to another
 * tile since the last look. A wounded unit (alive, fatal wounds) on the move drops blood on each tile it enters (the drops, HD_STEP_DROPS). A unit that has bloody soles (HD_STEP_TILES more tiles to go) lays a print of its kind (HdFx::trackKind: boot,
 * bare foot, wheels, tracks, paws; a 2x2 body on all four tiles it covers) on the tile it has entered; a unit
 * that has entered a tile where another unit bleeds (fatal wounds, alive - standing or lying unconscious, a corpse does not count; the
 * bleeding one seen too, its 2x2 body counts on all its tiles) gets them from the next tile on, in the blood colour of the one who
 * bleeds. Flying and floating units, and the kind `none` (turrets, slime and so on), leave none. A unit the player does not see is not followed at all, so no sole tells of a move in
 * the fog. The turn only for the fading (SavedBattleGame::getTurn, read). Nothing of the units, the tiles or the save is touched.
 */
void Map::hdObserveSteps()
{
	// XP-000556: under water (depth > 0) no bloody soles and drops, as no blood spray there (XP-000533)
	if (!(Options::oxceHdBloodSteps || Options::oxceHdSnowTracks) || _canvas->getHdMode() == HD_MODE_NEAREST || _save->getDepth() > 0)
	{
		if (!_hdStepTracks.empty() || !_hdSteps.empty() || !_hdSnowSteps.empty())
		{
			_hdStepTracks.clear();
			_hdSteps.clear();
			_hdStepOrder.clear();
			_hdStepCount = 0;
			_hdSnowSteps.clear();
			_hdSnowOrder.clear();
			_hdSnowCount = 0;
		}
		return;
	}
	// the blood and the snow are two options (XP-000563): the blood part below runs only when its own is on; the snow only in a battle whose ground is
	// snow (the weather's biome, picked once for the battle - also when the weather itself is off), on any floor but water and lava
	const bool blood = Options::oxceHdBloodSteps;
	bool snow = false;
	if (Options::oxceHdSnowTracks)
	{
		hdWeatherPick();
		snow = _hdWeatherBiome == HdWeather::B_SNOW;
	}
	if (!blood && !_hdSteps.empty())
	{
		_hdSteps.clear();
		_hdStepOrder.clear();
		_hdStepCount = 0;
	}
	if (!snow && !_hdSnowSteps.empty())
	{
		_hdSnowSteps.clear();
		_hdSnowOrder.clear();
		_hdSnowCount = 0;
	}
	// the cache of the print frames is cleared between frames when it grows (patterns x colours x directions), the frames are made again as they are met
	if (_hdStepFrames.size() > (size_t)HD_STEP_FRAMES_MAX)
	{
		_hdStepFrames.clear();
	}
	const int turn = _save->getTurn();
	const int life = hdStepLife();
	if (turn != _hdStepTurn || life != _hdStepLifeSeen)
	{
		_hdStepTurn = turn;
		_hdStepLifeSeen = life;
		for (auto s = _hdSteps.begin(); s != _hdSteps.end();)
		{
			auto &prints = s->second;
			const size_t before = prints.size();
			prints.erase(std::remove_if(prints.begin(), prints.end(), [&](const HdStep &p) { return turn < p.turn || (life > 0 && turn - p.turn >= life); }), prints.end());
			_hdStepCount -= before - prints.size();
			s = prints.empty() ? _hdSteps.erase(s) : std::next(s);
		}
		for (auto s = _hdSnowSteps.begin(); s != _hdSnowSteps.end();)
		{
			auto &prints = s->second;
			const size_t before = prints.size();
			prints.erase(std::remove_if(prints.begin(), prints.end(), [&](const HdStep &p) { return turn < p.turn || turn - p.turn >= HD_SNOW_LIFE; }), prints.end());
			_hdSnowCount -= before - prints.size();
			s = prints.empty() ? _hdSnowSteps.erase(s) : std::next(s);
		}
	}
	const bool redOnly = Options::oxceHdBloodStepsColor == 1;
	const bool debug = _save->getDebugMode();
	for (BattleUnit *bu : *_save->getUnits())
	{
		HdStepTrack &track = _hdStepTracks[bu->getId()];
		const Position pos = bu->getPosition();
		if (bu->isOut() || pos.x < 0 || !(bu->getFaction() == FACTION_PLAYER || bu->getVisible() || debug))
		{
			track.seen = false;
			track.left = 0;
			continue;
		}
		if (!track.seen)
		{
			track = HdStepTrack();
			track.seen = true;
			track.last = pos;
			continue;
		}
		if (pos == track.last)
		{
			continue;
		}
		const Position from = track.last;
		track.last = pos;
		const int dx = pos.x - from.x, dy = pos.y - from.y;
		if (std::abs(dx) > 1 || std::abs(dy) > 1)
		{
			track.left = 0;
			continue;
		}
		if (dx == 0 && dy == 0)
		{
			continue;
		}
		const MovementType mt = bu->getMovementType();
		if (mt == MT_FLY || mt == MT_FLOAT || bu->isFloating())
		{
			track.left = 0;
			continue;
		}
		const Tile *here = _save->getTile(pos);
		const int size = bu->getArmor()->getSize();
		const int kind = HdFx::trackKind(bu->getArmor());
		++track.count;
		// the wounded one on the move (alive, fatal wounds - read only) drops blood on each tile it enters: a few drops along its way, more and larger when
		// it has many wounds; in its own blood colour (or red by the setting)
		if (blood && bu->getFatalWounds() > 0 && bu->getHealth() > 0 && bu->getStatus() != STATUS_DEAD)
		{
			const int own = redOnly ? -1 : HdFx::bloodRgb(bu->getArmor(), true);
			for (int j = 0; j < size; ++j)
			{
				for (int i = 0; i < size; ++i)
				{
					const Position at(pos.x + i, pos.y + j, pos.z);
					const Tile *floorTile = _save->getTile(at);
					if (!floorTile || floorTile->hasNoFloor(_save) || !HdFx::dryFloor(floorTile))
					{
						continue;
					}
					const int index = _save->getTileIndex(at);
					const int pattern = (int)((hdStepMix((Uint32)index * 0x9E3779B1U ^ (Uint32)turn * 0x85EBCA6BU ^ (Uint32)bu->getId() * 0xC2B2AE35U ^ track.count * 0x27D4EB2FU ^ 0x5BD1E995U) >> 8) % HD_STEP_PATTERNS);
					hdLayStep(index, HdStep{ dx, dy, bu->getFatalWounds() >= 3 ? 1 : 0, HD_STEP_DROPS, own >= 0 ? own : HD_STEP_RED, turn, ++_hdStepSeq, pattern });
				}
			}
		}
		// XP-000563: in a snow battle every step of a walker leaves a dent of its kind (a 2x2 body on all its four tiles), the left or the right foot by turns;
		// no bloody soles needed; the colour is the snow's own
		if (snow && kind != HdFx::TRACK_NONE)
		{
			for (int j = 0; j < size; ++j)
			{
				for (int i = 0; i < size; ++i)
				{
					const Position at(pos.x + i, pos.y + j, pos.z);
					const Tile *floorTile = _save->getTile(at);
					if (!floorTile || floorTile->hasNoFloor(_save) || !HdFx::dryFloor(floorTile) || !hdSnowFloor(floorTile))
					{
						continue;
					}
					const int index = _save->getTileIndex(at);
					const int pattern = (int)((hdStepMix((Uint32)index * 0x9E3779B1U ^ (Uint32)turn * 0x85EBCA6BU ^ (Uint32)bu->getId() * 0xC2B2AE35U ^ track.count * 0x27D4EB2FU ^ 0x3C6EF372U) >> 8) % HD_STEP_PATTERNS);
					hdLaySnow(index, HdStep{ dx, dy, size > 1 ? 2 + (i & 1) + 2 * (j & 1) : (int)(track.count & 1), kind | HD_STEP_SNOW, HD_SNOW_RGB, turn, ++_hdStepSeq, pattern });
				}
			}
		}
		if (!blood)
		{
			continue;
		}
		if (kind == HdFx::TRACK_NONE)
		{
			track.left = 0;
			continue;
		}
		if (track.left > 0)
		{
			--track.left;
			track.foot ^= 1;
			// a unit of one tile leaves a print on it; a 2x2 body on each of its four (a wheeled or tracked one - its lanes, a walker - big prints)
			for (int j = 0; j < size; ++j)
			{
				for (int i = 0; i < size; ++i)
				{
					const Position at(pos.x + i, pos.y + j, pos.z);
					const Tile *floorTile = _save->getTile(at);
					if (!floorTile || floorTile->hasNoFloor(_save) || !HdFx::dryFloor(floorTile))
					{
						continue;
					}
					const int index = _save->getTileIndex(at);
					const int pattern = (int)((hdStepMix((Uint32)index * 0x9E3779B1U ^ (Uint32)turn * 0x85EBCA6BU ^ (Uint32)bu->getId() * 0xC2B2AE35U ^ track.count * 0x27D4EB2FU) >> 8) % HD_STEP_PATTERNS);
					hdLayStep(index, HdStep{ dx, dy, size > 1 ? 2 + (i & 1) + 2 * (j & 1) : track.foot, kind, track.rgb, turn, ++_hdStepSeq, pattern });
				}
			}
		}
		for (const BattleUnit *other : *_save->getUnits())
		{
			if (other == bu || other->getStatus() == STATUS_DEAD || other->getHealth() <= 0 || other->getFatalWounds() <= 0)
			{
				continue;
			}
			const Position op = other->getPosition();
			const int osize = other->getArmor()->getSize();
			if (op.x < 0 || op.z != pos.z || op.x >= pos.x + size || pos.x >= op.x + osize || op.y >= pos.y + size || pos.y >= op.y + osize)
			{
				continue;
			}
			if (!(other->getFaction() == FACTION_PLAYER || other->getVisible() || debug || (here && here->getVisible() > 0)))
			{
				continue;
			}
			const int rgb = redOnly ? -1 : HdFx::bloodRgb(other->getArmor(), true);
			track.left = HD_STEP_TILES;
			track.rgb = rgb >= 0 ? rgb : HD_STEP_RED;
			break;
		}
	}
}

}
