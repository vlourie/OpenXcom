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
#include "HdItems.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <list>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <tuple>
#include <vector>
#include "FileMap.h"
#include "HdUi.h"
#include "HdUiArt.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "SDL2Helpers.h"
#include "Script.h"
#include "Surface.h"
#include "SurfaceSet.h"
#include "Unicode.h"
#include "../Mod/RuleInventory.h"
#include "../Mod/RuleItem.h"
#include "../Mod/Unit.h"
#include "../Savegame/BattleItem.h"

namespace OpenXcom
{

namespace HdItems
{

namespace
{

const char *FOLDER = "BIGOBS.PCK";

/// The files of one picture: the grid one and the hand frame's one (either may be missing).
struct Asset
{
	std::string path, hand;
	/// "<frame>.<type>.wide.png": the grid picture is drawn past the item's cells as its classic frame is
	/// (the AK's magazine in the next column) - the whole frame in the grid, the hand frame's inside in the hand
	bool wide = false;
};

/// (frame, item type in lower case; "" = the frame's common picture) -> files.
std::map<std::pair<int, std::string>, Asset> assets;
bool scanned = false;

/// The palette the pictures were made with (hd/BIGOBS.PCK/palette.pal.txt, 256 lines "r g b"); empty: they
/// are drawn as they are whatever the palette.
std::vector<SDL_Color> reference;
/// Shown palettes other than the reference one: pictures recoloured, the time it took (the log).
std::map<Uint64, std::pair<size_t, double>> recolouredFor;

/// (item type, frame, w, h, context, k, palette): a picture is the item's, never the frame's (R-056);
/// the palette is 0 for the pictures as they are, else the hash of the palette they are recoloured to.
typedef std::tuple<std::string, int, int, int, int, int, Uint64> Key;
struct Ready
{
	std::shared_ptr<const HdFrame> frame;     ///< null: the picture cannot be read
	size_t size = 0;
	std::list<Key>::iterator use;
};
std::map<Key, Ready> ready;
std::list<Key> uses;                          ///< most recently drawn first
size_t bytes = 0;
const size_t BUDGET = 64u * 1024u * 1024u;
std::set<std::string> noHand;                 ///< types already logged as classic in the hand frame
std::set<std::string> noGrid;                 ///< types already logged as classic in the grid

/// A picture attached to a surface, where it goes relative to the surface.
struct Placed
{
	Pick pick;
	int x, y;
};
/// Never destroyed: ~Surface asks it, and some surfaces outlive the static objects of this file.
std::map<const Surface*, std::vector<Placed>> &attached = *new std::map<const Surface*, std::vector<Placed>>();

/// A watched surface: the HD state its sprite was drawn for and how its owner draws it again.
struct Watched
{
	int state;
	std::function<void()> redraw;
};
std::map<const Surface*, Watched> &watched = *new std::map<const Surface*, Watched>();

/// What an item sprite is drawn for: 0 classic, else the HD pictures' k.
int hdState()
{
	return enabled() ? HdUi::scale() : 0;
}

std::string lower(const std::string &s)
{
	std::string out = s;
	Unicode::lowerCase(out);
	return out;
}

bool endsWith(const std::string &s, const char *tail)
{
	const std::string t = tail;
	return s.size() > t.size() && s.compare(s.size() - t.size(), t.size(), t) == 0;
}

/// Reads the folder once: which frame and item has which pictures.
void scan()
{
	if (scanned)
	{
		return;
	}
	scanned = true;
	for (const std::string &file : HdSprites::artFolder(FOLDER))
	{
		std::string stem = lower(file);
		if (!endsWith(stem, ".png"))
		{
			continue;
		}
		stem.resize(stem.size() - 4);
		const bool hand = endsWith(stem, ".hand");
		if (hand)
		{
			stem.resize(stem.size() - 5);
		}
		const bool wide = !hand && endsWith(stem, ".wide");
		if (wide)
		{
			stem.resize(stem.size() - 5);
		}
		const size_t dot = stem.find('.');
		const std::string number = stem.substr(0, dot);
		char *stop = nullptr;
		const long frame = std::strtol(number.c_str(), &stop, 10);
		if (number.empty() || *stop != '\0' || frame < 0)
		{
			continue;
		}
		const std::string type = dot == std::string::npos ? std::string() : stem.substr(dot + 1);
		Asset &asset = assets[std::make_pair((int)frame, type)];
		(hand ? asset.hand : asset.path) = HdSprites::artPath(std::string(FOLDER) + "/" + file);
		if (!hand)
		{
			asset.wide = wide;
		}
	}
	if (!assets.empty())
	{
		Log(LOG_INFO) << "HD items: " << assets.size() << " pictures in hd/" << FOLDER;
	}
	const std::string palPath = HdSprites::artPath(std::string(FOLDER) + "/palette.pal.txt");
	if (assets.empty() || !FileMap::fileExists(palPath))
	{
		return;
	}
	if (SDL_RWops *rw = FileMap::getRWops(palPath))
	{
		size_t size = 0;
		void *data = SDL_LoadFile_RW(rw, &size, SDL_TRUE);
		if (data)
		{
			std::istringstream in(std::string((const char*)data, size));
			int r, g, b;
			while (in >> r >> g >> b && reference.size() < 256)
			{
				SDL_Color c;
				c.r = (Uint8)r; c.g = (Uint8)g; c.b = (Uint8)b; c.unused = 255;
				reference.push_back(c);
			}
			SDL_free(data);
		}
	}
	if (reference.size() != 256)
	{
		Log(LOG_WARNING) << "HD items: " << palPath << " should hold 256 lines 'r g b' - no recolouring to the shown palette";
		reference.clear();
	}
}

/// The palette a picture is drawn for: 0 when it is drawn as it is (no reference palette, no palette given,
/// or the reference one), else the hash of the shown palette (the cache key of its recoloured pictures).
Uint64 tintOf(const SDL_Color *shown)
{
	if (reference.empty() || !shown)
	{
		return 0;
	}
	for (int i = 1; i < 256; ++i)
	{
		if (shown[i].r != reference[i].r || shown[i].g != reference[i].g || shown[i].b != reference[i].b)
		{
			return HdUiArt::foldPalette(0x51ED270B27A3C1F5ULL, shown) | 1;
		}
	}
	return 0;
}

/// V4 (docs/research/inventory-hd-enviro-palette.md §5): a picture made in the reference palette P0 shown
/// with the palette P1 (a battle's weather). Every pixel moves by the shift D = P1 - P0 of the palette
/// entries of the classic pixels around it (the 3x3 base pixels about its own), each weighted by how near
/// the pixel's colour is to the entry's in P0 (a kernel of 12 colour units): the pixel follows the entry it
/// was drawn from, not merely the nearest colour. With no classic pixel around (the outline's feather) - the
/// same kernel over the whole palette (M1t). `index` is the classic frame under the picture, `bw` x `bh`
/// base pixels; bands on all cores. Returns the pixels that had no classic pixel around.
int recolour(HdFrame &frame, const std::vector<Uint8> &index, int bw, int bh, int k, const SDL_Color *shown)
{
	float P0[256][3], D[256][3];
	for (int i = 0; i < 256; ++i)
	{
		P0[i][0] = reference[i].r; P0[i][1] = reference[i].g; P0[i][2] = reference[i].b;
		D[i][0] = (float)shown[i].r - reference[i].r;
		D[i][1] = (float)shown[i].g - reference[i].g;
		D[i][2] = (float)shown[i].b - reference[i].b;
	}
	const float inv2s2 = 1.0f / (2 * 12.0f * 12.0f);
	const int W = frame.width, H = frame.height;
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 16, pool.threads() * 2));
	std::vector<int> lonely(jobs, 0);
	pool.run(jobs, [&](int job)
	{
		for (int y = H * job / jobs, yEnd = H * (job + 1) / jobs; y < yEnd; ++y)
		{
			Uint32 *row = &frame.pixels[(size_t)y * W];
			const int by = y / k;
			for (int x = 0; x < W; ++x)
			{
				const Uint32 a = row[x] >> 24;
				if (!a)
				{
					continue;
				}
				const float c[3] = { (float)((row[x] >> 16) & 0xFF), (float)((row[x] >> 8) & 0xFF), (float)(row[x] & 0xFF) };
				const int bx = x / k;
				int ids[9], n = 0;
				float d2[9], lo = 1e30f;
				for (int dy = -1; dy <= 1; ++dy)
				{
					for (int dx = -1; dx <= 1; ++dx)
					{
						const int xx = bx + dx, yy = by + dy;
						if (xx < 0 || yy < 0 || xx >= bw || yy >= bh)
						{
							continue;
						}
						const Uint8 i = index[(size_t)yy * bw + xx];
						if (!i)
						{
							continue;
						}
						const float e0 = c[0] - P0[i][0], e1 = c[1] - P0[i][1], e2 = c[2] - P0[i][2];
						ids[n] = i;
						d2[n] = e0 * e0 + e1 * e1 + e2 * e2;
						lo = std::min(lo, d2[n]);
						++n;
					}
				}
				if (!n)
				{
					// the whole palette (entries 1..255)
					for (int i = 1; i < 256; ++i)
					{
						const float e0 = c[0] - P0[i][0], e1 = c[1] - P0[i][1], e2 = c[2] - P0[i][2];
						lo = std::min(lo, e0 * e0 + e1 * e1 + e2 * e2);
					}
					++lonely[job];
				}
				float d[3] = { 0, 0, 0 }, sw = 0;
				for (int j = 0, end = n ? n : 255; j < end; ++j)
				{
					const int i = n ? ids[j] : j + 1;
					const float e0 = c[0] - P0[i][0], e1 = c[1] - P0[i][1], e2 = c[2] - P0[i][2];
					const float w = std::exp(-((n ? d2[j] : e0 * e0 + e1 * e1 + e2 * e2) - lo) * inv2s2);
					sw += w;
					d[0] += w * D[i][0];
					d[1] += w * D[i][1];
					d[2] += w * D[i][2];
				}
				Uint32 o[3];
				for (int ch = 0; ch < 3; ++ch)
				{
					const long v = std::lrint(c[ch] + d[ch] / sw); // round half to even, as HdPaletteShift
					o[ch] = (Uint32)std::min(255L, std::max(0L, v));
				}
				row[x] = (a << 24) | (o[0] << 16) | (o[1] << 8) | o[2];
			}
		}
	});
	int total = 0;
	for (int l : lonely)
	{
		total += l;
	}
	return total;
}

/// What a picture is recoloured to, when it is: the shown palette, its hash, and the classic frame under the
/// picture (`classic` with its top left `offX`, `offY` base pixels into the picture; k: the picture's scale).
struct Tint
{
	const SDL_Color *shown = nullptr;
	Uint64 hash = 0;
	const Surface *classic = nullptr;
	int offX = 0, offY = 0, k = 1;
};

/// Drops the pictures drawn longest ago while the ready ones exceed the budget.
void trim()
{
	while (bytes > BUDGET && uses.size() > 1)
	{
		auto got = ready.find(uses.back());
		bytes -= got->second.size;
		ready.erase(got);
		uses.pop_back();
	}
}

/// A picture at w x h, read now if it was not (and recoloured to `tint`'s palette when its hash is not 0);
/// null when it cannot be read.
std::shared_ptr<const HdFrame> get(const Key &key, const std::string &path, int w, int h, const Tint &tint)
{
	auto got = ready.find(key);
	if (got != ready.end())
	{
		uses.splice(uses.begin(), uses, got->second.use);
		return got->second.frame;
	}
	HdFrame frame;
	if (!HdSprites::loadPng(path, frame) || frame.empty())
	{
		Log(LOG_WARNING) << "HD items: cannot read " << path;
		frame = HdFrame();
	}
	else if (frame.width != w || frame.height != h)
	{
		HdFrame fitted;
		HdSprites::resample(frame, w, h, fitted);
		frame = std::move(fitted);
	}
	if (!frame.empty() && tint.hash && tint.classic)
	{
		const auto t0 = std::chrono::steady_clock::now();
		const int bw = w / tint.k, bh = h / tint.k;
		std::vector<Uint8> index((size_t)bw * bh, 0);
		for (int y = 0; y < bh; ++y)
		{
			for (int x = 0; x < bw; ++x)
			{
				const int cx = x - tint.offX, cy = y - tint.offY;
				if (cx >= 0 && cy >= 0 && cx < tint.classic->getWidth() && cy < tint.classic->getHeight())
				{
					index[(size_t)y * bw + x] = tint.classic->getPixel(cx, cy);
				}
			}
		}
		const int lonely = recolour(frame, index, bw, bh, tint.k, tint.shown);
		const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
		auto &done = recolouredFor[tint.hash];
		++done.first;
		done.second += ms;
		// at 1, 2, 4, 8... pictures: how many and how long in all, for this palette
		if ((done.first & (done.first - 1)) == 0)
		{
			Log(LOG_INFO) << "HD items: recoloured " << done.first << " picture(s) for palette " << std::hex << tint.hash << std::dec
				<< " in " << (int)(done.second + 0.5) << " ms (last " << path << ", " << lonely << " pixel(s) with no classic pixel around)";
		}
	}
	if (!frame.empty())
	{
		frame.buildSpans();
	}
	uses.push_front(key);
	Ready &stored = ready[key];
	stored.size = frame.pixels.size() * sizeof(Uint32);
	if (!frame.empty())
	{
		stored.frame = std::make_shared<const HdFrame>(std::move(frame));
	}
	stored.use = uses.begin();
	bytes += stored.size;
	std::shared_ptr<const HdFrame> out = stored.frame;
	trim();
	return out;
}

/// Do the item's recolour scripts (its own, the mod's global ones, its unit's) change the frame now?
bool recoloured(const BattleItem *item, const SavedBattleGame *save, int animFrame, const Surface *frame)
{
	ScriptWorkerBlit work;
	BattleItem::ScriptFill(&work, item, save, BODYPART_ITEM_INVENTORY, animFrame, 0);
	if (!work.hasScript())
	{
		return false;
	}
	static std::unique_ptr<Surface> scratch;
	const int w = frame->getWidth(), h = frame->getHeight();
	if (!scratch || scratch->getWidth() < w || scratch->getHeight() < h)
	{
		scratch = std::make_unique<Surface>(std::max(w, 64), std::max(h, 64), 0, 0);
	}
	scratch->clear();
	work.executeBlit(frame, scratch.get(), 0, 0, 0);
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			if (scratch->getPixel(x, y) != frame->getPixel(x, y))
			{
				return true;
			}
		}
	}
	return false;
}

