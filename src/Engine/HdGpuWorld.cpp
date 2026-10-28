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
#include "HdGpuWorld.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>
#include "HdGpu.h"
#include "HdGpuGl.h"
#include "HdGpuAtlas.h"
#include "HdSprites.h"
#include "Logger.h"

namespace OpenXcom
{

HdGpuWorld &HdGpuWorld::instance()
{
	static HdGpuWorld one;
	return one;
}

#ifdef __NO_OPENGL

struct HdGpuWorld::Impl {};
HdGpuWorld::Impl &HdGpuWorld::impl() { static Impl one; return one; }
bool HdGpuWorld::begin(SDL_Surface *) { return false; }
void HdGpuWorld::cpu(const char *) {}
bool HdGpuWorld::end() { return false; }
bool HdGpuWorld::readInto(SDL_Surface *) { return false; }
bool HdGpuWorld::frame(const HdFrame &, int, int, int, int, int, int) { return false; }
bool HdGpuWorld::pixels(const Uint8 *, int, int, int, int, int, int, const Uint32 *, int, int, int, int) { return false; }
bool HdGpuWorld::fill(int, int, int, int, Uint32) { return false; }
bool HdGpuWorld::image(const Uint32 *, int, int, int, int, int, bool) { return false; }
bool HdGpuWorld::glyph(const Uint8 *, int, int, int, int, int, Uint32, const float *) { return false; }
bool HdGpuWorld::spans(const std::vector<Span> &) { return false; }
bool HdGpuWorld::cover(const std::vector<float> &, int, int, int, int, Uint32) { return false; }
bool HdGpuWorld::canvas(unsigned, const SDL_Surface *, int, int, int, int, int, int) { return false; }
bool HdGpuWorld::canvasZoomed(unsigned, const SDL_Surface *, const std::vector<int> &, const std::vector<Uint32> &,
	const std::vector<int> &, const std::vector<Uint32> &, Uint32, int, int, int, int) { return false; }
void HdGpuWorld::forget() {}
void HdGpuWorld::release() {}
void HdGpuWorld::fallBack(const char *) {}
bool HdGpuWorld::refuse(const char *) { return false; }

#else

namespace
{

using hdgl::gl;
using hdgl::Atlas;
using hdgl::Place;

/// The kinds of the writes (the first value of a write's second texel).
enum Kind { K_FILL, K_COPY, K_ZOOM, K_FRAME, K_PIXELS, K_IMAGE, K_GLYPH, K_SPANS, K_COVER };

/// The side of the tiles the writes are sorted into.
const int TILE = 32;
/// The fixed head of the data: (i / 255.0f) for the 256 alphas, then the two limits of HdUi's blendPixel.
const int DATA_LOW = 256, DATA_HIGH = 257, DATA_FIXED = 258;
/// Frames the processor draws after one with a writer the card does not take, before the card tries again.
const int WAIT_FRAMES = 30;
/// The reason given when the pictures' array has to be made bigger (the frame goes back, the array grows).
const char *const GROWING = "the pictures' layers grow";

// one triangle over the whole framebuffer; world row 0 is the framebuffer's row 0 (as HdGpu uploads it)
const char *const VERTEX_SHADER =
	"#version 330\n"
	"void main()\n"
	"{\n"
	"	gl_Position = vec4(float((gl_VertexID & 1) * 4 - 1), float((gl_VertexID & 2) * 2 - 1), 0.0, 1.0);\n"
	"}\n";

// every pixel runs through the writes over its tile in their order, from the cleared world (0): the formulas are
// those of the processor's routines, the floating point ones (blendPixel) without fused or reordered operations
// (precise) and with every division and root worked out by the processor beforehand
const char *const FRAGMENT_SHADER =
	"#version 330\n"
	"#extension GL_ARB_gpu_shader5 : require\n"
	"#define FILL 0\n"
	"#define COPY 1\n"
	"#define ZOOM 2\n"
	"#define FRAME 3\n"
	"#define PIXELS 4\n"
	"#define IMAGE 5\n"
	"#define GLYPH 6\n"
	"#define SPANS 7\n"
	"#define COVER 8\n"
	"uniform sampler2DArray atlas;\n"
	"uniform sampler2D canvas;\n"
	"uniform isamplerBuffer ops;\n"
	"uniform usamplerBuffer data;\n"
	"uniform isamplerBuffer bins;\n"
	"uniform int tilesX;\n"
	"uniform uint probe;\n"
	"out vec4 color;\n"
	"uint dat(int i) { return texelFetch(data, i).r; }\n"
	"float datf(int i) { return uintBitsToFloat(texelFetch(data, i).r); }\n"
	"uvec4 bytes(vec4 v) { return uvec4(v * 255.0 + 0.5); }\n"
	// a texel uploaded as BGRA bytes back to 0xAARRGGBB
	"uint argb(vec4 v) { uvec4 t = bytes(v); return (t.a << 24u) | (t.r << 16u) | (t.g << 8u) | t.b; }\n"
	"uint atlasAt(int layer, ivec2 p) { return argb(texelFetch(atlas, ivec3(p, layer), 0)); }\n"
	"uint atlasByte(int layer, ivec2 p) { return bytes(texelFetch(atlas, ivec3(p, layer), 0)).r; }\n"
	"uint canvasAt(ivec2 p) { return argb(texelFetch(canvas, p, 0)); }\n"
	// HdUi's blendPixel
	"uint blendPixel(uint d, uint c, float cov)\n"
	"{\n"
	"	precise float a = datf(int(c >> 24u)) * cov;\n"
	"	if (a <= datf(256)) return d;\n"
	"	if (a >= datf(257)) return c | 0xFF000000u;\n"
	"	precise float ia = 1.0 - a;\n"
	"	precise float r = float((c >> 16u) & 255u) * a + float((d >> 16u) & 255u) * ia + 0.5;\n"
	"	precise float g = float((c >> 8u) & 255u) * a + float((d >> 8u) & 255u) * ia + 0.5;\n"
	"	precise float b = float(c & 255u) * a + float(d & 255u) * ia + 0.5;\n"
	"	return 0xFF000000u | (uint(int(r)) << 16u) | (uint(int(g)) << 8u) | uint(int(b));\n"
	"}\n"
	// HdUiArt's blendInto: straight alpha in integers
	"uint blendInt(uint d, uint s)\n"
	"{\n"
	"	uint a = s >> 24u;\n"
	"	if (a == 0u) return d;\n"
	"	if (a == 255u) return s | 0xFF000000u;\n"
	"	uint ia = 255u - a;\n"
	"	uint r = (((s >> 16u) & 255u) * a + ((d >> 16u) & 255u) * ia) / 255u;\n"
	"	uint g = (((s >> 8u) & 255u) * a + ((d >> 8u) & 255u) * ia) / 255u;\n"
	"	uint b = ((s & 255u) * a + (d & 255u) * ia) / 255u;\n"
	"	return 0xFF000000u | (r << 16u) | (g << 8u) | b;\n"
	"}\n"
	// Canvas32's mix2: every channel, w of 256 of the second
	"uint mix2(uint a, uint b, uint w)\n"
	"{\n"
	"	uint o = 0u;\n"
	"	for (uint s = 0u; s < 32u; s += 8u)\n"
	"	{\n"
	"		o |= ((((a >> s) & 255u) * (256u - w) + ((b >> s) & 255u) * w) >> 8u) << s;\n"
	"	}\n"
	"	return o;\n"
	"}\n"
	"void main()\n"
	"{\n"
	"	ivec2 p = ivec2(gl_FragCoord.xy);\n"
	"	int tile = (p.y / 32) * tilesX + p.x / 32;\n"
	"	int start = texelFetch(bins, tile * 2).r, count = texelFetch(bins, tile * 2 + 1).r;\n"
	"	uint d = 0u;\n"
	"	for (int n = 0; n < count; ++n)\n"
	"	{\n"
	"		int i = texelFetch(bins, start + n).r;\n"
	"		ivec4 r = texelFetch(ops, i * 4);\n"
	"		if (p.x < r.x || p.y < r.y || p.x >= r.z || p.y >= r.w) continue;\n"
	"		ivec4 h = texelFetch(ops, i * 4 + 1);\n"
	"		ivec4 q = texelFetch(ops, i * 4 + 2);\n"
	"		switch (h.x)\n"
	"		{\n"
	"		case FILL:\n"
	"			d = uint(q.x);\n"
	"			break;\n"
	"		case COPY:\n"
	"			d = canvasAt(p - q.xy);\n"
	"			break;\n"
	"		case ZOOM:\n"
	"		{\n"
	"			int j = int(dat(q.y + (p.y - r.y) * 2));\n"
	"			if (j < 0)\n"
	"			{\n"
	"				d = uint(q.z);\n"
	"				break;\n"
	"			}\n"
	"			uint wy = dat(q.y + (p.y - r.y) * 2 + 1);\n"
	"			int c = int(dat(q.x + (p.x - r.x) * 2));\n"
	"			uint wx = dat(q.x + (p.x - r.x) * 2 + 1);\n"
	"			uint top = mix2(canvasAt(ivec2(c, j)), canvasAt(ivec2(c + 1, j)), wx);\n"
	"			uint low = mix2(canvasAt(ivec2(c, j + 1)), canvasAt(ivec2(c + 1, j + 1)), wx);\n"
	"			d = mix2(top, low, wy);\n"
	"			break;\n"
	"		}\n"
	"		case FRAME:\n"
	"			d = blendInt(d, atlasAt(h.y, p + h.zw));\n"
	"			break;\n"
	"		case PIXELS:\n"
	"		{\n"
	"			uint idx = atlasByte(h.y, h.zw + (p - q.xy) / q.z);\n"
	"			if (idx != 0u) d = dat(q.w + int(idx));\n"
	"			break;\n"
	"		}\n"
	"		case IMAGE:\n"
	"		{\n"
	"			uint c = atlasAt(h.y, p + h.zw);\n"
	"			if (q.x != 0) d = c;\n"
	"			else if ((c >> 24u) != 0u) d = blendPixel(d, c, 1.0);\n"
	"			break;\n"
	"		}\n"
	"		case GLYPH:\n"
	"		{\n"
	"			uint c = atlasByte(h.y, p + h.zw);\n"
	"			if (c != 0u) d = blendPixel(d, uint(q.x), datf(q.y + int(c)));\n"
	"			break;\n"
	"		}\n"
	"		case SPANS:\n"
	"		{\n"
	"			int at = q.x + (p.y - r.y) * 2;\n"
	"			int s = int(dat(at)), e = s + int(dat(at + 1)) * 6;\n"
	"			for (; s < e; s += 6)\n"
	"			{\n"
	"				int ia = int(dat(s)), ib = int(dat(s + 1));\n"
	"				if (p.x < ia || p.x > ib) continue;\n"
	"				float cov = p.x == ia ? datf(s + 2) : (p.x == ib ? datf(s + 3) : datf(s + 4));\n"
	"				d = blendPixel(d, dat(s + 5), cov);\n"
	"			}\n"
	"			break;\n"
	"		}\n"
	"		case COVER:\n"
	"		{\n"
	"			float cov = datf(q.x + (p.y - r.y) * q.y + (p.x - r.x));\n"
	"			if (cov > datf(256)) d = blendPixel(d, uint(q.z), cov);\n"
	"			break;\n"
	"		}\n"
	"		}\n"
	"	}\n"
	// probe (OXCE_HD_GPU_WORLD=probe): the lowest bit of blue flipped, the control of the dump comparison
	"	uvec4 o = uvec4(d >> 16u, d >> 8u, d ^ probe, d >> 24u) & 255u;\n"
	"	color = vec4(o) / 255.0;\n"
	"}\n";

/// The environment switch is set to something else than "0" (or unset and `fallback`).
bool envOn(const char *name, bool fallback)
{
	const char *v = std::getenv(name);
	return v && *v ? std::strcmp(v, "0") != 0 : fallback;
}

/// Says once per reason what the card does with the world.
void tellOnce(const std::string &what)
{
	static std::set<std::string> told;
	if (told.insert(what).second)
	{
		Log(LOG_INFO) << "HD GPU world: " << what;
	}
}

/// A hash of `rows` rows of `rowBytes` bytes, `pitch` apart.
Uint64 hashRows(const Uint8 *p, size_t rowBytes, int rows, size_t pitch, Uint64 seed)
{
	Uint64 h = seed * 0x9E3779B97F4A7C15ull + 0x632BE59BD9B4E019ull;
	for (int y = 0; y < rows; ++y)
	{
		const Uint8 *row = p + (size_t)y * pitch;
		size_t i = 0;
		for (; i + 8 <= rowBytes; i += 8)
		{
			Uint64 v;
			std::memcpy(&v, row + i, 8);
			h = (h ^ v) * 0x100000001B3ull;
			h ^= h >> 29;
		}
		for (; i < rowBytes; ++i)
		{
			h = (h ^ row[i]) * 0x100000001B3ull;
		}
		h ^= h >> 31;
		h *= 0xBF58476D1CE4E5B9ull;
	}
	return h ^ (h >> 33);
}

}

struct HdGpuWorld::Impl
{
	bool built = false, failed = false, enabled = true, probe = false, verify = false;
	GLuint program = 0, vao = 0, canvasOwn = 0;
	GLuint buffers[3] = { 0, 0, 0 }, textures[3] = { 0, 0, 0 };
	GLint tilesAt = -1, probeAt = -1, maxTexels = 0;
	int canvasOwnW = 0, canvasOwnH = 0;
	Atlas atlas;
	/// The coverages, palette pixels and pictures handed over by their pointers, by a hash of their bytes.
	std::unordered_map<Uint64, Uint64> transient;
	// the frame being recorded
	int W = 0, H = 0;
	std::vector<Sint32> ops;
	std::vector<Uint32> data;
	/// The tables of this frame (palettes, coverage curves) by a hash of their values: their place in `data`.
	std::unordered_map<Uint64, Sint32> tables;
	/// The canvas the frame copies: the texture it is read from, and the processor's pixels uploaded into canvasOwn.
	GLuint canvasTexture = 0;
	const SDL_Surface *canvasPixels = nullptr;
	std::vector<std::vector<int>> lists;
	std::vector<Sint32> bins;
	std::vector<Uint32> scratch;
	/// A frame had a writer the card does not take; frames the processor still draws before the card tries again.
	bool dirty = false;
	int wait = 0;
	/// OXCE_HD_GPU_VERIFY: frames compared, and those that differed.
	long long verified = 0, differed = 0;
	/// OXCE_HD_GPU_STATS: a line every 5 s.
	struct Stats
	{
		bool on = false;
		std::chrono::steady_clock::time_point since;
		long long card = 0, cpu = 0, ops = 0, maxOps = 0, uploads = 0, uploadBytes = 0, composites = 0;
		double ms = 0, maxMs = 0;
		std::map<std::string, long long> why, held;
	} stats;

