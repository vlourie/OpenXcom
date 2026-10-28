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
#include "HdGpuCanvas.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <set>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include "HdCanvas.h"
#include "HdGpu.h"
#include "HdGpuGl.h"
#include "HdGpuAtlas.h"
#include "HdWorkers.h"
#include "Logger.h"

namespace OpenXcom
{

#ifdef __NO_OPENGL

struct HdGpuCanvas::Target {};
struct HdGpuCanvas::Prepared {};
HdGpuCanvas &HdGpuCanvas::instance() { static HdGpuCanvas one; return one; }
bool HdGpuCanvas::run(Canvas32 &) { return false; }
void HdGpuCanvas::take(Canvas32 &, bool) {}
void HdGpuCanvas::drawnByCpu(Canvas32 &) {}
unsigned HdGpuCanvas::texture(const Canvas32 &) const { return 0; }
bool HdGpuCanvas::verifying() const { return false; }
void HdGpuCanvas::verify(Canvas32 &) {}
void HdGpuCanvas::forget(Canvas32 &) {}
void HdGpuCanvas::release() {}
HdGpuCanvas::Target *HdGpuCanvas::targetFor(Canvas32 &) { return nullptr; }
bool HdGpuCanvas::prepare(Canvas32 &, Target &, Prepared &) { return false; }
void HdGpuCanvas::draw(Canvas32 &, Target &, Prepared &) {}

#else

namespace
{

using hdgl::gl;
using hdgl::Atlas;
using hdgl::Place;

/// The command kinds of the program (the first value of a command's second texel).
enum Op { OP_FILL, OP_BACKDROP, OP_BLIT, OP_SCALED, OP_HD, OP_HD_LIT, OP_VAPOR_SOFT, OP_FLASH };

// one quad per command out of six vertex numbers (no vertex buffer): its rectangle is the command's first texel;
// canvas row 0 is the framebuffer's row 0, so the frame reads back top row first
const char *const VERTEX_SHADER =
	"#version 330\n"
	"uniform isamplerBuffer cmds;\n"
	"uniform vec2 size;\n"
	"flat out int cmd;\n"
	"void main()\n"
	"{\n"
	"	int q = gl_VertexID / 6, c = gl_VertexID % 6;\n"
	"	ivec4 r = texelFetch(cmds, q * 4);\n"
	"	bool right = c == 1 || c == 3 || c == 4, low = c == 2 || c == 4 || c == 5;\n"
	"	cmd = q;\n"
	"	gl_Position = vec4(vec2(right ? r.z : r.x, low ? r.w : r.y) / size * 2.0 - 1.0, 0.0, 1.0);\n"
	"}\n";

// the strips of Canvas32 (execute and the do* routines) in integers: the same pixel, byte for byte; the straight
// alpha of the HD frames is the blending of the card, (s * a + d * (255 - a)) / 255 rounded as the strips round it
const char *const FRAGMENT_SHADER =
	"#version 330\n"
	"#define FILL 0\n"
	"#define BACKDROP 1\n"
	"#define BLIT 2\n"
	"#define SCALED 3\n"
	"#define HD 4\n"
	"#define HD_LIT 5\n"
	"#define VAPOR_SOFT 6\n"
	"#define FLASH 7\n"
	"flat in int cmd;\n"
	"uniform sampler2DArray atlas;\n"
	"uniform sampler2D stream;\n"
	"uniform sampler2D under;\n"
	"uniform isamplerBuffer cmds;\n"
	"uniform usampler2D luts;\n"
	"uniform int extras;\n"
	"uniform uint probe;\n"
	"out vec4 color;\n"
	"uvec4 bytes(vec4 v) { return uvec4(v * 255.0 + 0.5); }\n"
	// rows of the tables: 0 the palette's pixels, 1 its colours (0xRRGGBB), 2 luminance -> ramp level, 3 + 17 c + s the tone curves
	"uint lut(int row, uint i) { return texelFetch(luts, ivec2(int(i), row), 0).r; }\n"
	"uint tone(int c, int s, uint m) { return lut(3 + c * 17 + s, m); }\n"
	"uvec3 rgb(uint p) { return uvec3(p >> 16u, p >> 8u, p) & 255u; }\n"
	// probe (OXCE_HD_GPU_CANVAS=probe): the lowest bit of blue flipped, the control of the dump comparison
	"void put(uvec3 c, uint a) { color = vec4(vec3(c ^ uvec3(0u, 0u, probe)) / 255.0, float(a) / 255.0); }\n"
	// Canvas32::classicTable: StandardShade, or helper::ColorReplace with a colour group
	"uint classic(uint i, int shade, int nbc)\n"
	"{\n"
	"	uint s;\n"
	"	if (nbc != 0)\n"
	"	{\n"
	"		uint n = ((i & 15u) + uint(shade)) & 255u;\n"
	"		s = (n & 0xF0u) != 0u ? 15u : (((uint(nbc - 1) << 4u) | n) & 255u);\n"
	"	}\n"
	"	else\n"
	"	{\n"
	"		uint n = (i + uint(shade)) & 255u;\n"
	"		s = ((n ^ i) & 0xF0u) != 0u ? 15u : n;\n"
	"	}\n"
	"	return lut(0, s);\n"
	"}\n"
	"uint node(int at, int n) { return uint(texelFetch(cmds, at + n / 4)[n % 4]); }\n"
	"void main()\n"
	"{\n"
	"	ivec2 d = ivec2(gl_FragCoord.xy);\n"
	"	int b = cmd * 4;\n"
	"	ivec4 t1 = texelFetch(cmds, b + 1);\n"
	"	ivec4 t2 = texelFetch(cmds, b + 2);\n"
	"	ivec4 t3 = texelFetch(cmds, b + 3);\n"
	"	int op = t1.x;\n"
	"	if (op == FILL)\n"
	"	{\n"
	"		put(rgb(uint(t2.x)), 255u);\n"
	"		return;\n"
	"	}\n"
	"	if (op == BACKDROP)\n"
	"	{\n"
	"		int pos = ((2 * d.y + 1) * 512) / (2 * t2.w);\n"
	"		int w = pos >= 256 ? min(pos - 256, 256) : pos;\n"
	"		uvec3 a = rgb(uint(pos >= 256 ? t2.y : t2.x)), c = rgb(uint(pos >= 256 ? t2.z : t2.y));\n"
	"		put((a * uint(256 - w) + c * uint(w) + 128u) >> 8u, 255u);\n"
	"		return;\n"
	"	}\n"
	"	if (op == FLASH)\n"
	"	{\n"
	"		uvec3 c = bytes(texelFetch(under, d, 0)).rgb;\n"
	"		put(255u - (255u - c) / 4u, 255u);\n"
	"		return;\n"
	"	}\n"
	"	if (op == VAPOR_SOFT)\n"
	"	{\n"
	"		int px = d.x * 16 + 8 - t2.x, py = d.y * 16 + 8 - t2.y;\n"
	"		int d2 = px * px + py * py;\n"
	"		if (d2 >= t2.z) discard;\n"
	"		int q = ((t2.z - d2) * t2.w) >> 16;\n"
	"		int m = (q * q) >> 8;\n"
	"		if (m <= 0) discard;\n"
	"		ivec3 c = ivec3(bytes(texelFetch(under, d, 0)).rgb);\n"
	"		ivec3 t = min(ivec3(255), c * t3.w / 255 + t3.xyz);\n"
	"		put(uvec3(c + (((t - c) * m) >> 8)), 255u);\n"
	"		return;\n"
	"	}\n"
	"	ivec2 s = (d - t1.yz) / t2.z + t2.xy;\n"
	"	if (op == BLIT || op == SCALED)\n"
	"	{\n"
	"		uint i = op == BLIT ? bytes(texelFetch(atlas, ivec3(s, t1.w), 0)).r : bytes(texelFetch(stream, s, 0)).r;\n"
	"		if (i == 0u) discard;\n"
	"		put(rgb(classic(i, t3.x, t3.y)), 255u);\n"
	"		return;\n"
	"	}\n"
	"	uvec4 p = bytes(texelFetch(atlas, ivec3(s, t1.w), 0));\n"
	"	if (p.a == 0u) discard;\n"
	"	uvec3 c = p.rgb;\n"
	"	uint m = max(c.r, max(c.g, c.b));\n"
	"	if (op == HD)\n"
	"	{\n"
	"		int shade = t3.x, nbc = t3.y;\n"
	"		if (nbc != 0)\n"
	"		{\n"
	"			uint lum = (c.r * 77u + c.g * 151u + c.b * 28u) >> 8u;\n"
	"			int n = int(lut(2, lum)) + shade;\n"
	"			c = rgb(lut(1, n > 15 ? 15u : (((uint(nbc - 1) << 4u) & 255u) | uint(n))));\n"
	"		}\n"
	"		else if (shade != 0)\n"
	"		{\n"
	"			c = (c * uvec3(tone(0, shade, m), tone(1, shade, m), tone(2, shade, m)) + 32768u) >> 16u;\n"
	"		}\n"
	"	}\n"
	"	else\n"
	"	{\n"
	// Canvas32::LitOf: the four nodes of the pixel's quadrant, the shade and the light colour between them
	"		int e = extras + t2.w;\n"
	"		ivec4 e0 = texelFetch(cmds, e);\n"
	"		ivec4 flags = texelFetch(cmds, e + 7);\n"
	"		ivec2 o = d - t1.yz;\n"
	"		uvec4 w = bytes(texelFetch(atlas, ivec3(e0.y + o.x, e0.z + o.y, e0.x), 0));\n"
	"		uint q = bytes(texelFetch(atlas, ivec3(e0.y + e0.w + o.x, e0.z + o.y, e0.x), 0)).r;\n"
	"		int n0 = int(q >> 1u) * 3 + int(q & 1u), n1 = n0 + 1, n2 = n0 + 4, n3 = n0 + 3;\n"
	"		uint shade8 = (w.x * node(e + 1, n0) + w.y * node(e + 1, n1) + w.z * node(e + 1, n2) + w.w * node(e + 1, n3)) >> 8u;\n"
	"		int s0 = min(16, int(shade8 >> 8u)), s1 = min(16, s0 + 1), frac = int(shade8 & 255u);\n"
	"		uvec3 tn0 = rgb(node(e + 4, n0)), tn1 = rgb(node(e + 4, n1)), tn2 = rgb(node(e + 4, n2)), tn3 = rgb(node(e + 4, n3));\n"
	"		uvec3 tf = rgb(node(e + 4, 4)) + 1u;\n"
	"		uvec3 f;\n"
	"		for (int ch = 0; ch < 3; ++ch)\n"
	"		{\n"
	"			int fa = int(tone(ch, s0, m)), fb = int(tone(ch, s1, m));\n"
	"			uint v = uint(fa + (((fb - fa) * frac) >> 8));\n"
	"			if (flags.y == 0)\n"
	"			{\n"
	"				if (flags.x != 0)\n"
	"				{\n"
	"					v = (v * tf[ch]) >> 8u;\n"
	"				}\n"
	"				else\n"
	"				{\n"
	"					uint t = (w.x * tn0[ch] + w.y * tn1[ch] + w.z * tn2[ch] + w.w * tn3[ch]) >> 8u;\n"
	"					v = (v * (t + 1u)) >> 8u;\n"
	"				}\n"
	"			}\n"
	"			f[ch] = v;\n"
	"		}\n"
	"		c = (c * f + 32768u) >> 16u;\n"
	"	}\n"
	"	put(c, p.a);\n"
	"}\n";

/// The environment switch is set to something else than "0" (or unset and `fallback`).
bool envOn(const char *name, bool fallback)
{
	const char *v = std::getenv(name);
	return v && *v ? std::strcmp(v, "0") != 0 : fallback;
}

/// Says once per reason why the processor draws the canvas (or what the card does).
void tellOnce(const std::string &what)
{
	static std::set<std::string> told;
	if (told.insert(what).second)
	{
		Log(LOG_INFO) << "HD GPU canvas: " << what;
	}
}

/// FNV-1a of rows of bytes (OXCE_HD_GPU_CHECK: is the card's copy of a frame still the frame).
Uint64 hashRows(const void *data, int rowBytes, int rows, int pitch)
{
	Uint64 h = 1469598103934665603ull;
	for (int y = 0; y < rows; ++y)
	{
		const Uint8 *p = (const Uint8 *)data + (size_t)y * pitch;
		for (int x = 0; x < rowBytes; ++x)
		{
			h = (h ^ p[x]) * 1099511628211ull;
		}
	}
	return h;
}

/// Where a frame is in the texture array.
/// A palette frame in the atlas: its pixel buffer, size and pitch (the frames are kept while the battle lasts,
/// like the span tables of Canvas32 keyed the same way).
struct IndexedKey
{
	const void *buffer;
	int w, h, pitch;
	bool operator==(const IndexedKey &o) const { return buffer == o.buffer && w == o.w && h == o.h && pitch == o.pitch; }
};
struct IndexedKeyHash
{
	size_t operator()(const IndexedKey &k) const
	{
		return std::hash<const void *>()(k.buffer) ^ ((size_t)k.w * 0x9E3779B9u) ^ ((size_t)k.h << 20) ^ ((size_t)k.pitch << 40);
	}
};

/// What every canvas shares: the program, the atlas, the commands' buffer, the per-flush texture of classic elements.
struct Shared
{
	bool built = false, failed = false;
	GLuint program = 0, vao = 0, cmdBuffer = 0, cmdTexture = 0, stream = 0;
	int streamW = 0, streamH = 0;
	GLint sizeAt = -1, extrasAt = -1, probeAt = -1;
	bool probe = false;
	GLint maxTexels = 0;
	size_t cmdBytes = 0;
	bool check = false, sync = false, verify = false;
	/// OXCE_HD_GPU_VERIFY: flushes compared, and those that differed.
	long long verified = 0, differed = 0;
	Atlas atlas;
	std::unordered_map<IndexedKey, Uint64, IndexedKeyHash> indexed;
	std::unordered_map<Uint32, Uint64> weights;
	/// Flushes drawn by the card, and by the processor while a canvas had a framebuffer (for the frame log).
	unsigned long long cardFlushes = 0;
	/// OXCE_HD_GPU_STATS: a line every 5 s - flushes, commands, copies of the canvas, uploads, the wait for frames.
	struct Stats
	{
		bool on = false;
		std::chrono::steady_clock::time_point since;
		long long flushes = 0, cmds = 0, copies = 0, maxCopies = 0, uploads = 0, uploadBytes = 0, grows = 0, resets = 0;
		double prepareMs = 0, drawMs = 0, waitMs = 0, maxPrepareMs = 0, maxDrawMs = 0, maxWaitMs = 0;
	} stats;

