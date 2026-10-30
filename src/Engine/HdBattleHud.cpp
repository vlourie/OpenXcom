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
#include "HdBattleHud.h"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <mutex>
#include <string>
#include <unordered_map>
#include "HdFont.h"
#include "HdSprites.h"
#include "HdUi.h"
#include "HdUiArt.h"
#include "HdWorkers.h"
#include "Options.h"
#include "Unicode.h"

namespace OpenXcom
{

namespace
{

// the panel's own colours (0xAARRGGBB), the same in every mod: a dark slate with one warm accent, or
// the brass of the original panel (oxceHdBattleHudColor 1: brushed brass keys on dark steel)
struct Theme
{
	Uint32 panelTop, panelBottom, panelEdge;
	Uint32 tileTop, tileBottom, tileEdge, hoverTop, hoverBottom, sheenTop, sheenBottom;
	Uint32 accent, litTop, litBottom;
	Uint32 icon, iconHover, iconLit;
	Uint32 wellTop, wellBottom, wellEdge;
	Uint32 cardTop, cardBottom, cardEdge;
	Uint32 rankFill;
	bool plaques;     ///< the keys are the original's plaques in relief, the pictograms struck in (drawPlaque)
	// the plaques' metal: its shades dark to light (rampColor), the texture of its face, the steel between the
	// keys, the floors of the hands' wells and of the card, the light caught by a lip, a bar's groove
	const Uint32 *ramp;
	bool plated;      ///< cast hull plating (mottled) instead of brushed metal
	Uint32 steel, wellBase, cardBase, lipLight, grooveTop, grooveBottom;
	int hull;         ///< the hull's relief on the metal: 0 none, 1 the Consul's shingled plates, 2 the Cruiser's riveted panels
};

/// Pale brass, dark to light, at the shades 0, 0.15 ... 1: a flat face facing the light sits at 0.6.
const float RAMP_AT[] = { 0.0f, 0.15f, 0.3f, 0.45f, 0.6f, 0.75f, 1.0f };
const Uint32 BRASS[] = { 0xFF100C07u, 0xFF292016u, 0xFF4B3D26u, 0xFF786341u, 0xFFA9926Au, 0xFFBAA57Du, 0xFFD3C3A1u };
/// The lilac steel of the ships' hulls as the HD pack paints them (the Consul's sides, light; the Cruiser's, dark).
const Uint32 HULL_LIGHT[] = { 0xFF120F1Au, 0xFF281F34u, 0xFF413A5Bu, 0xFF6E6586u, 0xFF8C86A6u, 0xFFA3A0BEu, 0xFFCFCEE6u };
const Uint32 HULL_DARK[] = { 0xFF0C0814u, 0xFF1A1129u, 0xFF2E2642u, 0xFF4B4365u, 0xFF655D7Cu, 0xFF7E7590u, 0xFFAEA4B4u };
/// The dark panel's keys: blued graphite steel.
const Uint32 GRAPHITE[] = { 0xFF06080Bu, 0xFF10141Au, 0xFF1C222Bu, 0xFF2B333Eu, 0xFF3B4551u, 0xFF4C5764u, 0xFF7A8594u };
/// Polished ship's brass, warmer and deeper than the original's pale gold (the pirate panel).
const Uint32 SHIP_BRASS[] = { 0xFF140C05u, 0xFF33210Fu, 0xFF5E4220u, 0xFF94703Au, 0xFFC9A35Au, 0xFFDDBB72u, 0xFFF6E3A8u };
/// The keys' metal of the painted panels after the brass one: lilac anodized alloy, sterling silver, blackened wrought
/// iron, bronze green with verdigris (the shades of their painted plates).
const Uint32 LILAC_ALLOY[] = { 0xFF0E0A16u, 0xFF241A36u, 0xFF3E2E5Eu, 0xFF5E4888u, 0xFF8466B0u, 0xFFA084C8u, 0xFFD8C6F0u };
const Uint32 STERLING[] = { 0xFF0A0B0Du, 0xFF22262Bu, 0xFF444A52u, 0xFF6E767Fu, 0xFF9AA2ABu, 0xFFB8BFC7u, 0xFFEEF2F6u };
const Uint32 WROUGHT_IRON[] = { 0xFF0A0908u, 0xFF1C1916u, 0xFF2E2A26u, 0xFF46403Au, 0xFF625A52u, 0xFF7C7268u, 0xFFB0A498u };
const Uint32 VERDIGRIS[] = { 0xFF08100Cu, 0xFF16261Eu, 0xFF2A4436u, 0xFF436A54u, 0xFF5E9478u, 0xFF78AE92u, 0xFFB8E0CCu };

const Theme SLATE = {
	0xF4171D26u, 0xF40B0E13u, 0x38FFFFFFu,
	0xFF2A323Eu, 0xFF1C222Bu, 0x2EFFFFFFu, 0xFF36414Fu, 0xFF252D38u, 0x14FFFFFFu, 0x02FFFFFFu,
	0xFFE6A23Cu, 0xFFF2B655u, 0xFFC2822Au,
	0xFFCDD6E1u, 0xFFFFFFFFu, 0xFF22180Bu,
	0xFF05070Au, 0xFF0D1015u, 0x36FFFFFFu,
	0xFF0E1218u, 0xFF0A0D11u, 0x22FFFFFFu,
	0xFF151A22u,
	false,
	GRAPHITE, false, 0, 0, 0, 0, 0, 0,
	0,
};

const Theme GOLD = {
	0xF4301A0Au, 0xF4120904u, 0xA0F8E57Bu,
	0xFFD8A73Du, 0xFFA36725u, 0x90FFF6AFu, 0xFFE4CA48u, 0xFFB77B2Cu, 0x38FFF6AFu, 0x04FFF6AFu,
	0xFFFFF6AFu, 0xFFFFF6AFu, 0xFFE4CA48u,
	0xFF43210Du, 0xFF221209u, 0xFF341A0Bu,
	0xFF56575Au, 0xFF2E2F31u, 0xB0C79033u,
	0xFF2A2116u, 0xFF19130Bu, 0x90B77B2Cu,
	0xFF3A2D1Bu,
	true,
	BRASS, false, 0xFF8A8C90u, 0x48484Bu, 0x4E3E2Au, 0xF0D8A0u, 0xF0140E08u, 0xF0281E12u,
	0,
};

// the ships' hulls (oxceHdBattleHudColor 2 the Consul's light lilac steel, 3 the Cruiser's dark one): the plaques
// cast in the hull's plating, the steel between them and the floors in the same cool tone
const Theme CONSUL = {
	0xF4211C2Cu, 0xF40E0B14u, 0x60CFCEE6u,
	0xFF8C86A6u, 0xFF6E6586u, 0x70CFCEE6u, 0xFFA3A0BEu, 0xFF7A7396u, 0x30CFCEE6u, 0x04CFCEE6u,
	0xFFCFCEE6u, 0xFFCFCEE6u, 0xFFA3A0BEu,
	0xFF1A1526u, 0xFF0E0B14u, 0xFF15111Eu,
	0xFF4E4A5Cu, 0xFF2C2934u, 0xB08C86A6u,
	0xFF221E2Eu, 0xFF14111Cu, 0x906E6586u,
	0xFF2E2840u,
	true,
	HULL_LIGHT, true, 0xFF6C6680u, 0x44404Eu, 0x3C3650u, 0xDCD8F4u, 0xF00E0C14u, 0xF01E1A28u,
	1,
};

const Theme CRUISER = {
	0xF4181420u, 0xF40A080Eu, 0x60AEA4B4u,
	0xFF655D7Cu, 0xFF4B4365u, 0x70AEA4B4u, 0xFF7E7590u, 0xFF564E6Eu, 0x30AEA4B4u, 0x04AEA4B4u,
	0xFFAEA4B4u, 0xFFAEA4B4u, 0xFF7E7590u,
	0xFF120E1Au, 0xFF0A080Eu, 0xFF0E0B14u,
	0xFF3E3A4Au, 0xFF221F28u, 0xB0655D7Cu,
	0xFF1A1622u, 0xFF0E0B14u, 0x904B4365u,
	0xFF241F32u,
	true,
	HULL_DARK, true, 0xFF4E4860u, 0x3A3644u, 0x302A40u, 0xC8C0D8u, 0xF00A0810u, 0xF0161220u,
	2,
};

// the pirate panel (oxceHdBattleHudColor 4): ship's brass keys screwed onto dark mahogany planking, the signs
// engraved and hatched, the reserve keys' signs filled with enamel of their colour
const Theme PIRATE = {
	0xF42A1A10u, 0xF4140C07u, 0xA0E0B860u,
	0xFFD8A73Du, 0xFFA36725u, 0x90FFF6AFu, 0xFFE4CA48u, 0xFFB77B2Cu, 0x38FFF6AFu, 0x04FFF6AFu,
	0xFFFFD27Au, 0xFFFFE2A0u, 0xFFE4B048u,
	0xFF2E1A0Au, 0xFF1A0E06u, 0xFF26150Au,
	0xFF3A2A1Cu, 0xFF20160Eu, 0xB0C79033u,
	0xFF2A1C12u, 0xFF180F09u, 0x90B77B2Cu,
	0xFF3A2614u,
	true,
	SHIP_BRASS, false, 0xFF70401Eu, 0x3E2A1Cu, 0x46301Eu, 0xF4D49Au, 0xF0120A05u, 0xF0261A10u,
	3,
};

// the painted panels after it, built the same way, each with its own pictures (keyLook().folder): a starship's
// bridge (5: lilac alloy keys on graphite plating), a nobleman's console (6: silver and niello on black lacquer),
// a grim captain's (7: black iron inlaid with bone on charred oak), a diving vessel's (8: bronze on copper sheets)
const Theme STARSHIP = {
	0xF41A1826u, 0xF40A0A10u, 0xA0A084C8u,
	0xFF8466B0u, 0xFF5E4888u, 0x90D8C6F0u, 0xFFA084C8u, 0xFF6A5294u, 0x38D8C6F0u, 0x04D8C6F0u,
	0xFFE0C8FFu, 0xFFEEDDFFu, 0xFFB08EE8u,
	0xFF140E20u, 0xFF0A0812u, 0xFF100A1Au,
	0xFF1E1C26u, 0xFF0E0D14u, 0xB08466B0u,
	0xFF1A1824u, 0xFF0E0C14u, 0x905E4888u,
	0xFF2A2238u,
	true,
	LILAC_ALLOY, false, 0xFF3A3448u, 0x1A1A22u, 0x221E2Cu, 0xD8C6F0u, 0xF00A0812u, 0xF01A1626u,
	2,
};

const Theme NIELLO = {
	0xF4100E0Eu, 0xF4050404u, 0xA0D8DEE6u,
	0xFF9AA2ABu, 0xFF6E767Fu, 0x90EEF2F6u, 0xFFB8BFC7u, 0xFF7E868Fu, 0x38EEF2F6u, 0x04EEF2F6u,
	0xFFF2F6FAu, 0xFFFFFFFFu, 0xFFC2CAD2u,
	0xFF0E1014u, 0xFF06070Au, 0xFF0A0C0Fu,
	0xFF141C34u, 0xFF080C1Au, 0xB09AA2ABu,
	0xFF121418u, 0xFF08090Bu, 0x906E767Fu,
	0xFF1C2028u,
	true,
	STERLING, false, 0xFF5A6068u, 0x101A30u, 0x1A1E26u, 0xF0F4F8u, 0xF0050506u, 0xF0141618u,
	3,
};

const Theme IRON_BONE = {
	0xF4241810u, 0xF40E0805u, 0xA0A08870u,
	0xFF625A52u, 0xFF46403Au, 0x90B0A498u, 0xFF7C7268u, 0xFF524A44u, 0x38B0A498u, 0x04B0A498u,
	0xFFF0E2C0u, 0xFFFFF0D0u, 0xFFC8B48Cu,
	0xFFE0D2B0u, 0xFFF4E8CCu, 0xFF2A1A0Cu,
	0xFF3A1410u, 0xFF1E0A08u, 0xB07C7268u,
	0xFF22160Eu, 0xFF120B07u, 0x9046403Au,
	0xFF2E2218u,
	true,
	WROUGHT_IRON, false, 0xFF3A3530u, 0x3A1810u, 0x2A1E16u, 0xD8C8B0u, 0xF00A0806u, 0xF01A1612u,
	3,
};

const Theme DEEP_BRONZE = {
	0xF4122018u, 0xF4060C08u, 0xA078C8A8u,
	0xFF5E9478u, 0xFF436A54u, 0x90B8E0CCu, 0xFF78AE92u, 0xFF4A765Eu, 0x38B8E0CCu, 0x04B8E0CCu,
	0xFF9CF0D4u, 0xFFC0FFE8u, 0xFF5CC8A4u,
	0xFF06120Cu, 0xFF030A06u, 0xFF050E09u,
	0xFF0E3A30u, 0xFF06201Au, 0xB05E9478u,
	0xFF0E1C16u, 0xFF07100Cu, 0x90436A54u,
	0xFF1A3028u,
	true,
	VERDIGRIS, false, 0xFF2E5040u, 0x0E3A30u, 0x142A22u, 0xB8E8D0u, 0xF0040A08u, 0xF0102018u,
	2,
};

/// The bars laid in grooves of the panel's card (HdHudPanel::PART_BAR), the numbers on the hands' wells (PART_COUNT).
std::vector<const Surface*> grooves, counters;

// --- the player's own colour (oxceHdBattleHudColor 9, XP-000377) ---
// A theme built from two colours the player picks (hue, saturation, value each): the keys' (their metal, the legends'
// light, the accent) and the background's (the panel's steel, wells, card, grooves). It is the Cruiser's theme with
// every colour moved to the chosen hue and saturation and the chosen value, the steps of the metal keeping their
// brightness relative to each other (and the alpha of each colour). Built again only when an option changes.

struct Hsv { float h, s, v; };   ///< h 0..360, s and v 0..1

Hsv toHsv(Uint32 c)
{
	const float r = (float)((c >> 16) & 0xFF) / 255.0f, g = (float)((c >> 8) & 0xFF) / 255.0f, b = (float)(c & 0xFF) / 255.0f;
	const float mx = std::max(r, std::max(g, b)), mn = std::min(r, std::min(g, b)), d = mx - mn;
	float h = 0.0f;
	if (d > 1e-6f)
	{
		if (mx == r) h = 60.0f * std::fmod((g - b) / d, 6.0f);
		else if (mx == g) h = 60.0f * ((b - r) / d + 2.0f);
		else h = 60.0f * ((r - g) / d + 4.0f);
		if (h < 0.0f) h += 360.0f;
	}
	return Hsv{ h, mx > 1e-6f ? d / mx : 0.0f, mx };
}

/// 0xAARRGGBB with the alpha byte of `like`.
Uint32 fromHsv(float h, float s, float v, Uint32 like = 0xFF000000u)
{
	h = std::fmod(std::fmod(h, 360.0f) + 360.0f, 360.0f);
	s = std::min(std::max(s, 0.0f), 1.0f);
	v = std::min(std::max(v, 0.0f), 1.0f);
	const float c = v * s, x = c * (1.0f - std::fabs(std::fmod(h / 60.0f, 2.0f) - 1.0f)), m = v - c;
	float r = 0, g = 0, b = 0;
	switch ((int)(h / 60.0f))
	{
	case 0: r = c; g = x; break;
	case 1: r = x; g = c; break;
	case 2: g = c; b = x; break;
	case 3: g = x; b = c; break;
	case 4: r = x; b = c; break;
	default: r = c; b = x; break;
	}
	auto ch = [&](float f) { return (Uint32)std::min(std::max((f + m) * 255.0f + 0.5f, 0.0f), 255.0f); };
	return (like & 0xFF000000u) | (ch(r) << 16) | (ch(g) << 8) | ch(b);
}

/// What the player's colours made: the theme, its metal's ramp, the keys' hue for their legends' light.
struct CustomState
{
	int sig[6] = { -1, -1, -1, -1, -1, -1 };   ///< the options it was built from
	unsigned version = 0;                      ///< counts the buildings: what caches of it are keyed by
	Theme theme = CRUISER;
	Uint32 ramp[7] = {};
	float keyH = 0.0f, keyV = 0.0f;
};
CustomState custom;
std::mutex customMutex;

/// A colour of the keys' group moved to the player's key colour k (the Cruiser's face colour is where k lands).
Uint32 keyTone(Uint32 c, const Hsv &k)
{
	static const Hsv ref = toHsv(HULL_DARK[4]), top = toHsv(HULL_DARK[6]);
	const Hsv a = toHsv(c);
	float v;
	if (a.v <= ref.v)
	{
		v = k.v * a.v / ref.v;
	}
	else
	{
		// above the face the highlights climb toward white, by as much as is left
		const float ceil = k.v + (1.0f - k.v) * 0.6f;
		v = k.v + std::min((a.v - ref.v) / (top.v - ref.v), 1.3f) * (ceil - k.v);
	}
	const float s = k.s * std::min(std::max(a.s / ref.s, 0.35f), 1.25f);
	return fromHsv(k.h, s, v, c);
}

/// A colour of the background's group moved to the player's background colour b (the Cruiser's steel is where b lands).
Uint32 backTone(Uint32 c, const Hsv &b)
{
	static const Hsv ref = toHsv(CRUISER.steel);
	const Hsv a = toHsv(c);
	const float s = b.s * std::min(std::max(a.s / ref.s, 0.35f), 1.25f);
	return fromHsv(b.h, s, a.v * b.v / ref.v, c);
}

/// Builds the theme again if an option it comes from changed. The first call after a change must come from the main
/// thread, before the render threads read the theme (themeKey, metalCached and the drawing calls do).
void customRefresh()
{
	auto in = [](int v, int hi) { return std::min(std::max(v, 0), hi); };
	const int sig[6] = { in(Options::oxceHdCustomKeyHue, 359), in(Options::oxceHdCustomKeySat, 100), in(Options::oxceHdCustomKeyVal, 100),
		in(Options::oxceHdCustomBackHue, 359), in(Options::oxceHdCustomBackSat, 100), in(Options::oxceHdCustomBackVal, 100) };
	if (std::equal(sig, sig + 6, custom.sig))
	{
		return;
	}
	std::lock_guard<std::mutex> lock(customMutex);
	if (std::equal(sig, sig + 6, custom.sig))
	{
		return;
	}
	const Hsv k = { (float)sig[0], (float)sig[1] / 100.0f, (float)sig[2] / 100.0f }, b = { (float)sig[3], (float)sig[4] / 100.0f, (float)sig[5] / 100.0f };
	const Theme &base = CRUISER;
	Theme t = base;
	for (int i = 0; i < 7; ++i) custom.ramp[i] = keyTone(HULL_DARK[i], k) | 0xFF000000u;
	t.ramp = custom.ramp;
	t.tileTop = keyTone(base.tileTop, k); t.tileBottom = keyTone(base.tileBottom, k); t.tileEdge = keyTone(base.tileEdge, k);
	t.hoverTop = keyTone(base.hoverTop, k); t.hoverBottom = keyTone(base.hoverBottom, k);
	t.sheenTop = keyTone(base.sheenTop, k); t.sheenBottom = keyTone(base.sheenBottom, k);
	t.accent = keyTone(base.accent, k); t.litTop = keyTone(base.litTop, k); t.litBottom = keyTone(base.litBottom, k);
	t.icon = keyTone(base.icon, k); t.iconHover = keyTone(base.iconHover, k); t.iconLit = keyTone(base.iconLit, k);
	t.panelTop = backTone(base.panelTop, b); t.panelBottom = backTone(base.panelBottom, b); t.panelEdge = backTone(base.panelEdge, b);
	t.wellTop = backTone(base.wellTop, b); t.wellBottom = backTone(base.wellBottom, b); t.wellEdge = backTone(base.wellEdge, b);
	t.cardTop = backTone(base.cardTop, b); t.cardBottom = backTone(base.cardBottom, b); t.cardEdge = backTone(base.cardEdge, b);
	t.rankFill = backTone(base.rankFill, b);
	t.steel = backTone(base.steel, b); t.wellBase = backTone(base.wellBase, b); t.cardBase = backTone(base.cardBase, b);
	t.lipLight = backTone(base.lipLight, b);
	t.grooveTop = backTone(base.grooveTop, b); t.grooveBottom = backTone(base.grooveBottom, b);
	custom.theme = t;
	custom.keyH = k.h;
	custom.keyV = k.v;
	std::copy(sig, sig + 6, custom.sig);
	++custom.version;
}

const Theme &theme()
{
	switch (Options::oxceHdBattleHudColor)
	{
	case HdBattleHud::COLOR_CUSTOM: customRefresh(); return custom.theme;
	case 1: return GOLD;
	case 2: return CONSUL;
	case 3: return CRUISER;
	case 4: return PIRATE;
	case 5: return STARSHIP;
	case 6: return NIELLO;
	case 7: return IRON_BONE;
	case 8: return DEEP_BRONZE;
	default: return SLATE;
	}
}

inline Uint32 withAlpha(Uint32 c, Uint32 a) { return (c & 0x00FFFFFFu) | (a << 24); }

/// A shape of a pictogram, in the button's base pixels; a cut takes away from what is drawn before it.
struct Shape
{
	enum Type { CIRCLE, ARC, SEGMENT, POLYGON, ROUND_RECT } type;
	bool cut = false;
	float a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0;
	std::vector<float> pts;
	float x0 = 0, y0 = 0, x1 = 0, y1 = 0;   ///< the bounding box