	bool build()
	{
		built = true;
		const char *mode = std::getenv("OXCE_HD_GPU_WORLD");
		enabled = !(mode && std::strcmp(mode, "0") == 0);
		probe = mode && std::strcmp(mode, "probe") == 0;
		verify = envOn("OXCE_HD_GPU_VERIFY", false);
		stats.on = envOn("OXCE_HD_GPU_STATS", false);
		stats.since = std::chrono::steady_clock::now();
		if (!enabled)
		{
			Log(LOG_INFO) << "HD GPU world: off (OXCE_HD_GPU_WORLD=0) - the processor draws the world";
			failed = true;
			return false;
		}
		program = hdgl::program(VERTEX_SHADER, FRAGMENT_SHADER, "the world");
		if (!program)
		{
			Log(LOG_ERROR) << "HD GPU world: no program (GL_ARB_gpu_shader5 is needed) - the processor draws the world";
			failed = true;
			return false;
		}
		gl.UseProgram(program);
		gl.Uniform1i(gl.GetUniformLocation(program, "atlas"), 0);
		gl.Uniform1i(gl.GetUniformLocation(program, "canvas"), 1);
		gl.Uniform1i(gl.GetUniformLocation(program, "ops"), 2);
		gl.Uniform1i(gl.GetUniformLocation(program, "data"), 3);
		gl.Uniform1i(gl.GetUniformLocation(program, "bins"), 4);
		tilesAt = gl.GetUniformLocation(program, "tilesX");
		probeAt = gl.GetUniformLocation(program, "probe");
		gl.UseProgram(0);
		gl.GenVertexArrays(1, &vao);
		gl.GenBuffers(3, buffers);
		glGenTextures(3, textures);
		const GLenum formats[3] = { GL_RGBA32I, GL_R32UI, 0x8235 /* GL_R32I */ };
		for (int i = 0; i < 3; ++i)
		{
			gl.BindBuffer(GL_TEXTURE_BUFFER, buffers[i]);
			gl.BufferData(GL_TEXTURE_BUFFER, 64, nullptr, GL_STREAM_DRAW);
			gl.ActiveTexture(GL_TEXTURE0 + 2 + i);
			glBindTexture(GL_TEXTURE_BUFFER, textures[i]);
			gl.TexBuffer(GL_TEXTURE_BUFFER, formats[i], buffers[i]);
			glBindTexture(GL_TEXTURE_BUFFER, 0);
		}
		gl.BindBuffer(GL_TEXTURE_BUFFER, 0);
		gl.ActiveTexture(GL_TEXTURE0);
		glGetIntegerv(GL_MAX_TEXTURE_BUFFER_SIZE, &maxTexels);
		GLint maxSize = 0, maxArray = 0;
		glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxSize);
		glGetIntegerv(GL_MAX_ARRAY_TEXTURE_LAYERS, &maxArray);
		atlas.page = std::min(4096, (int)maxSize);
		// OXCE_HD_GPU_WORLD_MB: the most the interface's pictures take on the card
		const char *mb = std::getenv("OXCE_HD_GPU_WORLD_MB");
		const long long budget = (mb && std::atoi(mb) > 0 ? std::atoi(mb) : 512) * (1LL << 20);
		const long long layerBytes = (long long)atlas.page * atlas.page * 4;
		atlas.maxLayers = (int)std::max(1LL, std::min((long long)maxArray, budget / layerBytes));
		if (atlas.page < 2048 || !atlas.create(1) || glGetError() != GL_NO_ERROR)
		{
			Log(LOG_ERROR) << "HD GPU world: no texture array of " << atlas.page << "x" << atlas.page << " - the processor draws the world";
			failed = true;
			return false;
		}
		Log(LOG_INFO) << "HD GPU world: on, pictures in " << atlas.page << "x" << atlas.page << " layers (up to " << atlas.maxLayers << "), "
			<< maxTexels << " texels a buffer" << (verify ? ", every frame of the card compared with the processor's" : "")
			<< (probe ? ", probe on" : "");
		return true;
	}