	bool build()
	{
		built = true;
		check = envOn("OXCE_HD_GPU_CHECK", false);
		sync = envOn("OXCE_HD_GPU_SYNC", false);
		const char *mode = std::getenv("OXCE_HD_GPU_CANVAS");
		probe = mode && std::strcmp(mode, "probe") == 0;
		stats.on = envOn("OXCE_HD_GPU_STATS", false);
		verify = envOn("OXCE_HD_GPU_VERIFY", false);
		stats.since = std::chrono::steady_clock::now();
		program =hdgl::program(VERTEX_SHADER, FRAGMENT_SHADER, "the battle canvas");
		if (!program)
		{
			failed = true;
			return false;
		}
		gl.UseProgram(program);
		gl.Uniform1i(gl.GetUniformLocation(program, "atlas"), 0);
		gl.Uniform1i(gl.GetUniformLocation(program, "stream"), 1);
		gl.Uniform1i(gl.GetUniformLocation(program, "under"), 2);
		gl.Uniform1i(gl.GetUniformLocation(program, "cmds"), 3);
		gl.Uniform1i(gl.GetUniformLocation(program, "luts"), 4);
		sizeAt = gl.GetUniformLocation(program, "size");
		extrasAt = gl.GetUniformLocation(program, "extras");
		probeAt = gl.GetUniformLocation(program, "probe");
		gl.UseProgram(0);
		gl.GenVertexArrays(1, &vao);
		gl.GenBuffers(1, &cmdBuffer);
		gl.BindBuffer(GL_TEXTURE_BUFFER, cmdBuffer);
		gl.BufferData(GL_TEXTURE_BUFFER, 64, nullptr, GL_STREAM_DRAW);
		gl.BindBuffer(GL_TEXTURE_BUFFER, 0);
		cmdBytes = 64;
		glGenTextures(1, &cmdTexture);
		gl.ActiveTexture(GL_TEXTURE0 + 3);
		glBindTexture(GL_TEXTURE_BUFFER, cmdTexture);
		gl.TexBuffer(GL_TEXTURE_BUFFER, GL_RGBA32I, cmdBuffer);
		glBindTexture(GL_TEXTURE_BUFFER, 0);
		gl.ActiveTexture(GL_TEXTURE0);
		glGetIntegerv(GL_MAX_TEXTURE_BUFFER_SIZE, &maxTexels);
		GLint maxSize = 0, maxArray = 0;
		glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxSize);
		glGetIntegerv(GL_MAX_ARRAY_TEXTURE_LAYERS, &maxArray);
		atlas.page = std::min(2048, (int)maxSize);
		// OXCE_HD_GPU_ATLAS_MB: the most the frames take on the card (512 MB: the units, the terrain and the shaded
		// copies of a big view; a bigger array costs seconds to make - 64 layers took 5.5 s on an RTX 5090)
		const char *mb = std::getenv("OXCE_HD_GPU_ATLAS_MB");
		const long long budget = (mb && std::atoi(mb) > 0 ? std::atoi(mb) : 512) * (1LL << 20);
		const long long layerBytes = (long long)atlas.page * atlas.page * 4;
		atlas.maxLayers = (int)std::max(1LL, std::min((long long)maxArray, budget / layerBytes));
		if (atlas.page < 512 || !atlas.create(std::min(4, atlas.maxLayers)) || glGetError() != GL_NO_ERROR)
		{
			Log(LOG_ERROR) << "HD GPU canvas: no texture array of " << atlas.page << "x" << atlas.page << " - the processor draws the battle canvas";
			failed = true;
			return false;
		}
		Log(LOG_INFO) << "HD GPU canvas: on, frames in " << atlas.page << "x" << atlas.page << " layers (" << atlas.layers.size()
			<< ", up to " << atlas.maxLayers << "), " << maxTexels << " command texels" << (check ? ", frames checked on every use" : "")
			<< (sync ? ", read back at once" : ", read back a frame late");
		return true;
	}
	/// The per-flush texture of classic elements at least w x h.
	bool streamFor(int w, int h)
	{
		if (w <= streamW && h <= streamH)
		{
			return true;
		}
		const int nw = std::max(w, streamW), nh = std::max(h, std::max(streamH, 256));
		if (!stream)
		{
			glGenTextures(1, &stream);
		}
		while (glGetError() != GL_NO_ERROR) {}
		gl.ActiveTexture(GL_TEXTURE0 + 1);
		glBindTexture(GL_TEXTURE_2D, stream);
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, nw, nh, 0, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
		glBindTexture(GL_TEXTURE_2D, 0);
		gl.ActiveTexture(GL_TEXTURE0);
		if (glGetError() != GL_NO_ERROR)
		{
			streamW = streamH = 0;
			return false;
		}
		streamW = nw;
		streamH = nh;
		return true;
	}
	void release()
	{
		if (program) gl.DeleteProgram(program);
		if (vao) gl.DeleteVertexArrays(1, &vao);
		if (cmdBuffer) gl.DeleteBuffers(1, &cmdBuffer);
		if (cmdTexture) glDeleteTextures(1, &cmdTexture);
		if (stream) glDeleteTextures(1, &stream);
		program = vao = cmdBuffer = cmdTexture = stream = 0;
		streamW = streamH = 0;
		atlas.release();
		indexed.clear();
		weights.clear();
		built = failed = false;
	}
};

Shared shared;

/// The rows of the tables the program reads (see lut in the fragment shader).
const int LUT_ROWS = 3 + 3 * 17;

bool signaled(void *fence, bool flush)
{
	const GLenum r = gl.ClientWaitSync(fence, flush ? GL_SYNC_FLUSH_COMMANDS_BIT : 0, 0);
	return r == GL_ALREADY_SIGNALED || r == GL_CONDITION_SATISFIED || r == GL_WAIT_FAILED;
}

void waitFor(void *fence)
{
	if (signaled(fence, true))
	{
		return;
	}
	while (!signaled(fence, false))
	{
		std::this_thread::yield();
	}
}

}