	bool inside(float x, float y) const
	{
		if (x < x0 || x > x1 || y < y0 || y > y1) return false;
		switch (type)
		{
		case CIRCLE:
		{
			const float dx = x - a, dy = y - b;
			return dx * dx + dy * dy <= c * c;
		}
		case ARC:
		{
			// a ring (centre a b, radius c, width d) from angle e to f (degrees, clockwise from +x on screen)
			const float dx = x - a, dy = y - b;
			const float r = std::sqrt(dx * dx + dy * dy);
			if (std::fabs(r - c) > d * 0.5f) return false;
			if (f - e >= 360.0f) return true;
			float ang = std::atan2(dy, dx) * 57.29578f;
			while (ang < e) ang += 360.0f;
			return ang <= f;
		}
		case SEGMENT:
		{
			// a stroke from (a, b) to (c, d), e wide, round ends
			const float vx = c - a, vy = d - b, wx = x - a, wy = y - b;
			const float l2 = vx * vx + vy * vy;
			const float t = l2 > 0 ? std::min(std::max((wx * vx + wy * vy) / l2, 0.0f), 1.0f) : 0.0f;
			const float px = wx - t * vx, py = wy - t * vy;
			return px * px + py * py <= e * e * 0.25f;
		}
		case POLYGON:
		{
			bool in = false;
			const size_t n = pts.size() / 2;
			for (size_t i = 0, j = n - 1; i < n; j = i++)
			{
				const float xi = pts[2 * i], yi = pts[2 * i + 1], xj = pts[2 * j], yj = pts[2 * j + 1];
				if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) in = !in;
			}
			return in;
		}
		case ROUND_RECT:
		{
			// (a, b) - (c, d), corner radius e
			const float r = e;
			const float cx = std::min(std::max(x, a + r), c - r), cy = std::min(std::max(y, b + r), d - r);
			const float dx = x - cx, dy = y - cy;
			return dx * dx + dy * dy <= r * r;
		}
		}
		return false;
	}
};

/// A pictogram: shapes in drawing order, in a frame moved by (ox, oy).
struct Pic
{
	std::vector<Shape> shapes;
	float ox = 0, oy = 0;
	bool cutting = false;
	bool drawn = false;   ///< the pirate panel's figures: tricornes, coats and boots

	Pic &at(float x, float y) { ox = x; oy = y; return *this; }
	Pic &cut(bool on) { cutting = on; return *this; }
	Shape &add(Shape::Type t)
	{
		shapes.emplace_back();
		Shape &s = shapes.back();
		s.type = t;
		s.cut = cutting;
		return s;
	}
	Pic &circle(float x, float y, float r)
	{
		Shape &s = add(Shape::CIRCLE);
		s.a = x + ox; s.b = y + oy; s.c = r;
		s.x0 = s.a - r; s.x1 = s.a + r; s.y0 = s.b - r; s.y1 = s.b + r;
		return *this;
	}
	Pic &arc(float x, float y, float r, float w, float from = 0, float to = 360)
	{
		Shape &s = add(Shape::ARC);
		s.a = x + ox; s.b = y + oy; s.c = r; s.d = w; s.e = from; s.f = to;
		const float o = r + w * 0.5f;
		s.x0 = s.a - o; s.x1 = s.a + o; s.y0 = s.b - o; s.y1 = s.b + o;
		return *this;
	}
	Pic &line(float xa, float ya, float xb, float yb, float w)
	{
		Shape &s = add(Shape::SEGMENT);
		s.a = xa + ox; s.b = ya + oy; s.c = xb + ox; s.d = yb + oy; s.e = w;
		s.x0 = std::min(s.a, s.c) - w; s.x1 = std::max(s.a, s.c) + w;
		s.y0 = std::min(s.b, s.d) - w; s.y1 = std::max(s.b, s.d) + w;
		return *this;
	}
	Pic &poly(std::initializer_list<float> p)
	{
		Shape &s = add(Shape::POLYGON);
		s.pts.assign(p.begin(), p.end());
		s.x0 = s.y0 = 1e9f; s.x1 = s.y1 = -1e9f;
		for (size_t i = 0; i + 1 < s.pts.size(); i += 2)
		{
			s.pts[i] += ox; s.pts[i + 1] += oy;
			s.x0 = std::min(s.x0, s.pts[i]); s.x1 = std::max(s.x1, s.pts[i]);
			s.y0 = std::min(s.y0, s.pts[i + 1]); s.y1 = std::max(s.y1, s.pts[i + 1]);
		}
		return *this;
	}
	Pic &rect(float xa, float ya, float xb, float yb, float r)
	{
		Shape &s = add(Shape::ROUND_RECT);
		s.a = xa + ox; s.b = ya + oy; s.c = xb + ox; s.d = yb + oy;
		s.e = std::min(r, std::min(xb - xa, yb - ya) * 0.5f);
		s.x0 = s.a; s.x1 = s.c; s.y0 = s.b; s.y1 = s.d;
		return *this;
	}

	// --- the pieces the pictograms are made of (x = the piece's centre line) ---

