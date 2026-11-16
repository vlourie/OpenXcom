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
#include "HdPlateCanvas.h"
#include <algorithm>
#include <cmath>
#include "HdUi.h"
#include "Surface.h"
#include "Unicode.h"
#include "../Interface/Text.h"

namespace OpenXcom
{

Uint32 PlateCanvas::mix(Uint32 a, Uint32 b, float t)
{
	const auto ch = [&](int shift)
	{
		const float x = (float)((a >> shift) & 0xFF);
		const float y = (float)((b >> shift) & 0xFF);
		return (Uint32)std::max(0.0f, std::min(255.0f, x + (y - x) * t + 0.5f));
	};
	return (a & 0xFF000000u) | (ch(16) << 16) | (ch(8) << 8) | ch(0);
}

void PlateCanvas::note(float x, float y, Uint32 argb, float s)
{
	fill(x + 4.5f * s, y, 1.0f * s, 8.0f * s, argb);
	triangle(x + 5.5f * s, y, x + 8.0f * s, y + 2.5f * s, x + 5.5f * s, y + 4.5f * s, argb);
	const float cx = x + 2.75f * s, cy = y + 8.0f * s;
	const float px[6] = { 0.0f, 1.5f, 4.0f, 5.5f, 4.0f, 1.5f };
	const float py[6] = { 8.0f, 6.0f, 6.0f, 8.0f, 10.0f, 10.0f };
	for (int i = 0; i < 6; ++i)
	{
		const int j = (i + 1) % 6;
		triangle(cx, cy, x + px[i] * s, y + py[i] * s, x + px[j] * s, y + py[j] * s, argb);
	}
}

// ---- the classic canvas ----

ClassicPlateCanvas::ClassicPlateCanvas(Surface *surface, Font *big, Font *small, Language *lang) : _surface(surface), _palette(0)
{
	_small = new Text(700, 18, 0, 0);
	_big = new Text(700, 20, 0, 0);
	for (Text *t : { _small, _big })
	{
		t->initText(big, small, lang);
		t->setColor(1);
		t->setWordWrap(false);
	}
	_small->setSmall();
	_big->setBig();
	_clip = SDL_Rect{ 0, 0, 0, 0 };
}

ClassicPlateCanvas::~ClassicPlateCanvas()
{
	delete _small;
	delete _big;
}

void ClassicPlateCanvas::begin()
{
	if (_palette != _surface->getPalette())
	{
		_palette = _surface->getPalette();
		_index.clear();
	}
	unclip();
}

Uint8 ClassicPlateCanvas::nearest(Uint32 argb)
{
	const Uint32 key = argb & 0x00FFFFFFu;
	const auto found = _index.find(key);
	if (found != _index.end())
	{
		return found->second;
	}
	Uint8 best = 1;
	if (_palette)
	{
		const int r = (key >> 16) & 0xFF, g = (key >> 8) & 0xFF, b = key & 0xFF;
		int bestD = 1 << 30;
		for (int i = 1; i < 256; ++i)
		{
			const int dr = _palette[i].r - r, dg = _palette[i].g - g, db = _palette[i].b - b;
			const int d = dr * dr * 3 + dg * dg * 4 + db * db * 2;
			if (d < bestD)
			{
				bestD = d;
				best = (Uint8)i;
			}
		}
	}
	_index[key] = best;
	return best;
}

void ClassicPlateCanvas::span(int x0, int x1, int y, Uint8 index)
{
	if (y < _clip.y || y >= _clip.y + _clip.h)
	{
		return;
	}
	x0 = std::max(x0, (int)_clip.x);
	x1 = std::min(x1, _clip.x + _clip.w);
	if (x1 <= x0)
	{
		return;
	}
	SDL_Surface *s = _surface->getSurface();
	memset((Uint8*)s->pixels + y * s->pitch + x0, index, x1 - x0);
}

void ClassicPlateCanvas::fill(float x, float y, float w, float h, Uint32 argb)
{
	if ((argb >> 24) == 0)
	{
		return;
	}
	const Uint8 index = nearest(argb);
	const int x0 = (int)std::floor(x + 0.5f), x1 = (int)std::floor(x + w + 0.5f);
	const int y0 = (int)std::floor(y + 0.5f), y1 = (int)std::floor(y + h + 0.5f);
	for (int row = y0; row < y1; ++row)
	{
		span(x0, x1, row, index);
	}
}

void ClassicPlateCanvas::gradient(float x, float y, float w, float h, Uint32 top, Uint32 bottom)
{
	const float half = std::floor(h / 2.0f);
	fill(x, y, w, half, mix(top, bottom, 0.25f));
	fill(x, y + half, w, h - half, mix(top, bottom, 0.75f));
}

void ClassicPlateCanvas::triangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 argb)
{
	if ((argb >> 24) == 0)
	{
		return;
	}
	const Uint8 index = nearest(argb);
	const float px[3] = { ax, bx, cx }, py[3] = { ay, by, cy };
	const int y0 = (int)std::floor(std::min(ay, std::min(by, cy)));
	const int y1 = (int)std::ceil(std::max(ay, std::max(by, cy)));
	for (int row = y0; row < y1; ++row)
	{
		const float yc = row + 0.5f;
		float xs[3];
		int n = 0;
		for (int i = 0; i < 3; ++i)
		{
			const int j = (i + 1) % 3;
			if ((py[i] <= yc && yc < py[j]) || (py[j] <= yc && yc < py[i]))
			{
				xs[n++] = px[i] + (yc - py[i]) * (px[j] - px[i]) / (py[j] - py[i]);
			}
		}
		if (n >= 2)
		{
			const float l = std::min(xs[0], xs[1]), r = std::max(xs[0], xs[1]);
			span((int)std::floor(l + 0.5f), (int)std::floor(r + 0.5f), row, index);
		}
	}
}