/**
 * The canvas's framebuffer: its picture on the card, a copy of a part of it for the commands that read what is
 * under them, the tables of its palette and the pixel buffers its frames are read back through.
 */
struct HdGpuCanvas::Target
{
	Canvas32 *canvas = nullptr;
	int w = 0, h = 0;
	GLuint texture = 0, fbo = 0, under = 0, lut = 0;
	std::vector<Uint32> lutData;
	GLuint pbos[3] = { 0, 0, 0 };
	/// Frames on their way back, oldest first: the pixel buffer and its fence.
	struct Readback { int pbo; void *fence; };
	std::deque<Readback> pending;
	/// The framebuffer holds the canvas's picture (false: the processor drew it last, or nothing yet).
	bool valid = false;
	/// Drawn since the last read back.
	bool dirty = false;
	/// The processor drew the canvas off the GL thread: the frames on their way are older than its pixels.
	bool dropPending = false;

	void dropAll()
	{
		for (Readback &r : pending)
		{
			gl.DeleteSync(r.fence);
		}
		pending.clear();
		dropPending = false;
	}
	void releaseGl()
	{
		dropAll();
		if (fbo) gl.DeleteFramebuffers(1, &fbo);
		if (texture) glDeleteTextures(1, &texture);
		if (under) glDeleteTextures(1, &under);
		if (lut) glDeleteTextures(1, &lut);
		if (pbos[0]) gl.DeleteBuffers(3, pbos);
		fbo = texture = under = lut = 0;
		pbos[0] = pbos[1] = pbos[2] = 0;
	}
	/// Starts reading the framebuffer into a free pixel buffer.
	void readBack()
	{
		if (pending.size() >= 2)
		{
			gl.DeleteSync(pending.front().fence);
			pending.pop_front();
		}
		int free = 0;
		for (; free < 3; ++free)
		{
			bool busy = false;
			for (const Readback &r : pending)
			{
				busy = busy || r.pbo == free;
			}
			if (!busy)
			{
				break;
			}
		}
		gl.BindFramebuffer(GL_READ_FRAMEBUFFER, fbo);
		gl.BindBuffer(GL_PIXEL_PACK_BUFFER, pbos[free]);
		glPixelStorei(GL_PACK_ROW_LENGTH, 0);
		glPixelStorei(GL_PACK_ALIGNMENT, 4);
		glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
		gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
		gl.BindFramebuffer(GL_READ_FRAMEBUFFER, 0);
		pending.push_back(Readback{ free, gl.FenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0) });
		glFlush();
		dirty = false;
	}
};