	/// A standing figure, its head's top at y = top; s = 1 is 11.2 base pixels tall (feet at top + 11.2).
	Pic &person(float x, float top = 2.45f, float s = 1.0f)
	{
		auto Y = [&](float v) { return top + (v - 2.45f) * s; };
		if (drawn)
		{
			// a pirate: a hat with its brim turned up, a coat flaring below the belt, boots
			circle(x, Y(4.45f), 1.4f * s);
			rect(x - 1.3f * s, Y(2.45f), x + 1.3f * s, Y(3.8f), 0.45f * s);
			line(x - 2.55f * s, Y(3.75f), x + 2.55f * s, Y(3.75f), 0.75f * s);
			poly({ x - 2.0f * s, Y(6.1f), x + 2.0f * s, Y(6.1f), x + 1.35f * s, Y(9.0f), x + 1.95f * s, Y(10.7f), x - 1.95f * s, Y(10.7f), x - 1.35f * s, Y(9.0f) });
			circle(x - 1.75f * s, Y(6.6f), 0.7f * s).circle(x + 1.75f * s, Y(6.6f), 0.7f * s);
			line(x - 2.2f * s, Y(6.7f), x - 2.75f * s, Y(9.6f), 0.95f * s).circle(x - 2.8f * s, Y(9.9f), 0.55f * s);
			line(x + 2.2f * s, Y(6.7f), x + 2.75f * s, Y(9.6f), 0.95f * s).circle(x + 2.8f * s, Y(9.9f), 0.55f * s);
			line(x - 0.75f * s, Y(10.4f), x - 0.95f * s, Y(12.9f), 1.15f * s).line(x - 1.0f * s, Y(13.05f), x - 1.9f * s, Y(13.25f), 0.95f * s);
			line(x + 0.75f * s, Y(10.4f), x + 0.95f * s, Y(12.9f), 1.15f * s).line(x + 1.0f * s, Y(13.05f), x + 1.9f * s, Y(13.25f), 0.95f * s);
			return cut(true).line(x - 1.5f * s, Y(9.0f), x + 1.5f * s, Y(9.0f), 0.35f * s).cut(false);
		}
		circle(x, Y(4.2f), 1.75f * s);
		rect(x - 1.75f * s, Y(6.4f), x + 1.75f * s, Y(10.3f), 0.9f * s);
		line(x - 2.15f * s, Y(7.0f), x - 2.7f * s, Y(10.0f), 1.0f * s);
		line(x + 2.15f * s, Y(7.0f), x + 2.7f * s, Y(10.0f), 1.0f * s);
		line(x - 0.85f * s, Y(10.0f), x - 1.05f * s, Y(13.3f), 1.4f * s);
		line(x + 0.85f * s, Y(10.0f), x + 1.05f * s, Y(13.3f), 1.4f * s);
		return *this;
	}
	/// A figure shooting to the right, for the 17 x 11 reserve buttons: the gun at the hip (snap and
	/// auto) or raised to the eye (aimed), as the mod draws them.
	Pic &shooter(float x, bool aimed)
	{
		circle(x, 2.6f, 1.3f);
		rect(x - 1.05f, 3.9f, x + 1.05f, 6.8f, 0.5f);
		line(x - 0.45f, 6.5f, x - 1.7f, 9.2f, 1.15f);
		line(x + 0.45f, 6.5f, x + 1.5f, 9.2f, 1.15f);
		if (aimed)
		{
			line(x + 0.6f, 4.3f, x + 2.4f, 3.3f, 1.0f);
			rect(x + 1.6f, 2.75f, x + 7.0f, 3.75f, 0.3f);
		}
		else
		{
			line(x + 0.6f, 4.6f, x + 2.6f, 4.9f, 1.0f);
			rect(x + 2.0f, 4.35f, x + 7.0f, 5.35f, 0.3f);
		}
		return *this;
	}
	/// The levels of the map: a narrow column of three storeys.
	Pic &storeys(float x)
	{
		rect(x - 2.4f, 3.0f, x + 2.4f, 13.0f, 0.5f);
		cut(true);
		for (int i = 0; i < 3; ++i)
		{
			rect(x - 1.25f, 4.15f + 2.95f * i, x + 1.25f, 6.05f + 2.95f * i, 0.2f);
		}
		return cut(false);
	}
	/// A kneeling figure, the same feet line.
	Pic &kneeling(float x)
	{
		// upright, one knee on the ground, the other leg bent forward
		if (drawn)
		{
			circle(x, 5.6f, 1.4f);
			rect(x - 1.3f, 3.6f, x + 1.3f, 4.95f, 0.45f);
			line(x - 2.55f, 4.9f, x + 2.55f, 4.9f, 0.75f);
			poly({ x - 1.9f, 7.2f, x + 1.9f, 7.2f, x + 1.3f, 9.9f, x + 1.7f, 10.9f, x - 1.7f, 10.9f, x - 1.3f, 9.9f });
			circle(x - 1.65f, 7.7f, 0.65f).circle(x + 1.65f, 7.7f, 0.65f);
			line(x - 2.05f, 7.8f, x - 2.5f, 10.4f, 0.95f).line(x + 2.05f, 7.8f, x + 2.5f, 10.4f, 0.95f);
			line(x + 0.6f, 10.6f, x + 3.4f, 10.8f, 1.25f).line(x + 3.4f, 10.8f, x + 3.6f, 13.0f, 1.2f).line(x + 3.6f, 13.2f, x + 4.4f, 13.3f, 0.95f);
			line(x - 0.8f, 10.6f, x - 1.0f, 13.0f, 1.25f).line(x - 1.0f, 13.3f, x - 3.6f, 13.4f, 1.15f);
			return cut(true).line(x - 1.45f, 9.9f, x + 1.45f, 9.9f, 0.35f).cut(false);
		}
		circle(x, 5.3f, 1.75f);
		rect(x - 1.65f, 7.5f, x + 1.65f, 10.9f, 0.9f);
		line(x - 2.05f, 8.1f, x - 2.5f, 10.6f, 1.0f);
		line(x + 2.05f, 8.1f, x + 2.5f, 10.6f, 1.0f);
		line(x + 0.6f, 10.5f, x + 3.4f, 10.8f, 1.4f);
		line(x + 3.4f, 10.8f, x + 3.6f, 13.4f, 1.4f);
		line(x - 0.8f, 10.5f, x - 1.0f, 13.1f, 1.4f);
		line(x - 1.0f, 13.3f, x - 3.6f, 13.4f, 1.3f);
		return *this;
	}
	/// A triangle pointing up or down, centred at (x, y); big: as wide as on the brass keys.
	Pic &arrow(float x, float y, bool up, bool big = false)
	{
		const float s = up ? 1.0f : -1.0f, hw = big ? 4.8f : 3.2f, lo = big ? 2.6f : 2.0f, hi = big ? 3.4f : 2.6f;
		return poly({ x - hw, y + lo * s, x + hw, y + lo * s, x, y - hi * s });
	}
	/// A triangle pointing right, centred at (x, y).
	Pic &arrowRight(float x, float y)
	{
		return poly({ x - 2.0f, y - 2.8f, x + 2.4f, y, x - 2.0f, y + 2.8f });
	}
};

/// The pictograms follow the mod's own picture of the panel (the same sign on the same button), drawn
/// again as clean shapes: what the player knows a button by stays. cast: for the brass keys, where the
/// sign is cut into the metal and the small triangles would be lost.
Pic makeIcon(HdBattleHud::Icon icon, bool cast = false, bool drawn = false)
{
	Pic p;
	p.drawn = drawn;
	const float ax = cast ? 9.6f : 10.5f;
	switch (icon)
	{
	case HdBattleHud::ICON_UNIT_UP: p.arrow(ax, 8.2f, true, cast).person(20.5f); break;
	case HdBattleHud::ICON_UNIT_DOWN: p.arrow(ax, 7.8f, false, cast).person(20.5f); break;
	case HdBattleHud::ICON_MAP_UP: p.arrow(ax, 8.2f, true, cast).storeys(20.5f); break;
	case HdBattleHud::ICON_MAP_DOWN: p.arrow(ax, 7.8f, false, cast).storeys(20.5f); break;
	case HdBattleHud::ICON_SHOW_MAP:
		// a map sheet with a tab, its left part a grid of squares
		p.rect(8.6f, 4.2f, 23.4f, 13.0f, 0.9f).rect(17.0f, 2.6f, 23.4f, 5.2f, 0.7f);
		p.cut(true).rect(9.8f, 5.4f, 22.2f, 11.8f, 0.3f).cut(false);
		for (int i = 0; i < 9; ++i)
		{
			const float x = 10.5f + (i % 3) * 1.85f, y = 6.1f + (i / 3) * 1.85f;
			p.rect(x, y, x + 1.3f, y + 1.3f, 0.15f);
		}
		break;
	case HdBattleHud::ICON_KNEEL:
		// stand / kneel
		p.person(8.6f).line(13.6f, 12.8f, 18.4f, 3.2f, 1.0f).kneeling(22.8f);
		break;
	case HdBattleHud::ICON_INVENTORY:
		p.person(16.0f);
		break;
	case HdBattleHud::ICON_CENTER:
		// the unit in the middle of the view: a small figure in four ticks
		p.person(16.0f, 4.3f, 0.66f);
		p.line(10.6f, 6.2f, 10.6f, 9.8f, 1.1f).line(21.4f, 6.2f, 21.4f, 9.8f, 1.1f);
		p.line(14.2f, 2.6f, 17.8f, 2.6f, 1.1f).line(14.2f, 13.4f, 17.8f, 13.4f, 1.1f);
		break;
	case HdBattleHud::ICON_NEXT_SOLDIER: p.person(9.0f).arrowRight(16.3f, 8.2f).person(23.0f); break;
	case HdBattleHud::ICON_NEXT_STOP:
		// done with this one (struck through), on to the next
		p.person(8.4f).cut(true).line(4.6f, 13.4f, 12.2f, 2.8f, 2.6f).cut(false).line(4.6f, 13.4f, 12.2f, 2.8f, 1.0f);
		p.line(13.6f, 8.2f, 17.2f, 8.2f, 1.1f).poly({ 16.4f, 6.0f, 19.2f, 8.2f, 16.4f, 10.4f });
		p.person(23.6f);
		break;
	case HdBattleHud::ICON_SHOW_LAYERS:
	{
		// three stacked diamonds, each lower one cut where the upper lies over it
		auto diamond = [&](float y, float grow) { p.poly({ 16.0f, y - 2.7f - grow, 22.2f + grow * 2.0f, y, 16.0f, y + 2.7f + grow, 9.8f - grow * 2.0f, y }); };
		diamond(11.2f, 0.0f);
		p.cut(true); diamond(8.0f, 0.75f); p.cut(false);
		diamond(8.0f, 0.0f);
		p.cut(true); diamond(4.8f, 0.75f); p.cut(false);
		diamond(4.8f, 0.0f);
		break;
	}
	case HdBattleHud::ICON_LINKS:
		p.rect(10.4f, 3.9f, 21.6f, 5.6f, 0.8f).rect(10.4f, 7.15f, 21.6f, 8.85f, 0.8f).rect(10.4f, 10.4f, 21.6f, 12.1f, 0.8f);
		break;
	case HdBattleHud::ICON_OPTIONS:
		// a question mark
		p.arc(16.0f, 5.9f, 2.7f, 1.7f, 180.0f, 405.0f);
		p.line(17.9f, 7.8f, 16.0f, 9.2f, 1.7f).line(16.0f, 9.2f, 16.0f, 10.1f, 1.7f);
		p.circle(16.0f, 12.6f, 1.05f);
		break;
	case HdBattleHud::ICON_END_TURN:
		// a struck circle
		p.arc(16.0f, 8.0f, 4.1f, 1.4f).line(13.3f, 10.7f, 18.7f, 5.3f, 1.4f);
		break;
	case HdBattleHud::ICON_ABORT:
		// back on board: the craft, an arrow up to it
		p.poly({ 8.6f, 6.6f, 10.0f, 5.2f, 20.4f, 4.7f, 22.4f, 2.0f, 24.0f, 2.0f, 23.4f, 5.4f, 22.2f, 6.9f, 10.2f, 7.5f });
		p.poly({ 14.4f, 6.8f, 18.6f, 6.8f, 16.6f, 8.0f, 13.8f, 8.0f });
		p.poly({ 13.4f, 11.8f, 18.6f, 11.8f, 16.0f, 9.2f }).line(16.0f, 11.4f, 16.0f, 13.8f, 1.3f);
		break;
	case HdBattleHud::ICON_RESERVE_NONE:
		p.line(2.6f, 5.5f, 11.6f, 5.5f, 1.3f).poly({ 10.8f, 2.7f, 14.6f, 5.5f, 10.8f, 8.3f });
		break;
	case HdBattleHud::ICON_RESERVE_SNAP:
		p.shooter(4.4f, false).line(12.6f, 4.85f, 14.4f, 4.85f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_AIMED:
		p.shooter(4.4f, true).line(12.6f, 3.25f, 14.4f, 3.25f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_AUTO:
		p.shooter(4.4f, false).line(10.4f, 4.85f, 11.0f, 4.85f, 1.0f).line(12.2f, 4.85f, 12.8f, 4.85f, 1.0f).line(14.0f, 4.85f, 14.6f, 4.85f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_KNEEL:
		// down to the knee: an arrow over a kneeling figure
		p.line(5.0f, 2.4f, 5.0f, 6.6f, 1.2f).poly({ 2.6f, 5.6f, 7.4f, 5.6f, 5.0f, 8.6f });
		p.at(1.8f, 6.2f).kneeling(3.2f);
		break;
	case HdBattleHud::ICON_ZERO_TUS:
		// the unit's time units to nought: a figure over a struck zero
		p.person(5.0f, 2.4f, 0.66f).rect(2.2f, 10.5f, 7.8f, 11.5f, 0.3f);
		p.rect(2.9f, 13.0f, 7.1f, 19.6f, 2.1f).cut(true).rect(4.1f, 14.2f, 5.9f, 18.4f, 0.9f).cut(false);
		p.line(4.2f, 17.9f, 5.8f, 14.7f, 0.8f);
		break;
	default:
		break;
	}
	return p;
}

/// A pictogram's coverage at a scale (one byte per world pixel), and its colourings.
struct Raster
{
	int w = 0, h = 0;
	std::vector<Uint8> cov;
	std::unordered_map<Uint32, std::vector<Uint32>> colored;
};

int cacheScale = 0;
std::unordered_map<Uint64, Raster> cache;

bool drawnSigns();

const Raster &raster(HdBattleHud::Icon icon, int w, int h, int k, float shrink = 1.0f, bool cast = false)
{
	if (k != cacheScale)
	{
		cache.clear();
		cacheScale = k;
	}
	const bool drawn = drawnSigns();
	const Uint64 key = ((Uint64)drawn << 51) | ((Uint64)cast << 50) | ((Uint64)std::lround(shrink * 100.0f) << 40) | ((Uint64)icon << 32) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	auto found = cache.find(key);
	if (found != cache.end()) return found->second;
	Raster &r = cache[key];
	r.w = w * k;
	r.h = h * k;
	r.cov.assign((size_t)r.w * r.h, 0);
	const Pic pic = makeIcon(icon, cast, drawn);
	// 4 x 4 samples a pixel; the rows are shared out to the render threads (a hand of pictograms a scale)
	const int S = 4;
	// shrink: about the button's centre, to keep clear of a plaque's edge
	const float grow = 1.0f / shrink;
	const float inv = grow / (float)k, cx = w * 0.5f * (1.0f - grow), cy = h * 0.5f * (1.0f - grow);
	auto rows = [&](int ra, int rb)
	{
		for (int py = ra; py < rb; ++py)
		{
			for (int px = 0; px < r.w; ++px)
			{
				int hits = 0;
				for (int sy = 0; sy < S; ++sy)
				{
					const float y = (py + (sy + 0.5f) / S) * inv + cy;
					for (int sx = 0; sx < S; ++sx)
					{
						const float x = (px + (sx + 0.5f) / S) * inv + cx;
						bool in = false;
						for (const Shape &s : pic.shapes)
						{
							if (s.cut ? in : !in)
							{
								if (s.inside(x, y)) in = !s.cut;
							}
						}
						hits += in;
					}
				}
				r.cov[(size_t)py * r.w + px] = (Uint8)((hits * 255 + S * S / 2) / (S * S));
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(r.h / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { rows((int)((long long)r.h * job / jobs), (int)((long long)r.h * (job + 1) / jobs)); });
	return r;
}

/// The pictogram in a colour: straight alpha 0xAARRGGBB, cached per colour.
const std::vector<Uint32> &colored(const Raster &r, Uint32 color)
{
	Raster &rw = const_cast<Raster&>(r);
	auto found = rw.colored.find(color);
	if (found != rw.colored.end()) return found->second;
	std::vector<Uint32> &out = rw.colored[color];
	out.resize(r.cov.size());
	const Uint32 a = color >> 24;
	for (size_t i = 0; i < r.cov.size(); ++i)
	{
		out[i] = withAlpha(color, (r.cov[i] * a + 127) / 255);
	}
	return out;
}

/// The colour of a palette entry, or the accent for none.
Uint32 tintOf(Uint8 tint, const SDL_Color *pal)
{
	return tint && pal ? HdUi::rgba(pal[tint]) : theme().accent;
}

Uint32 mix(Uint32 a, Uint32 b, float t)
{
	auto ch = [&](int sh) { return (Uint32)((float)((a >> sh) & 0xFF) * (1.0f - t) + (float)((b >> sh) & 0xFF) * t + 0.5f) << sh; };
	return 0xFF000000u | ch(16) | ch(8) | ch(0);
}

/// A shade 0..1 of the metal: the theme's (brass, hull steel), or a key's own colour from nearly black to nearly white.
Uint32 rampColor(float s, Uint32 tint)
{
	s = std::min(std::max(s, 0.0f), 1.0f);
	if (!tint)
	{
		const Uint32 *ramp = theme().ramp ? theme().ramp : BRASS;
		int i = 0;
		while (i < 5 && s > RAMP_AT[i + 1]) ++i;
		return mix(ramp[i], ramp[i + 1], (s - RAMP_AT[i]) / (RAMP_AT[i + 1] - RAMP_AT[i]));
	}
	if (s < 0.6f) return mix(0xFF000000u, tint | 0xFF000000u, 0.12f + 0.88f * s / 0.6f);
	return mix(tint | 0xFF000000u, 0xFFFFFFE0u, (s - 0.6f) / 0.4f * 0.5f);
}

/// A key's own colour made as deep as the original's plaques: more saturated, its strongest channel at D8.
Uint32 vivid(Uint32 c)
{
	float ch[3] = { (float)((c >> 16) & 0xFF), (float)((c >> 8) & 0xFF), (float)(c & 0xFF) };
	const float grey = (ch[0] + ch[1] + ch[2]) / 3.0f;
	float top = 1.0f;
	for (float &v : ch)
	{
		v = std::max(grey + 1.25f * (v - grey), 0.0f);
		top = std::max(top, v);
	}
	Uint32 out = 0xFF000000u;
	for (int i = 0; i < 3; ++i)
	{
		out |= (Uint32)std::min(ch[i] * 216.0f / top + 0.5f, 255.0f) << (16 - 8 * i);
	}
	return out;
}

/// Distance inside a rounded box (negative outside), at a pixel's centre.
float insideBox(float x, float y, float x0, float y0, float x1, float y1, float r)
{
	const float qx = std::fabs(x - (x0 + x1) * 0.5f) - ((x1 - x0) * 0.5f - r);
	const float qy = std::fabs(y - (y0 + y1) * 0.5f) - ((y1 - y0) * 0.5f - r);
	const float ox = std::max(qx, 0.0f), oy = std::max(qy, 0.0f);
	return r - std::sqrt(ox * ox + oy * oy) - std::min(std::max(qx, qy), 0.0f);
}

inline float ease(float t) { t = std::min(std::max(t, 0.0f), 1.0f); return t * (2.0f - t); }

/// The HUD textures' hash: 0..1, the same for the same number every time.
inline float hash01(Uint32 a)
{
	a ^= a >> 16; a *= 0x7FEB352Du; a ^= a >> 15; a *= 0x846CA68Bu; a ^= a >> 16;
	return (float)(a & 0xFFFF) / 65535.0f;
}

/// Smooth value noise over the lattice of hash01, 0..1.
inline float valueNoise(float fx, float fy, Uint32 seed)
{
	const int xi = (int)std::floor(fx), yi = (int)std::floor(fy);
	const float tx = fx - (float)xi, ty = fy - (float)yi;
	const float sx = tx * tx * (3.0f - 2.0f * tx), sy = ty * ty * (3.0f - 2.0f * ty);
	auto at = [&](int i, int j) { return hash01(seed ^ ((Uint32)i * 0x85EBCA77u) ^ ((Uint32)j * 0xC2B2AE3Du)); };
	const float top = at(xi, yi) + (at(xi + 1, yi) - at(xi, yi)) * sx;
	const float bottom = at(xi, yi + 1) + (at(xi + 1, yi + 1) - at(xi, yi + 1)) * sx;
	return top + (bottom - top) * sy;
}

/// Brushed metal: fine streaks along the rows, -0.5..0.5, the same at the same pixel every time.
float brushed(int x, int y, float k)
{
	const float fx = (float)x / (6.0f * k);
	const int xi = (int)fx;
	const Uint32 row = (Uint32)y * 0x9E3779B1u;
	const float a = hash01(row ^ ((Uint32)xi * 0x85EBCA77u)), b = hash01(row ^ ((Uint32)(xi + 1) * 0x85EBCA77u));
	return a + (b - a) * (fx - (float)xi) - 0.5f;
}

/// Cast hull plating: a soft mottling a few base pixels across with a fine grain over it, -0.5..0.5,
/// the same at the same pixel every time.
float plating(int x, int y, float k)
{
	const float coarse = valueNoise((float)x / (5.0f * k), (float)y / (5.0f * k), 0x2545F491u);
	const float fine = valueNoise((float)x / (1.5f * k), (float)y / (1.5f * k), 0x9E3779B9u);
	const float grain = hash01((Uint32)x * 0x27D4EB2Fu ^ (Uint32)y * 0x165667B1u);
	return 0.6f * coarse + 0.25f * fine + 0.15f * grain - 0.5f;
}

/// The face texture of the theme's metal: brushed brass, or hull plating.
float texture(int x, int y, float k)
{
	return theme().plated ? 2.0f * plating(x, y, k) : brushed(x, y, k);
}

/// Distance inside a box with its corners cut off at c (negative outside), at a pixel's centre.
float insideChamfer(float x, float y, float x0, float y0, float x1, float y1, float c)
{
	const float dx = std::min(x - x0, x1 - x), dy = std::min(y - y0, y1 - y);
	return std::min(std::min(dx, dy), (dx + dy - c) * 0.70710678f);
}

/// A height and a darkening the hull's relief adds to a flat face.
struct Relief { float h = 0, dk = 0, metal = 0; };

/// The Consul's sides: rows of small plates laid like shingles, each rising toward its lower edge and dropping
/// onto the row below, the joints across a row a fine groove, every other row shifted by half a plate. pw x ph
/// screen pixels a plate, a groove `seam` wide.
Relief shingles(float x, float y, float pw, float ph, float seam)
{
	Relief r;
	const float row = std::floor(y / ph);
	const float sx = x + (std::fmod(row, 2.0f) != 0.0f ? pw * 0.5f : 0.0f);
	const float u = sx - std::floor(sx / pw) * pw, v = y - row * ph;
	const float across = std::min(u, pw - u);
	const float joint = std::max(1.0f - across / (0.6f * seam), 0.0f);
	const float bulge = 1.0f - std::pow(2.0f * u / pw - 1.0f, 2.0f);
	r.h = 0.4f * (v / ph) * (v / ph) + 0.1f * bulge - 0.1f * joint;
	r.dk = 0.05f * joint * joint + 0.04f * std::max(1.0f - (ph - v) / seam, 0.0f);
	return r;
}

/// A round rivet head of radius rr at (cx, cy).
void rivet(Relief &r, float x, float y, float cx, float cy, float rr)
{
	const float d = std::sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy)) / rr;
	if (d >= 1.25f) return;
	r.h += 0.4f * std::sqrt(std::max(1.0f - d * d, 0.0f));
	r.dk += 0.18f * std::max(1.0f - std::fabs(d - 1.05f) / 0.2f, 0.0f);
}

/// Mahogany planking: planks laid along the panel, their ends staggered, each a little cupped; the grain runs along a
/// plank in wavy streaks, a brass nail at each end (`metal` = the nail's coverage).
Relief planking(float x, float y, float k)
{
	Relief r;
	const float ph = 6.5f * k, pw = 52.0f * k;
	const float row = std::floor(y / ph);
	const float shift = hash01((Uint32)(int)row * 0x9E3779B1u) * pw;
	const float sx = x + shift;
	const float plank = std::floor(sx / pw);
	const float u = sx - plank * pw, v = y - row * ph;
	const Uint32 seed = (Uint32)(int)row * 0x27D4EB2Fu ^ (Uint32)(int)plank * 0x165667B1u;
	// the seams: a dark groove along and across, the plank's edges eased into it
	const float edge = std::min(std::min(v, ph - v), std::min(u, pw - u));
	const float seam = std::max(1.0f - edge / (0.55f * k), 0.0f);
	const float bow = 2.0f * v / ph - 1.0f;
	r.h = 0.12f * (1.0f - bow * bow) - 0.35f * seam * seam;
	// the grain: streaks wandering along the plank, a knot of darker rings now and then
	const float wander = 2.6f * valueNoise(sx / (14.0f * k), v / (3.0f * k), seed) + 0.8f * valueNoise(sx / (4.0f * k), v / k, seed ^ 0x5A5A5A5Au);
	const float streak = 0.5f + 0.5f * std::sin((v / (0.75f * k) + wander) * 3.14159265f);
	const float tone = valueNoise(sx / (24.0f * k), v / (6.0f * k), seed ^ 0x1234567u);
	const float fibre = hash01((Uint32)(int)std::floor(sx / (0.6f * k)) * 0x85EBCA77u ^ (Uint32)(int)y * 0xC2B2AE3Du);
	r.dk = 0.16f * streak * streak + 0.12f * tone + 0.04f * fibre + 0.35f * seam * seam - 0.06f;
	// a nail a little in from each end of the plank, at its middle
	const float nr = 0.55f * k;
	Relief nail;
	rivet(nail, u, v, 1.8f * k, ph * 0.5f, nr);
	rivet(nail, u, v, pw - 1.8f * k, ph * 0.5f, nr);
	r.h += nail.h;
	r.dk += nail.dk;
	r.metal = std::min(nail.h / 0.12f, 1.0f);
	return r;
}

/// The hull's relief on the steel between the keys: larger shingles, or the Cruiser's big panels with chamfered
/// corners, their seams lined with rivets.
Relief steelRelief(float x, float y, float k)
{
	Relief r;
	switch (theme().hull)
	{
	case 1:
		r = shingles(x, y, 5.0f * k, 3.0f * k, 0.55f * k);
		break;
	case 2:
	{
		const float pw = 40.0f * k, ph = 20.0f * k;
		const float u = x - std::floor(x / pw) * pw, v = y - std::floor(y / ph) * ph;
		const float sd = insideChamfer(u, v, 0.0f, 0.0f, pw, ph, 3.0f * k);
		const float seam = std::max(1.0f - sd / (0.7f * k), 0.0f);
		r.h = -0.3f * seam;
		r.dk = 0.2f * seam * seam;
		// rivets along the seams, a few base pixels apart
		const float step = 4.0f * k, in = 1.6f * k, rr = 0.6f * k;
		const float cu = (std::floor(u / step) + 0.5f) * step, cv = (std::floor(v / step) + 0.5f) * step;
		if (cu > 2.5f * k && cu < pw - 2.5f * k)
		{
			rivet(r, u, v, cu, in, rr);
			rivet(r, u, v, cu, ph - in, rr);
		}
		if (cv > 2.5f * k && cv < ph - 2.5f * k)
		{
			rivet(r, u, v, in, cv, rr);
			rivet(r, u, v, pw - in, cv, rr);
		}
		break;
	}
	case 3:
		r = planking(x, y, k);
		break;
	default:
		break;
	}
	return r;
}

/// Metal in relief, lit from the upper left as the original picture is: a height a pixel (1 = the top of a
/// plaque), a darkening (the bottom of a cut, the outline of a plaque) and a coverage; the slopes catch or
/// lose the light, the steepest ones facing it glint, the face is brushed. A key's own colour (tint) is
/// laid where brass[i] is 0, brass where it is 1. The rows go to the render threads.
std::vector<Uint32> shadeMetal(const std::vector<float> &height, const std::vector<float> &dark, const std::vector<float> &cover, int W, int H, float k, float lift, Uint32 tint, const std::vector<float> *brass = nullptr, const std::vector<float> *dull = nullptr)
{
	std::vector<Uint32> out((size_t)W * H, 0);
	const float lx = -0.5f, ly = -0.6f, lz = 0.62f;
	const float kb = (float)HdUi::scale();
	auto rows = [&](int ra, int rb)
	{
		for (int y = ra; y < rb; ++y)
		{
			const int yu = std::max(y - 1, 0), yd = std::min(y + 1, H - 1);
			for (int x = 0; x < W; ++x)
			{
				const size_t i = (size_t)y * W + x;
				const float a = cover[i];
				if (a <= 0.0f) continue;
				const int xl = std::max(x - 1, 0), xr = std::min(x + 1, W - 1);
				const float gx = (height[(size_t)y * W + xr] - height[(size_t)y * W + xl]) * 0.5f * k;
				const float gy = (height[(size_t)yd * W + x] - height[(size_t)yu * W + x]) * 0.5f * k;
				const float d = (-gx * lx - gy * ly + lz) / std::sqrt(gx * gx + gy * gy + 1.0f);
				const float glint = 0.12f * std::pow(std::max(d, 0.0f), 12.0f);
				const float s = 0.6f + 0.9f * (d - lz) + glint - dark[i] + lift + 0.035f * texture(x, y, kb);
				Uint32 c = rampColor(s, tint);
				if (tint && brass && (*brass)[i] > 0.0f)
				{
					c = mix(c, rampColor(s + 0.05f, 0), std::min((*brass)[i] * 1.5f, 1.0f));
				}
				if (dull && (*dull)[i] > 0.0f)
				{
					// the floor of a cut: greyer than the face, as tarnished metal is
					const Uint32 r = (c >> 16) & 0xFF, gg = (c >> 8) & 0xFF, bb = c & 0xFF;
					const Uint32 grey = (r * 3 + gg * 5 + bb * 2) / 10;
					c = mix(c, 0xFF000000u | grey << 16 | grey << 8 | grey, (*dull)[i]);
				}
				out[i] = withAlpha(c, (Uint32)(std::min(a, 1.0f) * 255.0f + 0.5f));
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { rows((int)((long long)H * job / jobs), (int)((long long)H * (job + 1) / jobs)); });
	return out;
}

/// Two box passes of radius rb over the W x H picture a, rows then columns, clamped at the edges; b is scratch.
void boxBlur2(std::vector<float> &a, std::vector<float> &b, int W, int H, int rb)
{
	const float n = 1.0f / (float)(2 * rb + 1);
	for (int pass = 0; pass < 2; ++pass)
	{
		for (int y = 0; y < H; ++y)
			for (int x = 0; x < W; ++x)
			{
				float sum = 0;
				for (int d = -rb; d <= rb; ++d) sum += a[(size_t)y * W + std::min(std::max(x + d, 0), W - 1)];
				b[(size_t)y * W + x] = sum * n;
			}
		for (int y = 0; y < H; ++y)
			for (int x = 0; x < W; ++x)
			{
				float sum = 0;
				for (int d = -rb; d <= rb; ++d) sum += b[(size_t)std::min(std::max(y + d, 0), H - 1) * W + x];
				a[(size_t)y * W + x] = sum * n;
			}
	}
}

/// A pictogram's coverage softened by two box passes of radius rb: the walls of the cut.
std::vector<float> softCover(const Raster &pic, int rb)
{
	std::vector<float> a(pic.cov.size()), b(pic.cov.size());
	for (size_t i = 0; i < a.size(); ++i) a[i] = pic.cov[i] / 255.0f;
	boxBlur2(a, b, pic.w, pic.h, rb);
	return a;
}

int metalScale = 0, metalTheme = -1;
std::unordered_map<Uint64, std::vector<Uint32>> metalCache;

std::vector<Uint32> *metalCached(Uint64 key, int k)
{
	const int themeNow = HdBattleHud::themeKey();
	if (k != metalScale || themeNow != metalTheme)
	{
		metalCache.clear();
		metalScale = k;
		metalTheme = themeNow;
	}
	auto found = metalCache.find(key);
	return found != metalCache.end() ? &found->second : nullptr;
}

/// The light in a key that is on without a colour of its own (the unit kneels).
const Uint32 LAMP = 0xFF8CF05Au;

/// How the keys look in a theme: a window of dark glass in the cap with the legend lit inside it (the dark panel and
/// the hulls), or the legend cut into the metal (the brass keys); the colours of that light.
struct KeyLook
{
	bool glass;
	Uint32 glassTop, glassBottom;  ///< the window's glass at its top and bottom
	Uint32 legend;                 ///< the legend's light at rest
	Uint32 glow;                   ///< the light round it under the mouse and in the flash of a press
	Uint32 rim;                    ///< the light on the cap's edge under the mouse, on the socket's lower lip
	/// an engraver's plate (the pirate panel): the sign cut in outline and hatched, a screw in each corner, patina
	/// at the edges; a reserve key is brass too, its sign filled with enamel of its colour; a key that is on glows warm
	bool gravure;
	// the painted panels (gravure) only:
	Uint32 ember;                  ///< the light round a key that is on
	Uint32 signLit;                ///< the colour its sign lights up in
	bool paleSign;                 ///< the sign is lighter than the plate (bone in iron), not an engraving filled dark
	const char *folder;            ///< where the panel's pictures lie in the hd mod (paintedFace)
};

/// The warm light of a pirate key that is on, and of the glow round it.
const Uint32 EMBER = 0xFFFFB04Au;

const KeyLook &customKeyLook();

const KeyLook &keyLook()
{
	static const KeyLook DARK = { true, 0xFF121A26u, 0xFF05080Cu, 0xFFDCE6F2u, 0xFFE6A23Cu, 0xFFE6A23Cu, false, 0, 0, false, nullptr };
	static const KeyLook BRASS_KEYS = { false, 0, 0, 0, 0xFFFFE9A6u, 0xFFF8E57Bu, false, 0, 0, false, nullptr };
	static const KeyLook CONSUL_KEYS = { true, 0xFF1D1934u, 0xFF0A0816u, 0xFFF2F0FFu, 0xFFB8AEFFu, 0xFFE6E4FAu, false, 0, 0, false, nullptr };
	// the Cruiser's signs cut dark into its steel, as before the glass keys (players asked it back); its reserve keys
	// keep their lit glass
	static const KeyLook CRUISER_KEYS = { false, 0, 0, 0, 0xFFA494F0u, 0xFFCFC6E0u, false, 0, 0, false, nullptr };
	// a sign lit in a coal's orange, not the ember of the glow round the key: brass is light orange itself, and a sign
	// lit in that colour sinks into it; each metal after it lights its signs in a colour that stands out of it
	static const KeyLook PIRATE_KEYS = { false, 0, 0, 0, 0xFFFFC870u, 0xFFF6D890u, true, EMBER, 0xFFFF6A12u, false, "UI/battle_keys/" };
	static const KeyLook STARSHIP_KEYS = { false, 0, 0, 0, 0xFFC8A0FFu, 0xFFE0D0FFu, true, 0xFFB070FFu, 0xFFFF48E0u, false, "UI/battle_keys_space/" };
	static const KeyLook NIELLO_KEYS = { false, 0, 0, 0, 0xFFE8F0FFu, 0xFFF4F8FFu, true, 0xFF9FD0FFu, 0xFF30B0FFu, false, "UI/battle_keys_silver/" };
	static const KeyLook IRON_KEYS = { false, 0, 0, 0, 0xFFFFB060u, 0xFFE8D8B8u, true, 0xFFFF8A30u, 0xFFFF6A12u, true, "UI/battle_keys_iron/" };
	static const KeyLook BRONZE_KEYS = { false, 0, 0, 0, 0xFF80F0D0u, 0xFFB8F0DCu, true, 0xFF40F0C0u, 0xFF60FFF0u, false, "UI/battle_keys_bronze/" };
	switch (Options::oxceHdBattleHudColor)
	{
	case HdBattleHud::COLOR_CUSTOM: return customKeyLook();
	case 1: return BRASS_KEYS;
	case 2: return CONSUL_KEYS;
	case 3: return CRUISER_KEYS;
	case 4: return PIRATE_KEYS;
	case 5: return STARSHIP_KEYS;
	case 6: return NIELLO_KEYS;
	case 7: return IRON_KEYS;
	case 8: return BRONZE_KEYS;
	default: return DARK;
	}
}

/// The keys of the player's own colour: the legend cut dark into the metal, or - for keys too dark for that to show -
/// lit in a window of dark glass; the lights are of the keys' hue.
const KeyLook &customKeyLook()
{
	static KeyLook look = { false, 0, 0, 0, 0, 0, false, 0, 0, false, nullptr };
	static unsigned built = 0;
	customRefresh();
	if (built != custom.version)
	{
		const float h = custom.keyH;
		look = KeyLook{ custom.keyV < 0.30f, fromHsv(h, 0.55f, 0.10f), fromHsv(h, 0.6f, 0.04f), fromHsv(h, 0.10f, 0.96f),
			fromHsv(h, 0.45f, 0.97f), fromHsv(h, 0.12f, 0.88f), false, 0, 0, false, nullptr };
		built = custom.version;
	}
	return look;
}

/// Are the pictograms the pirate panel's drawn figures?
bool drawnSigns()
{
	return keyLook().gravure;
}

/// The enamel in a pirate reserve key's sign: its colour toned down to an old enamel, glowing when the key is on.
Uint32 enamel(Uint32 own, bool lit)
{
	const Uint32 aged = HdUi::mixed(own, 0xFF3A2414u, 0.3f) | 0xFF000000u;
	return lit ? HdUi::mixed(aged, 0xFFFFE6B0u, 0.25f) | 0xFF000000u : HdUi::scaled(aged, 0.72f) | 0xFF000000u;
}

/// Where a key's cap and its window lie in its cell, in screen pixels.
struct CapGeom
{
	float g, R, bevel;              ///< the cap's gap to the socket's edge, its corner radius, its bevels' width
	bool window;
	float wx0, wy0, wx1, wy1, wr;   ///< the window and its corner radius
	float shrink;                   ///< the legend's size about the cell's centre: inside the window, clear of the edge
};

CapGeom capGeom(int w, int h, int k, bool tinted)
{
	CapGeom c;
	const bool small = w < 20 || h < 14;
	c.g = 0.85f * k;
	c.R = (small ? 1.6f : 2.2f) * k;
	c.bevel = (small ? 0.85f : 1.15f) * k;
	// a reserve key is a lens of its own colour in a narrow bezel, the others a window in a broad frame
	c.window = keyLook().glass || (tinted && !keyLook().gravure);
	const float fw = (tinted ? 1.05f : 1.85f) * k, fh = (tinted ? 1.05f : 1.6f) * k;
	c.wx0 = c.g + fw;
	c.wy0 = c.g + fh;
	c.wx1 = w * k - c.g - fw;
	c.wy1 = h * k - c.g - fh;
	c.wr = (small ? 0.9f : 1.3f) * k;
	if (!c.window) c.shrink = h < 14 ? 0.8f : 0.86f;
	else if (!tinted) c.shrink = 0.8f;
	else c.shrink = w > h ? 0.76f : 0.8f;
	return c;
}

/// A legend's light spilled round it: its coverage softened, as a pictogram of its own (and its colourings).
const Raster &halo(HdBattleHud::Icon icon, int w, int h, int k, float shrink)
{
	static std::unordered_map<Uint64, Raster> halos;
	static int haloScale = 0;
	if (k != haloScale)
	{
		halos.clear();
		haloScale = k;
	}
	const Uint64 key = ((Uint64)drawnSigns() << 51) | ((Uint64)std::lround(shrink * 100.0f) << 40) | ((Uint64)icon << 32) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	auto found = halos.find(key);
	if (found != halos.end()) return found->second;
	const Raster &pic = raster(icon, w, h, k, shrink, true);
	const std::vector<float> soft = softCover(pic, std::max(1, (int)std::lround(0.7f * k)));
	Raster &r = halos[key];
	r.w = pic.w;
	r.h = pic.h;
	r.cov.resize(soft.size());
	for (size_t i = 0; i < soft.size(); ++i) r.cov[i] = (Uint8)(std::min(soft[i] * 1.8f, 1.0f) * 255.0f + 0.5f);
	return r;
}

/// Light added to a colour (0xAARRGGBB, the alpha kept): `s` of `light` on every channel, capped at white.
Uint32 lighten(Uint32 c, Uint32 light, float s)
{
	Uint32 out = c & 0xFF000000u;
	for (int sh = 0; sh <= 16; sh += 8)
	{
		out |= (Uint32)std::min((float)((c >> sh) & 0xFF) + (float)((light >> sh) & 0xFF) * s + 0.5f, 255.0f) << sh;
	}
	return out;
}

/// How far a pressed cap's upper and left edges lie in the shade of the socket's rim (0..1), at a pixel of its cell.
inline float rimShade(float px, float py, float g, float k)
{
	return std::max(std::exp(-(py - g) / (0.9f * k)), 0.7f * std::exp(-(px - g) / (0.9f * k)));
}

/// The steps a cap is drawn in on its way down (each one cached).
const int CAP_STEPS = 8;

/// A key's cap pressed `step` of CAP_STEPS - 1 into its socket. Up, its bevels round over and catch the light at the
/// upper left, as the keys of the original picture do; down, they turn into a shallow dish lit at the lower right and
/// the socket's rim shades the cap's upper and left edges - the original shows a pressed key by turning its colours,
/// here it is the relief that turns. The legend glows in a window of dark glass (the brass keys: it is cut into the
/// metal). lit = the key is on: a reserve key's lens lights up in its own colour, another key's legend green. tint =
/// the key's own colour (the reserve keys), 0 = none.
const std::vector<Uint32> &cap(HdBattleHud::Icon icon, int w, int h, int k, int step, bool lit, Uint32 tint)
{
	const Uint64 key = (1ull << 60) | ((Uint64)(tint & 0xFFFFFF) << 32) | ((Uint64)lit << 31) | ((Uint64)step << 27)
		| ((Uint64)(icon & 0x7F) << 20) | ((Uint64)(w & 0x3FF) << 10) | (Uint64)(h & 0x3FF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return *hit;
	const KeyLook &look = keyLook();
	const CapGeom c = capGeom(w, h, k, tint != 0);
	const int W = w * k, H = h * k;
	const float t = (float)step / (float)(CAP_STEPS - 1), line = 0.45f * k;
	const Raster *sharp = icon != HdBattleHud::ICON_NONE && icon < HdBattleHud::ICON_COUNT ? &raster(icon, w, h, k, c.shrink, true) : nullptr;
	const Raster *spill = sharp && c.window ? &halo(icon, w, h, k, c.shrink) : nullptr;
	// the brass keys' cut: its walls from the softened pictogram, its colour from the sharp one
	std::vector<float> cut, deep, core;
	if (sharp && !c.window)
	{
		cut = softCover(*sharp, std::max(1, (int)std::lround(0.2f * k)));
		deep = softCover(*sharp, std::max(1, (int)std::lround(0.9f * k)));
		// an engraver's plate: where the sign is broad enough to hatch rather than to cut out whole
		if (look.gravure && k >= 3) core = softCover(*sharp, std::max(1, (int)std::lround(0.45f * k)));
	}
	// the screws in an engraved plate's corners, each slot at its own angle
	const bool screws = look.gravure && w >= 24 && h >= 14;
	const float si = c.g + c.bevel + 0.85f * k, sr = 0.62f * k;
	const float sxs[4] = { si, W - si, si, W - si }, sys[4] = { si, si, H - si, H - si }, sang[4] = { 0.6f, 2.1f, 1.2f, 2.6f };
	std::vector<float> height((size_t)W * H), dark((size_t)W * H), cover((size_t)W * H), dull, glass;
	if (!cut.empty()) dull.assign((size_t)W * H, 0.0f);
	if (c.window) glass.assign((size_t)W * H, 0.0f);
	// the lit lip under a cut: the cut seen from half a base pixel up and to the left
	const int lo = std::max(1, (int)std::lround(0.5f * k));
	const float cx = W * 0.5f, cy = H * 0.5f;
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const size_t i = (size_t)y * W + x;
			const float px = x + 0.5f, py = y + 0.5f;
			const float sd = theme().hull == 2 ? insideChamfer(px, py, c.g, c.g, W - c.g, H - c.g, 1.2f * c.R)
				: insideBox(px, py, c.g, c.g, W - c.g, H - c.g, c.R);
			cover[i] = std::min(std::max(sd + 0.5f, 0.0f), 1.0f);
			const float e = ease(sd / c.bevel);
			const float ex = (px - cx) / cx, ey = (py - cy) / cy;
			// up: rounded over at the edges, the face a little domed; down: a dish
			float hgt = (1.0f - t) * (e + 0.08f * (1.0f - ex * ex) * (1.0f - ey * ey)) + t * (1.0f - 0.5f * e);
			// a fine dark outline, the face a touch darker toward its ends, the rim's shade on a pressed cap
			float dk = 0.3f * (1.0f - std::min(std::max(sd / line, 0.0f), 1.0f)) + 0.04f * (ex * ex + ey * ey)
				+ 0.28f * t * rimShade(px, py, c.g, (float)k);
			if (look.gravure)
			{
				// old brass: a mottled patina gathered toward the edges, the face polished by hands
				dk += 0.11f * (1.0f - ease(sd / (2.6f * k))) * (0.6f + plating(x, y, (float)k));
				for (int s = 0; screws && s < 4; ++s)
				{
					const float dx = px - sxs[s], dy = py - sys[s], dd = std::sqrt(dx * dx + dy * dy) / sr;
					if (dd >= 1.3f) continue;
					const float slot = dd < 0.85f ? std::max(1.0f - std::fabs(-std::sin(sang[s]) * dx + std::cos(sang[s]) * dy) / (0.16f * k), 0.0f) : 0.0f;
					hgt += 0.3f * std::sqrt(std::max(1.0f - dd * dd, 0.0f)) - 0.15f * slot;
					dk += 0.28f * std::max(1.0f - std::fabs(dd - 1.05f) / 0.22f, 0.0f) + 0.4f * slot;
				}
			}
			if (c.window)
			{
				// the window: a step down from the frame, its walls lit as the cap's are (the lower right catches the light)
				const float sw = insideBox(px, py, c.wx0, c.wy0, c.wx1, c.wy1, c.wr);
				hgt -= 0.55f * ease((sw + 0.45f * k) / (0.6f * k));
				glass[i] = std::min(std::max(sw + 0.5f, 0.0f), 1.0f);
			}
			else if (!cut.empty())
			{
				// a chiselled cut: a dark line along its edge, chamfered faces that catch the light inside
				const float cc = cut[i], ink = sharp->cov[i] / 255.0f;
				const float ed = 4.0f * cc * (1.0f - cc);
				const float up = cut[(size_t)std::max(y - lo, 0) * W + std::max(x - lo, 0)];
				const float lip = std::max(up - cc, 0.0f) * (1.0f - ink);
				// the engraver's plate: the sign's broad parts are hatched with fine diagonal cuts, its edges outlined
				float inkDark = ink;
				if (!core.empty())
				{
					const float inner = std::min(std::max((core[i] - 0.82f) / 0.12f, 0.0f), 1.0f);
					const float wave = 0.5f + 0.5f * std::cos((px - py) * 6.2831853f / std::max(3.0f, 0.95f * k));
					inkDark = ink * (1.0f - inner * (1.0f - std::min(std::max((wave - 0.4f) / 0.3f, 0.0f), 1.0f)));
				}
				hgt -= 0.6f * cc + 0.15f * deep[i];
				dk += 0.3f * ed * ed + 0.5f * inkDark * (1.0f - 0.45f * deep[i]) - 0.35f * lip;
				dull[i] = (look.gravure ? 0.2f : 0.45f) * ink;
			}
			height[i] = hgt;
			dark[i] = dk;
		}
	}
	std::vector<Uint32> img = shadeMetal(height, dark, cover, W, H, (float)k, -0.08f * t, 0, nullptr, dull.empty() ? nullptr : &dull);
	const Uint32 own = tint ? vivid(tint) : 0;
	// the legend's light: a reserve key's off-white in its own colour (white when on), green when on, the theme's
	const Uint32 light = own ? (lit ? 0xFFFFFFFFu : HdUi::mixed(0xFFF6F2F2u, own, 0.3f)) : (lit ? LAMP : look.legend);
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const size_t i = (size_t)y * W + x;
			if (!img[i]) continue;
			const float ink = sharp ? sharp->cov[i] / 255.0f : 0.0f;
			if (!c.window && look.gravure)
			{
				// the engraving glazed: with enamel of the key's colour (the reserve keys), with a warm light when on;
				// the hatching shows through the glaze
				if (ink > 0.0f && (own || lit))
				{
					const Uint32 v = img[i];
					const float lum = (float)(((v >> 16) & 0xFF) * 3 + ((v >> 8) & 0xFF) * 6 + (v & 0xFF)) / 10.0f;
					const Uint32 glaze = HdUi::scaled(own ? enamel(own, lit) : EMBER, std::min(std::max(lum / 150.0f, 0.3f), 1.4f));
					img[i] = (v & 0xFF000000u) | (HdUi::mixed(v, glaze, (own ? 0.9f : 0.85f) * ink) & 0x00FFFFFFu);
				}
				continue;
			}
			if (!c.window)
			{
				// a brass key that is on: the cut glows green like a lamp in it, the metal stays metal
				if (lit && ink > 0.0f) img[i] = (img[i] & 0xFF000000u) | (HdUi::mixed(img[i], LAMP, 0.9f * ink) & 0x00FFFFFFu);
				continue;
			}
			if (glass[i] <= 0.0f) continue;
			const float px = x + 0.5f, py = y + 0.5f;
			const float u = (px - c.wx0) / (c.wx1 - c.wx0), v = std::min(std::max((py - c.wy0) / (c.wy1 - c.wy0), 0.0f), 1.0f);
			Uint32 col;
			if (own && lit)
			{
				// a lens lit from within: hottest a little above its middle, its own colour deepening toward the bezel
				const float dx = (u - 0.5f) * 2.0f, dy = (v - 0.42f) * 2.0f;
				const float r2 = std::min(0.8f * dx * dx + dy * dy, 1.0f);
				col = HdUi::mixed(HdUi::scaled(own, 1.25f), HdUi::scaled(own, 0.62f), r2);
				col = HdUi::mixed(col, 0xFFFFFFFFu, 0.28f * (1.0f - r2) * (1.0f - r2));
			}
			else if (own)
			{
				col = HdUi::mixed(HdUi::scaled(own, 0.46f), HdUi::scaled(own, 0.2f), v);
			}
			else
			{
				col = HdUi::mixed(look.glassTop, look.glassBottom, v);
			}
			// the frame's upper and left edges throw a shadow into the window
			const float sh = 0.5f * std::exp(-(py - c.wy0) / (0.6f * k)) + 0.25f * std::exp(-(px - c.wx0) / (0.6f * k));
			col = HdUi::scaled(col, 1.0f - std::min(sh, 0.7f));
			// the light behind the legend spills into the glass
			if (spill) col = lighten(col, light, spill->cov[i] / 255.0f * (lit ? 0.5f : 0.16f));
			// a soft reflection across the upper part of the glass
			const float r = v + 0.35f * u;
			col = HdUi::mixed(col, 0xFFFFFFFFu, 0.09f * std::max(0.0f, 1.0f - std::fabs(r - 0.3f) / 0.16f) * (1.0f - v));
			if (ink > 0.0f) col = HdUi::mixed(col, lit || own ? light : HdUi::scaled(light, 0.9f), ink);
			// pressed, the glass lies in the rim's shade with the rest of the cap
			col = HdUi::scaled(col, 1.0f - 0.2f * t * rimShade(px, py, c.g, (float)k));
			img[i] = (img[i] & 0xFF000000u) | (HdUi::mixed(img[i], col, glass[i]) & 0x00FFFFFFu);
		}
	}
	return metalCache[key] = std::move(img);
}

/// The painted keys of the pirate panel: hd/UI/battle_keys/<name>.png in the hd mod is the face of a key - a brass
/// plate with its sign - painted by the image model at any size (tools/hdart/hud_panel_pilot.py, hud_buttons_cut.py);
/// the panels after it have theirs in folders of their own (KeyLook::folder).
const char *const PAINTED[HdBattleHud::ICON_COUNT] = {
	nullptr, "unit_up", "unit_down", "map_up", "map_down", "show_map", "kneel",
	"inventory", "center", "next_soldier", "next_stop", "show_layers", "links",
	"options", "end_turn", "abort",
	"reserve_none", "reserve_snap", "reserve_aimed", "reserve_auto", "reserve_kneel",
	"zero_tus",
};

struct PaintedFace { bool tried = false; HdFrame frame; };
std::vector<PaintedFace> faces;
unsigned facesGeneration = 0;
int facesTheme = -1;

/// The painted surface of the pirate panel under the keys, hd/UI/battle_keys/panel.png, and the well a hand's item
/// lies in, well.png (its brass frame and floor): asked for as the slots after the last icon.
const int PANEL_FACE = HdBattleHud::ICON_COUNT, WELL_FACE = PANEL_FACE + 1;

/// The painted face of a key (loaded when first asked), or of the panel or a well (PANEL_FACE, WELL_FACE), or
/// nullptr: another theme, no picture in the mod.
const HdFrame *paintedFace(int icon)
{
	if (!keyLook().gravure || icon <= HdBattleHud::ICON_NONE || icon > WELL_FACE || (icon < PANEL_FACE && !PAINTED[icon])) return nullptr;
	if (faces.empty() || facesGeneration != HdUiArt::generation() || facesTheme != Options::oxceHdBattleHudColor)
	{
		// the mods were loaded again, or another painted panel was chosen: the pictures, and the keys made of them,
		// may be others now
		faces.assign(WELL_FACE + 1, PaintedFace());
		facesGeneration = HdUiArt::generation();
		facesTheme = Options::oxceHdBattleHudColor;
		metalCache.clear();
	}
	PaintedFace &f = faces[icon];
	if (!f.tried)
	{
		f.tried = true;
		const char *name = icon == PANEL_FACE ? "panel" : icon == WELL_FACE ? "well" : PAINTED[icon];
		if (!HdSprites::loadPng(HdSprites::artPath(std::string(keyLook().folder) + name + ".png"), f.frame)) f.frame = HdFrame();
	}
	return f.frame.pixels.empty() ? nullptr : &f.frame;
}

/// A picture shrunk (or grown) to W x H by averaging the source pixels each target pixel covers: the painted faces
/// are drawn many times bigger than a key, and a bilinear shrink would sparkle.
std::vector<Uint32> resampled(const HdFrame &f, int W, int H)
{
	const float sx = (float)f.width / W, sy = (float)f.height / H;
	// across, then down, in floats per channel (a, r, g, b)
	std::vector<float> across((size_t)W * f.height * 4);
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const float a0 = x * sx, a1 = std::max(a0 + sx, a0 + 1.0f);
			float acc[4] = { 0, 0, 0, 0 }, wsum = 0;
			for (int s = (int)a0; s < (int)std::ceil(a1) && s < f.width; ++s)
			{
				const float wgt = std::min(a1, s + 1.0f) - std::max(a0, (float)s);
				if (wgt <= 0.0f) continue;
				const Uint32 p = f.pixels[(size_t)y * f.width + s];
				for (int c = 0; c < 4; ++c) acc[c] += wgt * ((p >> (24 - 8 * c)) & 0xFF);
				wsum += wgt;
			}
			for (int c = 0; c < 4; ++c) across[((size_t)y * W + x) * 4 + c] = wsum > 0 ? acc[c] / wsum : 0;
		}
	}
	std::vector<Uint32> out((size_t)W * H);
	for (int y = 0; y < H; ++y)
	{
		const float b0 = y * sy, b1 = std::max(b0 + sy, b0 + 1.0f);
		for (int x = 0; x < W; ++x)
		{
			float acc[4] = { 0, 0, 0, 0 }, wsum = 0;
			for (int s = (int)b0; s < (int)std::ceil(b1) && s < f.height; ++s)
			{
				const float wgt = std::min(b1, s + 1.0f) - std::max(b0, (float)s);
				if (wgt <= 0.0f) continue;
				for (int c = 0; c < 4; ++c) acc[c] += wgt * across[((size_t)s * W + x) * 4 + c];
				wsum += wgt;
			}
			Uint32 p = 0;
			for (int c = 0; c < 4; ++c) p |= (Uint32)std::min(wsum > 0 ? acc[c] / wsum + 0.5f : 0.0f, 255.0f) << (24 - 8 * c);
			out[(size_t)y * W + x] = p;
		}
	}
	return out;
}

/// A painted key pressed `step` of CAP_STEPS - 1 into its socket, or nullptr when it has no painted face (the vector
/// cap is drawn then). The face fills the cap's place with its rounded corners; on the way down it sinks into the
/// socket's shade - darker, the rim's shadow over its upper and left edges, its lower right edge catching the light
/// as the dish of a pressed vector cap does. lit = the key is on: the engraving glows warm (a reserve key's in its
/// colour), as if a lamp burned behind the plate.
const std::vector<Uint32> *paintedCap(HdBattleHud::Icon icon, int w, int h, int k, int step, bool lit, Uint32 tint)
{
	const HdFrame *face = paintedFace(icon);
	if (!face) return nullptr;
	const Uint64 key = (2ull << 60) | ((Uint64)(tint & 0xFFFFFF) << 32) | ((Uint64)lit << 31) | ((Uint64)step << 27)
		| ((Uint64)(icon & 0x7F) << 20) | ((Uint64)(w & 0x3FF) << 10) | (Uint64)(h & 0x3FF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return hit;
	const CapGeom c = capGeom(w, h, k, tint != 0);
	const int W = w * k, H = h * k;
	const int gi = (int)std::lround(c.g), iw = std::max(W - 2 * gi, 1), ih = std::max(H - 2 * gi, 1);
	const std::vector<Uint32> inner = resampled(*face, iw, ih);
	const float t = (float)step / (float)(CAP_STEPS - 1);
	const Uint32 own = tint ? vivid(tint) : 0;
	const KeyLook &look = keyLook();
	const Uint32 glow = look.signLit;
	std::vector<Uint32> img((size_t)W * H, 0);
	for (int y = 0; y < ih; ++y)
	{
		for (int x = 0; x < iw; ++x)
		{
			const int X = x + gi, Y = y + gi;
			const float px = X + 0.5f, py = Y + 0.5f;
			const float cover = std::min(std::max(insideBox(px, py, c.g, c.g, W - c.g, H - c.g, c.R) + 0.5f, 0.0f), 1.0f);
			if (cover <= 0.0f) continue;
			Uint32 col = inner[(size_t)y * iw + x] | 0xFF000000u;
			if (lit && own)
			{
				// a reserve key's enamel is lit from behind in its own colour, its pale sign stays pale: mixed towards
				// a glow, the dark enamel washed out to pink
				col = lighten(col, own, 0.45f);
			}
			else if (lit)
			{
				// the dark engraving lights up, the brass round it takes a little of the warmth
				const float lum = (float)(((col >> 16) & 0xFF) * 3 + ((col >> 8) & 0xFF) * 6 + (col & 0xFF)) / 10.0f;
				// (the engraving is near black; brass in shadow is darker than its light but not that dark. A bone sign is
				// the lightest thing on its iron, whose lit bevel stays under 150)
				const float ink = std::min(std::max(look.paleSign ? (lum - 150.0f) / 45.0f : (70.0f - lum) / 45.0f, 0.0f), 1.0f);
				col = HdUi::mixed(col, glow, 0.05f + 0.9f * ink) | 0xFF000000u;
			}
			if (t > 0.0f)
			{
				const float shade = 0.14f * t + 0.45f * t * rimShade(px, py, c.g, (float)k);
				col = HdUi::scaled(col, 1.0f - std::min(shade, 0.8f)) | 0xFF000000u;
				const float lip = std::max(std::exp(-(W - c.g - px) / (0.8f * k)), std::exp(-(H - c.g - py) / (0.8f * k)));
				col = lighten(col, 0xFFFFE6B0u, 0.12f * t * lip);
			}
			img[(size_t)Y * W + X] = ((Uint32)(cover * 255.0f + 0.5f) << 24) | (col & 0x00FFFFFFu);
		}
	}
	return &(metalCache[key] = std::move(img));
}

/// A brass frame cast round a box (the wells under the items in hand, the soldier's card): a rounded tube
/// f wide, w x h world pixels inside it.
const std::vector<Uint32> &metalFrame(int w, int h, int k, float f)
{
	const Uint64 key = (1ull << 63) | ((Uint64)std::lround(f * 8.0f) << 40) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return *hit;
	const int fw = (int)std::ceil(f);
	const int W = w + 2 * fw, H = h + 2 * fw;
	std::vector<float> height((size_t)W * H), dark((size_t)W * H, 0.0f), cover((size_t)W * H);
	const float R = 2.5f * k;
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const size_t i = (size_t)y * W + x;
			const float sd = insideBox(x + 0.5f, y + 0.5f, 0.0f, 0.0f, (float)W, (float)H, R);
			// across the frame, outside in: a round bead, a fine groove, a flat band and a chamfer down into the
			// well, a dark line at both edges
			const float t = std::min(std::max(sd / f, 0.0f), 1.0f);
			float hgt;
			if (t < 0.15f) { const float u = (t - 0.15f) / 0.15f; hgt = std::sqrt(std::max(1.0f - u * u, 0.0f)); }
			else if (t < 0.3f) { const float u = (t - 0.15f) / 0.15f; hgt = 0.75f + 0.25f * std::sqrt(std::max(1.0f - u * u, 0.0f)); }
			else if (t < 0.62f) hgt = 0.8f;
			else hgt = 0.8f - 0.65f * ease((t - 0.62f) / 0.38f);
			height[i] = hgt;
			dark[i] = 0.3f * std::max(0.05f - t, 0.0f) / 0.05f + 0.12f * std::max(1.0f - std::fabs(t - 0.3f) / 0.04f, 0.0f)
				+ 0.35f * std::max(t - 0.9f, 0.0f) / 0.1f;
			cover[i] = std::min(std::max(sd + 0.5f, 0.0f), 1.0f) * std::min(std::max(f - sd + 0.5f, 0.0f), 1.0f);
		}
	}
	return metalCache[key] = shadeMetal(height, dark, cover, W, H, (float)k * 0.6f, 0.0f, 0);
}

/// The floor of a well (a hand's, the card's), sunk under its frame: near black at the walls, `base` (0xRRGGBB)
/// toward the middle, the frame's shadow deepest along its top and left. w x h screen pixels.
const std::vector<Uint32> &wellFloor(int w, int h, int k, Uint32 base)
{
	const Uint64 key = (1ull << 61) | ((Uint64)(base & 0xFFFFFF) << 32) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return *hit;
	std::vector<Uint32> out((size_t)w * h, 0);
	const float R = 2.5f * k, sx = 1.2f * k, sy = 1.6f * k, soft = 3.5f * k;
	const float cx = w * 0.5f, cy = h * 0.5f;
	auto rows = [&](int ra, int rb)
	{
		for (int y = ra; y < rb; ++y)
		{
			for (int x = 0; x < w; ++x)
			{
				const float px = x + 0.5f, py = y + 0.5f;
				const float sd = insideBox(px, py, 0.0f, 0.0f, (float)w, (float)h, R);
				if (sd <= -0.5f) continue;
				// the light falls past the frame from the upper left: the lit part of the floor is the well moved down and right
				const float lit = ease(insideBox(px, py, sx, sy, (float)w + sx, (float)h + sy, R) / soft);
				const float ex = (px - cx) / cx, ey = (py - cy) / cy;
				const float glow = 1.0f - 0.55f * std::min(ex * ex + ey * ey, 1.0f);
				const float v = (14.0f + 58.0f * glow * (0.25f + 0.75f * lit) + 1.5f * texture(x, y, (float)k)) / 72.0f;
				Uint32 c = (Uint32)(std::min(sd + 0.5f, 1.0f) * 255.0f + 0.5f) << 24;
				for (int sh = 0; sh <= 16; sh += 8)
				{
					c |= (Uint32)std::min(std::max((float)((base >> sh) & 0xFF) * v, 0.0f), 255.0f) << sh;
				}
				out[(size_t)y * w + x] = c;
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(h / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { rows((int)((long long)h * job / jobs), (int)((long long)h * (job + 1) / jobs)); });
	return metalCache[key] = out;
}

/// The shadow an item in hand casts on the floor of its well: its silhouette softened, w x h world pixels at
/// scale k plus pad on every side. Kept per silhouette, a few dozen at most.
const std::vector<Uint32> &itemShadow(const Surface *s, int k, int pad)
{
	static std::unordered_map<Uint64, std::vector<Uint32>> shadows;
	static int shadowScale = 0;
	const int w = s->getWidth(), h = s->getHeight();
	Uint64 hash = 1469598103934665603ull;
	for (int y = 0; y < h; ++y)
		for (int x = 0; x < w; ++x)
			hash = (hash ^ (s->getPixel(x, y) ? 1u : 0u)) * 1099511628211ull;
	hash ^= ((Uint64)w << 48) ^ ((Uint64)h << 32);
	if (shadowScale != k || shadows.size() > 64)
	{
		shadows.clear();
		shadowScale = k;
	}
	auto found = shadows.find(hash);
	if (found != shadows.end()) return found->second;
	const int W = w * k + 2 * pad, H = h * k + 2 * pad;
	std::vector<float> a((size_t)W * H, 0.0f), b((size_t)W * H);
	for (int y = 0; y < h * k; ++y)
		for (int x = 0; x < w * k; ++x)
			if (s->getPixel(x / k, y / k)) a[(size_t)(y + pad) * W + x + pad] = 1.0f;
	boxBlur2(a, b, W, H, std::max(1, pad / 2));
	std::vector<Uint32> out((size_t)W * H);
	for (size_t i = 0; i < out.size(); ++i) out[i] = (Uint32)(std::min(a[i], 1.0f) * 150.0f + 0.5f) << 24;
	return shadows[hash] = out;
}

/// The panel itself in dark brushed steel, a bevelled brass lip along its top: W x H screen pixels.
const std::vector<Uint32> &panelMetal(int W, int H, int k)
{
	const Uint64 key = (1ull << 62) | ((Uint64)(W & 0xFFFF) << 16) | (Uint64)(H & 0xFFFF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return *hit;
	if (const HdFrame *face = paintedFace(PANEL_FACE))
	{
		// the pirate panel painted: its middle cut to the panel's proportions (the boards are not stretched), shrunk
		// to it, the top corners rounded as the metal's are
		HdFrame mid;
		const int fw = std::min(face->width, (int)std::lround((double)face->height * W / H));
		const int fh = std::min(face->height, (int)std::lround((double)face->width * H / W));
		mid.width = fw;
		mid.height = fh;
		mid.pixels.resize((size_t)fw * fh);
		const int sx = (face->width - fw) / 2, sy = (face->height - fh) / 2;
		for (int y = 0; y < fh; ++y)
			std::copy_n(&face->pixels[(size_t)(sy + y) * face->width + sx], fw, &mid.pixels[(size_t)y * fw]);
		std::vector<Uint32> img = resampled(mid, W, H);
		for (int y = 0; y < H; ++y)
		{
			for (int x = 0; x < W; ++x)
			{
				const float sd = insideBox(x + 0.5f, y + 0.5f, 0.0f, 0.0f, (float)W, (float)H + 4.0f * k, 3.0f * k);
				const float cover = std::min(std::max(sd + 0.5f, 0.0f), 1.0f);
				Uint32 &p = img[(size_t)y * W + x];
				p = ((Uint32)(cover * (float)(p >> 24) + 0.5f) << 24) | (p & 0x00FFFFFFu);
			}
		}
		return metalCache[key] = std::move(img);
	}
	std::vector<float> height((size_t)W * H), dark((size_t)W * H), cover((size_t)W * H), brass((size_t)W * H);
	const float lip = 1.6f * k;
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const size_t i = (size_t)y * W + x;
			const float sd = insideBox(x + 0.5f, y + 0.5f, 0.0f, 0.0f, (float)W, (float)H + 4.0f * k, 3.0f * k);
			cover[i] = std::min(std::max(sd + 0.5f, 0.0f), 1.0f);
			// the brass lip catches the light, the dark steel below it lies low
			const float t = std::min(std::max(sd / lip, 0.0f), 1.0f);
			height[i] = t < 0.5f ? ease(t * 2.0f) : 1.0f - 0.6f * ease((t - 0.5f) * 2.0f);
			dark[i] = t < 1.0f ? -0.05f : 0.3f;
			if (t >= 1.0f && theme().hull)
			{
				// the hull's relief, twice as tall: the panel is shaded at half the keys' slope
				const Relief rel = steelRelief(x + 0.5f, y + 0.5f, (float)k);
				height[i] += 2.0f * rel.h;
				dark[i] += rel.dk;
				brass[i] = rel.metal;
			}
			else
			{
				brass[i] = 1.0f - t;
			}
		}
	}
	return metalCache[key] = shadeMetal(height, dark, cover, W, H, (float)k * 0.5f, 0.0f, theme().steel, &brass);
}

/// A hand's well painted (the pirate panel), its brass frame and floor in one W x H picture with rounded corners, or
/// nullptr: no picture, the frame and floor are cast instead.
const std::vector<Uint32> *paintedWell(int W, int H, int k)
{
	const HdFrame *face = paintedFace(WELL_FACE);
	if (!face) return nullptr;
	const Uint64 key = (3ull << 60) | ((Uint64)(W & 0xFFFF) << 16) | (Uint64)(H & 0xFFFF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return hit;
	std::vector<Uint32> img = resampled(*face, W, H);
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const float sd = insideBox(x + 0.5f, y + 0.5f, 0.0f, 0.0f, (float)W, (float)H, 2.5f * k);
			const float cover = std::min(std::max(sd + 0.5f, 0.0f), 1.0f);
			Uint32 &p = img[(size_t)y * W + x];
			p = ((Uint32)(cover * (float)(p >> 24) + 0.5f) << 24) | (p & 0x00FFFFFFu);
		}
	}
	return &(metalCache[key] = std::move(img));
}

/// A key's motion, kept between frames: how far down it is (a spring: below 0 on the bounce back up), how much the
/// mouse is over it and for how long, the flash of a press and the glint that runs across it as the mouse comes in.
struct KeyAnim
{
	float depth = 0.0f, speed = 0.0f;
	float hover = 0.0f, hoverTime = 0.0f, flash = 0.0f, sweep = 1.0f;
	Uint32 tick = 0, pressedAt = 0;
	bool lit = false, over = false;
};
std::unordered_map<const void*, KeyAnim> anims;

/// A press shows for at least this long, even when the click is quicker than a frame.
const Uint32 PRESS_MS = 110;

/// Moves a key on to now.
void animate(KeyAnim &a, bool lit, bool held, bool over)
{
	const Uint32 now = SDL_GetTicks();
	const float dt = a.tick ? std::min((float)(now - a.tick) / 1000.0f, 0.1f) : 0.0f;
	a.tick = now;
	if (lit && !a.lit) a.flash = 1.0f;
	a.lit = lit;
	if (over && !a.over) a.sweep = 0.0f;
	a.over = over;
	const bool down = held || (a.pressedAt && now - a.pressedAt < PRESS_MS);
	// a key that is on stays down, not quite to the bottom: pressed again, it goes all the way and settles back
	const float target = down ? 1.0f : (lit ? 0.72f : 0.0f);
	for (float left = dt; left > 0.0f; left -= 0.004f)
	{
		const float h = std::min(left, 0.004f);
		// pushed: down fast, without a bounce; let go: back up on a soft spring that overshoots a little
		const bool pushed = target > 0.5f && target > a.depth;
		const float w0 = pushed ? 90.0f : 34.0f, zeta = pushed ? 1.0f : 0.38f;
		a.speed += (-w0 * w0 * (a.depth - target) - 2.0f * zeta * w0 * a.speed) * h;
		a.depth += a.speed * h;
	}
	a.hover += ((over ? 1.0f : 0.0f) - a.hover) * (1.0f - std::exp(-dt / 0.08f));
	a.hoverTime = over ? a.hoverTime + dt : 0.0f;
	a.flash *= std::exp(-dt / 0.22f);
	a.sweep = std::min(a.sweep + dt / 0.55f, 1.0f);
}

/// An alpha 0..1 in sixteen steps: the colourings of a pictogram are cached per colour.
inline Uint32 steps16(float a)
{
	return (Uint32)std::min(std::max(std::lround(a * 15.0f), 0L), 15L) * 17u;
}

/// The glint that runs across a key's glass (the brass keys: its face) as the mouse comes in: a soft diagonal band
/// at `pos` 0..1 of its way. X, Y = the cell's corner in screen pixels.
void drawGlint(int X, int Y, const CapGeom &c, int w, int h, int k, float pos)
{
	const float x0 = c.window ? c.wx0 : c.g + c.bevel, y0 = c.window ? c.wy0 : c.g + c.bevel;
	const float x1 = c.window ? c.wx1 : w * k - c.g - c.bevel, y1 = c.window ? c.wy1 : h * k - c.g - c.bevel;
	const float r = c.window ? c.wr : c.R * 0.5f;
	if (x1 <= x0 || y1 <= y0) return;
	const float at = -0.3f + 1.6f * pos, strength = 0.3f * std::sin(pos * 3.14159265f);
	const Uint32 white = 0xFFFFFFFFu;
	HdUi::instance().shadeCover(X + (int)x0, Y + (int)y0, (int)std::ceil(x1 - x0) + 1, (int)std::ceil(y1 - y0) + 1, 1, &white,
		[&](int py, int xa, int xb, float *cov)
		{
			const float ly = py - Y + 0.5f, v = (ly - y0) / (y1 - y0);
			for (int px = xa; px < xb; ++px)
			{
				const float lx = px - X + 0.5f;
				const float band = std::max(1.0f - std::fabs((lx - x0) / (x1 - x0) * 0.8f + v * 0.35f - at) / 0.09f, 0.0f);
				if (band <= 0.0f) continue;
				const float in = std::min(std::max(insideBox(lx, ly, x0, y0, x1, y1, r) + 0.5f, 0.0f), 1.0f);
				cov[px - xa] = strength * band * in;
			}
		});
}

/// The short name of a key on its badge: "I", "F1", "PgUp".
std::string keyLabel(const char *name)
{
	std::string s = name ? name : "";
	if (s.empty() || s == "unknown key") return "";
	static const std::pair<const char*, const char*> SHORT[] = {
		{ "page up", "PgUp" }, { "page down", "PgDn" }, { "escape", "Esc" }, { "return", "Enter" }, { "backspace", "BkSp" },
		{ "space", "Space" }, { "delete", "Del" }, { "insert", "Ins" }, { "home", "Home" }, { "end", "End" }, { "tab", "Tab" },
		{ "up", "Up" }, { "down", "Down" }, { "left", "Left" }, { "right", "Right" },
	};
	for (const auto &p : SHORT)
	{
		if (s == p.first) return p.second;
	}
	for (char &ch : s) ch = (char)std::toupper((unsigned char)ch);
	return s.size() > 5 ? s.substr(0, 5) : s;
}

/// The key's hotkey on a small dark badge in its lower right corner, `alpha` faded in.
void drawBadge(int x, int y, int w, int h, const std::string &label, float alpha)
{
	HdUi &ui = HdUi::instance();
	const int k = HdUi::scale();
	if (label.empty() || alpha <= 0.01f || !ui.hasFonts()) return;
	const UString s = Unicode::convUtf8ToUtf32(label);
	const float capH = (w < 20 || h < 14) ? 2.3f : 2.7f;
	const float tw = ui.ttfWidth(s, false, capH);
	HdFont &f = ui.font(false);
	const float deep = f.descent(f.sizeForCapHeight(capH * k)) / k;
	// where drawTtfString puts the baseline below its y: a line of the small font's 9-row cell, lifted for the tails
	const float centred = (9.0f + capH) * 0.5f;
	const float bl = (deep <= 0.0f || centred + deep <= 9.0f) ? centred : std::max(capH, 9.0f - deep);
	const int tx = x + w - 2 - (int)std::ceil(tw), ty = (int)std::floor(y + h - 1.7f - bl);
	const float base = (float)ty * k + (float)std::lround(bl * k);
	const float x0 = (tx - 0.8f) * k, x1 = (tx + tw + 0.8f) * k, y0 = base - (capH + 0.7f) * k, y1 = base + 0.7f * k;
	ui.fillRoundRect(x0, y0, x1, y1, 1.0f * k, withAlpha(0, (Uint32)(0xC8 * alpha)), withAlpha(0, (Uint32)(0xB0 * alpha)));
	ui.strokeRoundRect(x0, y0, x1, y1, 1.0f * k, std::max(1.0f, 0.3f * k), withAlpha(keyLook().rim, (Uint32)(0x70 * alpha)));
	ui.drawTtfString(s, false, capH, tx, ty, withAlpha(0xFFFFFFu, (Uint32)(0xFF * alpha)), 0);
}

}

bool HdBattleHud::on()
{
	return Options::oxceHdBattleHud && HdUi::skin();
}

void HdBattleHud::notePress(const void *key)
{
	KeyAnim &a = anims[key];
	a.pressedAt = std::max(SDL_GetTicks(), (Uint32)1);
	a.flash = 1.0f;
}

void HdBattleHud::drawButton(const void *key, int x, int y, int w, int h, Icon icon, bool lit, bool held, Uint8 tint, const SDL_Color *pal, const char *hotkey)
{
	const int k = HdUi::scale();
	if (k <= 0 || w <= 0 || h <= 0) return;
	HdUi &ui = HdUi::instance();
	ui.notePanel(x, y, w, h);
	KeyAnim &a = anims[key];
	animate(a, lit, held, ui.hover(x, y, w, h));
	const KeyLook &look = keyLook();
	const Uint32 own = tint ? vivid(tintOf(tint, pal)) : 0;
	const CapGeom c = capGeom(w, h, k, own != 0);
	const float X0 = (float)x * k, Y0 = (float)y * k, X1 = (float)(x + w) * k, Y1 = (float)(y + h) * k, in = 0.35f * k;
	// a key that is on lights the panel round it and its socket: a reserve key in its own colour, the others green
	const Uint32 glowColor = look.gravure ? (own ? enamel(own, true) : look.ember) : (own ? own : LAMP);
	if (lit)
	{
		for (int i = 0; i < 3; ++i)
		{
			const float e = (1.5f - 0.55f * i) * k;
			ui.fillRoundRect(X0 + in - e, Y0 + in - e, X1 - in + e, Y1 - in + e, c.R + e, withAlpha(glowColor, 0x14 + 0x0E * i), withAlpha(glowColor, 0x14 + 0x0E * i));
		}
	}
	// the socket the cap sits in: dark, its lower lip catching the light
	ui.fillRoundRect(X0 + in, Y0 + in, X1 - in, Y1 - in, c.R + 0.4f * k, 0xB0000000u, 0x70000000u);
	ui.fillRoundRect(X0 + c.R, Y1 - 0.6f * k, X1 - c.R, Y1 - 0.3f * k, 0.0f, withAlpha(look.rim, 0x38), withAlpha(look.rim, 0x18));
	if (lit) ui.fillRoundRect(X0 + in, Y0 + in, X1 - in, Y1 - in, c.R + 0.4f * k, withAlpha(glowColor, 0x90), withAlpha(glowColor, 0x58));
	// the cap: up, it throws a shadow down and to the right and rises a little more under the mouse; pressed, it sinks
	// down and to the right into the socket and its shadow goes under it
	const float pressed = std::min(std::max(a.depth, 0.0f), 1.0f);
	const float d = a.depth - 0.12f * a.hover * (1.0f - pressed);
	const float up = 1.0f - std::min(std::max(d, 0.0f), 1.0f) + std::max(-d, 0.0f);
	if (up > 0.02f)
	{
		const float sx = 0.4f * k * up, sy = 0.75f * k * up;
		ui.fillRoundRect(X0 + c.g + sx, Y0 + c.g + sy, X1 - c.g + sx + 0.2f * k, Y1 - c.g + sy + 0.2f * k, c.R,
			withAlpha(0, (Uint32)std::min(0x70 * up, 255.0f)), withAlpha(0, (Uint32)std::min(0x98 * up, 255.0f)));
	}
	const int IX = x * k + (int)std::lround(0.22f * k * d), IY = y * k + (int)std::lround(0.48f * k * d);
	const int step = (int)std::lround(pressed * (CAP_STEPS - 1));
	const std::vector<Uint32> *painted = paintedCap(icon, w, h, k, step, lit, own);
	const std::vector<Uint32> &img = painted ? *painted : cap(icon, w, h, k, step, lit, own);
	ui.drawImage(img.data(), w * k, h * k, IX, IY);
	if (icon != ICON_NONE && icon < ICON_COUNT && c.window)
	{
		// under the mouse and in the flash of a press the legend burns brighter and glows
		const float glow = std::min(0.5f * a.hover + 0.9f * a.flash + (lit ? 0.35f : 0.0f), 1.0f);
		const float bright = std::min(0.55f * a.hover + 0.8f * a.flash, 1.0f);
		if (glow > 0.03f)
		{
			const Uint32 color = own ? (lit ? HdUi::mixed(own, 0xFFFFFFFFu, 0.25f) : own) : (lit ? LAMP : look.glow);
			const Raster &r = halo(icon, w, h, k, c.shrink);
			ui.drawImage(colored(r, withAlpha(color, steps16(0.75f * glow))).data(), r.w, r.h, IX, IY);
		}
		if (bright > 0.03f)
		{
			const Raster &r = raster(icon, w, h, k, c.shrink, true);
			ui.drawImage(colored(r, withAlpha(0xFFFFFFu, steps16(0.8f * bright))).data(), r.w, r.h, IX, IY);
		}
	}
	if (a.over && a.sweep < 1.0f) drawGlint(IX, IY, c, w, h, k, a.sweep);
	if (a.hover > 0.03f)
	{
		ui.strokeRoundRect(IX + c.g, IY + c.g, IX + w * k - c.g, IY + h * k - c.g, c.R, std::max(1.0f, 0.4f * k), withAlpha(look.rim, steps16(0.45f * a.hover)));
	}
	// held a moment under the mouse, the key shows its hotkey
	if (hotkey && a.over) drawBadge(x, y, w, h, keyLabel(hotkey), std::min(std::max((a.hoverTime - 0.45f) / 0.2f, 0.0f), 1.0f));
}

void HdBattleHud::drawSample(int x, int y, int w, int h)
{
	const int k = HdUi::scale();
	if (k <= 0 || w < 40 || h < 20) return;
	HdUi &ui = HdUi::instance();
	// a piece of the panel's steel with three keys on it, one of them on: the colours as they will be on the battle panel
	const int pw = w * k, ph = h * k;
	ui.drawImage(panelMetal(pw, ph, k).data(), pw, ph, x * k, y * k);
	ui.notePanel(x, y, w, h);
	static const char sampleKeys[3] = { 0, 0, 0 };
	const int kw = 23, kh = 22, gap = (w - 3 * kw) / 4, ky = y + (h - kh) / 2;
	for (int i = 0; i < 3; ++i)
	{
		const Icon icon = i == 0 ? ICON_OPTIONS : i == 1 ? ICON_INVENTORY : ICON_KNEEL;
		drawButton(&sampleKeys[i], x + gap + i * (kw + gap), ky, kw, kh, icon, i == 2, false, 0, nullptr, nullptr);
	}
}

namespace
{

/// A rivet head, a hammered dimple: the distance from (x, y) to the nearest of the points jittered one in each cell of
/// a grid `cell` wide (the point's cell number goes to `id`).
float nearestJittered(float x, float y, float cell, Uint32 seed, Uint32 &id)
{
	const int cx = (int)std::floor(x / cell), cy = (int)std::floor(y / cell);
	float best = 1e9f;
	for (int j = cy - 1; j <= cy + 1; ++j)
		for (int i = cx - 1; i <= cx + 1; ++i)
		{
			const Uint32 h = seed ^ ((Uint32)i * 0x85EBCA77u) ^ ((Uint32)j * 0xC2B2AE3Du);
			const float px = ((float)i + 0.2f + 0.6f * hash01(h)) * cell, py = ((float)j + 0.2f + 0.6f * hash01(h ^ 0x68E31DA4u)) * cell;
			const float d = (x - px) * (x - px) + (y - py) * (y - py);
			if (d < best)
			{
				best = d;
				id = h;
			}
		}
	return std::sqrt(best);
}

/// The relief of a window button's face (oxceHdButtonFace): a height, a darkening and a lightening of the metal (`metal`,
/// -1..1) at (x, y) of a W x H face, k screen pixels a base pixel.
Relief faceRelief(int face, float x, float y, float W, float H, float k)
{
	Relief r;
	switch (face)
	{
	case 2:
		// brushed: fine streaks along the rows
		r.metal = 2.0f * brushed((int)x, (int)y, k);
		break;
	case 3:
	{
		// cast: soft mottling with a grain over it
		const float p = plating((int)x, (int)y, k);
		r.metal = 2.0f * p;
		r.h = 0.06f * p;
		break;
	}
	case 4:
	{
		// hammered: overlapping shallow dimples a few base pixels across, each catching the light on its far side
		Uint32 id = 0;
		const float cell = 3.2f * k, d = nearestJittered(x, y, cell, 0x3C6EF372u, id) / (0.62f * cell);
		r.h = -0.22f * std::max(1.0f - d * d, 0.0f);
		r.metal = 0.5f * (hash01(id) - 0.5f);
		break;
	}
	case 5:
	{
		// riveted: a brushed plate with a rivet in each corner and along the long edges every dozen base pixels
		r.metal = 1.2f * brushed((int)x, (int)y, k);
		const float in = 2.4f * k, rr = 0.8f * k;
		rivet(r, x, y, in, in, rr);
		rivet(r, x, y, W - in, in, rr);
		rivet(r, x, y, in, H - in, rr);
		rivet(r, x, y, W - in, H - in, rr);
		const int n = (int)((W - 2.0f * in) / (12.0f * k));
		for (int i = 1; i < n; ++i)
		{
			const float cx = in + (W - 2.0f * in) * (float)i / (float)n;
			rivet(r, x, y, cx, in, rr);
			rivet(r, x, y, cx, H - in, rr);
		}
		break;
	}
	case 6:
		// scales: small plates laid like shingles
		r = shingles(x, y, 4.0f * k, 2.5f * k, 0.5f * k);
		break;
	case 7:
	{
		// tread plate: raised lozenges in rows, every other one turned the other way
		const float cell = 4.5f * k;
		const float i = std::floor(x / cell), j = std::floor(y / cell);
		const float u = x - (i + 0.5f) * cell, v = y - (j + 0.5f) * cell;
		const float s = std::fmod(i + j, 2.0f) != 0.0f ? 1.0f : -1.0f;
		const float a = (u + s * v) * 0.70710678f, b = (u - s * v) * 0.70710678f;
		const float e = (a / (1.7f * k)) * (a / (1.7f * k)) + (b / (0.45f * k)) * (b / (0.45f * k));
		r.h = 0.35f * std::sqrt(std::max(1.0f - e, 0.0f));
		r.metal = 0.4f * brushed((int)x, (int)y, k);
		break;
	}
	case 8:
	{
		// carbon: a 2x2 twill of dark tows, the ones along the rows and the ones across lit differently
		const float t = 1.4f * k;
		const int i = (int)std::floor(x / t), j = (int)std::floor(y / t);
		const bool along = (((i - j) % 4) + 4) % 4 < 2;
		const float f = along ? y / t - std::floor(y / t) : x / t - std::floor(x / t);
		const float bulge = std::sin(f * 3.14159265f);
		r.h = 0.1f * bulge;
		r.dk = 0.24f - (along ? 0.16f : 0.07f) * bulge;
		break;
	}
	case 9:
		// wood: the pirate panel's mahogany planking
		r = planking(x, y, k);
		r.metal = 0.0f;
		break;
	case 10:
	{
		// lightning: two zigzag bolts engraved across the face, their floors polished bright
		if (x < 2.0f * k || x > W - 2.0f * k) break;
		const float seg = 5.0f * k;
		const int i = (int)std::floor(x / seg);
		const float f = x / seg - (float)i;
		float g = 0.0f;
		for (int b = 0; b < 2; ++b)
		{
			const Uint32 seed = b ? 0x1B873593u : 0xCC9E2D51u;
			const float mid = H * (b ? 0.68f : 0.32f), amp = 0.32f * H;
			const float ya = mid + (hash01(seed ^ (Uint32)i * 0x9E3779B1u) - 0.5f) * amp;
			const float yb = mid + (hash01(seed ^ (Uint32)(i + 1) * 0x9E3779B1u) - 0.5f) * amp;
			const float slope = (yb - ya) / seg;
			const float dist = std::fabs(y - (ya + (yb - ya) * f)) / std::sqrt(1.0f + slope * slope);
			g = std::max(g, std::max(1.0f - dist / (0.5f * k), 0.0f));
		}
		r.h = -0.3f * g;
		r.metal = 1.4f * g * g;
		break;
	}
	case 11:
	{
		// worn: grime in blotches, thicker towards the edges, and bright scratches through it
		const float dust = valueNoise(x / (4.0f * k), y / (4.0f * k), 0x2F6B1D35u);
		const float rim = std::max(1.0f - std::min(std::min(x, W - x), std::min(y, H - y)) / (3.5f * k), 0.0f);
		r.dk = 0.1f * dust + 0.12f * rim * dust;
		const float cell = 7.0f * k;
		float scratch = 0.0f;
		const int ci = (int)std::floor(x / cell), cj = (int)std::floor(y / cell);
		for (int j = cj - 1; j <= cj + 1; ++j)
			for (int i = ci - 1; i <= ci + 1; ++i)
			{
				const Uint32 h = 0x7A5B3C1Du ^ ((Uint32)i * 0x85EBCA77u) ^ ((Uint32)j * 0xC2B2AE3Du);
				if (hash01(h) < 0.45f) continue;
				const float px = ((float)i + hash01(h ^ 1u)) * cell, py = ((float)j + hash01(h ^ 2u)) * cell;
				const float ang = hash01(h ^ 3u) * 3.14159265f, len = (0.4f + 0.6f * hash01(h ^ 4u)) * cell;
				const float dx = std::cos(ang), dy = std::sin(ang);
				const float along = (x - px) * dx + (y - py) * dy;
				if (std::fabs(along) > len) continue;
				const float across = std::fabs(-(x - px) * dy + (y - py) * dx);
				scratch = std::max(scratch, std::max(1.0f - across / (0.3f * k), 0.0f) * (1.0f - std::fabs(along) / len));
			}
		r.dk -= 0.2f * scratch;
		r.metal = -0.5f * dust;
		break;
	}
	default:
		break;
	}
	return r;
}

/// A window button's face as it is cast: W x H screen pixels, the shades of the metal at 0..1 in `lut` (256).
std::vector<Uint32> castFace(int W, int H, float k, int face, int shape, float gloss, bool pressed, bool over, const Uint32 *lut)
{
	const size_t n = (size_t)W * H;
	std::vector<float> height(n, 0.0f), dark(n, 0.0f), metal(n, 0.0f), cover(n, 0.0f);
	const float r = 1.5f * k, bevel = std::max(1.6f * k, 1.0f), dome = 0.5f * (float)std::min(W, H);
	auto shapeRows = [&](int ra, int rb)
	{
		for (int y = ra; y < rb; ++y)
			for (int x = 0; x < W; ++x)
			{
				const size_t i = (size_t)y * W + x;
				const float px = (float)x + 0.5f, py = (float)y + 0.5f;
				const float d = insideBox(px, py, 0.0f, 0.0f, (float)W, (float)H, r);
				cover[i] = std::min(std::max(d + 0.5f, 0.0f), 1.0f);
				if (cover[i] <= 0.0f) continue;
				float h;
				switch (shape)
				{
				case 1:
				{
					// a pillow: rounded all the way to its middle
					const float t = 1.0f - std::min(d / dome, 1.0f);
					h = std::sqrt(std::max(1.0f - t * t, 0.0f));
					break;
				}
				case 2:
				{
					// a rim, then a panel sunk inside it
					const float t = d / bevel;
					h = t < 1.0f ? t : t < 2.0f ? 1.0f - 0.55f * (t - 1.0f) : 0.45f;
					break;
				}
				default:
					// a plate with a chamfer round it
					h = std::min(d / bevel, 1.0f);
					break;
				}
				const Relief rel = faceRelief(face, px, py, (float)W, (float)H, k);
				h += rel.h;
				// pressed: the face sinks, the slopes that caught the light lose it
				height[i] = pressed ? -0.6f * h : h;
				// a thin dark outline holds the shape against any background
				dark[i] = rel.dk + 0.25f * std::max(1.0f - d / (0.7f * k), 0.0f);
				metal[i] = rel.metal;
			}
	};
	auto shadeRows = [&](std::vector<Uint32> &out, int ra, int rb)
	{
		// the light from the upper left, as on the battle panel; the view straight on
		const float lx = -0.5f, ly = -0.6f, lz = 0.62f;
		const float hx = lx, hy = ly, hz = lz + 1.0f, hn = std::sqrt(hx * hx + hy * hy + hz * hz);
		// gloss 0 matte, 0.5 polished metal, 1 a mirror under coloured glass: the highlight narrows and brightens, the
		// texture's own streaks fade, past the middle the face reflects a horizon (light above, dark below)
		const float power = 3.0f + 90.0f * gloss * gloss, bright = 0.08f + 0.75f * gloss;
		const float grain = 0.075f * (1.0f - 0.7f * gloss), mirror = std::max(2.0f * gloss - 1.0f, 0.0f);
		// pressed (the chosen speed, tab or tile) reads lighter, as the lit button of the classic look, even under a mirror
		const float lift = (pressed ? 0.2f : 0.0f) + (over ? 0.07f : 0.0f);
		for (int y = ra; y < rb; ++y)
		{
			const int yu = std::max(y - 1, 0), yd = std::min(y + 1, H - 1);
			for (int x = 0; x < W; ++x)
			{
				const size_t i = (size_t)y * W + x;
				if (cover[i] <= 0.0f) continue;
				const int xl = std::max(x - 1, 0), xr = std::min(x + 1, W - 1);
				const float gx = (height[(size_t)y * W + xr] - height[(size_t)y * W + xl]) * 0.5f * k;
				const float gy = (height[(size_t)yd * W + x] - height[(size_t)yu * W + x]) * 0.5f * k;
				const float nl = 1.0f / std::sqrt(gx * gx + gy * gy + 1.0f);
				const float nx = -gx * nl, ny = -gy * nl, nz = nl;
				const float d = nx * lx + ny * ly + nz * lz;
				const float spec = bright * std::pow(std::max((nx * hx + ny * hy + nz * hz) / hn, 0.0f), power);
				float s = 0.6f + 0.9f * (d - lz) - dark[i] + lift + grain * metal[i];
				if (mirror > 0.0f)
				{
					// the reflected horizon bends with the face's slopes
					const float v = ((float)y + 0.5f) / (float)H + 0.35f * ny;
					const float sky = std::min(std::max((0.46f - v) / 0.04f, -1.0f), 1.0f);
					s += mirror * (0.22f * sky - 0.06f);
				}
				const Uint32 c = lut[std::min(std::max((int)(s * 255.0f + 0.5f), 0), 255)];
				const Uint32 lit = mix(c, 0xFFFFFFFFu, std::min(spec, 1.0f) * 0.85f);
				out[i] = withAlpha(lit, (Uint32)(cover[i] * 255.0f + 0.5f));
			}
		}
	};
	std::vector<Uint32> out(n, 0);
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { shapeRows((int)((long long)H * job / jobs), (int)((long long)H * (job + 1) / jobs)); });
	pool.run(jobs, [&](int job) { shadeRows(out, (int)((long long)H * job / jobs), (int)((long long)H * (job + 1) / jobs)); });
	return out;
}

int faceScale = 0, faceTheme = -1;
std::unordered_map<Uint64, std::vector<Uint32>> faceCache;
Uint32 faceLut[256];

}