void ClassicPlateCanvas::text(const std::string &s, float x, float y, Uint32 argb, bool big)
{
	if (s.empty() || (argb >> 24) == 0)
	{
		return;
	}
	Text *t = big ? _big : _small;
	t->setText(s);
	t->draw();
	const Uint8 index = nearest(argb);
	SDL_Surface *src = t->getSurface();
	SDL_Surface *dst = _surface->getSurface();
	const int ox = (int)std::floor(x + 0.5f), oy = (int)std::floor(y + 0.5f);
	const int tw = std::min(src->w, t->getTextWidth() + 2);
	for (int sy = 0; sy < src->h; ++sy)
	{
		const int dy = oy + sy;
		if (dy < _clip.y || dy >= _clip.y + _clip.h)
		{
			continue;
		}
		const Uint8 *row = (const Uint8*)src->pixels + sy * src->pitch;
		for (int sx = 0; sx < tw; ++sx)
		{
			const int dx = ox + sx;
			if (row[sx] && dx >= _clip.x && dx < _clip.x + _clip.w)
			{
				// only the letter: with setColor(1) a pixel is 1 + shade, shades 1-3 are the letter and
				// 4-5 its dark outline; one flat colour over the outline too ran the letters together
				// (Vitali 16.11, variant A of the player page)
				if (row[sx] - 1 < 4)
				{
					*((Uint8*)dst->pixels + dy * dst->pitch + dx) = index;
				}
			}
		}
	}
}

float ClassicPlateCanvas::textWidth(const std::string &s, bool big)
{
	Text *t = big ? _big : _small;
	t->setText(s);
	return (float)t->getTextWidth();
}

void ClassicPlateCanvas::clip(float x, float y, float w, float h)
{
	SDL_Surface *s = _surface->getSurface();
	const int x0 = std::max(0, (int)std::floor(x + 0.5f)), y0 = std::max(0, (int)std::floor(y + 0.5f));
	const int x1 = std::min(s->w, (int)std::floor(x + w + 0.5f)), y1 = std::min(s->h, (int)std::floor(y + h + 0.5f));
	_clip = SDL_Rect{ (Sint16)x0, (Sint16)y0, (Uint16)std::max(0, x1 - x0), (Uint16)std::max(0, y1 - y0) };
}

void ClassicPlateCanvas::unclip()
{
	SDL_Surface *s = _surface->getSurface();
	_clip = SDL_Rect{ 0, 0, (Uint16)s->w, (Uint16)s->h };
}

// ---- the HD canvas ----

HdPlateCanvas::HdPlateCanvas(float ox, float oy, Font *big, Font *small) : _ox(ox), _oy(oy), _small(small), _big(big)
{
}

float HdPlateCanvas::cap(bool big)
{
	return HdUi::instance().metrics(big ? _big : _small).cap;
}

void HdPlateCanvas::fill(float x, float y, float w, float h, Uint32 argb)
{
	const float k = (float)HdUi::scale();
	HdUi::instance().fillRoundRect((_ox + x) * k, (_oy + y) * k, (_ox + x + w) * k, (_oy + y + h) * k, 0.0f, argb, argb);
}

void HdPlateCanvas::gradient(float x, float y, float w, float h, Uint32 top, Uint32 bottom)
{
	const float k = (float)HdUi::scale();
	HdUi::instance().fillRoundRect((_ox + x) * k, (_oy + y) * k, (_ox + x + w) * k, (_oy + y + h) * k, 0.0f, top, bottom);
}

void HdPlateCanvas::triangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 argb)
{
	const float k = (float)HdUi::scale();
	HdUi::instance().fillTriangle((_ox + ax) * k, (_oy + ay) * k, (_ox + bx) * k, (_oy + by) * k, (_ox + cx) * k, (_oy + cy) * k, argb);
}

void HdPlateCanvas::text(const std::string &s, float x, float y, Uint32 argb, bool big)
{
	if (s.empty())
	{
		return;
	}
	HdUi::instance().drawTtfString(Unicode::convUtf8ToUtf32(s), big, cap(big), (int)std::floor(_ox + x + 0.5f), (int)std::floor(_oy + y + 0.5f), argb, 0);
}

float HdPlateCanvas::textWidth(const std::string &s, bool big)
{
	return HdUi::instance().ttfWidth(Unicode::convUtf8ToUtf32(s), big, cap(big));
}

void HdPlateCanvas::clip(float x, float y, float w, float h)
{
	HdUi::instance().setClip((int)std::floor(_ox + x + 0.5f), (int)std::floor(_oy + y + 0.5f), (int)std::floor(w + 0.5f), (int)std::floor(h + 0.5f));
}

void HdPlateCanvas::unclip()
{
	HdUi::instance().clearClip();
}

}