/// One flush made ready for the card: the commands as texels, the frames to upload first.
struct HdGpuCanvas::Prepared
{
	/// 4 texels of 4 ints per command: the rectangle, then what the op needs (see the fragment shader).
	std::vector<Sint32> data;
	/// The light fields of the lit commands (8 texels each), after the commands.
	std::vector<Sint32> extras;
	/// Per command: it reads the canvas under it (vapor, flash).
	std::vector<Uint8> reads;
	enum Kind { UP_HD, UP_INDEXED, UP_WEIGHTS };
	struct Upload
	{
		Kind kind;
		const void *src;
		int pitch;
		int layer, x, y, w, h;
	};
	std::vector<Upload> uploads;
	/// Classic elements of this flush in the stream texture: arena offset, place.
	struct StreamUpload { size_t arena; int x, y, w, h; };
	std::vector<StreamUpload> streamUploads;
	int streamX = 0, streamY = 0, streamRow = 0;
	/// The numbers placed by this flush (dropped again when it does not go to the card).
	std::vector<Uint64> fresh;
	std::vector<Uint8> scratch;
	/// The first command paints every pixel (the framebuffer need not hold the canvas before it).
	bool coversAll = false;
	/// Copies of the canvas the draw took for the commands that read it (OXCE_HD_GPU_STATS).
	int copies = 0;

	void clear()
	{
		data.clear();
		extras.clear();
		reads.clear();
		uploads.clear();
		streamUploads.clear();
		streamX = streamY = streamRow = 0;
		fresh.clear();
		coversAll = false;
	}
};

HdGpuCanvas &HdGpuCanvas::instance()
{
	static HdGpuCanvas one;
	return one;
}

HdGpuCanvas::Target *HdGpuCanvas::targetFor(Canvas32 &canvas)
{
	Target *t = nullptr;
	for (Target *each : _targets)
	{
		if (each->canvas == &canvas)
		{
			t = each;
		}
	}
	if (t && t->w == canvas._width && t->h == canvas._height)
	{
		return t;
	}
	if (t)
	{
		forget(canvas);
	}
	t = new Target();
	t->canvas = &canvas;
	t->w = canvas._width;
	t->h = canvas._height;
	while (glGetError() != GL_NO_ERROR) {}
	GLuint made[3];
	glGenTextures(3, made);
	t->texture = made[0];
	t->under = made[1];
	t->lut = made[2];
	gl.ActiveTexture(GL_TEXTURE0);
	for (GLuint tex : { t->texture, t->under })
	{
		glBindTexture(GL_TEXTURE_2D, tex);
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, t->w, t->h, 0, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	}
	glBindTexture(GL_TEXTURE_2D, t->lut);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_R32UI, 256, LUT_ROWS, 0, GL_RED_INTEGER, GL_UNSIGNED_INT, nullptr);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	glBindTexture(GL_TEXTURE_2D, 0);
	gl.GenFramebuffers(1, &t->fbo);
	gl.BindFramebuffer(GL_FRAMEBUFFER, t->fbo);
	gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t->texture, 0);
	const GLenum status = gl.CheckFramebufferStatus(GL_FRAMEBUFFER);
	// the alpha bytes are never drawn: zero, as in the canvas's surface
	glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
	glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
	glClear(GL_COLOR_BUFFER_BIT);
	gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
	gl.GenBuffers(3, t->pbos);
	for (GLuint pbo : t->pbos)
	{
		gl.BindBuffer(GL_PIXEL_PACK_BUFFER, pbo);
		gl.BufferData(GL_PIXEL_PACK_BUFFER, (std::ptrdiff_t)t->w * t->h * 4, nullptr, GL_STREAM_READ);
	}
	gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
	const GLenum error = glGetError();
	if (status != GL_FRAMEBUFFER_COMPLETE || error != GL_NO_ERROR)
	{
		tellOnce("no framebuffer of " + std::to_string(t->w) + "x" + std::to_string(t->h) + " - the processor draws the canvas");
		t->releaseGl();
		delete t;
		return nullptr;
	}
	_targets.push_back(t);
	return t;
}

