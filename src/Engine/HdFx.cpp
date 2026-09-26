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
#include "HdFx.h"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <sstream>
#include <unordered_map>
#include "FileMap.h"
#include "HdSprites.h"
#include "Logger.h"
#include "../Mod/Armor.h"
#include "../Mod/MapData.h"
#include "../Mod/MapDataSet.h"
#include "../Mod/RuleDamageType.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{

namespace HdFx
{

namespace
{

const char *FOLDER = "FX";
/// Frames of the loaded clips above this are dropped by trim() (bytes).
const size_t BUDGET = 96u << 20;
/// A clip not drawn for this long may be dropped (ms).
const Uint32 IDLE = 3000;
/// The muzzle flash: frames over this many ms (gen_combat_fx.py DUR_FLASH).
const Uint32 FLASH_MS = 120;

/// hd/FX/weapons.txt: item type -> kind, one table per moment.
bool tableRead = false;
std::unordered_map<std::string, std::string> flashOf, hitOf, swingOf;

struct Clip
{
	/// Frames on disk (0: the mod has no such clip).
	int count = 0;
	/// Loaded frames, by index (empty: not read yet), at scale `k`.
	std::vector<HdFrame> frames;
	std::vector<bool> tried;
	int k = 0;
	Uint32 used = 0;
	size_t bytes = 0;
};
std::unordered_map<std::string, Clip> clips;
size_t loadedBytes = 0;
/// Colour name of a classic frame, by its pixel buffer.
std::unordered_map<const void*, std::string> colours;
std::vector<Live> live;

void readTable()
{
	if (tableRead)
	{
		return;
	}
	tableRead = true;
	const std::string path = HdSprites::artPath(std::string(FOLDER) + "/weapons.txt");
	if (!FileMap::fileExists(path))
	{
		return;
	}
	std::unique_ptr<std::istream> in = FileMap::getIStream(path);
	if (!in)
	{
		return;
	}
	std::string line;
	while (std::getline(*in, line))
	{
		std::istringstream ss(line);
		std::string what, item, kind;
		if (!(ss >> what >> item >> kind) || what[0] == '#')
		{
			continue;
		}
		if (what == "flash") flashOf[item] = kind;
		else if (what == "hit") hitOf[item] = kind;
		else if (what == "swing") swingOf[item] = kind;
	}
	Log(LOG_INFO) << "HD fx: " << flashOf.size() << " guns, " << hitOf.size() << " hits, " << swingOf.size() << " melee weapons";
}

const std::string *lookup(const std::unordered_map<std::string, std::string> &table, const RuleItem *item)
{
	readTable();
	if (!item)
	{
		return nullptr;
	}
	auto i = table.find(item->getType());
	return i != table.end() ? &i->second : nullptr;
}

int damageType(const RuleItem *item, bool melee)
{
	const RuleDamageType *dt = item ? (melee ? item->getMeleeType() : item->getDamageType()) : nullptr;
	return dt ? (int)dt->ResistType : -1;
}

/// Hit family by damage type (X-Piratez names; vanilla 0..9 mean the same kinds), for items the table lacks.
std::string familyByDamage(int dt)
{
	switch (dt)
	{
	case 0: return "charm";
	case 2: return "fire";
	case 4: return "laser";
	case 5: return "plasma";
	case 8: return "acid";
	case 9: return "gas";
	case 11: return "bio";
	case 12: case 13: return "electric";
	case 14: return "warp";
	case 15: return "psi";
	default: return "cal3";
	}
}

std::string boomByDamage(int dt)
{
	switch (dt)
	{
	case 2: return "fire";
	case 4: return "energy";
	case 5: return "plasma";
	case 6: return "stun";
	case 8: return "acid";
	case 9: return "gas";
	case 11: return "bio";
	case 12: case 13: return "electric";
	case 0: case 14: case 15: return "psi";
	default: return "he";
	}
}

bool coloured(const std::string &family)
{
	return family == "laser" || family == "plasma" || family == "electric" || family == "warp" || family == "psi";
}

bool special(const std::string &family)
{
	return family == "acid" || family == "bio" || family == "fire" || family == "gas" || family == "charm" || family == "daze";
}

bool has(const std::string &name, const char *word)
{
	return name.find(word) != std::string::npos;
}

/// What the ground of a tile is made of: the footstep sound of its part, refined by the set name
/// where the sound is shared by unlike grounds (2: asphalt, grass, rock and snow alike).
const char *material(const Tile *tile, int voxelZ)
{
	if (!tile)
	{
		return "dirt";
	}
	static const TilePart low[] = { O_FLOOR, O_OBJECT, O_WESTWALL, O_NORTHWALL };
	static const TilePart high[] = { O_OBJECT, O_WESTWALL, O_NORTHWALL, O_FLOOR };
	const TilePart *order = (voxelZ % 24) <= 2 ? low : high;
	const MapData *data = nullptr;
	for (int i = 0; i < 4 && !data; ++i)
	{
		data = tile->getMapData(order[i]);
	}
	if (!data)
	{
		return "dirt";
	}
	const int step = data->getFootstepSound();
	switch (step)
	{
	case 1: return "metal";
	case 3: return "soft";
	case 4: return "water";
	case 5: return "sand";
	default: break;
	}
	std::string set = data->getDataset() ? data->getDataset()->getName() : "";
	std::transform(set.begin(), set.end(), set.begin(), [](unsigned char c) { return (char)std::toupper(c); });
	if (has(set, "SNOW") || has(set, "POLAR") || has(set, "ICE") || has(set, "ARCTIC")) return "snow";
	if (has(set, "DESERT") || has(set, "SAND") || has(set, "DUNE")) return "sand";
	if (has(set, "WATER") || has(set, "SEA") || has(set, "SWAMP")) return "water";
	if (has(set, "FOREST") || has(set, "JUNGLE") || has(set, "FARM") || has(set, "GRASS") || has(set, "CULT") || has(set, "FIELD")) return "grass";
	if (has(set, "BARN") || has(set, "WOOD") || has(set, "SHACK") || has(set, "HUT")) return "wood";
	if (has(set, "URBAN") || has(set, "ROAD") || has(set, "CITY") || has(set, "STREET") || has(set, "MOUNT") || has(set, "ROCK") || has(set, "CAVE") || has(set, "STONE")) return "stone";
	return step == 6 ? "snow" : step == 0 ? "stone" : "dirt";
}

/// What a hit unit is: the armour immunities give machines and the bloodless (docs/research/combat-fx.md, section 4).
const char *target(const BattleUnit *unit, bool armorHeld)
{
	if (armorHeld)
	{
		return "armor";
	}
	const Armor *armor = unit ? unit->getArmor() : nullptr;
	if (!armor)
	{
		return "flesh";
	}
	const bool bleed = armor->getBleedImmune(), pain = armor->getPainImmune(), zombi = armor->getZombiImmune(), fear = armor->getFearImmune();
	if (fear && (bleed == pain) && (pain == zombi))
	{
		return "mech";          // all four, or fear alone: drones, turrets, the guns of trucks and bunkers
	}
	if (bleed && pain && zombi)
	{
		return "ghost";         // skeletons, ghosts, slimes
	}
	return "flesh";
}

std::string dirName(int direction)
{
	return std::to_string(((direction % 8) + 8) % 8);
}

Clip &clipOf(const std::string &name)
{
	auto i = clips.find(name);
	if (i != clips.end())
	{
		return i->second;
	}
	Clip &clip = clips[name];
	const std::string suffix = ".png";
	for (const std::string &file : HdSprites::artFolder(std::string(FOLDER) + "/" + name))
	{
		if (file.size() > suffix.size() && file.compare(file.size() - suffix.size(), suffix.size(), suffix) == 0 && std::isdigit((unsigned char)file[0]))
		{
			clip.count = std::max(clip.count, std::atoi(file.c_str()) + 1);
		}
	}
	Log(LOG_INFO) << "HD fx clip " << name << ": " << clip.count << " frame(s)" << (clip.count ? "" : " - MISSING, classic animation stays");
	return clip;
}

void drop(Clip &clip)
{
	loadedBytes -= std::min(loadedBytes, clip.bytes);
	clip.frames.clear();
	clip.tried.clear();
	clip.bytes = 0;
	clip.k = 0;
}

}

std::string hitClip(const RuleItem *damageItem, bool onUnit, const BattleUnit *targetUnit, bool armorHeld, const Tile *tile, int voxelZ)
{
	const std::string *table = lookup(hitOf, damageItem);
	std::string family = table ? *table : familyByDamage(damageType(damageItem, false));
	if (family.compare(0, 5, "boom_") == 0)
	{
		family = "cal4";        // an explosive round that hit without a blast
	}
	if (coloured(family))
	{
		return "hit_" + family + "_%c_" + (onUnit ? "unit" : "ground");
	}
	if (special(family))
	{
		return "hit_" + family + "_" + (onUnit ? "unit" : "ground");
	}
	return "hit_" + family + "_" + (onUnit ? target(targetUnit, armorHeld) : material(tile, voxelZ));
}

std::string boomClip(const RuleItem *damageItem)
{
	const std::string *table = lookup(hitOf, damageItem);
	std::string family = table && table->compare(0, 5, "boom_") == 0 ? table->substr(5) : boomByDamage(damageType(damageItem, false));
	if (family == "plasma" || family == "electric" || family == "psi" || family == "energy")
	{
		return "boom_" + family + "_%c";
	}
	return "boom_" + family;
}

std::string swingClip(const RuleItem *weapon, const RuleItem *damage, int direction)
{
	const std::string *table = lookup(swingOf, weapon);
	std::string kind = table ? *table : (weapon && weapon->getBattleType() == BT_FIREARM ? "butt" : "fist");
	const int dt = damageType(damage ? damage : weapon, true);
	if (dt == 12 || dt == 13)
	{
		kind = "shock";
	}
	else if (kind == "blade" && (dt == 4 || dt == 5 || dt == 14))
	{
		return "swing_blade_%c_" + dirName(direction);      // an energy blade glows the colour of its hit
	}
	return "swing_" + kind + "_" + dirName(direction);
}

std::string flashClip(const RuleItem *weapon, const RuleItem *ammo, int direction)
{
	const std::string *table = lookup(flashOf, weapon);
	std::string kind;
	if (table)
	{
		kind = *table;
	}
	else
	{
		const std::string family = familyByDamage(damageType(ammo ? ammo : weapon, false));
		kind = family == "laser" || family == "plasma" || family == "electric" ? family : "rifle";
	}
	if (kind == "laser" || kind == "plasma" || kind == "electric")
	{
		return "flash_" + kind + "_%c_" + dirName(direction);
	}
	return "flash_" + kind + "_" + dirName(direction);
}

std::string colour(const std::string &clip, SurfaceRaw<const Uint8> frame, const SDL_Color *palette)
{
	const size_t at = clip.find("%c");
	if (at == std::string::npos)
	{
		return clip;
	}
	std::string name = "white";
	if (frame && palette)
	{
		auto i = colours.find(frame.getBuffer());
		if (i != colours.end())
		{
			name = i->second;
		}
		else
		{
			// the frame's own colour: the average of its pixels, weighted by brightness
			double r = 0, g = 0, b = 0, w = 0;
			for (int y = 0; y < frame.getHeight(); ++y)
			{
				const Uint8 *row = frame.getBuffer() + (size_t)y * frame.getPitch();
				for (int x = 0; x < frame.getWidth(); ++x)
				{
					if (!row[x]) continue;
					const SDL_Color &c = palette[row[x]];
					const double v = std::max({ c.r, c.g, c.b }) + 1.0;
					r += c.r * v; g += c.g * v; b += c.b * v; w += v;
				}
			}
			if (w > 0)
			{
				r /= w; g /= w; b /= w;
				const double mx = std::max({ r, g, b }), mn = std::min({ r, g, b });
				if (mx > 0 && (mx - mn) / mx >= 0.25)
				{
					double h;
					if (mx == r) h = std::fmod((g - b) / (mx - mn) + 6.0, 6.0);
					else if (mx == g) h = (b - r) / (mx - mn) + 2.0;
					else h = (r - g) / (mx - mn) + 4.0;
					h *= 60.0;
					name = h < 15 || h >= 330 ? "red" : h < 40 ? "orange" : h < 70 ? "yellow" : h < 170 ? "green" : h < 260 ? "blue" : "purple";
				}
			}
			colours[frame.getBuffer()] = name;
		}
	}
	return clip.substr(0, at) + name + clip.substr(at + 2);
}

const HdFrame *frame(const std::string &name, int step, int steps, int k)
{
	if (name.empty() || steps <= 0 || step < 0)
	{
		return nullptr;
	}
	Clip &clip = clipOf(name);
	if (clip.count <= 0)
	{
		return nullptr;
	}
	if (clip.k != k)
	{
		drop(clip);
		clip.k = k;
	}
	if (clip.frames.empty())
	{
		clip.frames.resize(clip.count);
		clip.tried.assign(clip.count, false);
	}
	const int index = std::min(clip.count - 1, step * clip.count / steps);
	clip.used = SDL_GetTicks();
	HdFrame &hd = clip.frames[index];
	if (!clip.tried[index])
	{
		clip.tried[index] = true;
		HdFrame loaded;
		if (HdSprites::loadPng(HdSprites::artPath(std::string(FOLDER) + "/" + name + "/" + std::to_string(index) + ".png"), loaded))
		{
			// the pictures are 4x; another scale gets them resampled
			const int w = loaded.width / 4 * k, h = loaded.height / 4 * k;
			if (w != loaded.width || h != loaded.height)
			{
				HdSprites::resample(loaded, w, h, hd);
			}
			else
			{
				hd = std::move(loaded);
			}
			hd.buildSpans();
			const size_t bytes = hd.pixels.size() * sizeof(Uint32);
			clip.bytes += bytes;
			loadedBytes += bytes;
		}
	}
	return hd.empty() ? nullptr : &hd;
}

void spawn(const std::string &clip, Position voxel)
{
	live.push_back(Live{ clip, voxel, SDL_GetTicks() });
}

bool active()
{
	return !live.empty();
}

void running(Uint32 now, int k, std::vector<std::pair<const Live*, const HdFrame*>> &out)
{
	live.erase(std::remove_if(live.begin(), live.end(), [now](const Live &l) { return now - l.start >= FLASH_MS; }), live.end());
	for (const Live &l : live)
	{
		const HdFrame *hd = frame(l.clip, (int)(now - l.start), (int)FLASH_MS, k);
		if (hd)
		{
			out.push_back(std::make_pair(&l, hd));
		}
	}
}

void trim()
{
	if (loadedBytes <= BUDGET)
	{
		return;
	}
	const Uint32 now = SDL_GetTicks();
	for (auto &i : clips)
	{
		if (i.second.bytes && now - i.second.used > IDLE)
		{
			drop(i.second);
		}
	}
}

void clear()
{
	clips.clear();
	colours.clear();
	live.clear();
	loadedBytes = 0;
	tableRead = false;
	flashOf.clear();
	hitOf.clear();
	swingOf.clear();
}

}

}