/// The base rectangle [x0, x1) x [y0, y1) as a clip of a pick, empty when it is.
void setClip(Pick &out, int x0, int y0, int x1, int y1)
{
	out.clipX = x0;
	out.clipY = y0;
	out.clipW = std::max(0, x1 - x0);
	out.clipH = std::max(0, y1 - y0);
}

}

bool enabled()
{
	if (!HdUi::active())
	{
		return false;
	}
	scan();
	return !assets.empty();
}

int indexOf(const SurfaceSet *set, const Surface *frame)
{
	// the frames of a set are one array: the index is where the frame lies in it
	const Surface *first = set && frame ? set->getFrame(0) : nullptr;
	if (first)
	{
		const std::ptrdiff_t index = frame - first;
		if (index >= 0 && index < (std::ptrdiff_t)set->getTotalFrames() && set->getFrame((int)index) == frame)
		{
			return (int)index;
		}
	}
	return -1;
}

bool pick(const RuleItem *rule, const BattleItem *item, const SavedBattleGame *save, int animFrame,
	int frame, const SurfaceSet *set, Context context, int k, Pick &out, const SDL_Color *shown)
{
	out = Pick();
	if (!rule || !set || frame < 0 || k < 2 || !enabled())
	{
		return false;
	}
	const Surface *classic = set->getFrame(frame);
	if (!classic)
	{
		return false;
	}
	// step 1: the item's picture - its own when it has any file of its own, else the frame's common one.
	// The common one never stands in for a version the own picture lacks (a junk pile stays a junk pile)
	const std::string type = lower(rule->getType());
	auto found = assets.find(std::make_pair(frame, type));
	if (found == assets.end())
	{
		found = assets.find(std::make_pair(frame, std::string()));
		if (found == assets.end())
		{
			return false;
		}
	}
	const Asset &asset = found->second;
	// a script recolours the sprite now (energy shields): classic, the interface has no brightness transfer yet
	if (item && recoloured(item, save, animFrame, classic))
	{
		return false;
	}
	const int w = rule->getInventoryWidth(), h = rule->getInventoryHeight();
	// the item's cells, the grid's lines left out (docs/research/inventory-items-hd.md §5.3)
	const int xMax = RuleInventory::SLOT_W * w - (w == 2 ? 1 : 0);
	const int yMax = RuleInventory::SLOT_H * h - (h == 3 ? 1 : 0);
	const int handW = RuleInventory::HAND_W * RuleInventory::SLOT_W, handH = RuleInventory::HAND_H * RuleInventory::SLOT_H;
	const bool fitsHand = w <= RuleInventory::HAND_W && h <= RuleInventory::HAND_H;
	const int offX = rule->getHandSpriteOffX(), offY = rule->getHandSpriteOffY();
	Tint tint;
	tint.hash = tintOf(shown);
	tint.shown = shown;
	tint.classic = classic;
	tint.k = k;
	const Key key(type, frame, w, h, (int)context, k, tint.hash);
	// step 2: the version for the context
	if (context == GRID)
	{
		if (asset.path.empty())
		{
			// only a hand version: the grid shows the classic frame, not the frame's common picture
			if (noGrid.insert(type).second)
			{
				Log(LOG_INFO) << "HD BIGOBS " << rule->getType() << ": no grid picture, classic";
			}
			return false;
		}
		out.frame = get(key, asset.path, classic->getWidth() * k, classic->getHeight() * k, tint);
		if (asset.wide)
		{
			setClip(out, 0, 0, classic->getWidth(), classic->getHeight());
		}
		else
		{
			setClip(out, 1, 1, xMax, yMax);
		}
	}
	else if (!asset.hand.empty())
	{
		// the hand frame: the classic sprite in it at the usual hand offset
		tint.offX = offX;
		tint.offY = offY;
		out.frame = get(key, asset.hand, handW * k, handH * k, tint);
		if (fitsHand)
		{
			// the item's cells after the usual hand offset, inside the frame's lines (§5.4): a small item
			// does not get the whole frame
			setClip(out, std::max(1, offX), std::max(1, offY),
				std::min(handW - 1, offX + RuleInventory::SLOT_W * w), std::min(handH - 1, offY + RuleInventory::SLOT_H * h));
		}
		else
		{
			// 3x2, 3x3: bigger than the frame, all of it inside the lines
			setClip(out, 1, 1, handW - 1, handH - 1);
		}
	}
	else if (fitsHand)
	{
		// the grid picture with the usual hand offset: its cells' rectangle, inside the hand frame's lines
		out.frame = get(key, asset.path, classic->getWidth() * k, classic->getHeight() * k, tint);
		out.dx = offX;
		out.dy = offY;
		if (asset.wide)
		{
			setClip(out, 1, 1, handW - 1, handH - 1);
		}
		else
		{
			setClip(out, std::max(1, offX + 1), std::max(1, offY + 1),
				std::min(handW - 1, offX + xMax), std::min(handH - 1, offY + yMax));
		}
	}
	else
	{
		if (noHand.insert(type).second)
		{
			Log(LOG_INFO) << "HD BIGOBS " << rule->getType() << ": no .hand variant, classic";
		}
		return false;
	}
	return out.frame != nullptr && out.clipW > 0 && out.clipH > 0;
}