bool HdGpuCanvas::run(Canvas32 &canvas)
{
	static const bool wanted = envOn("OXCE_HD_GPU_CANVAS", true);
	if (!wanted || canvas._hdMode == HD_MODE_NEAREST || !HdGpu::instance().current())
	{
		return false;
	}
	if (!canvas._argbLayout)
	{
		tellOnce("the canvas is not 0RGB - the processor draws it");
		return false;
	}
	if (!shared.built)
	{
		shared.build();
	}
	if (shared.failed)
	{
		return false;
	}
	Target *t = targetFor(canvas);
	if (!t)
	{
		return false;
	}
	if (t->dropPending)
	{
		t->dropAll();
	}
	static Prepared prepared;
	const auto t0 = std::chrono::steady_clock::now();
	if (!prepare(canvas, *t, prepared))
	{
		return false;
	}
	const auto t1 = std::chrono::steady_clock::now();
	draw(canvas, *t, prepared);
	if (shared.stats.on)
	{
		Shared::Stats &s = shared.stats;
		const auto t2 = std::chrono::steady_clock::now();
		const double prepareMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
		const double drawMs = std::chrono::duration<double, std::milli>(t2 - t1).count();
		++s.flushes;
		s.cmds += (long long)prepared.reads.size();
		s.copies += prepared.copies;
		s.maxCopies = std::max(s.maxCopies, (long long)prepared.copies);
		s.uploads += (long long)prepared.uploads.size();
		for (const Prepared::Upload &u : prepared.uploads)
		{
			s.uploadBytes += (long long)u.w * u.h * 4;
		}
		s.prepareMs += prepareMs;
		s.drawMs += drawMs;
		s.maxPrepareMs = std::max(s.maxPrepareMs, prepareMs);
		s.maxDrawMs = std::max(s.maxDrawMs, drawMs);
		if (t2 - s.since >= std::chrono::seconds(5))
		{
			const double f = (double)std::max(1LL, s.flushes);
			Log(LOG_INFO) << "HD GPU canvas stats: " << s.flushes << " flushes, " << s.cmds / s.flushes << " commands, "
				<< s.copies / f << " copies (max " << s.maxCopies << "), " << s.uploads << " uploads (" << (s.uploadBytes >> 10)
				<< " KB), " << s.grows << " grows, " << s.resets << " emptied; prepare " << s.prepareMs / f << " ms (max " << s.maxPrepareMs << "), draw "
				<< s.drawMs / f << " ms (max " << s.maxDrawMs << "), wait for frames " << s.waitMs << " ms (max " << s.maxWaitMs << ")";
			const bool on = s.on;
			s = Shared::Stats();
			s.on = on;
			s.since = t2;
		}
	}
	if (!shared.cardFlushes++)
	{
		tellOnce("the first flush drawn by the card: " + std::to_string(prepared.reads.size()) + " command(s), " +
			std::to_string(prepared.uploads.size()) + " frame(s) uploaded" + (shared.probe ? ", probe on" : ""));
	}
	return true;
}