	void release()
	{
		if (program) gl.DeleteProgram(program);
		if (vao) gl.DeleteVertexArrays(1, &vao);
		if (buffers[0]) gl.DeleteBuffers(3, buffers);
		if (textures[0]) glDeleteTextures(3, textures);
		if (canvasOwn) glDeleteTextures(1, &canvasOwn);
		program = vao = canvasOwn = 0;
		buffers[0] = buffers[1] = buffers[2] = 0;
		textures[0] = textures[1] = textures[2] = 0;
		canvasOwnW = canvasOwnH = 0;
		atlas.release();
		transient.clear();
		built = failed = false;
	}

	void start(int w, int h)
	{
		W = w;
		H = h;
		ops.clear();
		data.resize(DATA_FIXED);
		for (int i = 0; i < 256; ++i)
		{
			const float a = i / 255.0f;
			std::memcpy(&data[i], &a, 4);
		}
		const float low = 0.002f, high = 0.998f;
		std::memcpy(&data[DATA_LOW], &low, 4);
		std::memcpy(&data[DATA_HIGH], &high, 4);
		tables.clear();
		canvasTexture = 0;
		canvasPixels = nullptr;
		++atlas.clock;
	}

	/// A write of `kind` over [x0, x1) x [y0, y1): its 16 values, the rectangle filled in.
	Sint32 *push(Kind kind, int x0, int y0, int x1, int y1)
	{
		ops.resize(ops.size() + 16, 0);
		Sint32 *q = &ops[ops.size() - 16];
		q[0] = x0;
		q[1] = y0;
		q[2] = x1;
		q[3] = y1;
		q[4] = kind;
		return q;
	}