void HdBattleHud::drawFace(int x, int y, int w, int h, bool pressed, bool over, int face)
{
	const int k = HdUi::scale();
	if (k <= 0 || w <= 0 || h <= 0) return;
	if (face < 0) face = Options::oxceHdButtonFace;
	face = std::min(std::max(face, 1), FACES - 1);
	const int shape = std::min(std::max(Options::oxceHdButtonShape, 0), SHAPES - 1);
	const int gloss = std::min(std::max(Options::oxceHdButtonGloss, 0), 100);
	// the casts go with the colours (the metal's shades are read here, on the main thread) and the scale
	const int themeNow = themeKey();
	if (k != faceScale || themeNow != faceTheme || faceCache.size() > 256)
	{
		faceCache.clear();
		faceScale = k;
		faceTheme = themeNow;
		for (int i = 0; i < 256; ++i) faceLut[i] = metalShade((float)i / 255.0f);
	}
	const int W = w * k, H = h * k;
	const Uint64 key = (Uint64)W | (Uint64)H << 14 | (Uint64)face << 28 | (Uint64)shape << 33 | (Uint64)gloss << 36
		| (Uint64)pressed << 44 | (Uint64)over << 45;
	auto found = faceCache.find(key);
	if (found == faceCache.end())
	{
		found = faceCache.emplace(key, castFace(W, H, (float)k, face, shape, (float)gloss / 100.0f, pressed, over, faceLut)).first;
	}
	HdUi::instance().drawImage(found->second.data(), W, H, x * k, y * k);
}

