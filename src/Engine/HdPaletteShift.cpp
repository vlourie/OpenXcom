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
#include "HdPaletteShift.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <string>
#include <unordered_set>
#include <utility>
#include "HdSprites.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "Surface.h"
#include "SurfaceSet.h"

namespace OpenXcom
{

namespace HdPaletteShift
{

namespace
{
	/// The tables: n^3 cells, centres at (j + 0.5) * 256 / n, [r][g][b][channel].
	const int TN = 64;
	/// The colour grid of the samples (BR): 32^3 cells of 8, channels dR dG dB weight.
	const int GN = 32;
	const double GCELL = 256.0 / GN;
	/// M1t: the kernel over the palette entries, in colour units.
	const double LUT_SIGMA = 12.0;
	/// BR: the blur of the grid, in cells (10 colour units), and the weight of M1t where samples are few.
	const double BLUR_SIGMA = 10.0 / GCELL;
	const int BLUR_RADIUS = 4;
	const double TAU = 1.0;

	std::vector<float> lut;   ///< M1t: everything but the terrain
	std::vector<float> table; ///< BR blended into M1t: the terrain
	std::unordered_set<const void*> terrainKeys;
	bool on = false;
	std::atomic<unsigned> recolouredTerrain(0), recolouredOther(0);

	inline size_t cellOf(int r, int g, int b) { return (((size_t)r * TN + g) * TN + b) * 3; }

	/// Trilinear read of a 64^3 table at a colour (the cell centres; clamped at the edges).
	inline void readTable(const float *t, float r, float g, float b, float out[3])
	{
		const float cell = 256.0f / TN;
		float x[3] = { r / cell - 0.5f, g / cell - 0.5f, b / cell - 0.5f };
		int i0[3];
		float f[3];
		for (int a = 0; a < 3; ++a)
		{
			x[a] = std::min(std::max(x[a], 0.0f), (float)(TN - 1));
			i0[a] = std::min((int)std::floor(x[a]), TN - 2);
			f[a] = x[a] - i0[a];
		}
		out[0] = out[1] = out[2] = 0.0f;
		for (int dz = 0; dz < 2; ++dz)
		{
			const float wz = dz ? f[0] : 1.0f - f[0];
			for (int dy = 0; dy < 2; ++dy)
			{
				const float wy = wz * (dy ? f[1] : 1.0f - f[1]);
				for (int dx = 0; dx < 2; ++dx)
				{
					const float w = wy * (dx ? f[2] : 1.0f - f[2]);
					const float *c = t + cellOf(i0[0] + dz, i0[1] + dy, i0[2] + dx);
					out[0] += w * c[0];
					out[1] += w * c[1];
					out[2] += w * c[2];
				}
			}
		}
	}

	/// Recolours a picture through a table (the alpha is kept; any thread).
	void apply(const float *t, HdFrame &frame)
	{
		for (Uint32 &p : frame.pixels)
		{
			const Uint32 a = p >> 24;
			if (a == 0)
			{
				continue;
			}
			const float c[3] = { (float)((p >> 16) & 0xFF), (float)((p >> 8) & 0xFF), (float)(p & 0xFF) };
			float d[3];
			readTable(t, c[0], c[1], c[2], d);
			Uint32 o[3];
			for (int k = 0; k < 3; ++k)
			{
				const long v = std::lrint(c[k] + d[k]); // round half to even, as numpy
				o[k] = (Uint32)std::min(255L, std::max(0L, v));
			}
			p = (a << 24) | (o[0] << 16) | (o[1] << 8) | o[2];
		}
	}

	/// HdSprites::Recolour: the terrain through BR, everything else through M1t.
	void recolour(const void *key, HdFrame &frame)
	{
		if (terrainKeys.count(key))
		{
			apply(table.data(), frame);
			++recolouredTerrain;
		}
		else
		{
			apply(lut.data(), frame);
			++recolouredOther;
		}
	}