bool HdGpuCanvas::prepare(Canvas32 &canvas, Target &target, Prepared &p)
{
	(void)target;
	typedef Canvas32::Cmd Cmd;
	Atlas &atlas = shared.atlas;
	const int W = canvas._width, H = canvas._height;
	const int page = atlas.page;
	++atlas.clock;
	bool emptied = false;
	for (int attempt = 0; attempt < 8; ++attempt)
	{
		p.clear();
		bool grow = false, full = false, fail = false;
		std::string why;
		// a frame in the atlas under its number: uploaded now when it is not there
		auto placeFor = [&](Uint64 &id, int w, int h, Prepared::Kind kind, const void *src, int pitch, Uint64 hash) -> const Place *
		{
			Place *at = atlas.find(id);
			if (at && shared.check && at->hash != hash)
			{
				tellOnce("a frame changed under its copy on the card (made anew)");
				at = nullptr;
			}
			if (at)
			{
				return at;
			}
			if (w > page || h > page)
			{
				why = "a frame of " + std::to_string(w) + "x" + std::to_string(h) + " does not fit a layer";
				fail = true;
				return nullptr;
			}
			Uint64 made = 0;
			const Atlas::Result r = atlas.place(w, h, made);
			if (r != Atlas::PLACED)
			{
				if (r == Atlas::GROW)
				{
					grow = true;
				}
				else
				{
					full = true;
				}
				return nullptr;
			}
			id = made;
			p.fresh.push_back(made);
			Place &pl = atlas.places[made];
			pl.hash = hash;
			p.uploads.push_back(Prepared::Upload{ kind, src, pitch, pl.layer, pl.x, pl.y, w, h });
			return &pl;
		};
		for (const Cmd &cmd : canvas._cmds)
		{
			if (grow || full || fail)
			{
				break;
			}
			// the rows the strips give the command, clipped as execute clips them
			int x0 = 0, x1 = W, y0 = cmd.y0, y1 = cmd.y1;
			const bool clipped = cmd.type != Cmd::FILL && cmd.type != Cmd::FILL_BACKDROP && cmd.type != Cmd::FLASH;
			if (clipped)
			{
				y0 = std::max(y0, cmd.clip.beg_y);
				y1 = std::min(y1, cmd.clip.end_y);
				x0 = std::max(0, cmd.clip.beg_x);
				x1 = std::min(W, cmd.clip.end_x);
			}
			Sint32 q[16] = {};
			switch (cmd.type)
			{
			case Cmd::FILL:
				q[4] = OP_FILL;
				q[8] = (Sint32)canvas._lut[cmd.color];
				break;
			case Cmd::FILL_BACKDROP:
				q[4] = OP_BACKDROP;
				for (int i = 0; i < 3; ++i)
				{
					q[8 + i] = (cmd.backdrop[i][0] << 16) | (cmd.backdrop[i][1] << 8) | cmd.backdrop[i][2];
				}
				q[11] = H;
				break;
			case Cmd::FLASH:
				q[4] = OP_FLASH;
				break;
			case Cmd::BLIT:
			{
				const int w = cmd.src.getWidth(), h = cmd.src.getHeight();
				x0 = std::max({ x0, cmd.srcDomain.beg_x + cmd.x, cmd.x });
				x1 = std::min({ x1, cmd.srcDomain.end_x + cmd.x, cmd.x + w });
				y0 = std::max({ y0, cmd.srcDomain.beg_y + cmd.y, cmd.y, 0 });
				y1 = std::min({ y1, cmd.srcDomain.end_y + cmd.y, cmd.y + h, H });
				if (x0 >= x1 || y0 >= y1)
				{
					continue;
				}
				const IndexedKey key{ cmd.src.getBuffer(), w, h, cmd.src.getPitch() };
				Uint64 &id = shared.indexed[key];
				const Place *pl = placeFor(id, w, h, Prepared::UP_INDEXED, key.buffer, key.pitch,
					shared.check ? hashRows(key.buffer, w, h, key.pitch) : 0);
				if (!pl)
				{
					continue;
				}
				q[4] = OP_BLIT; q[5] = cmd.x; q[6] = cmd.y; q[7] = pl->layer;
				q[8] = pl->x; q[9] = pl->y; q[10] = 1;
				q[12] = cmd.shade; q[13] = cmd.newBaseColor;
				break;
			}
			case Cmd::BLIT_SCALED:
			{
				const int w = cmd.srcW, h = cmd.srcH;
				x0 = std::max({ x0, cmd.x });
				x1 = std::min({ x1, cmd.x + w * cmd.scale });
				y0 = std::max({ y0, cmd.y, 0 });
				y1 = std::min({ y1, cmd.y + h * cmd.scale, H });
				if (x0 >= x1 || y0 >= y1 || w <= 0 || h <= 0)
				{
					continue;
				}
				if (w > page)
				{
					why = "a classic element " + std::to_string(w) + " wide";
					fail = true;
					continue;
				}
				// shelves of the stream texture, laid out anew every flush
				if (p.streamX + w > page)
				{
					p.streamY += p.streamRow;
					p.streamX = p.streamRow = 0;
				}
				if (p.streamY + h > page)
				{
					why = "the classic elements of one flush do not fit their texture";
					fail = true;
					continue;
				}
				p.streamUploads.push_back(Prepared::StreamUpload{ cmd.arena, p.streamX, p.streamY, w, h });
				q[4] = OP_SCALED; q[5] = cmd.x; q[6] = cmd.y;
				q[8] = p.streamX; q[9] = p.streamY; q[10] = cmd.scale;
				q[12] = cmd.shade; q[13] = cmd.newBaseColor;
				p.streamX += w;
				p.streamRow = std::max(p.streamRow, h);
				break;
			}
			case Cmd::BLIT_HD:
			case Cmd::BLIT_HD_LIT:
			{
				const HdFrame &hd = *cmd.hd;
				x0 = std::max({ x0, cmd.srcDomain.beg_x + cmd.x, cmd.x });
				x1 = std::min({ x1, cmd.srcDomain.end_x + cmd.x, hd.width + cmd.x });
				y0 = std::max({ y0, cmd.srcDomain.beg_y + cmd.y, cmd.y, 0 });
				y1 = std::min({ y1, cmd.srcDomain.end_y + cmd.y, hd.height + cmd.y, H });
				if (x0 >= x1 || y0 >= y1 || hd.pixels.size() < (size_t)hd.width * hd.height)
				{
					continue;
				}
				const Place *pl = placeFor(hd.gpu.id, hd.width, hd.height, Prepared::UP_HD, &hd, hd.width * 4,
					shared.check ? hashRows(hd.pixels.data(), hd.width * 4, hd.height, hd.width * 4) : 0);
				if (!pl)
				{
					continue;
				}
				q[5] = cmd.x; q[6] = cmd.y; q[7] = pl->layer;
				q[8] = pl->x; q[9] = pl->y; q[10] = 1;
				if (cmd.type == Cmd::BLIT_HD)
				{
					q[4] = OP_HD;
					q[12] = std::max(0, std::min(16, (int)cmd.shade));
					q[13] = cmd.newBaseColor;
					break;
				}
				// the weights of the frame's size: the processor draws nothing without them (built when recorded)
				const Uint32 wkey = ((Uint32)hd.width << 16) | (Uint32)hd.height;
				auto wit = canvas._lightWeights.find(wkey);
				if (wit == canvas._lightWeights.end())
				{
					continue;
				}
				if (hd.width * 2 > page)
				{
					why = "a lit frame " + std::to_string(hd.width) + " wide";
					fail = true;
					continue;
				}
				const Place *wp = placeFor(shared.weights[wkey], hd.width * 2, hd.height, Prepared::UP_WEIGHTS,
					wit->second.w.data(), hd.width * 5, 0);
				if (!wp)
				{
					continue;
				}
				q[4] = OP_HD_LIT;
				q[11] = (Sint32)p.extras.size() / 4;
				const size_t e = p.extras.size();
				p.extras.resize(e + 8 * 4, 0);
				Sint32 *x = &p.extras[e];
				x[0] = wp->layer; x[1] = wp->x; x[2] = wp->y; x[3] = hd.width;
				for (int n = 0; n < HdLight::NODES; ++n)
				{
					x[4 + n] = cmd.lightShade[n];
					x[16 + n] = (cmd.lightTint[n][0] << 16) | (cmd.lightTint[n][1] << 8) | cmd.lightTint[n][2];
				}
				const bool white = cmd.tintFlat && cmd.lightTint[4][0] == 255 && cmd.lightTint[4][1] == 255 && cmd.lightTint[4][2] == 255;
				x[28] = cmd.tintFlat ? 1 : 0;
				x[29] = white ? 1 : 0;
				break;
			}
			case Cmd::VAPOR_SOFT:
			{
				const int r16 = Canvas32::vaporSoftRadius16(cmd.size, cmd.scale);
				const int r2 = r16 * r16;
				y0 = std::max({ y0, ((cmd.y - r16) >> 4) - 1, 0 });
				y1 = std::min({ y1, ((cmd.y + r16) >> 4) + 2, H });
				x0 = std::max(x0, ((cmd.x - r16) >> 4) - 1);
				x1 = std::min(x1, ((cmd.x + r16) >> 4) + 2);
				q[4] = OP_VAPOR_SOFT;
				q[8] = cmd.x; q[9] = cmd.y; q[10] = r2; q[11] = (int)((256LL << 16) / r2);
				q[12] = cmd.tint.r; q[13] = cmd.tint.g; q[14] = cmd.tint.b; q[15] = cmd.tint.unused;
				break;
			}
			case Cmd::VAPOR:
				// the 2x2 patterns of mode 0 (the HD modes draw soft puffs)
				why = "vapor patterns";
				fail = true;
				continue;
			}
			if (x0 >= x1 || y0 >= y1)
			{
				continue;
			}
			q[0] = x0; q[1] = y0; q[2] = x1; q[3] = y1;
			if (p.data.empty())
			{
				p.coversAll = (cmd.type == Cmd::FILL || cmd.type == Cmd::FILL_BACKDROP) && x0 == 0 && y0 == 0 && x1 == W && y1 == H;
			}
			p.data.insert(p.data.end(), q, q + 16);
			p.reads.push_back(cmd.type == Cmd::VAPOR_SOFT || cmd.type == Cmd::FLASH ? 1 : 0);
		}
		const size_t texels = (p.data.size() + p.extras.size()) / 4;
		if (!fail && !grow && !full && shared.maxTexels > 0 && texels > (size_t)shared.maxTexels)
		{
			why = std::to_string(texels) + " command texels";
			fail = true;
		}
		if (!fail && !grow && !full && !p.streamUploads.empty() && !shared.streamFor(page, p.streamY + p.streamRow))
		{
			why = "no texture for the classic elements";
			fail = true;
		}
		if (grow)
		{
			// every layer holds frames of this flush: a bigger array, the frames there staying; those this attempt
			// placed went up with nothing - placed again
			for (Uint64 id : p.fresh)
			{
				atlas.drop(id);
			}
			if (atlas.grow(true))
			{
				tellOnce("frames in " + std::to_string(atlas.layers.size()) + " layers");
				++shared.stats.grows;
				continue;
			}
			why = "no bigger texture array";
			fail = true;
		}
		if (full)
		{
			// the array is as big as it may be and every layer holds frames of this flush: emptied once, only this
			// flush's frames go up again (packed together)
			if (!emptied)
			{
				atlas.empty();
				emptied = true;
				++shared.stats.resets;
				continue;
			}
			why = "the frames of one flush do not fit " + std::to_string(atlas.layers.size()) + " layers";
			fail = true;
		}
		if (!fail)
		{
			return true;
		}
		for (Uint64 id : p.fresh)
		{
			atlas.drop(id);
		}
		tellOnce(why + " - the processor draws such flushes");
		return false;
	}
	return false;
}