	/// A table of n values in the data, once a frame for the same values.
	Sint32 table(const Uint32 *v, int n)
	{
		const Uint64 key = hashRows((const Uint8 *)v, (size_t)n * 4, 1, 0, (Uint64)n);
		auto it = tables.find(key);
		if (it != tables.end())
		{
			return it->second;
		}
		const Sint32 at = (Sint32)data.size();
		data.insert(data.end(), v, v + n);
		tables[key] = at;
		return at;
	}

	const Place *transientPlace(const void *src, int pitchBytes, int w, int h, bool bytes, const char *&why);
	GLuint canvasSource(unsigned texture, const SDL_Surface *pixels, const char *&why);

	void upload(const Place &pl, const void *src, int pitchPixels, int w, int h, bool bytes)
	{
		gl.ActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D_ARRAY, atlas.texture);
		glPixelStorei(GL_UNPACK_ALIGNMENT, bytes ? 1 : 4);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, pitchPixels);
		gl.TexSubImage3D(GL_TEXTURE_2D_ARRAY, 0, pl.x, pl.y, pl.layer, w, h, 1, bytes ? GL_RED : GL_BGRA, GL_UNSIGNED_BYTE, src);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
		glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
		glBindTexture(GL_TEXTURE_2D_ARRAY, 0);
		++stats.uploads;
		stats.uploadBytes += (long long)w * h * (bytes ? 1 : 4);
	}

	/// Sorts the writes into the tiles (a write that hides a whole tile drops the ones before it there), uploads
	/// them and draws the world into its framebuffer.
	void composite()
	{
		const auto t0 = std::chrono::steady_clock::now();
		const int tilesX = (W + TILE - 1) / TILE, tilesY = (H + TILE - 1) / TILE;
		const int count = (int)(ops.size() / 16);
		lists.resize((size_t)tilesX * tilesY);
		for (std::vector<int> &l : lists)
		{
			l.clear();
		}
		for (int i = 0; i < count; ++i)
		{
			const Sint32 *q = &ops[(size_t)i * 16];
			const bool opaque = q[4] == K_FILL || q[4] == K_COPY || q[4] == K_ZOOM || (q[4] == K_IMAGE && q[8] != 0);
			for (int ty = q[1] / TILE; ty <= (q[3] - 1) / TILE; ++ty)
			{
				for (int tx = q[0] / TILE; tx <= (q[2] - 1) / TILE; ++tx)
				{
					std::vector<int> &l = lists[(size_t)ty * tilesX + tx];
					if (opaque && q[0] <= tx * TILE && q[1] <= ty * TILE && q[2] >= std::min(W, (tx + 1) * TILE) && q[3] >= std::min(H, (ty + 1) * TILE))
					{
						l.clear();
					}
					l.push_back(i);
				}
			}
		}
		bins.resize(lists.size() * 2);
		for (size_t t = 0; t < lists.size(); ++t)
		{
			bins[t * 2] = (Sint32)bins.size();
			bins[t * 2 + 1] = (Sint32)lists[t].size();
			bins.insert(bins.end(), lists[t].begin(), lists[t].end());
		}
		if ((long long)ops.size() / 4 > maxTexels || (long long)data.size() > maxTexels || (long long)bins.size() > maxTexels)
		{
			tellOnce("a frame over the size of a texture buffer - drawn wrong");
		}
		const auto t1 = std::chrono::steady_clock::now();
		const void *src[3] = { ops.data(), data.data(), bins.data() };
		const size_t bytes[3] = { ops.size() * 4, data.size() * 4, bins.size() * 4 };
		for (int i = 0; i < 3; ++i)
		{
			gl.BindBuffer(GL_TEXTURE_BUFFER, buffers[i]);
			gl.BufferData(GL_TEXTURE_BUFFER, (std::ptrdiff_t)std::max<size_t>(bytes[i], 64), nullptr, GL_STREAM_DRAW);
			gl.BufferSubData(GL_TEXTURE_BUFFER, 0, (std::ptrdiff_t)bytes[i], src[i]);
		}
		gl.BindBuffer(GL_TEXTURE_BUFFER, 0);
		const auto t2 = std::chrono::steady_clock::now();
		// no glGet here: a driver drawing on a thread of its own answers one only after every command before it,
		// the canvas's uploads too (0.1-1.1 s when its pictures' array grows); present() sets the viewport again
		gl.BindFramebuffer(GL_FRAMEBUFFER, HdGpu::instance().framebuffer());
		glViewport(0, 0, W, H);
		glDisable(GL_SCISSOR_TEST);
		glDisable(GL_DEPTH_TEST);
		glDisable(GL_BLEND);
		glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
		gl.UseProgram(program);
		gl.Uniform1i(tilesAt, tilesX);
		gl.Uniform1ui(probeAt, probe ? 1u : 0u);
		gl.ActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D_ARRAY, atlas.texture);
		gl.ActiveTexture(GL_TEXTURE0 + 1);
		glBindTexture(GL_TEXTURE_2D, canvasTexture);
		for (int i = 0; i < 3; ++i)
		{
			gl.ActiveTexture(GL_TEXTURE0 + 2 + i);
			glBindTexture(GL_TEXTURE_BUFFER, textures[i]);
		}
		gl.BindVertexArray(vao);
		const auto t3 = std::chrono::steady_clock::now();
		glDrawArrays(GL_TRIANGLES, 0, 3);
		gl.BindVertexArray(0);
		const auto t4 = std::chrono::steady_clock::now();
		for (int i = 2; i >= 0; --i)
		{
			gl.ActiveTexture(GL_TEXTURE0 + 2 + i);
			glBindTexture(GL_TEXTURE_BUFFER, 0);
		}
		gl.ActiveTexture(GL_TEXTURE0 + 1);
		glBindTexture(GL_TEXTURE_2D, 0);
		gl.ActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D_ARRAY, 0);
		gl.UseProgram(0);
		gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
		if (stats.on)
		{
			auto span = [](std::chrono::steady_clock::time_point a, std::chrono::steady_clock::time_point b)
			{
				return std::chrono::duration<double, std::milli>(b - a).count();
			};
			const double ms = span(t0, std::chrono::steady_clock::now());
			if (ms >= 50.0)
			{
				Log(LOG_INFO) << "HD GPU world: a composite of " << ms << " ms (bins " << span(t0, t1) << ", buffers " << span(t1, t2)
					<< ", binding " << span(t2, t3) << ", draw " << span(t3, t4) << ", " << count << " writes, data " << (data.size() >> 8) << " KB)";
			}
			stats.ms += ms;
			stats.maxMs = std::max(stats.maxMs, ms);
			++stats.composites;
			stats.ops += count;
			stats.maxOps = std::max(stats.maxOps, (long long)count);
		}
	}

	void report()
	{
		if (!stats.on)
		{
			return;
		}
		const auto now = std::chrono::steady_clock::now();
		if (std::chrono::duration<double>(now - stats.since).count() < 5.0)
		{
			return;
		}
		std::string why;
		for (const auto &w : stats.why)
		{
			why += (why.empty() ? "" : ", ") + w.first + " " + std::to_string(w.second);
		}
		std::string held;
		for (const auto &w : stats.held)
		{
			held += (held.empty() ? "" : ", ") + w.first + " " + std::to_string(w.second);
		}
		const long long n = std::max(1LL, stats.composites);
		Log(LOG_INFO) << "HD GPU world stats: frames card " << stats.card << ", processor " << stats.cpu
			<< (why.empty() ? std::string() : " (back to the processor: " + why + ")")
			<< (held.empty() ? std::string() : " (writers on the processor's frames: " + held + ")")
			<< " | writes " << stats.ops / n << " a frame, up to " << stats.maxOps
			<< " | uploads " << stats.uploads << " (" << (stats.uploadBytes >> 10) << " KB)"
			<< " | composite " << stats.ms / n << " ms, up to " << stats.maxMs << " ms";
		const bool on = stats.on;
		stats = Stats();
		stats.on = on;
		stats.since = now;
	}
};

