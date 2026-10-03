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
#include <cstddef>
#include <cstdlib>
#include <list>
#include <map>
#include <memory>
#include <set>
#include <tuple>
#include <vector>
#include "HdUi.h"
#include "Logger.h"
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
};

/// (frame, item type in lower case; "" = the frame's common picture) -> files.
std::map<std::pair<int, std::string>, Asset> assets;
bool scanned = false;

/// (item type, frame, w, h, context, k): a picture is the item's, never the frame's (R-056).
typedef std::tuple<std::string, int, int, int, int, int> Key;
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
	}
	if (!assets.empty())
	{
		Log(LOG_INFO) << "HD items: " << assets.size() << " pictures in hd/" << FOLDER;
	}
}

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

/// A picture at w x h, read now if it was not; null when it cannot be read.
std::shared_ptr<const HdFrame> get(const Key &key, const std::string &path, int w, int h)
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
	int frame, const SurfaceSet *set, Context context, int k, Pick &out)
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
	// the item's cells, the hand frame's lines left out (docs/research/inventory-items-hd.md §5.3)
	const int xMax = RuleInventory::SLOT_W * w - (w == 2 ? 1 : 0);
	const int yMax = RuleInventory::SLOT_H * h - (h == 3 ? 1 : 0);
	const int handW = RuleInventory::HAND_W * RuleInventory::SLOT_W, handH = RuleInventory::HAND_H * RuleInventory::SLOT_H;
	const Key key(type, frame, w, h, (int)context, k);
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
		out.frame = get(key, asset.path, classic->getWidth() * k, classic->getHeight() * k);
		setClip(out, 1, 1, xMax, yMax);
	}
	else if (!asset.hand.empty())
	{
		out.frame = get(key, asset.hand, handW * k, handH * k);
		setClip(out, 1, 1, handW - 1, handH - 1);
	}
	else if (w <= RuleInventory::HAND_W && h <= RuleInventory::HAND_H)
	{
		// the grid picture with the usual hand offset: its cells, inside the hand frame's lines
		out.frame = get(key, asset.path, classic->getWidth() * k, classic->getHeight() * k);
		out.dx = rule->getHandSpriteOffX();
		out.dy = rule->getHandSpriteOffY();
		setClip(out, std::max(1, out.dx + 1), std::max(1, out.dy + 1),
			std::min(handW - 1, out.dx + xMax), std::min(handH - 1, out.dy + yMax));
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
	if (!pick(rule, item, save, animFrame, frame, set, HAND, k, picked))
	{
		return false;
	}
	attach(surface, picked);
	return true;
}

void clear()
{
	attached.clear();
	assets.clear();
	scanned = false;
	ready.clear();
	uses.clear();
	bytes = 0;
	noHand.clear();
	noGrid.clear();
}

}

}