void HdGpuCanvas::draw(Canvas32 &canvas, Target &t, Prepared &p)
{
	// nothing asked of the driver here: a glGet waits for its whole queue (R-519, R-520); what comes after this sets
	// its own viewport and program (the world's compositor, HdGpu::present)
	gl.ActiveTexture(GL_TEXTURE0);
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	// the frames first seen
	glBindTexture(GL_TEXTURE_2D_ARRAY, shared.atlas.texture);
	for (const Prepared::Upload &u : p.uploads)
	{
		switch (u.kind)
		{
		case Prepared::UP_HD:
		{
			const HdFrame &hd = *(const HdFrame *)u.src;
			glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
			gl.TexSubImage3D(GL_TEXTURE_2D_ARRAY, 0, u.x, u.y, u.layer, u.w, u.h, 1, GL_BGRA, GL_UNSIGNED_BYTE, hd.pixels.data());
			break;
		}
		case Prepared::UP_INDEXED:
			glPixelStorei(GL_UNPACK_ROW_LENGTH, u.pitch);
			gl.TexSubImage3D(GL_TEXTURE_2D_ARRAY, 0, u.x, u.y, u.layer, u.w, u.h, 1, GL_RED, GL_UNSIGNED_BYTE, u.src);
			break;
		case Prepared::UP_WEIGHTS:
		{
			// the 5 bytes of a pixel: the node weights on the left half, the quadrant on the right
			const int fw = u.w / 2;
			p.scratch.assign((size_t)u.w * u.h * 4, 0);
			const Uint8 *src = (const Uint8 *)u.src;
			for (int y = 0; y < u.h; ++y)
			{
				Uint8 *row = &p.scratch[(size_t)y * u.w * 4];
				for (int x = 0; x < fw; ++x)
				{
					const Uint8 *wq = src + ((size_t)y * fw + x) * 5;
					std::memcpy(row + x * 4, wq + 1, 4);
					row[(fw + x) * 4] = wq[0];
				}
			}
			glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
			gl.TexSubImage3D(GL_TEXTURE_2D_ARRAY, 0, u.x, u.y, u.layer, u.w, u.h, 1, GL_RGBA, GL_UNSIGNED_BYTE, p.scratch.data());
			break;
		}
		}
	}
	glBindTexture(GL_TEXTURE_2D_ARRAY, 0);
	// the classic elements of this flush
	if (!p.streamUploads.empty())
	{
		glBindTexture(GL_TEXTURE_2D, shared.stream);
		for (const Prepared::StreamUpload &u : p.streamUploads)
		{
			glPixelStorei(GL_UNPACK_ROW_LENGTH, u.w);
			glTexSubImage2D(GL_TEXTURE_2D, 0, u.x, u.y, u.w, u.h, GL_RED, GL_UNSIGNED_BYTE, canvas._arena.data() + u.arena);
		}
	}
	// the palette's tables, when they changed
	std::vector<Uint32> &lut = t.lutData;
	static std::vector<Uint32> next;
	next.resize(256 * LUT_ROWS);
	std::memcpy(&next[0], canvas._lut, 256 * sizeof(Uint32));
	for (int i = 0; i < 256; ++i)
	{
		next[256 + i] = ((Uint32)canvas._colors[i].r << 16) | ((Uint32)canvas._colors[i].g << 8) | canvas._colors[i].b;
		next[512 + i] = canvas._level[i];
	}
	std::memcpy(&next[768], canvas._toneFactor, sizeof(canvas._toneFactor));
	if (lut != next)
	{
		lut = next;
		glBindTexture(GL_TEXTURE_2D, t.lut);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
		glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
		glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 256, LUT_ROWS, GL_RED_INTEGER, GL_UNSIGNED_INT, lut.data());
	}
	// the canvas the processor drew last goes up, unless the first command paints it all
	if (!t.valid && !p.coversAll)
	{
		SDL_Surface *s = canvas._surface.get();
		glBindTexture(GL_TEXTURE_2D, t.texture);
		glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, s->pitch / 4);
		glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, t.w, t.h, GL_BGRA, GL_UNSIGNED_BYTE, s->pixels);
	}
	glBindTexture(GL_TEXTURE_2D, 0);
	glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
	glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
	// the commands
	const size_t bytes = (p.data.size() + p.extras.size()) * sizeof(Sint32);
	gl.BindBuffer(GL_TEXTURE_BUFFER, shared.cmdBuffer);
	gl.BufferData(GL_TEXTURE_BUFFER, (std::ptrdiff_t)std::max<size_t>(bytes, 64), nullptr, GL_STREAM_DRAW);
	gl.BufferSubData(GL_TEXTURE_BUFFER, 0, (std::ptrdiff_t)(p.data.size() * sizeof(Sint32)), p.data.data());
	if (!p.extras.empty())
	{
		gl.BufferSubData(GL_TEXTURE_BUFFER, (std::ptrdiff_t)(p.data.size() * sizeof(Sint32)), (std::ptrdiff_t)(p.extras.size() * sizeof(Sint32)), p.extras.data());
	}
	gl.BindBuffer(GL_TEXTURE_BUFFER, 0);
	// the state of the drawing
	gl.BindFramebuffer(GL_FRAMEBUFFER, t.fbo);
	glViewport(0, 0, t.w, t.h);
	glDisable(GL_SCISSOR_TEST);
	glDisable(GL_DEPTH_TEST);
	glEnable(GL_BLEND);
	glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
	glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_FALSE);
	gl.UseProgram(shared.program);
	gl.Uniform2f(shared.sizeAt, (float)t.w, (float)t.h);
	gl.Uniform1i(shared.extrasAt, (GLint)(p.data.size() / 4));
	gl.Uniform1ui(shared.probeAt, shared.probe ? 1u : 0u);
	gl.ActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D_ARRAY, shared.atlas.texture);
	gl.ActiveTexture(GL_TEXTURE0 + 1);
	glBindTexture(GL_TEXTURE_2D, shared.stream);
	gl.ActiveTexture(GL_TEXTURE0 + 3);
	glBindTexture(GL_TEXTURE_BUFFER, shared.cmdTexture);
	gl.ActiveTexture(GL_TEXTURE0 + 4);
	glBindTexture(GL_TEXTURE_2D, t.lut);
	gl.ActiveTexture(GL_TEXTURE0 + 2);
	glBindTexture(GL_TEXTURE_2D, t.under);
	gl.BindVertexArray(shared.vao);
	// runs of commands in one call each; the ones that read the canvas under them see a copy of it, taken before a
	// set of them that do not overlap one another (the copy holds everything drawn before)
	const int n = (int)p.reads.size();
	const Sint32 *data = p.data.data();
	auto rect = [&](int i) { return data + (size_t)i * 16; };
	auto overlap = [](const Sint32 *a, const Sint32 *b) { return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]; };
	std::vector<int> set;
	p.copies = 0;
	for (int i = 0; i < n;)
	{
		const int start = i;
		if (!p.reads[i])
		{
			while (i < n && !p.reads[i])
			{
				++i;
			}
		}
		else
		{
			set.clear();
			int bx0 = rect(i)[0], by0 = rect(i)[1], bx1 = rect(i)[2], by1 = rect(i)[3];
			while (i < n && p.reads[i] && set.size() < 512)
			{
				bool free = true;
				for (int j : set)
				{
					if (overlap(rect(i), rect(j)))
					{
						free = false;
						break;
					}
				}
				if (!free)
				{
					break;
				}
				set.push_back(i);
				bx0 = std::min(bx0, rect(i)[0]);
				by0 = std::min(by0, rect(i)[1]);
				bx1 = std::max(bx1, rect(i)[2]);
				by1 = std::max(by1, rect(i)[3]);
				++i;
			}
			glCopyTexSubImage2D(GL_TEXTURE_2D, 0, bx0, by0, bx0, by0, bx1 - bx0, by1 - by0);
			++p.copies;
		}
		glDrawArrays(GL_TRIANGLES, start * 6, (i - start) * 6);
	}
	// back to what the rest of the frame expects
	gl.BindVertexArray(0);
	for (int unit = 4; unit >= 0; --unit)
	{
		gl.ActiveTexture(GL_TEXTURE0 + unit);
		glBindTexture(GL_TEXTURE_2D, 0);
	}
	gl.ActiveTexture(GL_TEXTURE0 + 3);
	glBindTexture(GL_TEXTURE_BUFFER, 0);
	gl.ActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D_ARRAY, 0);
	gl.UseProgram(0);
	glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
	glDisable(GL_BLEND);
	gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
	t.valid = true;
	t.dirty = true;
}