HdGpuWorld::Impl &HdGpuWorld::impl()
{
	if (!_impl)
	{
		_impl = new Impl();
	}
	return *_impl;
}

bool HdGpuWorld::begin(SDL_Surface *world)
{
	_on = false;
	Impl &m = impl();
	if (m.dirty)
	{
		m.wait = WAIT_FRAMES;
		m.dirty = false;
	}
	else if (m.wait > 0)
	{
		--m.wait;
	}
	HdGpu &gpu = HdGpu::instance();
	if (m.wait > 0 || !gpu.current() || !world || world->format->BytesPerPixel != 4 || world->w != gpu.width() || world->h != gpu.height())
	{
		return false;
	}
	if (!m.built)
	{
		m.build();
	}
	if (m.failed)
	{
		return false;
	}
	m.start(world->w, world->h);
	_world = world;
	_thread = SDL_ThreadID();
	_verify = m.verify;
	_on = true;
	return true;
}

void HdGpuWorld::cpu(const char *who)
{
	if (!_impl)
	{
		return;
	}
	_impl->dirty = true;
	if (!_on && _impl->stats.on)
	{
		++_impl->stats.held[who];
	}
	if (_on)
	{
		if (SDL_ThreadID() != _thread)
		{
			tellOnce(std::string("a writer off the thread of the context (") + who + ") - the frame may be wrong");
			return;
		}
		fallBack(who);
	}
}

