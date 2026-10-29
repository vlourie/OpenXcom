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
#include "HdScreens.h"
#include <algorithm>
#include <cmath>
#include <list>
#include <random>
#include <sstream>
#include <unordered_map>
#include <vector>
#include "FileMap.h"
#include "HdBattleHud.h"
#include "HdSprites.h"
#include "HdUi.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "Options.h"
#include "SDL2Helpers.h"

namespace OpenXcom
{

namespace HdScreens
{

namespace
{

const char *const FOLDER = "UI/screens";

/// The themes: the picture's path (artPath) by interface id.
std::vector<std::string> pictures;
std::unordered_map<std::string, int> themeOf;   ///< the line of screens.txt (index of `lines`) by interface id
/// The pictures of each line: one, or several the screens change between (nextVariant), and the one shown now.
std::vector<std::vector<int>> lines;
std::vector<size_t> shown;
/// The pictures that could not be read (not tried again).
std::vector<bool> failed;

/// A theme picture prepared for one window size and scale: sharp (muted, darkened, vignetted) and frosted
/// (the same blurred and darker), both W x H world pixels, opaque.
struct Prepared
{
	int theme = -1, w = 0, h = 0, k = 0;
	std::vector<Uint32> sharp, frosted;
	std::vector<Uint32> composed;             ///< sharp and frosted mixed by the veil of hash `veil` (what is drawn)
	Uint64 veil = 0;
};
std::list<Prepared> prepared;                 ///< most recently used first
/// at most this many bytes of prepared pictures (three planes each): a dozen windows the size of the screen at k = 4
const size_t PREPARED_BYTES = 144u << 20;

/// The frost mask of a window: where its text lay in the last frame, softened, one cell per base pixel.
struct Veil
{
	Uint64 hash = 0;
	int w = 0, h = 0;
	std::vector<float> m;
};
std::unordered_map<const void*, Veil> veils;

/// A window frame in metal: the four strips of the band (top and bottom W x B, left and right B x (H - 2B)).
struct Frame
{
	int w = 0, h = 0, k = 0, inset = 0, metal = 0;
	bool thin = false;
	Uint32 accent = 0;
	std::vector<Uint32> top, bottom, left, right;
};
std::list<Frame> frames;
const size_t FRAMES_MAX = 16;

inline float lum(float r, float g, float b) { return 0.299f * r + 0.587f * g + 0.114f * b; }

inline Uint32 pack(float r, float g, float b)
{
	auto ch = [](float v) { return (Uint32)std::min(std::max((int)(v + 0.5f), 0), 255); };
	return 0xFF000000u | (ch(r) << 16) | (ch(g) << 8) | ch(b);
}

/// Runs fn(a, b) over [0, n) in bands on the render threads.
void bands(int n, const std::function<void(int, int)> &fn)
{
	if (n < 64)
	{
		fn(0, n);
		return;
	}
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(n / 16, pool.threads() * 4));
	pool.run(jobs, [&](int job) { fn((int)((long long)n * job / jobs), (int)((long long)n * (job + 1) / jobs)); });
}

/// Three box blurs of radius r one after another (about a Gaussian of sigma r), opaque pixels, in place.
void blur(std::vector<Uint32> &px, int w, int h, int r)
{
	std::vector<Uint32> tmp(px.size());
	auto pass = [&](const std::vector<Uint32> &src, std::vector<Uint32> &dst, bool across)
	{
		const int n = across ? h : w, len = across ? w : h;
		const size_t step = across ? 1 : (size_t)w;
		bands(n, [&](int a, int b)
		{
			for (int line = a; line < b; ++line)
			{
				const size_t base = across ? (size_t)line * w : (size_t)line;
				auto at = [&](int i) { return src[base + (size_t)std::min(std::max(i, 0), len - 1) * step]; };
				int sr = 0, sg = 0, sb = 0;
				for (int i = -r; i <= r; ++i)
				{
					const Uint32 c = at(i);
					sr += (c >> 16) & 0xFF; sg += (c >> 8) & 0xFF; sb += c & 0xFF;
				}
				const int div = 2 * r + 1;
				for (int i = 0; i < len; ++i)
				{
					dst[base + (size_t)i * step] = 0xFF000000u | ((Uint32)(sr / div) << 16) | ((Uint32)(sg / div) << 8) | (Uint32)(sb / div);
					const Uint32 out = at(i - r), in = at(i + r + 1);
					sr += (int)((in >> 16) & 0xFF) - (int)((out >> 16) & 0xFF);
					sg += (int)((in >> 8) & 0xFF) - (int)((out >> 8) & 0xFF);
					sb += (int)(in & 0xFF) - (int)(out & 0xFF);
				}
			}
		});
	};
	for (int i = 0; i < 3; ++i)
	{
		pass(px, tmp, true);
		pass(tmp, px, false);
	}
}

/// The same for a float mask (one cell per base pixel), zero outside.
void blurMask(std::vector<float> &m, int w, int h, int r)
{
	std::vector<float> tmp(m.size());
	auto pass = [&](const std::vector<float> &src, std::vector<float> &dst, bool across)
	{
		const int n = across ? h : w, len = across ? w : h;
		const size_t step = across ? 1 : (size_t)w;
		for (int line = 0; line < n; ++line)
		{
			const size_t base = across ? (size_t)line * w : (size_t)line;
			auto at = [&](int i) { return i < 0 || i >= len ? 0.0f : src[base + (size_t)i * step]; };
			float s = 0.0f;
			for (int i = -r; i <= r; ++i) s += at(i);
			for (int i = 0; i < len; ++i)
			{
				dst[base + (size_t)i * step] = s / (2 * r + 1);
				s += at(i + r + 1) - at(i - r);
			}
		}
	};
	for (int i = 0; i < 2; ++i)
	{
		pass(m, tmp, true);
		pass(tmp, m, false);
	}
}

/// The theme picture for a window of W x H world pixels at scale k: fitted (cover), muted and darkened.
const Prepared *prepare(int theme, int W, int H, int k)
{
	for (auto it = prepared.begin(); it != prepared.end(); ++it)
	{
		if (it->theme == theme && it->w == W && it->h == H && it->k == k)
		{
			prepared.splice(prepared.begin(), prepared, it);
			return &prepared.front();
		}
	}
	if (failed[theme])
	{
		return nullptr;
	}
	const Uint32 t0 = SDL_GetTicks();
	HdFrame src;
	if (!HdSprites::loadPng(pictures[theme], src) || src.width <= 0 || src.height <= 0)
	{
		Log(LOG_WARNING) << "HD screens: " << pictures[theme] << " cannot be read";
		failed[theme] = true;
		return nullptr;
	}
	const Uint32 tLoad = SDL_GetTicks();
	// cover: the middle of the picture in the window's proportions, then scaled to it
	const double s = std::max((double)W / src.width, (double)H / src.height);
	const int cw = std::min(src.width, std::max(1, (int)std::lround(W / s))), ch = std::min(src.height, std::max(1, (int)std::lround(H / s)));
	const int cx = (src.width - cw) / 2, cy = (src.height - ch) / 2;
	HdFrame crop;
	crop.width = cw;
	crop.height = ch;
	crop.pixels.resize((size_t)cw * ch);
	for (int y = 0; y < ch; ++y)
	{
		std::copy_n(src.row(cy + y) + cx, cw, crop.pixels.begin() + (size_t)y * cw);
	}
	src = HdFrame();
	HdFrame fit;
	HdSprites::resample(crop, W, H, fit);
	crop = HdFrame();
	const Uint32 tFit = SDL_GetTicks();
	if ((int)fit.pixels.size() != W * H)
	{
		failed[theme] = true;
		return nullptr;
	}
	size_t bytes = (size_t)W * H * 12;
	for (const Prepared &q : prepared) bytes += (size_t)q.w * q.h * 12;
	while (!prepared.empty() && bytes > PREPARED_BYTES)
	{
		bytes -= (size_t)prepared.back().w * prepared.back().h * 12;
		prepared.pop_back();
	}
	prepared.emplace_front();
	Prepared &p = prepared.front();
	p.theme = theme; p.w = W; p.h = H; p.k = k;
	p.sharp.resize((size_t)W * H);
	// the picture is a backdrop: its own colours a little muted, its light well below the text's, darker
	// to the corners and in the frame's shadow along the edge
	const float edgeFall = 2.5f * k;
	bands(H, [&](int a, int b)
	{
		for (int y = a; y < b; ++y)
		{
			const float vy = (y - H * 0.5f) / (H * 0.5f);
			for (int x = 0; x < W; ++x)
			{
				const Uint32 c = fit.pixels[(size_t)y * W + x];
				float r = (float)((c >> 16) & 0xFF), g = (float)((c >> 8) & 0xFF), bl = (float)(c & 0xFF);
				const float l = lum(r, g, bl);
				const float vx = (x - W * 0.5f) / (W * 0.5f);
				const float e = (float)std::min(std::min(x, W - 1 - x), std::min(y, H - 1 - y));
				const float vr = std::sqrt(vx * vx + vy * vy);
				const float f = 0.72f * (1.0f - 0.55f * std::exp(-e / edgeFall)) * (1.0f - 0.35f * std::min(std::max(vr - 0.55f, 0.0f), 1.0f) / 0.9f);
				r = (l + (r - l) * 0.7f) * f;
				g = (l + (g - l) * 0.7f) * f;
				bl = (l + (bl - l) * 0.7f) * f;
				p.sharp[(size_t)y * W + x] = pack(r, g, bl);
			}
		}
	});
	// frosted: blurred about a base pixel and a quarter, and darker by two fifths
	p.frosted = p.sharp;
	blur(p.frosted, W, H, std::max(1, k));
	bands(H, [&](int a, int b)
	{
		for (size_t i = (size_t)a * W; i < (size_t)b * W; ++i)
		{
			const Uint32 c = p.frosted[i];
			p.frosted[i] = pack(((c >> 16) & 0xFF) * 0.6f, ((c >> 8) & 0xFF) * 0.6f, (c & 0xFF) * 0.6f);
		}
	});
	Log(LOG_INFO) << "HD screens: " << pictures[theme] << " prepared at " << W << "x" << H << " in " << (SDL_GetTicks() - t0) << " ms (read " << (tLoad - t0) << ", fit " << (tFit - tLoad) << ")";
	return &p;
}

/// The frost mask of a window of w x h base pixels at base (x, y) from its text of the last frame.
const Veil &veilOf(const void *owner, int x, int y, int w, int h)
{
	static const std::vector<SDL_Rect> none;
	const std::vector<SDL_Rect> *rects = HdUi::instance().backdropText(owner);
	if (!rects) rects = &none;
	Uint64 hash = 1469598103934665603ULL;
	auto fold = [&](int v) { hash = (hash ^ (Uint64)(Uint32)v) * 1099511628211ULL; };
	fold(x); fold(y); fold(w); fold(h);
	for (const SDL_Rect &r : *rects) { fold(r.x); fold(r.y); fold(r.w); fold(r.h); }
	if (veils.size() > 32 && veils.find(owner) == veils.end())
	{
		veils.clear();
	}
	Veil &v = veils[owner];
	if (v.hash == hash && v.w == w && v.h == h)
	{
		return v;
	}
	v.hash = hash;
	v.w = w;
	v.h = h;
	v.m.assign((size_t)w * h, 0.0f);
	// each line with a margin of two base pixels, softened over three more
	const int PAD = 2;
	for (const SDL_Rect &r : *rects)
	{
		const int x0 = std::max(r.x - x - PAD, 0), x1 = std::min(r.x - x + r.w + PAD, w);
		const int y0 = std::max(r.y - y - PAD, 0), y1 = std::min(r.y - y + r.h + PAD, h);
		for (int yy = y0; yy < y1; ++yy)
		{
			std::fill(v.m.begin() + (size_t)yy * w + x0, v.m.begin() + (size_t)yy * w + std::max(x0, x1), 1.0f);
		}
	}
	blurMask(v.m, w, h, 2);
	for (float &m : v.m) m = std::min(m * 1.6f, 1.0f);
	return v;
}

}

void load()
{
	pictures.clear();
	themeOf.clear();
	lines.clear();
	shown.clear();
	failed.clear();
	clearCaches();
	const std::string list = HdSprites::artPath(std::string(FOLDER) + "/screens.txt");
	if (!FileMap::fileExists(list))
	{
		return;
	}
	SDL_RWops *rw = FileMap::getRWops(list);
	if (!rw)
	{
		return;
	}
	size_t size = 0;
	void *data = SDL_LoadFile_RW(rw, &size, SDL_TRUE);
	if (!data)
	{
		return;
	}
	std::istringstream in(std::string((const char*)data, size));
	SDL_free(data);
	std::string line;
	int screens = 0;
	while (std::getline(in, line))
	{
		const size_t hash = line.find('#');
		if (hash != std::string::npos) line.erase(hash);
		const size_t eq = line.find('=');
		if (eq == std::string::npos) continue;
		std::istringstream left(line.substr(0, eq)), right(line.substr(eq + 1));
		std::string file, name;
		// several pictures on the left (hidden.png hidden_jungle.png ... = ...): the screens change between them
		std::vector<int> group;
		while (left >> file)
		{
			// the BOM a UTF-8 editor puts in front of the first line
			if (file.size() >= 3 && (unsigned char)file[0] == 0xEF && (unsigned char)file[1] == 0xBB && (unsigned char)file[2] == 0xBF) file.erase(0, 3);
			const std::string path = HdSprites::artPath(std::string(FOLDER) + "/" + file);
			int width, height;
			if (!HdSprites::pngSize(path, width, height))
			{
				Log(LOG_WARNING) << "HD screens: " << path << " is not a PNG";
				continue;
			}
			group.push_back((int)pictures.size());
			pictures.push_back(path);
			failed.push_back(false);
		}
		if (group.empty()) continue;
		const int theme = (int)lines.size();
		lines.push_back(group);
		shown.push_back(0);
		while (right >> name)
		{
			themeOf[name] = theme;
			++screens;
		}
	}
	if (!pictures.empty())
	{
		Log(LOG_INFO) << "HD screens: " << pictures.size() << " theme picture(s) for " << screens << " screen(s)";
	}
}

bool has(const std::string &interfaceName)
{
	return Options::oxceHdPictures && !interfaceName.empty() && themeOf.find(interfaceName) != themeOf.end();
}

void nextVariant(const std::string &interfaceName)
{
	auto it = themeOf.find(interfaceName);
	if (it == themeOf.end() || lines[it->second].size() < 2)
	{
		return;
	}
	// not the game's RNG: which picture shows must not touch the battle's random numbers
	static std::minstd_rand pick(SDL_GetTicks() + 1);
	const size_t n = lines[it->second].size();
	size_t &now = shown[it->second];
	now = (now + 1 + pick() % (n - 1)) % n;     // any other picture of the line, never the same twice in a row
}

bool metalFrames()
{
	return Options::oxceHdPictures && !pictures.empty() && HdUi::skin();
}

bool drawBackdrop(const void *owner, const std::string &interfaceName, int x, int y, int w, int h)
{
	const int k = HdUi::scale();
	if (k <= 0 || w <= 0 || h <= 0 || !has(interfaceName))
	{
		return false;
	}
	const int line = themeOf[interfaceName];
	Prepared *p = const_cast<Prepared*>(prepare(lines[line][shown[line] % lines[line].size()], w * k, h * k, k));
	if (!p)
	{
		return false;
	}
	const Veil &v = veilOf(owner, x, y, w, h);
	const int W = p->w, H = p->h;
	if (p->composed.empty() || p->veil != v.hash)
	{
		// the text moved (a list scrolled, a screen opened): the picture mixed with its frosted copy anew
		p->composed.resize((size_t)W * H);
		p->veil = v.hash;
		const float inv = 1.0f / k;
		bands(H, [&](int a, int b)
		{
			for (int ly = a; ly < b; ++ly)
			{
				// the mask between the base cells: bilinear at the world pixel's centre
				const float my = std::min(std::max((ly + 0.5f) * inv - 0.5f, 0.0f), (float)(v.h - 1));
				const int my0 = (int)my, my1 = std::min(my0 + 1, v.h - 1);
				const float fy = my - my0;
				const float *m0 = v.m.data() + (size_t)my0 * v.w, *m1 = v.m.data() + (size_t)my1 * v.w;
				const Uint32 *sharp = p->sharp.data() + (size_t)ly * W, *frost = p->frosted.data() + (size_t)ly * W;
				Uint32 *out = p->composed.data() + (size_t)ly * W;
				for (int lx = 0; lx < W; ++lx)
				{
					const float mx = std::min(std::max((lx + 0.5f) * inv - 0.5f, 0.0f), (float)(v.w - 1));
					const int mx0 = (int)mx, mx1 = std::min(mx0 + 1, v.w - 1);
					const float fx = mx - mx0;
					const float m = (m0[mx0] * (1 - fx) + m0[mx1] * fx) * (1 - fy) + (m1[mx0] * (1 - fx) + m1[mx1] * fx) * fy;
					const Uint32 ca = sharp[lx];
					if (m <= 0.002f)
					{
						out[lx] = ca;
						continue;
					}
					const Uint32 cb = frost[lx];
					const int t = (int)(m * 256.0f);
					auto ch = [&](int sh) { const int va = (ca >> sh) & 0xFF, vb = (cb >> sh) & 0xFF; return (Uint32)(va + (((vb - va) * t) >> 8)) << sh; };
					out[lx] = 0xFF000000u | ch(16) | ch(8) | ch(0);
				}
			}
		});
	}
	// opaque: a plain copy of the rows under the clip
	const int X = x * k, Y = y * k;
	const Uint32 *src = p->composed.data();
	HdUi::instance().copyRows(X, Y, W, H, src, W);
	return true;
}

void drawFrame(int x, int y, int w, int h, int inset, bool thin, Uint32 accent)
{
	HdUi &ui = HdUi::instance();
	const int k = HdUi::scale();
	if (k <= 0 || w <= 0 || h <= 0 || inset <= 0)
	{
		return;
	}
	// what lies inside is a window: its labels keep the classic shadow (as drawPanelFrame says)
	ui.notePanel(x, y, w, h);
	const int W = w * k, H = h * k, B = std::min(inset * k, std::min(W, H) / 2);
	const int metal = HdBattleHud::themeKey();
	Frame *f = nullptr;
	for (auto it = frames.begin(); it != frames.end(); ++it)
	{
		if (it->w == W && it->h == H && it->k == k && it->inset == B && it->thin == thin && it->accent == accent && it->metal == metal)
		{
			frames.splice(frames.begin(), frames, it);
			f = &frames.front();
			break;
		}
	}
	if (!f)
	{
		if (frames.size() >= FRAMES_MAX)
		{
			frames.pop_back();
		}
		frames.emplace_front();
		f = &frames.front();
		f->w = W; f->h = H; f->k = k; f->inset = B; f->thin = thin; f->accent = accent; f->metal = metal;
		const float band = (float)B, round = 1.25f * k, bevel = 1.1f * k, relief = 1.5f * k;
		// rivets along the middle of the band every 14 base pixels (none on a thin frame)
		const bool rivets = !thin && B >= 3 * k;
		const float rivetR = 0.85f * k, pitch = 14.0f * k, mid = band * 0.5f;
		// the moulding's height: rising over `bevel` from either edge of the band, the rivets' domes on it
		auto height = [&](float px, float py) -> float
		{
			const float dx = std::min(px, W - px), dy = std::min(py, H - py);
			float d = std::min(dx, dy);
			if (dx < round && dy < round)
			{
				const float ax = round - dx, ay = round - dy;
				d = round - std::sqrt(ax * ax + ay * ay);
			}
			const float t = std::min(std::max(d, 0.0f), band);
			float hgt = std::sqrt(std::min(std::min(t / bevel, 1.0f), std::min((band - t) / bevel, 1.0f))) * relief;
			if (rivets)
			{
				// the nearest rivet: on the band's middle line, every `pitch` from 40 base pixels... and the corners
				auto dome = [&](float u, float v) { const float dd = u * u + v * v; return dd < rivetR * rivetR ? std::sqrt(rivetR * rivetR - dd) * 1.3f : 0.0f; };
				float best = 0.0f;
				if (dy < band && dx >= mid - rivetR)
				{
					const float along = px - mid;
					const float n = std::round(along / pitch);
					best = std::max(best, dome(along - n * pitch, dy - mid));
				}
				if (dx < band && dy >= mid - rivetR)
				{
					const float along = py - mid;
					const float n = std::round(along / pitch);
					best = std::max(best, dome(dx - mid, along - n * pitch));
				}
				hgt += best;
			}
			return hgt;
		};
		// the light from the top left, a little in front; the metal's shades are the battle panel's (HdBattleHud)
		const float lx = -0.6f, ly = -0.8f, lz = 0.9f, ll = std::sqrt(lx * lx + ly * ly + lz * lz);
		const float hx = lx / ll, hy = ly / ll, hz = lz / ll + 1.0f, hl = std::sqrt(hx * hx + hy * hy + hz * hz);
		const Uint32 line = HdUi::mixed(accent | 0xFF000000u, 0xFFFFFFFFu, 0.2f);
		const float lineW = std::max(1.0f, 0.5f * k);
		auto shade = [&](int px, int py) -> Uint32
		{
			const float cx = px + 0.5f, cy = py + 0.5f;
			const float dx = std::min(cx, W - cx), dy = std::min(cy, H - cy);
			float d = std::min(dx, dy);
			if (dx < round && dy < round)
			{
				const float ax = round - dx, ay = round - dy;
				d = round - std::sqrt(ax * ax + ay * ay);
			}
			const float cover = std::min(std::max(d + 0.5f, 0.0f), 1.0f) * std::min(std::max(band - d + 0.5f, 0.0f), 1.0f);
			if (cover <= 0.0f) return 0u;
			const float gx = (height(cx + 1, cy) - height(cx - 1, cy)) * 0.5f, gy = (height(cx, cy + 1) - height(cx, cy - 1)) * 0.5f;
			const float nl = std::sqrt(gx * gx + gy * gy + 1.0f);
			const float nx = -gx / nl, ny = -gy / nl, nz = 1.0f / nl;
			const float diff = std::max((nx * lx + ny * ly + nz * lz) / ll, 0.0f);
			const float spec = std::pow(std::max((nx * hx + ny * hy + nz * hz) / hl, 0.0f), 28.0f);
			// brushed along the band: a faint grain that runs with the edge it lies on
			const int along = dy < dx ? px : py, across = dy < dx ? py : px;
			const Uint32 seed = (Uint32)(across / std::max(1, k / 2)) * 2654435761u ^ (Uint32)(along / (6 * k)) * 40503u;
			const float grain = ((seed >> 8) & 0xFF) / 255.0f - 0.5f;
			Uint32 c = HdBattleHud::metalShade(0.12f + 0.62f * diff + 0.05f * grain);
			c = HdUi::mixed(c, 0xFFFFFFF0u, std::min(spec * 0.55f, 1.0f));
			// the thin line in the screen's colour along the inner edge
			const float li = band - d - 0.25f * k;
			if (li >= 0.0f && li < lineW) c = HdUi::mixed(c, line, 0.85f);
			return (c & 0x00FFFFFFu) | ((Uint32)(cover * 255.0f + 0.5f) << 24);
		};
		auto strip = [&](std::vector<Uint32> &out, int sx, int sy, int sw, int sh)
		{
			out.assign((size_t)std::max(sw, 0) * std::max(sh, 0), 0u);
			if (sw <= 0 || sh <= 0) return;
			bands(sh, [&](int a, int b)
			{
				for (int yy = a; yy < b; ++yy)
					for (int xx = 0; xx < sw; ++xx)
						out[(size_t)yy * sw + xx] = shade(sx + xx, sy + yy);
			});
		};
		strip(f->top, 0, 0, W, B);
		strip(f->bottom, 0, H - B, W, B);
		strip(f->left, 0, B, B, H - 2 * B);
		strip(f->right, W - B, B, B, H - 2 * B);
	}
	const int X = x * k, Y = y * k;
	ui.drawImage(f->top.data(), W, B, X, Y);
	ui.drawImage(f->bottom.data(), W, B, X, Y + H - B);
	if (H > 2 * B)
	{
		ui.drawImage(f->left.data(), B, H - 2 * B, X, Y + B);
		ui.drawImage(f->right.data(), B, H - 2 * B, X + W - B, Y + B);
	}
}

void clearCaches()
{
	prepared.clear();
	veils.clear();
	frames.clear();
}

}

}