void HdGpuCanvas::take(Canvas32 &canvas, bool latest)
{
	Target *t = nullptr;
	for (Target *each : _targets)
	{
		if (each->canvas == &canvas)
		{
			t = each;
		}
	}
	if (!t || !HdGpu::instance().current())
	{
		return;
	}
	if (t->dropPending)
	{
		t->dropAll();
	}
	if (t->dirty)
	{
		t->readBack();
	}
	if (t->pending.empty())
	{
		return;
	}
	// the last frame when it is there, else the one before it: the card is a frame behind, the processor does not wait
	size_t pick = t->pending.size() - 1;
	if (!latest && !shared.sync && pick > 0 && !signaled(t->pending[pick].fence, true))
	{
		--pick;
	}
	const auto w0 = std::chrono::steady_clock::now();
	waitFor(t->pending[pick].fence);
	if (shared.stats.on)
	{
		const double waitMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - w0).count();
		shared.stats.waitMs += waitMs;
		shared.stats.maxWaitMs = std::max(shared.stats.maxWaitMs, waitMs);
		if (waitMs > 100)
		{
			Log(LOG_INFO) << "HD GPU canvas stats: waited " << waitMs << " ms for a frame";
		}
	}
	SDL_Surface *s = canvas._surface.get();
	gl.BindBuffer(GL_PIXEL_PACK_BUFFER, t->pbos[t->pending[pick].pbo]);
	const Uint8 *src = (const Uint8 *)gl.MapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY);
	if (src && s->w == t->w && s->h == t->h)
	{
		const int rows = t->h;
		const size_t rowBytes = (size_t)t->w * 4;
		HdWorkers &pool = HdWorkers::instance();
		const int jobs = std::max(1, std::min(rows / 32, pool.threads() * 2));
		pool.run(jobs, [&](int job)
		{
			const int ya = (int)((long long)rows * job / jobs);
			const int yb = (int)((long long)rows * (job + 1) / jobs);
			for (int y = ya; y < yb; ++y)
			{
				std::memcpy((Uint8 *)s->pixels + (size_t)y * s->pitch, src + (size_t)y * rowBytes, rowBytes);
			}
		});
	}
	if (src)
	{
		gl.UnmapBuffer(GL_PIXEL_PACK_BUFFER);
	}
	gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
	for (size_t i = 0; i <= pick; ++i)
	{
		gl.DeleteSync(t->pending.front().fence);
		t->pending.pop_front();
	}
}

void HdGpuCanvas::drawnByCpu(Canvas32 &canvas)
{
	for (Target *t : _targets)
	{
		if (t->canvas == &canvas)
		{
			t->valid = false;
			t->dirty = false;
			if (HdGpu::instance().current())
			{
				t->dropAll();
			}
			else
			{
				t->dropPending = true;
			}
		}
	}
}

unsigned HdGpuCanvas::texture(const Canvas32 &canvas) const
{
	for (const Target *t : _targets)
	{
		if (t->canvas == &canvas)
		{
			return t->valid ? t->texture : 0;
		}
	}
	return 0;
}

bool HdGpuCanvas::verifying() const
{
	return shared.verify;
}

void HdGpuCanvas::verify(Canvas32 &canvas)
{
	Target *t = nullptr;
	for (Target *each : _targets)
	{
		if (each->canvas == &canvas)
		{
			t = each;
		}
	}
	if (!t || !HdGpu::instance().current())
	{
		return;
	}
	if (t->dirty)
	{
		t->readBack();
	}
	if (t->pending.empty())
	{
		return;
	}
	waitFor(t->pending.back().fence);
	const SDL_Surface *s = canvas._surface.get();
	gl.BindBuffer(GL_PIXEL_PACK_BUFFER, t->pbos[t->pending.back().pbo]);
	const Uint32 *card = (const Uint32 *)gl.MapBuffer(GL_PIXEL_PACK_BUFFER, GL_READ_ONLY);
	long long differ = 0;
	int firstX = -1, firstY = -1;
	Uint32 cpuPixel = 0, cardPixel = 0;
	if (card && s->w == t->w && s->h == t->h)
	{
		for (int y = 0; y < t->h; ++y)
		{
			const Uint32 *row = (const Uint32 *)((const Uint8 *)s->pixels + (size_t)y * s->pitch);
			const Uint32 *cardRow = card + (size_t)y * t->w;
			if (std::memcmp(row, cardRow, (size_t)t->w * 4) == 0)
			{
				continue;
			}
			for (int x = 0; x < t->w; ++x)
			{
				if (row[x] != cardRow[x])
				{
					if (!differ++)
					{
						firstX = x;
						firstY = y;
						cpuPixel = row[x];
						cardPixel = cardRow[x];
					}
				}
			}
		}
	}
	if (card)
	{
		gl.UnmapBuffer(GL_PIXEL_PACK_BUFFER);
	}
	gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
	t->dropAll();
	++shared.verified;
	if (differ)
	{
		if (shared.differed++ < 20)
		{
			Log(LOG_INFO) << "HD GPU canvas verify: flush " << shared.verified << " differs in " << differ << " pixel(s), the first at "
				<< firstX << "," << firstY << ": processor " << std::hex << cpuPixel << ", card " << cardPixel << std::dec;
		}
	}
	if (shared.verified % 600 == 0)
	{
		Log(LOG_INFO) << "HD GPU canvas verify: " << shared.verified << " flushes compared, " << shared.differed << " differ";
	}
}

void HdGpuCanvas::forget(Canvas32 &canvas)
{
	for (size_t i = 0; i < _targets.size(); ++i)
	{
		if (_targets[i]->canvas == &canvas)
		{
			if (HdGpu::instance().current())
			{
				_targets[i]->releaseGl();
			}
			delete _targets[i];
			_targets.erase(_targets.begin() + i);
			break;
		}
	}
	// palette frames are known by their buffers: a battle that ends frees them
	shared.indexed.clear();
}

void HdGpuCanvas::release()
{
	for (Target *t : _targets)
	{
		// the frame shown a frame late comes back while the context is there
		if (HdGpu::instance().current())
		{
			take(*t->canvas, true);
			t->releaseGl();
		}
		delete t;
	}
	_targets.clear();
	shared.release();
}

#endif

}