void HdGpuWorld::fallBack(const char *why)
{
	Impl &m = *_impl;
	if (m.stats.on)
	{
		++m.stats.why[why];
	}
	tellOnce(std::string("the processor takes a frame over: ") + why);
	// what was handed over comes back into the processor's world (with VERIFY the processor drew it already)
	if (!_verify)
	{
		m.composite();
		HdGpu &gpu = HdGpu::instance();
		if (!gpu.readBack(_world))
		{
			// the processor's world was not cleared at the frame's start: cleared now, without what the card drew
			Log(LOG_ERROR) << "HD GPU world: the frame could not be read back (world " << _world->w << "x" << _world->h
				<< ", card " << gpu.width() << "x" << gpu.height() << ")";
			for (int y = 0; y < _world->h; ++y)
			{
				std::memset((Uint8*)_world->pixels + (size_t)y * _world->pitch, 0, (size_t)_world->w * 4);
			}
		}
	}
	_on = false;
	m.dirty = true;
}

bool HdGpuWorld::refuse(const char *why)
{
	fallBack(why);
	// the frame is the processor's now: the array may be made anew (everything on it goes up again)
	if (why == GROWING && _impl->atlas.grow())
	{
		_impl->transient.clear();
	}
	return false;
}

bool HdGpuWorld::end()
{
	if (!_impl)
	{
		return false;
	}
	Impl &m = *_impl;
	if (!_on)
	{
		++m.stats.cpu;
		m.report();
		return false;
	}
	m.composite();
	_on = false;
	++m.stats.card;
	if (_verify)
	{
		// the card's frame against the processor's, pixel for pixel
		const int W = m.W, H = m.H;
		m.scratch.resize((size_t)W * H);
		gl.BindFramebuffer(GL_READ_FRAMEBUFFER, HdGpu::instance().framebuffer());
		glReadPixels(0, 0, W, H, GL_BGRA, GL_UNSIGNED_BYTE, m.scratch.data());
		gl.BindFramebuffer(GL_READ_FRAMEBUFFER, 0);
		long long differ = 0;
		int firstX = -1, firstY = -1;
		Uint32 cpuPixel = 0, cardPixel = 0;
		for (int y = 0; y < H; ++y)
		{
			const Uint32 *row = (const Uint32 *)((const Uint8 *)_world->pixels + (size_t)y * _world->pitch);
			const Uint32 *card = m.scratch.data() + (size_t)y * W;
			if (std::memcmp(row, card, (size_t)W * 4) == 0)
			{
				continue;
			}
			for (int x = 0; x < W; ++x)
			{
				if (row[x] != card[x] && !differ++)
				{
					firstX = x;
					firstY = y;
					cpuPixel = row[x];
					cardPixel = card[x];
				}
			}
		}
		++m.verified;
		if (differ && m.differed++ < 20)
		{
			Log(LOG_INFO) << "HD GPU world verify: frame " << m.verified << " differs in " << differ << " pixel(s), the first at "
				<< firstX << "," << firstY << ": processor " << std::hex << cpuPixel << ", card " << cardPixel << std::dec
				<< " (" << m.ops.size() / 16 << " writes)";
		}
		if (m.verified % 600 == 0)
		{
			Log(LOG_INFO) << "HD GPU world verify: " << m.verified << " frames compared, " << m.differed << " differ";
		}
	}
	m.report();
	return true;
}

bool HdGpuWorld::readInto(SDL_Surface *out)
{
	if (!_on || SDL_ThreadID() != _thread)
	{
		return false;
	}
	_impl->composite();
	return HdGpu::instance().readBack(out);
}

namespace
{

/// The rectangle within the world; false when nothing is left.
bool within(int W, int H, int &x0, int &y0, int &x1, int &y1)
{
	x0 = std::max(x0, 0);
	y0 = std::max(y0, 0);
	x1 = std::min(x1, W);
	y1 = std::min(y1, H);
	return x0 < x1 && y0 < y1;
}

}