void draw(const Pick &pick, int x, int y, const SDL_Rect &outer)
{
	const int k = HdUi::scale();
	if (!pick.frame || k < 2)
	{
		return;
	}
	int x0 = x + pick.clipX, y0 = y + pick.clipY;
	int x1 = x0 + pick.clipW, y1 = y0 + pick.clipH;
	if (outer.w > 0 && outer.h > 0)
	{
		x0 = std::max(x0, (int)outer.x);
		y0 = std::max(y0, (int)outer.y);
		x1 = std::min(x1, outer.x + (int)outer.w);
		y1 = std::min(y1, outer.y + (int)outer.h);
	}
	if (x1 <= x0 || y1 <= y0)
	{
		return;
	}
	HdUi &ui = HdUi::instance();
	ui.setClip(x0, y0, x1 - x0, y1 - y0);
	ui.drawImage(pick.frame->pixels.data(), pick.frame->width, pick.frame->height, (x + pick.dx) * k, (y + pick.dy) * k);
	ui.clearClip();
}

void attach(const Surface *surface, const Pick &pick, int x, int y)
{
	attached[surface].push_back(Placed{pick, x, y});
}

void detach(const Surface *surface)
{
	if (!attached.empty())
	{
		attached.erase(surface);
	}
}

void watch(const Surface *surface, std::function<void()> redraw)
{
	watched[surface] = Watched{ hdState(), std::move(redraw) };
}