bool HdBattleHud::grooved(const Surface *bar)
{
	return on() && theme().plaques && std::find(grooves.begin(), grooves.end(), bar) != grooves.end();
}

bool HdBattleHud::counter(const Surface *number, Uint32 &plate, Uint32 &edge)
{
	if (!on() || !keyLook().gravure || std::find(counters.begin(), counters.end(), number) == counters.end()) return false;
	// the painted well's frame and leather are light and busy under a thin digit: a dark enamel tab in the
	// keys' metal
	plate = 0xF0140C06u;
	edge = theme().ramp[3];
	return true;
}

int HdBattleHud::themeKey()
{
	if (Options::oxceHdBattleHudColor == COLOR_CUSTOM)
	{
		customRefresh();
		return 1000 + (int)(custom.version & 0xFFFFFF);
	}
	return Options::oxceHdBattleHudColor;
}

Uint32 HdBattleHud::metalShade(float s)
{
	// the dark panel's graphite reads as no metal at all round a window: its frames are the pirate panel's brass
	if (theme().ramp == GRAPHITE)
	{
		s = std::min(std::max(s, 0.0f), 1.0f);
		int i = 0;
		while (i < 5 && s > RAMP_AT[i + 1]) ++i;
		return mix(SHIP_BRASS[i], SHIP_BRASS[i + 1], (s - RAMP_AT[i]) / (RAMP_AT[i + 1] - RAMP_AT[i]));
	}
	return rampColor(s, 0);
}