	/// M1t: the kernel-weighted mean shift P - B of the palette entries 1..255 near each cell centre.
	void buildLut(const SDL_Color *shown, const SDL_Color *base)
	{
		lut.assign((size_t)TN * TN * TN * 3, 0.0f);
		double src[255][3], d[255][3];
		for (int i = 1; i < 256; ++i)
		{
			src[i - 1][0] = base[i].r; src[i - 1][1] = base[i].g; src[i - 1][2] = base[i].b;
			d[i - 1][0] = (double)shown[i].r - base[i].r;
			d[i - 1][1] = (double)shown[i].g - base[i].g;
			d[i - 1][2] = (double)shown[i].b - base[i].b;
		}
		const double cell = 256.0 / TN;
		HdWorkers::instance().run(TN, [&](int r)
		{
			double d2[255];
			for (int g = 0; g < TN; ++g)
			{
				for (int b = 0; b < TN; ++b)
				{
					const double q[3] = { (r + 0.5) * cell, (g + 0.5) * cell, (b + 0.5) * cell };
					double lo = 1e300;
					for (int i = 0; i < 255; ++i)
					{
						const double x = q[0] - src[i][0], y = q[1] - src[i][1], z = q[2] - src[i][2];
						d2[i] = x * x + y * y + z * z;
						lo = std::min(lo, d2[i]);
					}
					double sw = 0, s[3] = { 0, 0, 0 };
					for (int i = 0; i < 255; ++i)
					{
						const double w = std::exp(-(d2[i] - lo) / (2 * LUT_SIGMA * LUT_SIGMA));
						sw += w;
						s[0] += w * d[i][0];
						s[1] += w * d[i][1];
						s[2] += w * d[i][2];
					}
					float *out = &lut[cellOf(r, g, b)];
					out[0] = (float)(s[0] / sw);
					out[1] = (float)(s[1] / sw);
					out[2] = (float)(s[2] / sw);
				}
			}
		});
	}

	/// One BR sample: the mean colour of a block of a picture and the classic index under it.
	struct Sample
	{
		float c[3];
		Uint8 index;
	};

	/// The samples of one picture: k x k blocks at least half opaque over a visible classic pixel.
	void samplesOf(const Surface &classic, const HdFrame &picture, std::vector<Sample> &out)
	{
		const int k = classic.getWidth() / 32;
		if (k < 1 || picture.width != classic.getWidth() || picture.height != classic.getHeight())
		{
			return;
		}
		const int wb = picture.width / k, hb = picture.height / k;
		for (int by = 0; by < hb; ++by)
		{
			for (int bx = 0; bx < wb; ++bx)
			{
				const Uint8 index = classic.getPixel(bx * k, by * k);
				if (index == 0)
				{
					continue;
				}
				int cnt = 0;
				double s[3] = { 0, 0, 0 };
				for (int y = by * k; y < by * k + k; ++y)
				{
					const Uint32 *row = picture.row(y);
					for (int x = bx * k; x < bx * k + k; ++x)
					{
						const Uint32 p = row[x];
						if ((p >> 24) == 0)
						{
							continue;
						}
						++cnt;
						s[0] += (p >> 16) & 0xFF;
						s[1] += (p >> 8) & 0xFF;
						s[2] += p & 0xFF;
					}
				}
				if (2 * cnt < k * k)
				{
					continue;
				}
				out.push_back(Sample{ { (float)(s[0] / cnt), (float)(s[1] / cnt), (float)(s[2] / cnt) }, index });
			}
		}
	}

	/// Pictures hashed for the dump (FNV-1a 64 over the pixels as 0xAARRGGBB, little end first).
	unsigned long long fnv(const HdFrame &picture)
	{
		unsigned long long h = 1469598103934665603ULL;
		for (Uint32 p : picture.pixels)
		{
			for (int k = 0; k < 4; ++k)
			{
				h ^= (p >> (8 * k)) & 0xFF;
				h *= 1099511628211ULL;
			}
		}
		return h;
	}