void refresh(const Surface *surface)
{
	if (watched.empty())
	{
		return;
	}
	auto got = watched.find(surface);
	if (got == watched.end())
	{
		return;
	}
	const int now = hdState();
	if (got->second.state != now)
	{
		got->second.state = now;
		// a copy: the owner may watch the surface again while it draws
		std::function<void()> redraw = got->second.redraw;
		if (redraw)
		{
			redraw();
		}
	}
}

void forget(const Surface *surface)
{
	detach(surface);
	if (!watched.empty())
	{
		watched.erase(surface);
	}
}

void drawAttached(const Surface *surface)
{
	if (attached.empty())
	{
		return;
	}
	auto got = attached.find(surface);
	if (got == attached.end())
	{
		return;
	}
	const SDL_Rect window = { (Sint16)surface->getX(), (Sint16)surface->getY(), (Uint16)surface->getWidth(), (Uint16)surface->getHeight() };
	for (const Placed &placed : got->second)
	{
		draw(placed.pick, surface->getX() + placed.x, surface->getY() + placed.y, window);
	}
}

bool attachHand(const RuleItem *rule, const BattleItem *item, const SavedBattleGame *save, int animFrame,
	const SurfaceSet *set, const Surface *surface)
{
	detach(surface);
	const int k = enabled() ? HdUi::scale() : 0;
	if (!k || !rule || !set)
	{
		return false;
	}
	// the frame RuleItem::drawHandSprite would draw
	const int frame = item ? indexOf(set, item->getBigSprite(set, save, animFrame)) : rule->getBigSprite();
	Pick picked;
	if (!pick(rule, item, save, animFrame, frame, set, HAND, k, picked, surface->getPalette()))
	{
		return false;
	}
	attach(surface, picked);
	return true;
}

void drawRuleHand(const RuleItem *rule, const SurfaceSet *set, Surface *surface)
{
	auto draw = [rule, set, surface]()
	{
		surface->clear();
		if (!attachHand(rule, nullptr, nullptr, 0, set, surface))
		{
			rule->drawHandSprite(set, surface);
		}
	};
	draw();
	watch(surface, draw);
}

void clear()
{
	attached.clear();
	watched.clear();
	assets.clear();
	scanned = false;
	ready.clear();
	uses.clear();
	bytes = 0;
	noHand.clear();
	noGrid.clear();
	reference.clear();
	recolouredFor.clear();
}

}

}