bool HdGpuWorld::frame(const HdFrame &f, int fx, int fy, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (!within(m.W, m.H, x0, y0, x1, y1))
	{
		return true;
	}
	Atlas &atlas = m.atlas;
	Place *pl = atlas.find(f.gpuWorld.id);
	if (!pl)
	{
		if (f.width > atlas.page || f.height > atlas.page)
		{
			fallBack("a picture bigger than a layer");
			return false;
		}
		Uint64 id = 0;
		const Atlas::Result r = atlas.place(f.width, f.height, id);
		if (r != Atlas::PLACED)
		{
			return refuse(r == Atlas::GROW ? GROWING : "the pictures' layers are full");
		}
		pl = &atlas.places[id];
		m.upload(*pl, f.pixels.data(), f.width, f.width, f.height, false);
		f.gpuWorld.id = id;
	}
	Sint32 *q = m.push(K_FRAME, x0, y0, x1, y1);
	q[5] = pl->layer;
	q[6] = pl->x - fx;
	q[7] = pl->y - fy;
	return true;
}

/// The place of bytes handed over by a pointer (looked up by a hash of them), uploaded when they are new.
const Place *HdGpuWorld::Impl::transientPlace(const void *src, int pitchBytes, int w, int h, bool bytes, const char *&why)
{
	Impl &m = *this;
	const size_t rowBytes = (size_t)w * (bytes ? 1 : 4);
	const Uint64 key = hashRows((const Uint8 *)src, rowBytes, h, (size_t)pitchBytes, ((Uint64)w << 32) ^ ((Uint64)h << 1) ^ (bytes ? 1u : 0u));
	auto it = m.transient.find(key);
	if (it != m.transient.end())
	{
		if (Place *pl = atlas.find(it->second))
		{
			return pl;
		}
	}
	if (w > atlas.page || h > atlas.page)
	{
		why = "a picture bigger than a layer";
		return nullptr;
	}
	Uint64 id = 0;
	const Atlas::Result r = atlas.place(w, h, id);
	if (r != Atlas::PLACED)
	{
		why = r == Atlas::GROW ? GROWING : "the pictures' layers are full";
		return nullptr;
	}
	if (m.transient.size() > 65536)
	{
		for (auto e = m.transient.begin(); e != m.transient.end();)
		{
			e = atlas.places.count(e->second) ? std::next(e) : m.transient.erase(e);
		}
	}
	m.transient[key] = id;
	const Place *pl = &atlas.places[id];
	m.upload(*pl, src, pitchBytes / (bytes ? 1 : 4), w, h, bytes);
	return pl;
}

bool HdGpuWorld::pixels(const Uint8 *pixels, int pitch, int w, int h, int ox, int oy, int k, const Uint32 *lut, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (!within(m.W, m.H, x0, y0, x1, y1) || w <= 0 || h <= 0)
	{
		return true;
	}
	const char *why = nullptr;
	const Place *pl = m.transientPlace(pixels, pitch, w, h, true, why);
	if (!pl)
	{
		return refuse(why);
	}
	const Sint32 at = m.table(lut, 256);
	Sint32 *q = m.push(K_PIXELS, x0, y0, x1, y1);
	q[5] = pl->layer;
	q[6] = pl->x;
	q[7] = pl->y;
	q[8] = ox;
	q[9] = oy;
	q[10] = k;
	q[11] = at;
	return true;
}

bool HdGpuWorld::fill(int x0, int y0, int x1, int y1, Uint32 v)
{
	Impl &m = *_impl;
	if (!within(m.W, m.H, x0, y0, x1, y1))
	{
		return true;
	}
	Sint32 *q = m.push(K_FILL, x0, y0, x1, y1);
	q[8] = (Sint32)v;
	return true;
}

bool HdGpuWorld::image(const Uint32 *argb, int pitch, int w, int h, int x, int y, bool copy)
{
	Impl &m = *_impl;
	int x0 = x, y0 = y, x1 = x + w, y1 = y + h;
	if (w <= 0 || h <= 0 || !within(m.W, m.H, x0, y0, x1, y1))
	{
		return true;
	}
	const char *why = nullptr;
	const Place *pl = m.transientPlace(argb, pitch * 4, w, h, false, why);
	if (!pl)
	{
		return refuse(why);
	}
	Sint32 *q = m.push(K_IMAGE, x0, y0, x1, y1);
	q[5] = pl->layer;
	q[6] = pl->x - x;
	q[7] = pl->y - y;
	q[8] = copy ? 1 : 0;
	return true;
}

bool HdGpuWorld::glyph(const Uint8 *cov, int pitch, int w, int h, int x, int y, Uint32 color, const float *lut)
{
	Impl &m = *_impl;
	int x0 = x, y0 = y, x1 = x + w, y1 = y + h;
	if (w <= 0 || h <= 0 || !within(m.W, m.H, x0, y0, x1, y1))
	{
		return true;
	}
	const char *why = nullptr;
	const Place *pl = m.transientPlace(cov, pitch, w, h, true, why);
	if (!pl)
	{
		return refuse(why);
	}
	static_assert(sizeof(float) == sizeof(Uint32), "floats go into the data as their bits");
	const Sint32 at = m.table((const Uint32 *)lut, 256);
	Sint32 *q = m.push(K_GLYPH, x0, y0, x1, y1);
	q[5] = pl->layer;
	q[6] = pl->x - x;
	q[7] = pl->y - y;
	q[8] = (Sint32)color;
	q[9] = at;
	return true;
}