void HdBattleHud::grooveColors(Uint32 &top, Uint32 &bottom, Uint32 &lip)
{
	const Theme &t = theme();
	top = t.grooveTop;
	bottom = t.grooveBottom;
	lip = t.lipLight;
}

void HdHudPanel::addPart(Part part, const Surface *widget, Uint8 color)
{
	if (part == PART_BAR || part == PART_COUNT)
	{
		(part == PART_BAR ? grooves : counters).push_back(widget);
		return;
	}
	_parts.push_back(Item{ part, widget, color });
}

HdHudPanel::~HdHudPanel()
{
	// the bars and the keys go with the screen; one made later at the same address is not this one
	grooves.clear();
	counters.clear();
	anims.clear();
}

void HdHudPanel::hdMirror()
{
	if (!HdBattleHud::on())
	{
		InteractiveSurface::hdMirror();
		return;
	}
	const int k = HdUi::scale();
	if (k <= 0) return;
	HdUi &ui = HdUi::instance();
	const SDL_Color *pal = HdUi::paletteOf(this);
	const Theme &t = theme();
	const float x0 = (float)getX() * k, y0 = (float)getY() * k;
	const float x1 = (float)(getX() + getWidth()) * k, y1 = (float)(getY() + getHeight()) * k;
	const float edge = std::max(1.0f, 0.5f * k);
	// the map fades into the panel instead of ending at a hard line
	ui.fillRoundRect(x0, y0 - 4.0f * k, x1, y0, 0.0f, 0x00000000u, 0x70000000u);
	// the panel: rounded at the top, a fine light edge along it
	if (t.plaques)
	{
		const int pw = getWidth() * k, ph = getHeight() * k;
		ui.drawImage(panelMetal(pw, ph, k).data(), pw, ph, getX() * k, getY() * k);
	}
	else
	{
		ui.fillRoundRect(x0, y0, x1, y1 + 3.0f * k, 3.0f * k, t.panelTop, t.panelBottom);
		ui.fillRoundRect(x0 + 2.0f * k, y0, x1 - 2.0f * k, y0 + edge, 0.0f, t.panelEdge, t.panelEdge);
	}
	ui.notePanel(getX(), getY(), getWidth(), getHeight());
	for (const Item &item : _parts)
	{
		const Surface *s = item.widget;
		const float wx0 = (float)s->getX() * k, wy0 = (float)s->getY() * k;
		const float wx1 = (float)(s->getX() + s->getWidth()) * k, wy1 = (float)(s->getY() + s->getHeight()) * k;
		switch (item.part)
		{
		case HdHudPanel::PART_HAND:
		{
			const float m = 1.5f * k;
			if (t.plaques)
			{
				// the original's gold frame round the hand, cast in the same metal as the keys, its chamfer
				// running a base pixel into the well, which lies sunk and shadowed under it
				const int ix = (int)std::lround(wx0 - m), iy = (int)std::lround(wy0 - m);
				const int iw = (int)std::lround(wx1 + m) - ix, ih = (int)std::lround(wy1 + m) - iy;
				const int in = (int)std::lround(1.0f * k);
				const float f = 2.8f * k + in;
				const int fw = (int)std::ceil(f);
				const int ow = iw - 2 * in + 2 * fw, oh = ih - 2 * in + 2 * fw;
				// the pirate panel's painted well (frame and floor in one) takes the place of both, under the item
				const std::vector<Uint32> *painted = paintedWell(ow, oh, k);
				if (painted) ui.drawImage(painted->data(), ow, oh, ix + in - fw, iy + in - fw);
				else ui.drawImage(wellFloor(iw, ih, k, t.wellBase).data(), iw, ih, ix, iy);
				// the item lies on that floor: its shadow falls down and to the right
				const int pad = (int)std::lround(1.5f * k), off = (int)std::lround(1.2f * k);
				ui.drawImage(itemShadow(s, k, pad).data(), s->getWidth() * k + 2 * pad, s->getHeight() * k + 2 * pad,
					s->getX() * k - pad + off, s->getY() * k - pad + (int)std::lround(1.6f * k));
				if (!painted)
				{
					const std::vector<Uint32> &frame = metalFrame(iw - 2 * in, ih - 2 * in, k, f);
					ui.drawImage(frame.data(), ow, oh, ix + in - fw, iy + in - fw);
				}
			}
			else
			{
				ui.fillRoundRect(wx0 - m, wy0 - m, wx1 + m, wy1 + m, 2.5f * k, t.wellTop, t.wellBottom);
				ui.strokeRoundRect(wx0 - m, wy0 - m, wx1 + m, wy1 + m, 2.5f * k, edge, t.wellEdge);
			}
			break;
		}
		case HdHudPanel::PART_CARD:
		{
			const float m = 1.0f * k;
			const float cy1 = std::min(wy1 + m, y1 - 0.5f * k);
			if (t.plaques)
			{
				// a dark plate sunk in a brass frame: the mod's coloured figures stay legible on it
				const float f = 1.6f * k;
				const int fw = (int)std::ceil(f);
				const int ix = (int)std::lround(wx0 - m), iy = (int)std::lround(wy0 - m);
				const int iw = (int)std::lround(wx1 + m) - ix, ih = (int)std::lround(cy1) - iy;
				ui.drawImage(wellFloor(iw, ih, k, t.cardBase).data(), iw, ih, ix, iy);
				const std::vector<Uint32> &frame = metalFrame(iw, ih, k, f);
				ui.drawImage(frame.data(), iw + 2 * fw, ih + 2 * fw, ix - fw, iy - fw);
			}
			else
			{
				ui.fillRoundRect(wx0 - m, wy0 - m, wx1 + m, cy1, 2.2f * k, t.cardTop, t.cardBottom);
				ui.strokeRoundRect(wx0 - m, wy0 - m, wx1 + m, cy1, 2.2f * k, edge, t.cardEdge);
			}
			break;
		}
		case HdHudPanel::PART_RANK:
			ui.fillRoundRect(wx0, wy0, wx1, wy1 - 0.5f * k, 1.6f * k, t.rankFill, t.rankFill);
			break;
		case HdHudPanel::PART_CHIP:
		{
			const Uint32 c = pal ? HdUi::rgba(pal[item.color]) : t.accent;
			const float cx0 = wx0 - 1.5f * k, cy0 = wy0 - 1.0f * k, cx1 = wx1 + 1.0f * k, cy1 = wy1 + 1.0f * k;
			if (t.plaques)
			{
				// a pocket in the plate: darker than it, the stat's colour in its floor, its upper wall in
				// shadow and its lower lip catching the light
				ui.fillRoundRect(cx0, cy0, cx1, cy1, 1.4f * k, 0x70000000u, 0x50000000u);
				ui.fillRoundRect(cx0, cy0, cx1, cy1, 1.4f * k, withAlpha(c, 0x30), withAlpha(c, 0x20));
				ui.fillRoundRect(cx0, cy0, cx1, cy0 + 1.2f * k, 1.4f * k, 0x90000000u, 0x00000000u);
				ui.fillRoundRect(cx0 + 1.2f * k, cy1 - 0.1f * k, cx1 - 1.2f * k, cy1 + 0.4f * k, 0.0f, withAlpha(t.lipLight, 0x58), withAlpha(t.lipLight, 0x10));
			}
			else
			{
				ui.fillRoundRect(cx0, cy0, cx1, cy1, 1.4f * k, withAlpha(c, 0x40), withAlpha(c, 0x28));
			}
			break;
		}
		case HdHudPanel::PART_BAR:
		case HdHudPanel::PART_COUNT:
			break; // the bar draws its groove itself (Bar::hdMirror), the counter its tab (NumberText::hdMirror)
		}
	}
}

