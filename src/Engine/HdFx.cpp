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
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <sstream>
#include <unordered_map>
#include "FileMap.h"
#include "HdSprites.h"
#include "Logger.h"
#include "Options.h"
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
/// The dust of a collapse, kinds A, B, C: frames over this many ms (gen_combat_fx.py DUR_DUST).
const Uint32 DUST_MS[3] = { 1100, 1600, 1500 };
/// A collapsed part falls one level (24 classic pixels) in this many ms, as from rest under gravity
/// (n levels: sqrt(n) times as long); one crumbling where it stood sinks CRUMBLE_PX in CRUMBLE_MS.
const double LEVEL_MS = 250.0;
const Uint32 CRUMBLE_MS = 220;
const int CRUMBLE_PX = 8;

/// hd/FX/weapons.txt: item type -> kind, one table per moment.
bool tableRead = false;
std::unordered_map<std::string, std::string> flashOf, hitOf, swingOf, tracerOf;

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
/// Colour name of a classic frame, by its pixel buffer; valid for the palette `coloursPalette` (a hash of its colours).
std::unordered_map<const void*, std::string> colours;
Uint32 coloursPalette = 0;
std::vector<Live> live;
std::vector<Piece> pieces;

/// How long a piece falling `levels` levels takes (ms).
Uint32 fallMs(int levels)
{
	return levels > 0 ? (Uint32)std::lround(LEVEL_MS * std::sqrt((double)levels)) : CRUMBLE_MS;
}

/// Has a flash or dust ended at `now` (one not started yet has not)?
bool over(const Live &l, Uint32 now)
{
	return (Sint32)(now - l.start) >= (Sint32)(l.ms ? l.ms : FLASH_MS);
}

void dropLanded(Uint32 now)
{
	live.erase(std::remove_if(live.begin(), live.end(), [now](const Live &l) { return over(l, now); }), live.end());
	pieces.erase(std::remove_if(pieces.begin(), pieces.end(), [now](const Piece &p) { return now - p.start >= fallMs(p.levels); }), pieces.end());
}

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
		else if (what == "tracer") tracerOf[item] = kind;
	}
	Log(LOG_INFO) << "HD fx: " << flashOf.size() << " guns, " << hitOf.size() << " hits, " << swingOf.size() << " melee weapons, " << tracerOf.size() << " tracer styles";
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

const char *materialOf(const MapData *data);

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
	return materialOf(data);
}

/// What a terrain part is made of (see material).
const char *materialOf(const MapData *data)
{
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
	// a tinted clip ("<clip>@RRGGBB", tinted()) lives in the folder of its plain clip
	for (const std::string &file : HdSprites::artFolder(std::string(FOLDER) + "/" + name.substr(0, name.find('@'))))
	{
		if (file.size() > suffix.size() && file.compare(file.size() - suffix.size(), suffix.size(), suffix) == 0 && std::isdigit((unsigned char)file[0]))
		{
			clip.count = std::max(clip.count, std::atoi(file.c_str()) + 1);
		}
	}
	Log(LOG_INFO) << "HD fx clip " << name << ": " << clip.count << " frame(s)" << (clip.count ? "" : " - MISSING, classic animation stays");
	return clip;
}

/// XP-000366: hd/blood.txt, "NAME RRGGBB" a line ('#' a comment): exact armour types and prefixes ("ZOMBIE_*"), read once.
bool bloodRead = false;
std::unordered_map<std::string, int> bloodExact;
std::vector<std::pair<std::string, int>> bloodPrefix;
/// The colour found for an armour type (-1: none), so the table is searched once for each type.
std::unordered_map<std::string, int> bloodOf;