bool HdGpuWorld::spans(const std::vector<Span> &spans)
{
	Impl &m = *_impl;
	if (spans.empty())
	{
		return true;
	}
	int x0 = spans[0].ia, x1 = spans[0].ib + 1, y0 = spans[0].y, y1 = spans[0].y + 1;
	for (const Span &s : spans)
	{
		x0 = std::min(x0, s.ia);
		x1 = std::max(x1, s.ib + 1);
		y0 = std::min(y0, s.y);
		y1 = std::max(y1, s.y + 1);
	}
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H)
	{
		fallBack("a shape out of the world");
		return false;
	}
	// per row of the rectangle: where its runs start and how many there are; the runs by row, in their order
	const int rows = y1 - y0;
	const Sint32 at = (Sint32)m.data.size();
	m.data.resize(m.data.size() + (size_t)rows * 2, 0);
	for (const Span &s : spans)
	{
		++m.data[at + (s.y - y0) * 2 + 1];
	}
	Uint32 next = (Uint32)m.data.size();
	for (int r = 0; r < rows; ++r)
	{
		m.data[at + r * 2] = next;
		next += m.data[at + r * 2 + 1] * 6;
	}
	m.data.resize(next, 0);
	std::vector<Uint32> fillAt(rows, 0);
	for (const Span &s : spans)
	{
		const int r = s.y - y0;
		Uint32 *v = &m.data[m.data[at + r * 2] + fillAt[r] * 6];
		++fillAt[r];
		v[0] = (Uint32)s.ia;
		v[1] = (Uint32)s.ib;
		std::memcpy(&v[2], &s.first, 4);
		std::memcpy(&v[3], &s.last, 4);
		std::memcpy(&v[4], &s.inner, 4);
		v[5] = s.color;
	}
	Sint32 *q = m.push(K_SPANS, x0, y0, x1, y1);
	q[8] = at;
	return true;
}

bool HdGpuWorld::cover(const std::vector<float> &cov, int x0, int y0, int x1, int y1, Uint32 color)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || cov.size() != (size_t)(x1 - x0) * (y1 - y0))
	{
		fallBack("a shape out of the world");
		return false;
	}
	const Sint32 at = (Sint32)m.data.size();
	m.data.resize(m.data.size() + cov.size());
	std::memcpy(&m.data[at], cov.data(), cov.size() * 4);
	Sint32 *q = m.push(K_COVER, x0, y0, x1, y1);
	q[8] = at;
	q[9] = x1 - x0;
	q[10] = (Sint32)color;
	return true;
}

/// The texture the frame reads the canvas from: the card's framebuffer, or the processor's pixels uploaded once a
/// frame; one canvas a frame (why says otherwise).
GLuint HdGpuWorld::Impl::canvasSource(unsigned texture, const SDL_Surface *pixels, const char *&why)
{
	Impl &m = *this;
	if (!texture)
	{
		if (!pixels || pixels->format->BytesPerPixel != 4)
		{
			why = "a canvas of another format";
			return 0;
		}
		if (m.canvasTexture == m.canvasOwn && m.canvasPixels == pixels && m.canvasTexture)
		{
			return m.canvasOwn;
		}
		if (m.canvasTexture)
		{
			why = "two canvases in a frame";
			return 0;
		}
		gl.ActiveTexture(GL_TEXTURE0 + 1);
		if (!m.canvasOwn)
		{
			glGenTextures(1, &m.canvasOwn);
		}
		glBindTexture(GL_TEXTURE_2D, m.canvasOwn);
		if (m.canvasOwnW != pixels->w || m.canvasOwnH != pixels->h)
		{
			glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, pixels->w, pixels->h, 0, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
			m.canvasOwnW = pixels->w;
			m.canvasOwnH = pixels->h;
		}
		glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, pixels->pitch / 4);
		glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, pixels->w, pixels->h, GL_BGRA, GL_UNSIGNED_BYTE, pixels->pixels);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
		glBindTexture(GL_TEXTURE_2D, 0);
		gl.ActiveTexture(GL_TEXTURE0);
		++m.stats.uploads;
		m.stats.uploadBytes += (long long)pixels->w * pixels->h * 4;
		m.canvasTexture = m.canvasOwn;
		m.canvasPixels = pixels;
		return m.canvasOwn;
	}
	if (m.canvasTexture && m.canvasTexture != texture)
	{
		why = "two canvases in a frame";
		return 0;
	}
	m.canvasTexture = texture;
	return texture;
}

bool HdGpuWorld::canvas(unsigned texture, const SDL_Surface *pixels, int ox, int oy, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (!within(m.W, m.H, x0, y0, x1, y1))
	{
		return true;
	}
	const char *why = nullptr;
	if (!m.canvasSource(texture, pixels, why))
	{
		fallBack(why);
		return false;
	}
	Sint32 *q = m.push(K_COPY, x0, y0, x1, y1);
	q[8] = ox;
	q[9] = oy;
	return true;
}

bool HdGpuWorld::canvasZoomed(unsigned texture, const SDL_Surface *pixels, const std::vector<int> &cols, const std::vector<Uint32> &colWeights,
	const std::vector<int> &rows, const std::vector<Uint32> &rowWeights, Uint32 black, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || cols.size() != (size_t)(x1 - x0) || rows.size() != (size_t)(y1 - y0))
	{
		fallBack("a zoomed canvas out of the world");
		return false;
	}
	const char *why = nullptr;
	if (!m.canvasSource(texture, pixels, why))
	{
		fallBack(why);
		return false;
	}
	const Sint32 colsAt = (Sint32)m.data.size();
	for (size_t i = 0; i < cols.size(); ++i)
	{
		m.data.push_back((Uint32)cols[i]);
		m.data.push_back(colWeights[i]);
	}
	const Sint32 rowsAt = (Sint32)m.data.size();
	for (size_t i = 0; i < rows.size(); ++i)
	{
		m.data.push_back((Uint32)rows[i]);
		m.data.push_back(rowWeights[i]);
	}
	Sint32 *q = m.push(K_ZOOM, x0, y0, x1, y1);
	q[8] = colsAt;
	q[9] = rowsAt;
	q[10] = (Sint32)black;
	return true;
}

void HdGpuWorld::forget()
{
	_on = false;
	_world = nullptr;
	if (_impl)
	{
		_impl->dirty = true;
	}
}

void HdGpuWorld::release()
{
	_on = false;
	if (_impl)
	{
		_impl->release();
	}
}

#endif

}