void HdPanelToggle::hdMirror()
{
	const int k = HdUi::scale();
	if (k <= 0 || !HdBattleHud::on()) return;
	HdUi &ui = HdUi::instance();
	const Theme &t = theme();
	const bool over = ui.hover(getX(), getY(), getWidth(), getHeight());
	const float x0 = (float)getX() * k, y0 = (float)getY() * k;
	const float x1 = (float)(getX() + getWidth()) * k, y1 = (float)(getY() + getHeight()) * k;
	// a tab in the panel's colours, rounded at the top and running into the panel below it
	ui.fillRoundRect(x0, y0, x1, y1 + 2.0f * k, 2.0f * k, over ? t.hoverTop : t.panelTop, t.panelTop);
	ui.strokeRoundRect(x0, y0, x1, y1 + 2.0f * k, 2.0f * k, std::max(1.0f, 0.4f * k), withAlpha(keyLook().rim, 0x90));
	ui.notePanel(getX(), getY(), getWidth(), getHeight());
	const float cx = (x0 + x1) * 0.5f, cy = (y0 + y1) * 0.5f + 0.5f * k, hw = 2.6f * k, hh = 1.5f * k;
	const Uint32 c = over ? t.iconHover : t.icon;
	if (_down)
	{
		ui.fillTriangle(cx - hw, cy + hh, cx + hw, cy + hh, cx, cy - hh, c);
	}
	else
	{
		ui.fillTriangle(cx - hw, cy - hh, cx + hw, cy - hh, cx, cy + hh, c);
	}
}