void readBlood()
{
	if (bloodRead)
	{
		return;
	}
	bloodRead = true;
	const std::string path = HdSprites::artPath("blood.txt");
	std::unique_ptr<std::istream> in = FileMap::fileExists(path) ? FileMap::getIStream(path) : nullptr;
	if (!in)
	{
		return;
	}
	std::string line;
	while (std::getline(*in, line))
	{
		if (line.size() >= 3 && (unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF)
		{
			line.erase(0, 3);
		}
		std::istringstream fields(line);
		std::string name, hex;
		if (!(fields >> name >> hex) || name[0] == '#')
		{
			continue;
		}
		const int rgb = (int)(std::strtoul(hex.c_str() + (hex[0] == '#' ? 1 : 0), nullptr, 16) & 0xFFFFFF);
		if (name.back() == '*')
		{
			name.pop_back();
			bloodPrefix.emplace_back(name, rgb);
		}
		else
		{
			bloodExact[name] = rgb;
		}
	}
	Log(LOG_INFO) << "HD blood: " << bloodExact.size() << " names and " << bloodPrefix.size() << " prefixes of " << path;
}

/// Is `clip` a blood clip: a hit on flesh, a spray or a stab?
bool isBlood(const std::string &clip)
{
	static const std::string FLESH = "_flesh";
	return clip.compare(0, 6, "blood_") == 0 || clip.compare(0, 5, "stab_") == 0
		|| (clip.compare(0, 4, "hit_") == 0 && clip.size() > FLESH.size() && clip.compare(clip.size() - FLESH.size(), FLESH.size(), FLESH) == 0);
}

/// The tone of the blood becomes the colour `rgb`: a pixel that is red (the blood and the flash of a hit; the grey, white and
/// yellow of sparks are left) takes the colour scaled by its brightness against the clip's blood (190 of 255), so the body of the blood
/// is the table's colour itself, the highlights lighter (towards white) and the shadows darker; the alpha stays. Once, when a frame loads.
void tintBlood(HdFrame &hd, int rgb)
{
	const double tr = (rgb >> 16) & 255, tg = (rgb >> 8) & 255, tb = rgb & 255;
	for (Uint32 &p : hd.pixels)
	{
		const Uint32 a = p >> 24;
		const int r = (p >> 16) & 255, g = (p >> 8) & 255, b = p & 255;
		const int v = std::max({ r, g, b }), mn = std::min({ r, g, b });
		if (a == 0 || v == 0 || r != v)
		{
			continue;
		}
		// the hue within 45 degrees of red, and enough saturation (the flash of a hit is paler: it takes the colour partly)
		const double s = (double)(v - mn) / v;
		const int hue60 = (g - b) * 60;
		if (v == mn || std::abs(hue60) > 45 * (v - mn))
		{
			continue;
		}
		const double w = std::max(0.0, std::min(1.0, (s - 0.30) / 0.25));
		if (w <= 0.0)
		{
			continue;
		}
		const double f = v / 190.0;
		double nr = tr * f, ng = tg * f, nb = tb * f;
		const double top = std::max({ nr, ng, nb });
		if (top > 255.0)
		{
			// over the top: the highlight goes lighter towards white, keeping the tone
			const double lift = std::min(1.0, (top - 255.0) / 255.0), k = 255.0 / top;
			nr = nr * k * (1.0 - lift) + 255.0 * lift;
			ng = ng * k * (1.0 - lift) + 255.0 * lift;
			nb = nb * k * (1.0 - lift) + 255.0 * lift;
		}
		const int orr = (int)std::lround(r + (nr - r) * w), og = (int)std::lround(g + (ng - g) * w), ob = (int)std::lround(b + (nb - b) * w);
		p = (a << 24) | ((Uint32)std::max(0, std::min(255, orr)) << 16) | ((Uint32)std::max(0, std::min(255, og)) << 8) | (Uint32)std::max(0, std::min(255, ob));
	}
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
	const int dt = damageType(damageItem, false);
	std::string family = table ? *table : familyByDamage(dt);
	if (family == "classic")
	{
		return "";              // the weapon's own animation reads better than any clip (the flying CD discs)
	}
	if (family.compare(0, 5, "boom_") == 0)
	{
		family = "cal4";        // an explosive round that hit without a blast
	}
	// the table knows calibres, not what a round does: a stun round dazes, a light concussive one (a stone, a slug) strikes blunt
	if (dt == 6 && (family.compare(0, 3, "cal") == 0 || family == "pellet"))
	{
		family = "daze";
	}
	else if (dt == 3 && (family == "cal1" || family == "cal2" || family == "cal3"))
	{
		family = "blunt";
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

std::string sprayClip(const std::string &clip, int dx, int dy, int loss, unsigned int seed)
{
	static const std::string FLESH = "_flesh";
	if (loss <= 0 || (dx == 0 && dy == 0) || clip.size() <= FLESH.size() || clip.compare(0, 4, "hit_") != 0
		|| clip.compare(clip.size() - FLESH.size(), FLESH.size(), FLESH) != 0)
	{
		return "";
	}
	// the screen's angle, y down: clockwise from "right"; the clips name the eight directions the same way (gen_combat_fx.py blood_spray)
	const int d = (((int)std::lround(std::atan2((double)dy, (double)dx) / (3.14159265358979323846 / 4.0))) % 8 + 8) % 8;
	const int s = loss < 10 ? 1 : (loss < 30 ? 2 : 3);
	return "blood_" + std::to_string(s) + "_" + std::to_string(d) + "_" + (char)('a' + (seed >> 8) % 3);
}

std::string stabClip(const std::string &swing, int dx, int dy, int loss, unsigned int seed)
{
	static const char *KINDS[] = {"swing_blade_", "swing_pierce_", "swing_claw_", "swing_bite_", "swing_sting_", "swing_whip_"};
	if (loss <= 0 || (dx == 0 && dy == 0) || swing.find("%c") != std::string::npos)
	{
		return "";
	}
	bool blood = false;
	for (const char *kind : KINDS)
	{
		blood = blood || swing.compare(0, std::strlen(kind), kind) == 0;
	}
	if (!blood)
	{
		return "";
	}
	// the same eight directions and three strengths as sprayClip (gen_combat_fx.py stab_spray)
	const int d = (((int)std::lround(std::atan2((double)dy, (double)dx) / (3.14159265358979323846 / 4.0))) % 8 + 8) % 8;
	const int s = loss < 10 ? 1 : (loss < 30 ? 2 : 3);
	return "stab_" + std::to_string(s) + "_" + std::to_string(d) + "_" + (char)('a' + (seed >> 8) % 3);
}

int bloodRgb(const Armor *armor)
{
	if (!Options::oxceHdBloodColor || !armor)
	{
		return -1;
	}
	readBlood();
	const std::string &type = armor->getType();
	auto known = bloodOf.find(type);
	if (known != bloodOf.end())
	{
		return known->second;
	}
	int rgb = -1;
	auto exact = bloodExact.find(type);
	if (exact != bloodExact.end())
	{
		rgb = exact->second;
	}
	else
	{
		size_t longest = 0;
		for (const auto &p : bloodPrefix)
		{
			if (p.first.size() >= longest && type.compare(0, p.first.size(), p.first) == 0)
			{
				longest = p.first.size();
				rgb = p.second;
			}
		}
	}
	if (rgb >= 0)
	{
		// what the effects see in this armour, to know whether its blood or its sparks are drawn
		const bool bl = armor->getBleedImmune(), pa = armor->getPainImmune(), zo = armor->getZombiImmune(), fe = armor->getFearImmune();
		const char *kind = fe && bl == pa && pa == zo ? "mech (sparks, no blood)" : bl && pa && zo ? "ghost" : "flesh (blood)";     // as target()
		Log(LOG_INFO) << "HD blood: armour " << type << " -> " << std::hex << rgb << std::dec << ", a hit on it is drawn as " << kind
			<< " (bleed " << armor->getBleedImmune() << " pain " << armor->getPainImmune() << " zombi " << armor->getZombiImmune() << " fear " << armor->getFearImmune() << ")";
	}
	bloodOf[type] = rgb;
	return rgb;
}

std::string tinted(const std::string &clip, int rgb)
{
	if (rgb < 0 || clip.find('@') != std::string::npos || !isBlood(clip))
	{
		return clip;
	}
	char hex[8];
	std::snprintf(hex, sizeof(hex), "@%06X", rgb & 0xFFFFFF);
	return clip + hex;
}

int lossPercent(const BattleUnit *unit, int lost)
{
	const int full = unit ? std::max(1, (int)unit->getBaseStats()->health) : 1;
	return std::max(1, std::min(100, lost * 100 / full));
}

unsigned int hitHash(Position at, int loss)
{
	static unsigned int n = 0;
	unsigned int h = (unsigned int)at.x * 73856093u ^ (unsigned int)at.y * 19349663u ^ (unsigned int)at.z * 83492791u
		^ (unsigned int)loss * 2654435761u ^ (++n * 2246822519u);
	h ^= h >> 15;
	h *= 2246822519u;
	h ^= h >> 13;
	return h;
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
	if (kind == "none")
	{
		return "";              // bows, thrown weapons, creatures: nothing leaves a muzzle
	}
	if (kind == "laser" || kind == "plasma" || kind == "electric")
	{
		return "flash_" + kind + "_%c_" + dirName(direction);
	}
	return "flash_" + kind + "_" + dirName(direction);
}

bool tracerStyle(const RuleItem *item, DotStyle &style)
{
	const std::string *table = lookup(tracerOf, item);
	if (!table)
	{
		return false;
	}
	// "classic", "bright;fade=0.4", "head=90,170,255", "width=0.55"
	std::istringstream ss(*table);
	std::string opt;
	while (std::getline(ss, opt, ';'))
	{
		const size_t eq = opt.find('=');
		const std::string key = opt.substr(0, eq), value = eq == std::string::npos ? "" : opt.substr(eq + 1);
		if (key == "classic") style.classic = true;
		else if (key == "bright") style.bright = true;
		else if (key == "width") style.width = std::atof(value.c_str());
		else if (key == "fade") style.fade = std::atof(value.c_str());
		else if (key == "head" && std::sscanf(value.c_str(), "%d,%d,%d", &style.headR, &style.headG, &style.headB) != 3) style.headR = -1;
	}
	return true;
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
		// the same frame reads another colour under another palette: a new palette forgets the names
		Uint32 hash = 2166136261u;
		for (int c = 0; c < 256; ++c)
		{
			hash = (hash ^ (Uint32)((palette[c].r << 16) | (palette[c].g << 8) | palette[c].b)) * 16777619u;
		}
		if (hash != coloursPalette)
		{
			colours.clear();
			coloursPalette = hash;
		}
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
		// a tinted clip ("<clip>@RRGGBB", tinted()): the picture of the plain clip, recoloured once here and kept
		const size_t at = name.find('@');
		if (HdSprites::loadPng(HdSprites::artPath(std::string(FOLDER) + "/" + name.substr(0, at) + "/" + std::to_string(index) + ".png"), loaded))
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
			if (at != std::string::npos)
			{
				tintBlood(hd, (int)std::strtoul(name.c_str() + at + 1, nullptr, 16));
			}
			hd.buildSpans();
			const size_t bytes = hd.pixels.size() * sizeof(Uint32);
			clip.bytes += bytes;
			loadedBytes += bytes;
		}
	}
	return hd.empty() ? nullptr : &hd;
}

void spawn(const std::string &clip, Position voxel, int item)
{
	live.push_back(Live{ clip, voxel, SDL_GetTicks(), item, false, 0, 0 });
	noteForTest(clip);
}

void clearTips()
{
	for (Live &l : live)
	{
		l.tip = false;
	}
}

bool wantsTip(int item)
{
	for (const Live &l : live)
	{
		if (l.item == item && item >= 0)
		{
			return true;
		}
	}
	return false;
}

void noteTip(int item, const Surface *frame, int direction, int x, int y)
{
	if (!frame || direction < 0 || direction > 7)
	{
		return;
	}
	// the facing on screen, as Pathfinding::dir_x / dir_y through the isometric view
	static const int dirX[8] = { 0, 1, 1, 1, 0, -1, -1, -1 };
	static const int dirY[8] = { -1, -1, 0, 1, 1, 1, 0, -1 };
	const double sx = dirX[direction] - dirY[direction], sy = (dirX[direction] + dirY[direction]) * 0.5;
	// the muzzle: the drawn pixels furthest along the facing (the end of the barrel), averaged
	double best = -1e9;
	for (int py = 0; py < frame->getHeight(); ++py)
		for (int px = 0; px < frame->getWidth(); ++px)
			if (frame->getPixel(px, py))
				best = std::max(best, px * sx + py * sy);
	if (best < -1e8)
	{
		return;
	}
	const double band = 0.75 * frame->getWidth() / 32.0;   // a classic pixel, in the pixels of this frame
	double mx = 0, my = 0;
	int n = 0;
	for (int py = 0; py < frame->getHeight(); ++py)
		for (int px = 0; px < frame->getWidth(); ++px)
			if (frame->getPixel(px, py) && px * sx + py * sy >= best - band)
			{
				mx += px;
				my += py;
				++n;
			}
	for (Live &l : live)
	{
		if (l.item == item)
		{
			l.tip = true;
			l.tipX = x + (int)std::lround(mx / n + 0.5);
			l.tipY = y + (int)std::lround(my / n + 0.5);
		}
	}
}

namespace
{
std::vector<std::pair<std::string, Uint32>> testDumps;
int testDumped = 0;
}

void noteForTest(const std::string &clip, Uint32 after)
{
	static const char *prefix = getenv("OXCE_HD_DUMP_FX");
	if (!prefix || !*prefix || clip.empty() || testDumped + testDumps.size() >= 4)
	{
		return;
	}
	// OXCE_HD_DUMP_FX_ONLY=<part of the name>: only such clips (hits on a unit: "_unit", "_armor")
	static const char *only = getenv("OXCE_HD_DUMP_FX_ONLY");
	if (only && *only && clip.find(only) == std::string::npos)
	{
		return;
	}
	testDumps.emplace_back(clip, SDL_GetTicks() + after);  // a few frames in: the clip is on screen, not yet over
}

std::string takeTestDump(Uint32 now)
{
	if (testDumps.empty() || now < testDumps.front().second)
	{
		return "";
	}
	std::string name = testDumps.front().first;
	testDumps.erase(testDumps.begin());
	for (char &c : name)
	{
		if (!std::isalnum((unsigned char)c)) c = '_';
	}
	// queued only by noteForTest, so the variable is set
	static const std::string prefix = getenv("OXCE_HD_DUMP_FX");
	return prefix + "_" + std::to_string(++testDumped) + "_" + name + ".png";
}

Uint32 fall(SurfaceRaw<const Uint8> sprite, Position cell, int part, int yOffset, int levels)
{
	pieces.push_back(Piece{ sprite, cell, part, yOffset, levels, SDL_GetTicks() });
	return fallMs(levels);
}

void falling(Uint32 now, std::vector<std::pair<const Piece*, int>> &out)
{
	dropLanded(now);
	for (const Piece &p : pieces)
	{
		const double u = (double)(now - p.start) / fallMs(p.levels);
		// from rest under gravity: the way down grows with the square of the time
		const int down = p.levels > 0 ? (int)(24 * p.levels * u * u) : (int)(CRUMBLE_PX * u);
		out.push_back(std::make_pair(&p, down));
	}
}

void dust(char kind, Position cell, const MapData *what, Uint32 delay)
{
	const int i = kind == 'B' ? 1 : kind == 'C' ? 2 : 0;
	// the clips have the colours of stone, wood and metal (gen_combat_fx.py DUST); other grounds take stone's
	const std::string mat = materialOf(what);
	const std::string clip = std::string("collapse_dust_") + "ABC"[i] + "_" + (mat == "wood" || mat == "metal" ? mat : "stone");
	Live l{ clip, Position(cell.x * 16 + 8, cell.y * 16 + 8, cell.z * 24), SDL_GetTicks() + delay, -1, false, 0, 0 };
	l.ms = DUST_MS[i];
	live.push_back(l);
	noteForTest(clip, delay + l.ms / 3);
}

const char *partMaterial(const MapData *data)
{
	return materialOf(data);
}

bool active(Uint32 now)
{
	dropLanded(now);
	return !live.empty() || !pieces.empty();
}

void running(Uint32 now, int k, std::vector<std::pair<const Live*, const HdFrame*>> &out)
{
	dropLanded(now);
	for (const Live &l : live)
	{
		if ((Sint32)(now - l.start) < 0)
		{
			continue;
		}
		const Uint32 ms = l.ms ? l.ms : FLASH_MS;
		const HdFrame *hd = frame(l.clip, (int)(now - l.start), (int)ms, k);
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
	coloursPalette = 0;
	live.clear();
	pieces.clear();
	loadedBytes = 0;
	tableRead = false;
	flashOf.clear();
	hitOf.clear();
	swingOf.clear();
	tracerOf.clear();
}

}

}