	void writeFile(const std::string &path, const void *data, size_t bytes)
	{
		FILE *f = fopen(path.c_str(), "wb");
		if (f)
		{
			fwrite(data, 1, bytes, f);
			fclose(f);
		}
	}
}

void install(const SDL_Color *shown, const SDL_Color *base, const std::vector<const SurfaceSet*> &terrain)
{
	if (on)
	{
		remove();
	}
	const auto t0 = std::chrono::steady_clock::now();
	auto ms = [](std::chrono::steady_clock::time_point a, std::chrono::steady_clock::time_point b)
	{
		return (int)(std::chrono::duration<double, std::milli>(b - a).count() + 0.5);
	};
	buildLut(shown, base);
	const auto t1 = std::chrono::steady_clock::now();

	// the samples of every picture of the terrain, kept by place: the sum below goes in a fixed order
	const char *dumpDir = getenv("OXCE_HD_PALSHIFT_DUMP");
	const bool dump = dumpDir && *dumpDir;
	std::vector<std::pair<size_t, std::vector<Sample>>> byPlace;
	std::vector<std::pair<size_t, std::string>> placeLines;
	std::mutex lock;
	const size_t pictures = HdSprites::scanPictures(terrain, [&](size_t place, const Surface &classic, const HdFrame &picture)
	{
		std::vector<Sample> samples;
		samplesOf(classic, picture, samples);
		std::string line;
		if (dump)
		{
			char buf[96];
			snprintf(buf, sizeof(buf), "%zu\t%d\t%d\t%016llx\t%zu", place, picture.width, picture.height, fnv(picture), samples.size());
			line = buf;
		}
		std::lock_guard<std::mutex> guard(lock);
		byPlace.emplace_back(place, std::move(samples));
		if (dump)
		{
			placeLines.emplace_back(place, std::move(line));
		}
	});
	std::sort(byPlace.begin(), byPlace.end(), [](const std::pair<size_t, std::vector<Sample>> &a, const std::pair<size_t, std::vector<Sample>> &b) { return a.first < b.first; });
	const auto t2 = std::chrono::steady_clock::now();

	// splat into the 32^3 grid: dR dG dB of the classic shift and the weight
	std::vector<double> grid((size_t)GN * GN * GN * 4, 0.0);
	size_t samples = 0;
	for (const auto &pair : byPlace)
	{
		for (const Sample &s : pair.second)
		{
			const double v[4] = { (double)shown[s.index].r - base[s.index].r, (double)shown[s.index].g - base[s.index].g,
				(double)shown[s.index].b - base[s.index].b, 1.0 };
			int g0[3];
			double f[3];
			for (int a = 0; a < 3; ++a)
			{
				const double g = s.c[a] / GCELL - 0.5;
				g0[a] = (int)std::floor(g);
				f[a] = g - g0[a];
			}
			for (int dz = 0; dz < 2; ++dz)
			{
				const double wz = dz ? f[0] : 1.0 - f[0];
				const int iz = std::min(std::max(g0[0] + dz, 0), GN - 1);
				for (int dy = 0; dy < 2; ++dy)
				{
					const double wy = wz * (dy ? f[1] : 1.0 - f[1]);
					const int iy = std::min(std::max(g0[1] + dy, 0), GN - 1);
					for (int dx = 0; dx < 2; ++dx)
					{
						const double w = wy * (dx ? f[2] : 1.0 - f[2]);
						const int ix = std::min(std::max(g0[2] + dx, 0), GN - 1);
						double *c = &grid[(((size_t)iz * GN + iy) * GN + ix) * 4];
						for (int k = 0; k < 4; ++k)
						{
							c[k] += w * v[k];
						}
					}
				}
			}
			++samples;
		}
	}
	// separable Gaussian blur, zeros beyond the edges, then in "samples at the centre"
	{
		double kernel[2 * BLUR_RADIUS + 1], ksum = 0;
		for (int t = -BLUR_RADIUS; t <= BLUR_RADIUS; ++t)
		{
			kernel[t + BLUR_RADIUS] = std::exp(-(double)t * t / (2 * BLUR_SIGMA * BLUR_SIGMA));
			ksum += kernel[t + BLUR_RADIUS];
		}
		for (double &k : kernel)
		{
			k /= ksum;
		}
		const size_t stride[3] = { (size_t)GN * GN * 4, (size_t)GN * 4, 4 };
		std::vector<double> next(grid.size());
		for (int axis = 0; axis < 3; ++axis)
		{
			std::fill(next.begin(), next.end(), 0.0);
			for (int z = 0; z < GN; ++z)
			{
				for (int y = 0; y < GN; ++y)
				{
					for (int x = 0; x < GN; ++x)
					{
						const int pos[3] = { z, y, x };
						const size_t at = z * stride[0] + y * stride[1] + x * stride[2];
						for (int t = -BLUR_RADIUS; t <= BLUR_RADIUS; ++t)
						{
							const int j = pos[axis] + t;
							if (j < 0 || j >= GN)
							{
								continue;
							}
							const double w = kernel[t + BLUR_RADIUS];
							const double *in = &grid[at + (ptrdiff_t)t * (ptrdiff_t)stride[axis]];
							for (int k = 0; k < 4; ++k)
							{
								next[at + k] += w * in[k];
							}
						}
					}
				}
			}
			grid.swap(next);
		}
		const double pi = 3.14159265358979323846;
		const double peak = 1.0 / (std::pow(2 * pi, 1.5) * BLUR_SIGMA * BLUR_SIGMA * BLUR_SIGMA);
		for (double &v : grid)
		{
			v /= peak;
		}
	}
	// the table: at the cell centres, the grid's shift blended into M1t by the weight
	table.assign(lut.size(), 0.0f);
	HdWorkers::instance().run(TN, [&](int r)
	{
		const double cell = 256.0 / TN;
		for (int g = 0; g < TN; ++g)
		{
			for (int b = 0; b < TN; ++b)
			{
				const double q[3] = { (r + 0.5) * cell, (g + 0.5) * cell, (b + 0.5) * cell };
				int i0[3];
				double f[3];
				for (int a = 0; a < 3; ++a)
				{
					const double x = std::min(std::max(q[a] / GCELL - 0.5, 0.0), (double)(GN - 1));
					i0[a] = std::min((int)std::floor(x), GN - 2);
					f[a] = x - i0[a];
				}
				double s[4] = { 0, 0, 0, 0 };
				for (int dz = 0; dz < 2; ++dz)
				{
					const double wz = dz ? f[0] : 1.0 - f[0];
					for (int dy = 0; dy < 2; ++dy)
					{
						const double wy = wz * (dy ? f[1] : 1.0 - f[1]);
						for (int dx = 0; dx < 2; ++dx)
						{
							const double w = wy * (dx ? f[2] : 1.0 - f[2]);
							const double *c = &grid[(((size_t)(i0[0] + dz) * GN + (i0[1] + dy)) * GN + (i0[2] + dx)) * 4];
							for (int k = 0; k < 4; ++k)
							{
								s[k] += w * c[k];
							}
						}
					}
				}
				const size_t at = cellOf(r, g, b);
				for (int k = 0; k < 3; ++k)
				{
					table[at + k] = (float)((s[k] + TAU * lut[at + k]) / (s[3] + TAU));
				}
			}
		}
	});
	terrainKeys.clear();
	for (const SurfaceSet *set : terrain)
	{
		for (size_t i = 0; set && i < set->getTotalFrames(); ++i)
		{
			const Surface *frame = set->getFrame((int)i);
			if (frame)
			{
				terrainKeys.insert(frame->getBuffer());
			}
		}
	}
	const auto t3 = std::chrono::steady_clock::now();

	if (dump)
	{
		const std::string dir = dumpDir;
		writeFile(dir + "/lut.f32", lut.data(), lut.size() * sizeof(float));
		writeFile(dir + "/table.f32", table.data(), table.size() * sizeof(float));
		writeFile(dir + "/grid.f64", grid.data(), grid.size() * sizeof(double));
		unsigned char pals[2][768];
		for (int i = 0; i < 256; ++i)
		{
			pals[0][i * 3] = shown[i].r; pals[0][i * 3 + 1] = shown[i].g; pals[0][i * 3 + 2] = shown[i].b;
			pals[1][i * 3] = base[i].r; pals[1][i * 3 + 1] = base[i].g; pals[1][i * 3 + 2] = base[i].b;
		}
		writeFile(dir + "/shown.pal", pals[0], 768);
		writeFile(dir + "/base.pal", pals[1], 768);
		// the samples in the order they were summed: place u32, index u32, r g b f32
		std::vector<unsigned char> raw;
		for (const auto &pair : byPlace)
		{
			for (const Sample &s : pair.second)
			{
				const Uint32 head[2] = { (Uint32)pair.first, s.index };
				raw.insert(raw.end(), (const unsigned char*)head, (const unsigned char*)head + sizeof(head));
				raw.insert(raw.end(), (const unsigned char*)s.c, (const unsigned char*)s.c + sizeof(s.c));
			}
		}
		writeFile(dir + "/samples.bin", raw.data(), raw.size());
		std::sort(placeLines.begin(), placeLines.end());
		std::string tsv = "place\twidth\theight\tfnv64\tsamples\n";
		for (const auto &line : placeLines)
		{
			tsv += line.second + "\n";
		}
		writeFile(dir + "/places.tsv", tsv.data(), tsv.size());
		Log(LOG_INFO) << "HD palette shift: tables dumped to " << dir;
	}

	recolouredTerrain = 0;
	recolouredOther = 0;
	on = true;
	HdSprites::setRecolour(&recolour);
	const auto t4 = std::chrono::steady_clock::now();
	Log(LOG_INFO) << "HD palette shift: on in " << ms(t0, t4) << " ms (M1t " << ms(t0, t1) << " ms, scan " << ms(t1, t2) << " ms: "
		<< pictures << " picture(s) of " << terrain.size() << " terrain set(s), " << samples << " sample(s); BR " << ms(t2, t3)
		<< " ms; loaded frames " << ms(t3, t4) << " ms), tables " << ((lut.size() + table.size()) * sizeof(float) >> 10) << " KB";
}

void remove()
{
	if (!on)
	{
		return;
	}
	HdSprites::setRecolour(nullptr);
	Log(LOG_INFO) << "HD palette shift: off, recoloured " << recolouredTerrain.load() << " terrain and " << recolouredOther.load() << " other frame(s)";
	on = false;
	terrainKeys.clear();
	std::vector<float>().swap(lut);
	std::vector<float>().swap(table);
}

bool active()
{
	return on;
}

}

}