void HdTurnMark::hdMirror()
{
	const int k = HdUi::scale();
	if (k <= 0 || _kind == NONE) return;
	HdUi &ui = HdUi::instance();
	// a plate with a line of text, centred, its middle `cyBase` base pixels from the top: the text's cell is 16 base pixels
	// tall, its capitals in the middle
	const auto plate = [&](float cyBase)
	{
		if (!ui.hasFonts() || _text.empty()) return;
		const UString s = Unicode::convUtf8ToUtf32(_text);
		const float cap = 6.0f;
		HdFont &f = ui.font(true);
		const float w = f.measure(s, f.sizeForCapHeight(cap * k)) / k;
		const int tx = (int)std::lround((getWidth() - w) * 0.5f), ty = (int)std::lround(cyBase) - 8;
		const float cy = (ty + 8.0f) * k, hh = (cap * 0.5f + 5.0f) * k;
		const float x0 = (tx - 10.0f) * k, x1 = (tx + w + 10.0f) * k;
		ui.fillRoundRect(x0, cy - hh, x1, cy + hh, hh, 0xD8300C0Cu, 0xD8140404u);
		ui.strokeRoundRect(x0, cy - hh, x1, cy + hh, hh, std::max(1.0f, 0.4f * k), 0xFFD84438u);
		ui.drawTtfString(s, true, cap, tx, ty, 0xFFFFE6DCu, 0xC0000000u);
	};
	if (_kind == STRIP)
	{
		plate(getHeight() * 0.5f); // under the screen's title
		return;
	}
	// the frame: a glow falling off toward the centre, a thin line a little inside the edge and thicker corner brackets
	const int W = getWidth() * k, H = getHeight() * k;
	const float m = (float)std::min(W, H);
	const float glow = 0.05f * m, lineAt = 0.006f * m, lineW = std::max(1.5f, 0.0021f * m);
	const float brLen = 0.10f * m, brW = lineW * 2.2f;
	const bool red = _kind == FRAME_ENEMY;
	const Uint32 face = 0xFF000000u | (red ? 0xD82020u : 0xE8B818u);
	const Uint32 bright = 0xFF000000u | (red ? 0xF04030u : 0xFFD838u);
	// per pixel the glow (face), then the line (bright)
	const Uint32 colors[2] = { face, bright };
	const auto rowFn = [=](int y, int x0, int x1, float *cov)
	{
		const int dy = std::min(y, H - 1 - y), n = x1 - x0;
		for (int x = x0; x < x1; ++x)
		{
			const int dx = std::min(x, W - 1 - x);
			const float d = (float)std::min(dx, dy);
			if (d < glow)
			{
				const float t = 1.0f - d / glow;
				cov[x - x0] = 0.50f * t * t;
			}
			const float lw = (float)std::max(dx, dy) < brLen ? brW : lineW;
			const float line = std::max(0.0f, std::min(1.0f, std::min(d + 1.0f - lineAt, lineAt + lw - d)));
			if (line > 0.0f)
			{
				cov[n + x - x0] = (lw == brW ? 0.95f : 0.72f) * line;
			}
		}
	};
	const int band = (int)std::ceil(std::max(glow, lineAt + brW)) + 2;
	if (band * 2 >= H || band * 2 >= W) return;
	ui.shadeCover(0, 0, W, band, 2, colors, rowFn);
	ui.shadeCover(0, H - band, W, band, 2, colors, rowFn);
	ui.shadeCover(0, band, band, H - 2 * band, 2, colors, rowFn);
	ui.shadeCover(W - band, band, band, H - 2 * band, 2, colors, rowFn);
	// the bottom centre (XP-000306/312): the progress bar of mode 3 and over its place the plate with the line of text (the
	// enemy's turn only); `_lift` base pixels up, so that the panel, if it stands in the way, stays clear
	const float baseBottom = (float)getHeight() - 8.0f - (float)_lift;
	const float barH = 6.0f, barTop = baseBottom - barH;
	if (_kind == FRAME_ENEMY)
	{
		plate(barTop - 14.0f);
	}
	if (_bar)
	{
		// the progress bar (oxceHdEnemyTurn 3), wide, at the bottom centre: a dark groove, a line round it in the frame's
		// colour and the share of the turn done filled from the left; the number is the stock hidden screen's own
		const float bh = barH * k, bw = std::max(72.0f, 0.5f * (float)getWidth()) * k, r = bh * 0.5f;
		const float x0 = ((float)W - bw) * 0.5f, x1 = x0 + bw, y0 = barTop * k, y1 = y0 + bh;
		const float line = std::max(1.0f, 0.4f * k);
		ui.fillRoundRect(x0, y0, x1, y1, r, 0xC0180808u, 0xC0080404u);
		const float fw = bw * (float)_percent / 100.0f;
		if (fw >= bh)
		{
			ui.fillRoundRect(x0, y0, x0 + fw, y1, r, bright, face);
		}
		else if (fw > 0.0f)
		{
			ui.fillRoundRect(x0, y0 + (bh - fw) * 0.5f, x0 + fw, y1 - (bh - fw) * 0.5f, fw * 0.5f, bright, face);
		}
		ui.strokeRoundRect(x0, y0, x1, y1, r, line, bright);
	}
}

}
