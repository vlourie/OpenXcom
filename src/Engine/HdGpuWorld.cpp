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
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <map>
#include <memory>
#include <new>
#include <set>
#include <string>
#include <unordered_map>
#include <utility>
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

namespace
{

/// The constants of HdRadar's formulas the card works out (HdGpuWorld::radar), at their places in the shader's `kd`:
/// capDist's least gradient, Zc's least, limb's start, drawBeam's margins; then fdlibm's arc tangent (pi / 2 and pi
/// high and low, atan(0.5) and atan(1) high and low, the 11 terms) and HdRadar's PI, TAU and PI / 2.
const double RADAR_K[] = {
	1e-4, 0.08, 0.97, 0.999, 0.01, 0.51,
	1.57079632679489655800e+00, 6.12323399573676603587e-17, 3.14159265358979311600e+00, 1.2246467991473531772e-16,
	4.63647609000806093515e-01, 7.85398163397448278999e-01, 2.26987774529616870924e-17, 3.06161699786838301793e-17,
	3.33333333333329318027e-01, -1.99999999998764832476e-01, 1.42857142725034663711e-01, -1.11111104054623557880e-01,
	9.09088713343650656196e-02, -7.69187620504482999495e-02, 6.66107313738753120669e-02, -5.83357013379057348645e-02,
	4.97687799461593236017e-02, -3.65315727442169155270e-02, 1.62858201153657823623e-02,
	3.14159265358979323846, 2 * 3.14159265358979323846, 3.14159265358979323846 / 2 };

}

double HdGpuWorld::atan2(double y, double x)
{
	const double *K = RADAR_K, *aT = RADAR_K + 14;
	const double ay = std::fabs(y), ax = std::fabs(x), hi = std::max(ay, ax);
	if (hi == 0) return 0;
	double t = std::min(ay, ax) / hi;
	int id = -1;
	if (t >= 0.4375)
	{
		if (t < 0.6875)
		{
			id = 0;
			t = (2.0 * t - 1.0) / (2.0 + t);
		}
		else
		{
			id = 1;
			t = (t - 1.0) / (t + 1.0);
		}
	}
	const double z = t * t, w = z * z;
	const double s1 = z * (aT[0] + w * (aT[2] + w * (aT[4] + w * (aT[6] + w * (aT[8] + w * aT[10])))));
	const double s2 = w * (aT[1] + w * (aT[3] + w * (aT[5] + w * (aT[7] + w * aT[9]))));
	double a = id < 0 ? t - t * (s1 + s2) : K[10 + id] - ((t * (s1 + s2) - K[12 + id]) - t);
	if (ay > ax) a = K[6] - (a - K[7]);
	if (x < 0) a = K[8] - (a - K[9]);
	return y < 0 ? -a : a;
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
bool HdGpuWorld::image(const Uint32 *, int, int, int, int, int, Image) { return false; }
bool HdGpuWorld::glyph(const Uint8 *, int, int, int, int, int, Uint32, const float *) { return false; }
bool HdGpuWorld::spans(const std::vector<Span> &) { return false; }
bool HdGpuWorld::cover(const std::vector<Sint32> &, const std::vector<float> &, int, int, int, int, Uint32) { return false; }
bool HdGpuWorld::shade(Shade, const std::vector<float> &, int, int, int, int, const float *) { return false; }
bool HdGpuWorld::light(unsigned long long, const std::vector<float> &, const std::vector<float> &, int, int, int, int,
	const std::vector<Lamp> &, const std::vector<Pipe> &, const unsigned char *, int, int) { return false; }
bool HdGpuWorld::canvas(unsigned, const SDL_Surface *, int, int, int, int, int, int) { return false; }
bool HdGpuWorld::canvasZoomed(unsigned, const SDL_Surface *, const std::vector<int> &, const std::vector<Uint32> &,
	const std::vector<int> &, const std::vector<Uint32> &, Uint32, int, int, int, int, int) { return false; }
unsigned HdGpuWorld::snapshot() { return 0; }
Uint32 *HdGpuWorld::steps(size_t, size_t, int, int, int, int) { return nullptr; }
bool HdGpuWorld::wash(const Uint32 *, int, int, int, int, Uint64, const std::vector<Sint32> &, int, int, int, int) { return false; }
bool HdGpuWorld::radar(const Radar &, int, int, int, int) { return false; }
bool HdGpuWorld::building(const std::vector<float> &, const float *, int, int, int, int, int) { return false; }
bool HdGpuWorld::alarm(const std::vector<Uint32> &, const Uint32 *, const Uint32 *, const Uint32 *, int, int, int, int) { return false; }
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
enum Kind { K_FILL, K_COPY, K_ZOOM, K_FRAME, K_PIXELS, K_IMAGE, K_GLYPH, K_SPANS, K_COVER, K_SHADE, K_LIGHT, K_STEPS, K_ALARM, K_WASH, K_RADAR };
/// The words of a radar's head in the data (HdGpuWorld::radar), a sweep, a group and a wave.
const int RADAR_HEAD = 37, RADAR_SWEEP = 23, RADAR_GROUP = 13, RADAR_WAVE = 7;
/// The kind of a K_SHADE write for drawBuilding, after HdGpuWorld::Shade's.
const int S_BUILD = 6;

/// The side of the tiles the writes are sorted into.
const int TILE = 32;

/// The allocator of the frame's data: values a resize adds are left as they come (each write fills its own at once).
template <typename T>
struct NoInit : std::allocator<T>
{
	template <typename U>
	struct rebind
	{
		using other = NoInit<U>;
	};
	NoInit() = default;
	template <typename U>
	NoInit(const NoInit<U> &) {}
	template <typename U>
	void construct(U *p) noexcept
	{
		::new ((void *)p) U;
	}
	template <typename U, typename... A>
	void construct(U *p, A &&...a)
	{
		::new ((void *)p) U(std::forward<A>(a)...);
	}
};
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
	"#extension GL_ARB_gpu_shader_fp64 : enable\n"
	"#define FILL 0\n"
	"#define COPY 1\n"
	"#define ZOOM 2\n"
	"#define FRAME 3\n"
	"#define PIXELS 4\n"
	"#define IMAGE 5\n"
	"#define GLYPH 6\n"
	"#define SPANS 7\n"
	"#define COVER 8\n"
	"#define SHADE 9\n"
	"#define LIGHT 10\n"
	"#define STEPS 11\n"
	"#define STEP_SET 0u\n"
	"#define STEP_OPAQUE 1u\n"
	"#define ALARM 12\n"
	"#define WASH 13\n"
	"#define RADAR 14\n"
	// HdGpuWorld::Shade, S_BUILD
	"#define S_ADD 0\n"
	"#define S_OVER 1\n"
	"#define S_MIX 2\n"
	"#define S_STAMP 3\n"
	"#define S_GLOW_ADD 4\n"
	"#define S_GLOW_OWN 5\n"
	"#define S_BUILD 6\n"
	// HdGpuWorld::Image
	"#define I_COPY 1\n"
	"#define I_OVER_INT 2\n"
	"uniform sampler2DArray atlas;\n"
	"uniform sampler2D canvas;\n"
	"uniform sampler2D heldAcc;\n"
	"uniform sampler2D heldGlow;\n"
	"uniform usampler2D heldWash;\n"
	"uniform isampler2D heldDist;\n"
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
	// HdRadar's blend of a of 256 (HdShadeRow::blend256)
	"uint blend256(uint d, uint c, uint a)\n"
	"{\n"
	"	uint ia = 256u - a;\n"
	"	uint rb = ((d & 0xFF00FFu) * ia + (c & 0xFF00FFu) * a) >> 8u;\n"
	"	uint g = ((d & 0xFF00u) * ia + (c & 0xFF00u) * a) >> 8u;\n"
	"	return 0xFF000000u | (rb & 0xFF00FFu) | (g & 0xFF00u);\n"
	"}\n"
	// a channel each through a table of CraftLaunchState's alarm (HdGpuWorld::alarm)
	"uvec3 through(uvec3 c, int t)\n"
	"{\n"
	"	return uvec3((dat(t + int(c.r)) >> 16u) & 255u, (dat(t + int(c.g)) >> 8u) & 255u, dat(t + int(c.b)) & 255u);\n"
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
	// std::lround, exactly: the fraction of a float is exact
	"int lroundi(float y)\n"
	"{\n"
	"	float a = min(abs(y), 1.0e6);\n"
	"	float t = floor(a);\n"
	"	int r = int(t) + (a - t >= 0.5 ? 1 : 0);\n"
	"	return y < 0.0 ? -r : r;\n"
	"}\n"
	// the base's routines per pixel (HdGpuWorld::shade), the values of the pixel from `at`
	"uint shade(uint d, int kind, int at, vec3 col)\n"
	"{\n"
	"	uint o = d & 0xFF000000u;\n"
	"	if (kind == S_STAMP && !(datf(at + 3) > datf(256))) return d;\n"
	"	precise float h = datf(at), c = datf(at + 1);\n"
	"	precise float a = 0.0;\n"
	"	if (kind >= S_GLOW_ADD)\n"
	"	{\n"
	"		if (h < 0.0) return d;\n"
	"		o = 0xFF000000u;\n"
	"		a = min(0.85 * h + c, 1.0);\n"
	"	}\n"
	"	for (int ch = 0; ch < 3; ++ch)\n"
	"	{\n"
	"		uint sh = uint(16 - 8 * ch);\n"
	"		uint b = (d >> sh) & 255u;\n"
	"		float v = datf(int(b)), cc = col[ch];\n"
	"		uint res;\n"
	"		if (kind == S_ADD) { precise float x = v + cc * h; res = uint(lroundi(clamp(x, 0.0, 1.0) * 255.0)); }\n"
	"		else if (kind == S_OVER) { precise float x = v + (cc - v) * h; res = uint(lroundi(clamp(x, 0.0, 1.0) * 255.0)); }\n"
	"		else if (kind == S_MIX)\n"
	"		{\n"
	"			precise float m = datf(at + 3);\n"
	"			precise float x = float(b) * (1.0 - m) + datf(at + ch) * m;\n"
	"			res = uint(clamp(lroundi(x), 0, 255));\n"
	"		}\n"
	"		else if (kind == S_STAMP) { precise float x = datf(at + ch) + v * (1.0 - datf(at + 3)); res = uint(lroundi(min(1.0, x) * 255.0)); }\n"
	"		else if (kind == S_GLOW_ADD) { precise float x = float(b) + 255.0 * (cc * h + c); res = uint(min(x, 255.0)); }\n"
	"		else { precise float x = float(b) * (1.0 - a) + 255.0 * cc * a; res = uint(min(x, 255.0)); }\n"
	"		o |= res << sh;\n"
	"	}\n"
	"	return o;\n"
	"}\n"
	// HdBaseScene's drawBuilding (HdGpuWorld::building), the values of the pixel from `at`, the glow table at `lut` of n
	"uint building(uint d, int at, int lut, int n)\n"
	"{\n"
	"	precise float reveal = datf(at), grid = datf(at + 1), beam = datf(at + 2), edge = datf(at + 3), line = datf(at + 4), lift = datf(at + 5);\n"
	"	precise vec3 pic = vec3(datf(int((d >> 16u) & 255u)), datf(int((d >> 8u) & 255u)), datf(int(d & 255u)));\n"
	"	precise vec3 outc = pic;\n"
	"	if (reveal < 1.0)\n"
	"	{\n"
	"		precise float lum = pic.x * 0.3 + pic.y * 0.55 + pic.z * 0.15;\n"
	"		precise float lumAt = lum * float(n - 1) + 0.5;\n"
	"		float glow = datf(lut + min(n - 1, int(lumAt)));\n"
	"		precise vec3 bp = vec3(0.05 + glow * 0.25, 0.12 + glow * 0.55, 0.20 + glow * 0.85);\n"
	"		const vec3 cyan = vec3(0.35, 0.85, 1.0), yellow = vec3(0.75, 0.62, 0.25);\n"
	"		for (int c = 0; c < 3; ++c)\n"
	"		{\n"
	"			precise float v = bp[c] * lift + cyan[c] * (grid * 0.4 + line);\n"
	"			precise float w = v * (1.0 - beam) + yellow[c] * beam;\n"
	"			outc[c] = pic[c] * reveal + w * (1.0 - reveal);\n"
	"		}\n"
	"	}\n"
	"	const vec3 hot = vec3(1.0, 0.55, 0.15);\n"
	"	uint o = d & 0xFF000000u;\n"
	"	for (int c = 0; c < 3; ++c)\n"
	"	{\n"
	"		precise float v = outc[c] + hot[c] * edge * 1.2;\n"
	"		precise float x = min(1.0, max(0.0, v)) * 255.0;\n"
	"		o |= uint(lroundi(x)) << uint(16 - 8 * c);\n"
	"	}\n"
	"	return o;\n"
	"}\n"
	// HdBaseScene::draw's light (HdGpuWorld::light), its head at `at`, the area's corner `corner`
	"uint light(uint d, ivec2 p, int at, ivec2 corner)\n"
	"{\n"
	"	ivec2 o = p - corner;\n"
	"	precise vec3 a = texelFetch(heldAcc, o, 0).rgb;\n"
	"	precise vec3 g = texelFetch(heldGlow, o, 0).rgb;\n"
	"	int nl = int(dat(at)), np = int(dat(at + 1)), lutAt = int(dat(at + 2)), lutTop = int(dat(at + 3));\n"
	"	float steps = datf(at + 4);\n"
	"	int e = at + 5;\n"
	"	for (int l = 0; l < nl; ++l, e += 11)\n"
	"	{\n"
	"		ivec4 bx = ivec4(dat(e), dat(e + 1), dat(e + 2), dat(e + 3));\n"
	"		if (p.x < bx.x || p.y < bx.y || p.x >= bx.z || p.y >= bx.w) continue;\n"
	"		int j = int(dat(e + 10)) + ((p.y - bx.y) * (bx.z - bx.x) + (p.x - bx.x)) * 2;\n"
	"		float m = datf(j), h = datf(j + 1);\n"
	"		a.r += datf(e + 4) * m;\n"
	"		a.g += datf(e + 5) * m;\n"
	"		a.b += datf(e + 6) * m;\n"
	"		g.r += datf(e + 7) * h;\n"
	"		g.g += datf(e + 8) * h;\n"
	"		g.b += datf(e + 9) * h;\n"
	"	}\n"
	"	for (int f = 0; f < np; ++f, e += 8)\n"
	"	{\n"
	"		ivec4 bx = ivec4(dat(e), dat(e + 1), dat(e + 2), dat(e + 3));\n"
	"		if (p.x < bx.x || p.y < bx.y || p.x >= bx.z || p.y >= bx.w) continue;\n"
	"		int j = int(dat(e + 7)) + ((p.y - bx.y) * (bx.z - bx.x) + (p.x - bx.x)) * 3;\n"
	"		float k = datf(j), white = datf(j + 1), darken = datf(j + 2);\n"
	"		g.r += datf(e + 4) * k + white * 0.85;\n"
	"		g.g += datf(e + 5) * k + white;\n"
	"		g.b += datf(e + 6) * k + white * 0.75;\n"
	"		a.r *= 1.0 - darken;\n"
	"		a.g *= 1.0 - darken;\n"
	"		a.b *= 1.0 - darken;\n"
	"	}\n"
	"	uint out_ = d & 0xFF000000u;\n"
	"	for (int ch = 0; ch < 3; ++ch)\n"
	"	{\n"
	"		uint sh = uint(16 - 8 * ch);\n"
	"		precise float v = datf(int((d >> sh) & 255u)) * a[ch] + g[ch];\n"
	"		int i = min(lutTop, int(v * steps));\n"
	"		out_ |= dat(lutAt + max(0, i)) << sh;\n"
	"	}\n"
	"	return out_;\n"
	"}\n"
	// HdRadar::draw's steps 2 and 3 (HdGpuWorld::radar): its formulas in double precision, every division, root and
	// conversion to float rounded as the processor's (the card's own only approximate them)
	"#ifdef GL_ARB_gpu_shader_fp64\n"
	"uniform int radarFp64;\n"
	"double datd(int i) { return packDouble2x32(uvec2(dat(i), dat(i + 1))); }\n"
	"double up(double v) { uvec2 b = unpackDouble2x32(v); b.x += 1u; if (b.x == 0u) b.y += 1u; return packDouble2x32(b); }\n"
	"double down(double v) { uvec2 b = unpackDouble2x32(v); if (b.x == 0u) b.y -= 1u; b.x -= 1u; return packDouble2x32(b); }\n"
	// a / b to the nearest (ties to even): the quotient below it found by the exact remainders, then the nearer one
	"double ddiv(double a, double b)\n"
	"{\n"
	"	if (a == 0.0) return a / b;\n"
	"	precise double aa = abs(a), bb = abs(b);\n"
	"	precise double y = 1.0 / bb;\n"
	"	precise double q = aa * y;\n"
	"	for (int i = 0; i < 2; ++i) { precise double r = fma(-q, bb, aa); q = fma(r, y, q); }\n"
	"	for (int i = 0; i < 4 && fma(-q, bb, aa) < 0.0; ++i) q = down(q);\n"
	"	for (int i = 0; i < 4; ++i) { precise double n = up(q); if (fma(-n, bb, aa) < 0.0) break; q = n; }\n"
	"	precise double n = up(q);\n"
	"	precise double rq = fma(-q, bb, aa), rn = fma(n, bb, -aa);\n"
	"	if (rn < rq || (rn == rq && (unpackDouble2x32(n).x & 1u) == 0u)) q = n;\n"
	"	return (a < 0.0) != (b < 0.0) ? -q : q;\n"
	"}\n"
	// the root to the nearest: the one below it, up when x - s^2 passes s ulp (the midpoint's square is never x)
	"double dsqrt(double x)\n"
	"{\n"
	"	if (x == 0.0) return x;\n"
	"	precise double s = sqrt(x);\n"
	"	precise double r = fma(-s, s, x);\n"
	"	s = fma(r, 0.5 / s, s);\n"
	"	for (int i = 0; i < 4 && fma(-s, s, x) < 0.0; ++i) s = down(s);\n"
	"	for (int i = 0; i < 4; ++i) { precise double n = up(s); if (fma(-n, n, x) < 0.0) break; s = n; }\n"
	"	precise double n = up(s);\n"
	"	precise double e = fma(-s, s, x), h = s * (n - s);\n"
	"	if (e > h) s = n;\n"
	"	return s;\n"
	"}\n"
	// (float) of a positive double to the nearest, ties to even
	"float tofloat(double v)\n"
	"{\n"
	"	float f = float(v);\n"
	"	if (!(v > 0.0) || !(f > 0.0)) return f;\n"
	"	uint b = floatBitsToUint(f);\n"
	"	float lo = uintBitsToFloat(b - 1u), hi = uintBitsToFloat(b + 1u);\n"
	"	precise double ef = abs(v - double(f)), el = abs(v - double(lo)), eh = abs(v - double(hi));\n"
	"	bool odd = (b & 1u) != 0u;\n"
	"	if (el < ef || (el == ef && odd)) return lo;\n"
	"	if (eh < ef || (eh == ef && odd)) return hi;\n"
	"	return f;\n"
	"}\n"
	"float clamp01d(double v) { return v <= 0.0 ? 0.0 : (v >= 1.0 ? 1.0 : tofloat(v)); }\n"
	"float fdiv(float a, float b) { return tofloat(ddiv(double(a), double(b))); }\n"
	// HdRadar's constants (RADAR_K) from `k`
	"double kd(int k, int i) { return datd(k + 2 * i); }\n"
	// HdGpuWorld::atan2
	"double atan2d(double y, double x, int k)\n"
	"{\n"
	"	precise double ay = abs(y), ax = abs(x);\n"
	"	precise double hi = max(ay, ax);\n"
	"	if (hi == 0.0) return 0.0;\n"
	"	precise double t = ddiv(min(ay, ax), hi);\n"
	"	int id = -1;\n"
	"	if (t >= 0.4375)\n"
	"	{\n"
	"		if (t < 0.6875) { id = 0; precise double n = 2.0 * t - 1.0, m = 2.0 + t; t = ddiv(n, m); }\n"
	"		else { id = 1; precise double n = t - 1.0, m = t + 1.0; t = ddiv(n, m); }\n"
	"	}\n"
	"	precise double z = t * t, w = z * z;\n"
	"	precise double s1 = z * (kd(k, 14) + w * (kd(k, 16) + w * (kd(k, 18) + w * (kd(k, 20) + w * (kd(k, 22) + w * kd(k, 24))))));\n"
	"	precise double s2 = w * (kd(k, 15) + w * (kd(k, 17) + w * (kd(k, 19) + w * (kd(k, 21) + w * kd(k, 23)))));\n"
	"	precise double a = id < 0 ? t - t * (s1 + s2) : kd(k, 10 + id) - ((t * (s1 + s2) - kd(k, 12 + id)) - t);\n"
	"	if (ay > ax) a = kd(k, 6) - (a - kd(k, 7));\n"
	"	if (x < 0.0) a = kd(k, 8) - (a - kd(k, 9));\n"
	"	return y < 0.0 ? -a : a;\n"
	"}\n"
	// HdRadar's limb: the globe's soft edge
	"float limb(double r2, double radius, int k)\n"
	"{\n"
	"	if (!(r2 > kd(k, 2))) return 1.0;\n"
	"	precise double v = (1.0 - dsqrt(r2)) * radius;\n"
	"	return clamp01d(v);\n"
	"}\n"
	// HdRadar's capDist of the circle at `c` (its centre and cosR first)
	"double capDist(int c, double X, double Y, double Z, double Zc, double radius, int k)\n"
	"{\n"
	"	double cx = datd(c), cy = datd(c + 2), cz = datd(c + 4), cosR = datd(c + 6);\n"
	"	precise double f = X * cx + Y * cy + Z * cz - cosR;\n"
	"	precise double px = cz * X, py = cz * Y;\n"
	"	precise double gx = cx - ddiv(px, Zc), gy = cy - ddiv(py, Zc);\n"
	"	precise double g2 = gx * gx + gy * gy;\n"
	"	precise double gl = max(dsqrt(g2), kd(k, 0));\n"
	"	precise double fr = f * radius;\n"
	"	return ddiv(fr, gl);\n"
	"}\n"
	"uint blendOwn(uint d, uint c) { uint a = c >> 24u; return a != 0u ? blend256(d, c, a + (a >> 7u)) : d; }\n"
	// HdRadar's washColor, the fill `fc`, the edge `ec`, the glow's part `gw`
	"uint washColor(double d, float lim, double lineW, double glowLen, bool withFill, uint fc, uint ec, float gw)\n"
	"{\n"
	"	precise float fill = withFill ? clamp01d(d + 0.5) * lim : 0.0;\n"
	"	precise double lv = lineW * 0.5 + 0.5 - abs(d - lineW * 0.5);\n"
	"	float line = clamp01d(lv);\n"
	"	precise float glow = 0.0;\n"
	"	if (d > 0.0 && d < glowLen) { precise double t = 1.0 - ddiv(d, glowLen); glow = tofloat(t * t) * gw; }\n"
	"	precise float aF = datf(int(fc >> 24u)) * fill;\n"
	"	precise float aE = datf(int(ec >> 24u)) * max(line, glow) * lim;\n"
	"	precise float a = 1.0 - (1.0 - aF) * (1.0 - aE);\n"
	"	if (a < datf(256)) return 0u;\n"
	"	precise float wn = aF * (1.0 - aE);\n"
	"	float wf = fdiv(wn, a), we = fdiv(aE, a);\n"
	"	precise float av = a * 255.0 + 0.5;\n"
	"	uint o = uint(av) << 24u;\n"
	"	for (uint s = 0u; s < 24u; s += 8u)\n"
	"	{\n"
	"		precise float v = float((fc >> s) & 255u) * wf + float((ec >> s) & 255u) * we + 0.5;\n"
	"		o |= uint(v) << s;\n"
	"	}\n"
	"	return o;\n"
	"}\n"
	// HdRadar's drawBeam of the sweep at `s`, the radar's head at `h`
	"uint beam(uint d, int s, float cov, ivec2 p, int h, int k)\n"
	"{\n"
	"	double sx = datd(s + 8), sy = datd(s + 10), angle = datd(s + 12), ux = datd(s + 14), uy = datd(s + 16);\n"
	"	double beamW = datd(h + 25), trail = datd(h + 33), trailCos2 = datd(h + 35), tau = kd(k, 26);\n"
	"	precise double dx = double(p.x) + 0.5 - sx, dy = double(p.y) + 0.5 - sy;\n"
	"	precise double along = dx * ux + dy * uy, crs = ux * dy - uy * dx, d2 = dx * dx + dy * dy;\n"
	"	precise double aa = along * along, edge = trailCos2 * d2 * kd(k, 3);\n"
	"	bool wedge = crs <= kd(k, 4) && (d2 < 4.0 || (along > 0.0 && aa > edge));\n"
	"	precise double hw = beamW * 0.5 + kd(k, 5);\n"
	"	bool strip = along > -kd(k, 4) && abs(crs) < hw;\n"
	"	if (!wedge && !strip) return d;\n"
	// fmod(x, TAU): x lies in (-pi, 3 pi), x - TAU is exact
	"	precise double delta = angle - atan2d(dy, dx, k);\n"
	"	if (delta >= tau) delta = delta - tau;\n"
	"	if (delta < 0.0) delta = delta + tau;\n"
	"	if (delta < trail)\n"
	"	{\n"
	"		precise double t = 1.0 - ddiv(delta, trail);\n"
	"		precise float c = tofloat(t * t) * cov;\n"
	"		d = blendPixel(d, dat(h + 29), c);\n"
	"	}\n"
	"	precise double sd = delta > kd(k, 25) ? delta - tau : delta;\n"
	"	if (abs(sd) < kd(k, 27))\n"
	"	{\n"
	"		precise double bv = beamW * 0.5 + 0.5 - abs(crs);\n"
	"		float b = clamp01d(bv);\n"
	"		if (b > 0.0) { precise float c = b * cov; d = blendPixel(d, dat(h + 30), c); }\n"
	"	}\n"
	"	return d;\n"
	"}\n"
	// the radar with its head at `h` over pixel p, the bases' distances from `origin`
	"uint radar(uint d, ivec2 p, int h, ivec2 origin)\n"
	"{\n"
	"	int k = int(dat(h + 12)), ox = int(dat(h + 17)), oy = int(dat(h + 18));\n"
	"	int ry = p.y - oy, rowsAt = int(dat(h + 5));\n"
	"	if (p.x < int(dat(rowsAt + ry * 2)) || p.x >= int(dat(rowsAt + ry * 2 + 1))) return d;\n"
	"	double X = datd(int(dat(h + 3)) + (p.x - ox) * 2), Y = datd(int(dat(h + 4)) + ry * 2);\n"
	"	precise double r2 = X * X + Y * Y;\n"
	"	if (r2 >= 1.0) return d;\n"
	"	precise double Z = dsqrt(1.0 - r2);\n"
	"	precise double Zc = max(Z, kd(k, 1));\n"
	"	double radius = datd(h + 19), lineW = datd(h + 21), glowLen = datd(h + 23);\n"
	"	int flags = int(dat(h)), nSweep = int(dat(h + 1)), nGroup = int(dat(h + 2));\n"
	"	int swAt = int(dat(h + 6)), grAt = int(dat(h + 7)), wvAt = int(dat(h + 8));\n"
	"	bool bare = (flags & 1) != 0, craftBeam = (flags & 2) != 0;\n"
	"	ivec4 db = ivec4(int(dat(h + 13)), int(dat(h + 14)), int(dat(h + 15)), int(dat(h + 16)));\n"
	"	bool drow = p.y >= db.y && p.y < db.w;\n"
	"	bool dcol = drow && p.x >= db.x && p.x < db.z;\n"
	"	int dv = dcol ? texelFetch(heldDist, p - origin, 0).r : 0;\n"
	"	float lim = limb(r2, radius, k);\n"
	"	uint fc = dat(h + 27), ec = dat(h + 28);\n"
	"	float gw = uintBitsToFloat(dat(h + 32));\n"
	// 2. the craft in the row (the first 64 of it), when the pixel is in one's box
	"	bool inCraft = false;\n"
	"	for (int i = 0, n = 0; i < nSweep && n < 64 && !inCraft; ++i)\n"
	"	{\n"
	"		int s = swAt + i * 23;\n"
	"		if (p.y < int(dat(s + 19)) || p.y >= int(dat(s + 21))) continue;\n"
	"		++n;\n"
	"		inCraft = p.x >= int(dat(s + 18)) && p.x < int(dat(s + 20));\n"
	"	}\n"
	"	if (inCraft && bare)\n"
	"	{\n"
	"		for (int i = 0, n = 0; i < nSweep && n < 64; ++i)\n"
	"		{\n"
	"			int s = swAt + i * 23;\n"
	"			if (p.y < int(dat(s + 19)) || p.y >= int(dat(s + 21))) continue;\n"
	"			++n;\n"
	"			if (p.x < int(dat(s + 18)) || p.x >= int(dat(s + 20))) continue;\n"
	"			double dd = capDist(s, X, Y, Z, Zc, radius, k);\n"
	"			if (dd < -lineW - 1.0) continue;\n"
	"			if (dd <= glowLen + 1.0) d = blendOwn(d, washColor(dd, lim, lineW, glowLen, false, fc, ec, gw));\n"
	"			if (craftBeam && dat(s + 22) != 0u && dd > -0.5) { precise float cov = clamp01d(dd + 0.5) * lim; d = beam(d, s, cov, p, h, k); }\n"
	"		}\n"
	"	}\n"
	"	else if (inCraft)\n"
	"	{\n"
	"		double dB = dcol ? double(dv) * 0.125 : -4000.0;\n"
	"		double dd = dB;\n"
	"		for (int i = 0, n = 0; i < nSweep && n < 64; ++i)\n"
	"		{\n"
	"			int s = swAt + i * 23;\n"
	"			if (p.y < int(dat(s + 19)) || p.y >= int(dat(s + 21))) continue;\n"
	"			++n;\n"
	"			double dc = p.x >= int(dat(s + 18)) && p.x < int(dat(s + 20)) ? capDist(s, X, Y, Z, Zc, radius, k) : -4000.0;\n"
	"			dd = max(dd, dc);\n"
	"		}\n"
	"		if (!(dd < -lineW - 1.0))\n"
	"		{\n"
	"			d = blendOwn(d, washColor(dd, lim, lineW, glowLen, true, fc, ec, gw));\n"
	"			precise float open = 1.0 - clamp01d(dB + 0.5);\n"
	"			if (craftBeam && !(open <= uintBitsToFloat(dat(h + 11))))\n"
	"			{\n"
	"				for (int i = 0, n = 0; i < nSweep && n < 64; ++i)\n"
	"				{\n"
	"					int s = swAt + i * 23;\n"
	"					if (p.y < int(dat(s + 19)) || p.y >= int(dat(s + 21))) continue;\n"
	"					++n;\n"
	"					if (dat(s + 22) == 0u) continue;\n"
	"					double dc = p.x >= int(dat(s + 18)) && p.x < int(dat(s + 20)) ? capDist(s, X, Y, Z, Zc, radius, k) : -4000.0;\n"
	"					if (dc <= -0.5) continue;\n"
	"					precise float cov = clamp01d(dc + 0.5) * open * lim;\n"
	"					d = beam(d, s, cov, p, h, k);\n"
	"				}\n"
	"			}\n"
	"		}\n"
	"	}\n"
	// 3. the waves: a base's inside the bases' coverage only, a craft's inside its own circle
	"	uint waveColor = dat(h + 9);\n"
	"	float waveK = uintBitsToFloat(dat(h + 10));\n"
	"	int lutTop = int(dat(h + 31));\n"
	"	for (int g = 0; g < nGroup; ++g)\n"
	"	{\n"
	"		int e = grAt + g * 13;\n"
	"		if (p.y < int(dat(e + 7)) || p.y >= int(dat(e + 9)) || p.x < int(dat(e + 6)) || p.x >= int(dat(e + 8))) continue;\n"
	"		bool craft = dat(e + 12) != 0u;\n"
	"		if (!craft && !dcol) continue;\n"
	"		int v = craft ? 64 : dv;\n"
	"		if (v <= -4) continue;\n"
	"		precise double c = X * datd(e) + Y * datd(e + 2) + Z * datd(e + 4);\n"
	"		precise float light = 0.0;\n"
	"		bool in_ = false;\n"
	"		for (int i = int(dat(e + 10)), end = int(dat(e + 11)); i < end; ++i)\n"
	"		{\n"
	"			int w = wvAt + i * 7;\n"
	"			double lo = datd(w), hi = datd(w + 2);\n"
	"			if (c < lo || c > hi) continue;\n"
	"			in_ = true;\n"
	"			precise double at = (c - lo) * datd(w + 4);\n"
	"			float l = datf(int(dat(w + 6)) + min(lutTop, int(at)));\n"
	"			light = 1.0 - (1.0 - light) * (1.0 - l);\n"
	"		}\n"
	"		if (!in_ || light <= 0.0) continue;\n"
	"		precise float a = light * clamp01d(double(v) * 0.125 + 0.5) * lim;\n"
	"		precise float a2 = a * float(waveColor >> 24u) * waveK + 0.5;\n"
	"		uint a256 = uint(a2);\n"
	"		if (a256 != 0u) d = blend256(d, waveColor, a256);\n"
	"	}\n"
	"	return d;\n"
	"}\n"
	"#endif\n"
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
	"			int c = int(dat(q.x + (p.x - r.x) * 2));\n"
	"			if (j < 0 || c < 0)\n"
	"			{\n"
	"				d = uint(q.z);\n"
	"				break;\n"
	"			}\n"
	"			uint wy = dat(q.y + (p.y - r.y) * 2 + 1);\n"
	"			uint wx = dat(q.x + (p.x - r.x) * 2 + 1);\n"
	"			uint top = mix2(canvasAt(ivec2(c, j)), canvasAt(ivec2(c + 1, j)), wx);\n"
	"			uint low = mix2(canvasAt(ivec2(c, j + 1)), canvasAt(ivec2(c + 1, j + 1)), wx);\n"
	"			d = mix2(top, low, wy);\n"
	"			if (q.w < 256) d = mix2(uint(q.z), d, uint(q.w));\n"
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
	"			if (q.x == I_COPY) d = c;\n"
	"			else if (q.x == I_OVER_INT) d = blendInt(d, c);\n"
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
	"			int at = q.x + (p.y - r.y) * 5;\n"
	"			int a0 = int(dat(at + 1)), b0 = int(dat(at + 2)), a1 = int(dat(at + 3)), b1 = int(dat(at + 4));\n"
	"			int j = p.x >= a0 && p.x < b0 ? p.x - a0 : (p.x >= a1 && p.x < b1 ? b0 - a0 + p.x - a1 : -1);\n"
	"			if (j < 0) break;\n"
	"			float cov = datf(int(dat(at)) + j);\n"
	"			if (cov > datf(256)) d = blendPixel(d, uint(q.z), cov);\n"
	"			break;\n"
	"		}\n"
	"		case SHADE:\n"
	"		{\n"
	"			if (q.y == S_BUILD)\n"
	"			{\n"
	"				d = building(d, q.x + ((p.y - r.y) * (r.z - r.x) + (p.x - r.x)) * 6, q.z, q.w);\n"
	"				break;\n"
	"			}\n"
	"			int st = q.y == S_MIX || q.y == S_STAMP ? 4 : (q.y >= S_GLOW_ADD ? 2 : 1);\n"
	"			ivec4 e = texelFetch(ops, i * 4 + 3);\n"
	"			d = shade(d, q.y, q.x + ((p.y - r.y) * (r.z - r.x) + (p.x - r.x)) * st, vec3(intBitsToFloat(q.z), intBitsToFloat(q.w), intBitsToFloat(e.x)));\n"
	"			break;\n"
	"		}\n"
	"		case LIGHT:\n"
	"			d = light(d, p, q.x, q.yz);\n"
	"			break;\n"
	"		case STEPS:\n"
	"		{\n"
	"			int at = q.x + (p.y - r.y) * 4;\n"
	"			int xa = int(dat(at + 1)), xb = int(dat(at + 2));\n"
	"			if (p.x < xa || p.x >= xb) break;\n"
	"			int t = q.y + int(dat(at)) + (p.x - xa), first = q.z + int(dat(at + 3));\n"
	"			for (int s = first + int(dat(t)), e = first + int(dat(t + 1)); s < e;)\n"
	"			{\n"
	"				uint w = dat(s);\n"
	"				if ((w >> 24u) != 0u)\n"
	"				{\n"
	"					d = blend256(d, w, w >> 24u);\n"
	"					s += 1;\n"
	"				}\n"
	"				else if (w == STEP_SET)\n"
	"				{\n"
	"					d = dat(s + 1) | 0xFF000000u;\n"
	"					s += 2;\n"
	"				}\n"
	"				else if (w == STEP_OPAQUE)\n"
	"				{\n"
	"					d |= 0xFF000000u;\n"
	"					s += 1;\n"
	"				}\n"
	"				else\n"
	"				{\n"
	"					d = blendPixel(d, dat(s + 1), uintBitsToFloat(dat(s + 2)));\n"
	"					s += 3;\n"
	"				}\n"
	"			}\n"
	"			break;\n"
	"		}\n"
	"		case ALARM:\n"
	"		{\n"
	"			uint v = dat(q.x + (p.y - r.y) * (r.z - r.x) + (p.x - r.x));\n"
	"			uvec3 c = through(uvec3((d >> 16u) & 255u, (d >> 8u) & 255u, d & 255u), q.y);\n"
	"			uint stripe = (v >> 24u) & 3u;\n"
	"			if (stripe != 0u) c = through(c, stripe == 1u ? q.z : q.w);\n"
	"			c = min(c + uvec3((v >> 16u) & 255u, (v >> 8u) & 255u, v & 255u), uvec3(255u));\n"
	"			d = (d & 0xFF000000u) | (c.r << 16u) | (c.g << 8u) | c.b;\n"
	"			break;\n"
	"		}\n"
	"		case WASH:\n"
	"		{\n"
	"			bool cut = false;\n"
	"			for (int j = q.x, e = q.x + q.y * 4; j < e && !cut; j += 4)\n"
	"			{\n"
	"				cut = p.x >= int(dat(j)) && p.y >= int(dat(j + 1)) && p.x < int(dat(j + 2)) && p.y < int(dat(j + 3));\n"
	"			}\n"
	"			if (cut) break;\n"
	"			uint w = texelFetch(heldWash, p - q.zw, 0).r;\n"
	"			if (w != 0u) d = blend256(d, w, (w >> 24u) + (w >> 31u));\n"
	"			break;\n"
	"		}\n"
	"#ifdef GL_ARB_gpu_shader_fp64\n"
	"		case RADAR:\n"
	"			if (radarFp64 != 0) d = radar(d, p, q.x, q.yz);\n"
	"			break;\n"
	"#endif\n"
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
	std::vector<Uint32, NoInit<Uint32>> data;
	/// The tables of this frame (palettes, coverage curves) by a hash of their values: their place in `data`.
	std::unordered_map<Uint64, Sint32> tables;
	/// The canvas the frame copies: the texture it is read from, and the processor's pixels uploaded into canvasOwn.
	GLuint canvasTexture = 0;
	const SDL_Surface *canvasPixels = nullptr;
	/// The base's lamps at rest (light): their two pictures, the key and the size they were uploaded for; the key of
	/// this frame's light (one a frame: a second would overwrite the pictures the first reads).
	GLuint rest[2] = { 0, 0 };
	int heldW = 0, heldH = 0;
	/// The world drawn so far (snapshot) and its size.
	GLuint snap = 0;
	int snapW = 0, snapH = 0;
	Uint64 heldKey = 0, frameKey = 0;
	bool heldValid = false, frameLight = false;
	/// HdRadar's wash (wash): the picture, its key and size; the key of this frame's (one a frame, as the light).
	GLuint washTex = 0;
	int washW = 0, washH = 0;
	Uint64 washKey = 0, frameWashKey = 0;
	bool washValid = false, frameWash = false;
	/// HdRadar's distances of the bases (radar), kept as the wash; the program works the radar out (double precision).
	GLuint distTex = 0;
	int distW = 0, distH = 0;
	Uint64 distKey = 0, frameDistKey = 0;
	bool distValid = false, frameDist = false, radarOK = false;
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
		/// the uploads by the writer and size of the picture: what fills the layers (count, bytes)
		std::map<std::string, std::pair<long long, long long>> kinds;
	} stats;
	/// The writer of the next upload (stats only).
	const char *uploading = "frame";

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
		gl.Uniform1i(gl.GetUniformLocation(program, "heldAcc"), 5);
		gl.Uniform1i(gl.GetUniformLocation(program, "heldGlow"), 6);
		gl.Uniform1i(gl.GetUniformLocation(program, "heldWash"), 7);
		gl.Uniform1i(gl.GetUniformLocation(program, "heldDist"), 8);
		// the radar's part of the program is there only with double precision (GL_ARB_gpu_shader_fp64)
		const GLint radarAt = gl.GetUniformLocation(program, "radarFp64");
		radarOK = radarAt >= 0 && envOn("OXCE_HD_GPU_RADAR", true);
		if (radarAt >= 0) gl.Uniform1i(radarAt, 1);
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
			<< maxTexels << " texels a buffer" << (radarOK ? ", the radar worked out on the card" : ", the radar's blends as steps")
			<< (verify ? ", every frame of the card compared with the processor's" : "")
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
		if (rest[0]) glDeleteTextures(2, rest);
		if (washTex) glDeleteTextures(1, &washTex);
		washTex = 0;
		washW = washH = 0;
		washValid = false;
		if (distTex) glDeleteTextures(1, &distTex);
		distTex = 0;
		distW = distH = 0;
		distValid = radarOK = false;
		if (snap) glDeleteTextures(1, &snap);
		snap = 0;
		snapW = snapH = 0;
		rest[0] = rest[1] = 0;
		heldW = heldH = 0;
		heldValid = false;
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
		frameLight = false;
		frameWash = false;
		frameDist = false;
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
		if (stats.on)
		{
			auto &k = stats.kinds[std::string(uploading) + " " + std::to_string(w) + "x" + std::to_string(h)];
			++k.first;
			k.second += (long long)w * h * (bytes ? 1 : 4);
		}
		uploading = "frame";
	}

	/// Sorts the writes into the tiles (a write that hides a whole tile drops the ones before it there), uploads
	/// them and draws the world into its framebuffer; `last` - the frame's own (the probe's bit flipped).
	void composite(bool last = true)
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
			const bool opaque = q[4] == K_FILL || q[4] == K_COPY || q[4] == K_ZOOM || (q[4] == K_IMAGE && q[8] == COPY);
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
		gl.Uniform1ui(probeAt, probe && last ? 1u : 0u);
		gl.ActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D_ARRAY, atlas.texture);
		gl.ActiveTexture(GL_TEXTURE0 + 1);
		glBindTexture(GL_TEXTURE_2D, canvasTexture);
		for (int i = 0; i < 2; ++i)
		{
			gl.ActiveTexture(GL_TEXTURE0 + 5 + i);
			glBindTexture(GL_TEXTURE_2D, frameLight ? rest[i] : 0);
		}
		gl.ActiveTexture(GL_TEXTURE0 + 7);
		glBindTexture(GL_TEXTURE_2D, frameWash ? washTex : 0);
		gl.ActiveTexture(GL_TEXTURE0 + 8);
		glBindTexture(GL_TEXTURE_2D, frameDist ? distTex : 0);
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
		gl.ActiveTexture(GL_TEXTURE0 + 8);
		glBindTexture(GL_TEXTURE_2D, 0);
		gl.ActiveTexture(GL_TEXTURE0 + 7);
		glBindTexture(GL_TEXTURE_2D, 0);
		for (int i = 1; i >= 0; --i)
		{
			gl.ActiveTexture(GL_TEXTURE0 + 5 + i);
			glBindTexture(GL_TEXTURE_2D, 0);
		}
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
		std::vector<std::pair<long long, std::string>> top;
		for (const auto &k : stats.kinds)
		{
			top.emplace_back(k.second.second, k.first + " x" + std::to_string(k.second.first));
		}
		std::sort(top.rbegin(), top.rend());
		std::string kinds;
		for (size_t i = 0; i < top.size() && i < 8; ++i)
		{
			kinds += (kinds.empty() ? "" : ", ") + top[i].second + " " + std::to_string(top[i].first >> 10) + " KB";
		}
		if (!kinds.empty())
		{
			Log(LOG_INFO) << "HD GPU world uploads: " << kinds << " | layers " << atlas.layers.size() << " of " << atlas.maxLayers;
		}
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
	// the frame is the processor's now: a bigger array, the pictures on it copied over on the card (R-520); made
	// anew, with everything going up again, only where the driver cannot copy
	if (why == GROWING && _impl->atlas.grow(true) && _impl->atlas.places.empty())
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
		// a frame drawn anew (touched) takes its former place again when the size is the same and no write of this
		// flush reads it: a picture that changes every frame (the globe, 13 MB) held a new place each time, and
		// every old one stayed KEEP flushes - the array grew to 8 layers and the driver's copy of it with it
		Uint64 id = f.gpuWorld.stale;
		auto old = id ? atlas.places.find(id) : atlas.places.end();
		f.gpuWorld.stale = 0;
		m.uploading = id == 0 ? "frame-new" : "frame";
		if (old != atlas.places.end() && old->second.w == f.width && old->second.h == f.height && old->second.used != atlas.clock)
		{
			pl = atlas.find(id);
		}
		else
		{
			if (id) m.uploading = old == atlas.places.end() ? "frame-gone" : "frame-moved"; // stats: why it took a new place
			const Atlas::Result r = atlas.place(f.width, f.height, id);
			if (r != Atlas::PLACED)
			{
				return refuse(r == Atlas::GROW ? GROWING : "the pictures' layers are full");
			}
			pl = &atlas.places[id];
		}
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
	m.uploading = "pixels";
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

bool HdGpuWorld::image(const Uint32 *argb, int pitch, int w, int h, int x, int y, Image how)
{
	Impl &m = *_impl;
	int x0 = x, y0 = y, x1 = x + w, y1 = y + h;
	if (w <= 0 || h <= 0 || !within(m.W, m.H, x0, y0, x1, y1))
	{
		return true;
	}
	const char *why = nullptr;
	m.uploading = how == 0 ? "image0" : "image";
	const Place *pl = m.transientPlace(argb, pitch * 4, w, h, false, why);
	if (!pl)
	{
		return refuse(why);
	}
	Sint32 *q = m.push(K_IMAGE, x0, y0, x1, y1);
	q[5] = pl->layer;
	q[6] = pl->x - x;
	q[7] = pl->y - y;
	q[8] = (Sint32)how;
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
	m.uploading = "glyph";
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

bool HdGpuWorld::cover(const std::vector<Sint32> &runs, const std::vector<float> &cov, int x0, int y0, int x1, int y1, Uint32 color)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	const int rows = y1 - y0;
	size_t total = 0;
	bool inside = runs.size() == (size_t)rows * 4;
	for (int r = 0; inside && r < rows; ++r)
	{
		const Sint32 *v = &runs[(size_t)r * 4];
		inside = x0 <= v[0] && v[0] <= v[1] && v[1] <= x1 && x0 <= v[2] && v[2] <= v[3] && v[3] <= x1;
		total += (size_t)(v[1] - v[0] + v[3] - v[2]);
	}
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || !inside || cov.size() != total)
	{
		fallBack("a shape out of the world");
		return false;
	}
	// per row of the rectangle: where its coverages start and its two stretches; then the coverages
	const Sint32 at = (Sint32)m.data.size();
	m.data.resize(m.data.size() + (size_t)rows * 5);
	Uint32 next = (Uint32)m.data.size();
	for (int r = 0; r < rows; ++r)
	{
		const Sint32 *v = &runs[(size_t)r * 4];
		Uint32 *h = &m.data[at + (size_t)r * 5];
		h[0] = next;
		for (int i = 0; i < 4; ++i)
		{
			h[1 + i] = (Uint32)v[i];
		}
		next += (Uint32)(v[1] - v[0] + v[3] - v[2]);
	}
	m.data.resize(next);
	std::memcpy(&m.data[at + (size_t)rows * 5], cov.data(), cov.size() * 4);
	Sint32 *q = m.push(K_COVER, x0, y0, x1, y1);
	q[8] = at;
	q[10] = (Sint32)color;
	return true;
}

bool HdGpuWorld::shade(Shade kind, const std::vector<float> &vals, int x0, int y0, int x1, int y1, const float col[3])
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	const size_t stride = kind == MIX || kind == STAMP ? 4 : kind >= GLOW_ADD ? 2 : 1;
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || vals.size() != (size_t)(x1 - x0) * (y1 - y0) * stride)
	{
		fallBack("a shape out of the world");
		return false;
	}
	const Sint32 at = (Sint32)m.data.size();
	m.data.resize(m.data.size() + vals.size());
	std::memcpy(&m.data[at], vals.data(), vals.size() * 4);
	Sint32 *q = m.push(K_SHADE, x0, y0, x1, y1);
	q[8] = at;
	q[9] = (Sint32)kind;
	const float none[3] = { 0, 0, 0 };
	std::memcpy(&q[10], col ? col : none, 12);
	return true;
}

bool HdGpuWorld::light(unsigned long long key, const std::vector<float> &acc, const std::vector<float> &glow, int ax0, int ay0, int w, int h,
	const std::vector<Lamp> &lamps, const std::vector<Pipe> &pipes, const unsigned char *curve, int lutSize, int lutSteps)
{
	Impl &m = *_impl;
	if (w <= 0 || h <= 0)
	{
		return true;
	}
	const size_t area = (size_t)w * h * 3;
	bool fits = ax0 >= 0 && ay0 >= 0 && ax0 + w <= m.W && ay0 + h <= m.H && acc.size() == area && glow.size() == area && lutSize > 0;
	for (const Lamp &L : lamps)
	{
		fits = fits && L.x0 >= 0 && L.y0 >= 0 && L.x1 <= m.W && L.y1 <= m.H && L.x0 < L.x1 && L.y0 < L.y1
			&& L.mh.size() == (size_t)(L.x1 - L.x0) * (L.y1 - L.y0) * 2;
	}
	for (const Pipe &P : pipes)
	{
		fits = fits && P.x0 >= 0 && P.y0 >= 0 && P.x1 <= m.W && P.y1 <= m.H && P.x0 < P.x1 && P.y0 < P.y1
			&& P.kwd.size() == (size_t)(P.x1 - P.x0) * (P.y1 - P.y0) * 3;
	}
	if (!fits)
	{
		fallBack("a light out of the world");
		return false;
	}
	if (m.frameLight && m.frameKey != key)
	{
		return refuse("two lights of the base in a frame");
	}
	// the lamps at rest: uploaded when they changed
	if (!m.heldValid || m.heldKey != key || m.heldW != w || m.heldH != h)
	{
		const bool fresh = !m.rest[0] || m.heldW != w || m.heldH != h;
		if (!m.rest[0])
		{
			glGenTextures(2, m.rest);
		}
		const std::vector<float> *pics[2] = { &acc, &glow };
		gl.ActiveTexture(GL_TEXTURE0);
		glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
		for (int i = 0; i < 2; ++i)
		{
			glBindTexture(GL_TEXTURE_2D, m.rest[i]);
			if (fresh)
			{
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
				glTexImage2D(GL_TEXTURE_2D, 0, 0x8815 /* GL_RGB32F */, w, h, 0, GL_RGB, GL_FLOAT, pics[i]->data());
			}
			else
			{
				glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RGB, GL_FLOAT, pics[i]->data());
			}
		}
		glBindTexture(GL_TEXTURE_2D, 0);
		m.heldW = w;
		m.heldH = h;
		m.heldKey = key;
		m.heldValid = true;
		++m.stats.uploads;
		m.stats.uploadBytes += (long long)area * 8;
	}
	m.frameLight = true;
	m.frameKey = key;
	// the head, the lamps and the pipes with where their values lie, the values, the curve
	std::vector<Uint32> curve32(curve, curve + lutSize);
	const Sint32 lut = m.table(curve32.data(), lutSize);
	const Sint32 at = (Sint32)m.data.size();
	m.data.resize(m.data.size() + 5 + lamps.size() * 11 + pipes.size() * 8);
	Uint32 next = (Uint32)m.data.size();
	Uint32 *v = &m.data[at];
	const float steps = (float)lutSteps;
	v[0] = (Uint32)lamps.size();
	v[1] = (Uint32)pipes.size();
	v[2] = (Uint32)lut;
	v[3] = (Uint32)(lutSize - 1);
	std::memcpy(&v[4], &steps, 4);
	v += 5;
	for (const Lamp &L : lamps)
	{
		v[0] = (Uint32)L.x0; v[1] = (Uint32)L.y0; v[2] = (Uint32)L.x1; v[3] = (Uint32)L.y1;
		std::memcpy(&v[4], L.add, 12);
		std::memcpy(&v[7], L.glow, 12);
		v[10] = next;
		next += (Uint32)L.mh.size();
		v += 11;
	}
	for (const Pipe &P : pipes)
	{
		v[0] = (Uint32)P.x0; v[1] = (Uint32)P.y0; v[2] = (Uint32)P.x1; v[3] = (Uint32)P.y1;
		std::memcpy(&v[4], P.colour, 12);
		v[7] = next;
		next += (Uint32)P.kwd.size();
		v += 8;
	}
	const size_t values = m.data.size();
	m.data.resize(next);
	Uint32 *out = &m.data[values];
	for (const Lamp &L : lamps)
	{
		std::memcpy(out, L.mh.data(), L.mh.size() * 4);
		out += L.mh.size();
	}
	for (const Pipe &P : pipes)
	{
		std::memcpy(out, P.kwd.data(), P.kwd.size() * 4);
		out += P.kwd.size();
	}
	Sint32 *q = m.push(K_LIGHT, ax0, ay0, ax0 + w, ay0 + h);
	q[8] = at;
	q[9] = ax0;
	q[10] = ay0;
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
	const std::vector<int> &rows, const std::vector<Uint32> &rowWeights, Uint32 black, int x0, int y0, int x1, int y1, int bright)
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
	q[11] = std::min(256, std::max(0, bright));
	return true;
}

unsigned HdGpuWorld::snapshot()
{
	if (!_on || !_impl)
	{
		return 0;
	}
	Impl &m = *_impl;
	// the writes so far into the framebuffer (no probe: the frame's own composite flips its bit once), copied out
	m.composite(false);
	gl.ActiveTexture(GL_TEXTURE0 + 1);
	if (!m.snap)
	{
		glGenTextures(1, &m.snap);
	}
	glBindTexture(GL_TEXTURE_2D, m.snap);
	if (m.snapW != m.W || m.snapH != m.H)
	{
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, m.W, m.H, 0, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
		m.snapW = m.W;
		m.snapH = m.H;
	}
	gl.BindFramebuffer(GL_READ_FRAMEBUFFER, HdGpu::instance().framebuffer());
	glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, m.W, m.H);
	gl.BindFramebuffer(GL_READ_FRAMEBUFFER, 0);
	glBindTexture(GL_TEXTURE_2D, 0);
	gl.ActiveTexture(GL_TEXTURE0);
	// the frame goes on from that picture
	m.start(m.W, m.H);
	m.canvasTexture = m.snap;
	Sint32 *q = m.push(K_COPY, 0, 0, m.W, m.H);
	q[8] = 0;
	q[9] = 0;
	return m.snap;
}

Uint32 *HdGpuWorld::steps(size_t table, size_t steps, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1 || x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H)
	{
		fallBack("a shape out of the world");
		return nullptr;
	}
	const size_t rowsAt = m.data.size(), rows = (size_t)(y1 - y0) * 4;
	m.data.resize(rowsAt + rows + table + steps);
	Sint32 *q = m.push(K_STEPS, x0, y0, x1, y1);
	q[8] = (Sint32)rowsAt;
	q[9] = (Sint32)(rowsAt + rows);
	q[10] = (Sint32)(rowsAt + rows + table);
	return m.data.data() + rowsAt;
}

bool HdGpuWorld::wash(const Uint32 *px, int w, int h, int ox, int oy, Uint64 key, const std::vector<Sint32> &holes,
	int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	if (!px || w <= 0 || h <= 0 || x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || x0 < ox || y0 < oy || x1 > ox + w || y1 > oy + h
		|| holes.size() % 4 != 0)
	{
		fallBack("a shape out of the world");
		return false;
	}
	if (m.frameWash && m.frameWashKey != key)
	{
		return refuse("two washes in a frame");
	}
	// the picture: uploaded when it changed
	if (!m.washValid || m.washKey != key || m.washW != w || m.washH != h)
	{
		const bool fresh = !m.washTex || m.washW != w || m.washH != h;
		if (!m.washTex)
		{
			glGenTextures(1, &m.washTex);
		}
		gl.ActiveTexture(GL_TEXTURE0);
		glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
		glBindTexture(GL_TEXTURE_2D, m.washTex);
		if (fresh)
		{
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
			glTexImage2D(GL_TEXTURE_2D, 0, 0x8236 /* GL_R32UI */, w, h, 0, 0x8D94 /* GL_RED_INTEGER */, GL_UNSIGNED_INT, px);
		}
		else
		{
			glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, 0x8D94 /* GL_RED_INTEGER */, GL_UNSIGNED_INT, px);
		}
		glBindTexture(GL_TEXTURE_2D, 0);
		m.washW = w;
		m.washH = h;
		m.washKey = key;
		m.washValid = true;
		++m.stats.uploads;
		m.stats.uploadBytes += (long long)w * h * 4;
	}
	m.frameWash = true;
	m.frameWashKey = key;
	const Sint32 at = (Sint32)m.data.size();
	m.data.insert(m.data.end(), holes.begin(), holes.end());
	Sint32 *q = m.push(K_WASH, x0, y0, x1, y1);
	q[8] = at;
	q[9] = (Sint32)(holes.size() / 4);
	q[10] = ox;
	q[11] = oy;
	return true;
}

bool HdGpuWorld::radar(const Radar &r, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (!m.radarOK)
	{
		return false;
	}
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	const size_t W = (size_t)(x1 - x0), H = (size_t)(y1 - y0);
	bool bad = x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || r.xs.size() != W || r.ys.size() != H || r.rows.size() != H * 2 || r.lut < 1
		|| (r.dist && (r.distW <= 0 || r.distH <= 0));
	for (const RadarGroup &g : r.groups)
	{
		bad = bad || g.a < 0 || g.a > g.b || g.b > (int)r.waves.size();
	}
	if (bad)
	{
		fallBack("a shape out of the world");
		return false;
	}
	// the distances: uploaded when they changed
	if (r.dist)
	{
		if (m.frameDist && m.frameDistKey != r.distKey)
		{
			return refuse("two radars in a frame");
		}
		if (!m.distValid || m.distKey != r.distKey || m.distW != r.distW || m.distH != r.distH)
		{
			const bool fresh = !m.distTex || m.distW != r.distW || m.distH != r.distH;
			if (!m.distTex)
			{
				glGenTextures(1, &m.distTex);
			}
			gl.ActiveTexture(GL_TEXTURE0);
			glPixelStorei(GL_UNPACK_ALIGNMENT, 2);
			glBindTexture(GL_TEXTURE_2D, m.distTex);
			if (fresh)
			{
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
				glTexImage2D(GL_TEXTURE_2D, 0, 0x8233 /* GL_R16I */, r.distW, r.distH, 0, 0x8D94 /* GL_RED_INTEGER */, GL_SHORT, r.dist);
			}
			else
			{
				glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, r.distW, r.distH, 0x8D94 /* GL_RED_INTEGER */, GL_SHORT, r.dist);
			}
			glBindTexture(GL_TEXTURE_2D, 0);
			glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
			m.distW = r.distW;
			m.distH = r.distH;
			m.distKey = r.distKey;
			m.distValid = true;
			++m.stats.uploads;
			m.stats.uploadBytes += (long long)r.distW * r.distH * 2;
		}
		m.frameDist = true;
		m.frameDistKey = r.distKey;
	}
	std::vector<Uint32, NoInit<Uint32>> &d = m.data, top;
	std::vector<Uint32, NoInit<Uint32>> *to = &d;
	auto word = [&](Sint32 v) { to->push_back((Uint32)v); };
	auto real = [&](double v) { Uint32 w[2]; std::memcpy(w, &v, 8); to->push_back(w[0]); to->push_back(w[1]); };
	auto bits = [&](float v) { Uint32 w; std::memcpy(&w, &v, 4); to->push_back(w); };
	// the boxes within the rectangle (the shader reads them as they are; a pixel outside is never asked about)
	auto box = [&](const RadarCap &c)
	{
		word(std::max(c.x0, x0));
		word(std::max(c.y0, y0));
		word(std::max(std::min(c.x1, x1), x0));
		word(std::max(std::min(c.y1, y1), y0));
	};
	const Sint32 kAt = m.table((const Uint32 *)RADAR_K, (int)(sizeof(RADAR_K) / 4));
	const Sint32 head = (Sint32)d.size();
	d.resize(d.size() + RADAR_HEAD, 0);
	const Sint32 xsAt = (Sint32)d.size();
	for (double v : r.xs) real(v);
	const Sint32 ysAt = (Sint32)d.size();
	for (double v : r.ys) real(v);
	const Sint32 rowsAt = (Sint32)d.size();
	for (Sint32 v : r.rows) word(std::max(v, 0));
	const Sint32 swAt = (Sint32)d.size();
	for (const RadarSweep &s : r.sweeps)
	{
		real(s.cap.cx); real(s.cap.cy); real(s.cap.cz); real(s.cap.cosR);
		real(s.sx); real(s.sy); real(s.angle); real(s.ux); real(s.uy);
		box(s.cap);
		word(s.front ? 1 : 0);
	}
	const Sint32 grAt = (Sint32)d.size();
	for (const RadarGroup &g : r.groups)
	{
		real(g.cap.cx); real(g.cap.cy); real(g.cap.cz);
		box(g.cap);
		word(g.a); word(g.b);
		word(g.craft ? 1 : 0);
	}
	std::vector<Sint32> luts;
	for (const RadarWave &w : r.waves)
	{
		luts.push_back((Sint32)d.size());
		d.insert(d.end(), (const Uint32 *)w.light, (const Uint32 *)w.light + r.lut + 1);
	}
	const Sint32 wvAt = (Sint32)d.size();
	for (size_t i = 0; i < r.waves.size(); ++i)
	{
		real(r.waves[i].cosLo); real(r.waves[i].cosHi); real(r.waves[i].scale);
		word(luts[i]);
	}
	// the head, its words as the shader's radar() reads them
	to = &top;
	word((r.bare ? 1 : 0) | (r.craftBeam ? 2 : 0));
	word((Sint32)r.sweeps.size()); word((Sint32)r.groups.size());
	word(xsAt); word(ysAt); word(rowsAt); word(swAt); word(grAt); word(wvAt);
	word((Sint32)r.wave);
	bits(256.0f / 255.0f);   // HdRadar's a256 of a wave
	bits(0.01f);             // the least open sky a beam shows in
	word(kAt);
	if (r.dist)
	{
		word(std::max(r.distX, x0)); word(std::max(r.distY, y0));
		word(std::max(std::min(r.distX + r.distW, x1), x0)); word(std::max(std::min(r.distY + r.distH, y1), y0));
	}
	else
	{
		word(0); word(0); word(0); word(0);
	}
	word(x0); word(y0);
	real(r.radius); real(r.lineW); real(r.glowLen); real(r.beamW);
	word((Sint32)r.fill); word((Sint32)r.edge); word((Sint32)r.trailColor); word((Sint32)r.beam);
	word(r.lut);
	bits(r.glow);
	real(r.trail); real(r.trailCos2);
	if (top.size() != (size_t)RADAR_HEAD)
	{
		fallBack("a radar head of the wrong size");
		return false;
	}
	std::memcpy(&d[head], top.data(), sizeof(Uint32) * RADAR_HEAD);
	Sint32 *q = m.push(K_RADAR, x0, y0, x1, y1);
	q[8] = head;
	q[9] = r.distX;
	q[10] = r.distY;
	return true;
}

bool HdGpuWorld::building(const std::vector<float> &vals, const float *glowLut, int lutSize, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || lutSize < 1 || vals.size() != (size_t)(x1 - x0) * (y1 - y0) * 6)
	{
		fallBack("a shape out of the world");
		return false;
	}
	const Sint32 lutAt = m.table((const Uint32 *)glowLut, lutSize);
	const Sint32 at = (Sint32)m.data.size();
	m.data.resize(m.data.size() + vals.size());
	std::memcpy(&m.data[at], vals.data(), vals.size() * 4);
	Sint32 *q = m.push(K_SHADE, x0, y0, x1, y1);
	q[8] = at;
	q[9] = S_BUILD;
	q[10] = lutAt;
	q[11] = lutSize;
	return true;
}

bool HdGpuWorld::alarm(const std::vector<Uint32> &px, const Uint32 *wash, const Uint32 *stripe1, const Uint32 *stripe2, int x0, int y0, int x1, int y1)
{
	Impl &m = *_impl;
	if (x0 >= x1 || y0 >= y1)
	{
		return true;
	}
	if (x0 < 0 || y0 < 0 || x1 > m.W || y1 > m.H || px.size() != (size_t)(x1 - x0) * (y1 - y0))
	{
		fallBack("a shape out of the world");
		return false;
	}
	const Sint32 washAt = m.table(wash, 256), s1At = m.table(stripe1, 256), s2At = m.table(stripe2, 256);
	const Sint32 at = (Sint32)m.data.size();
	m.data.insert(m.data.end(), px.begin(), px.end());
	Sint32 *q = m.push(K_ALARM, x0, y0, x1, y1);
	q[8] = at;
	q[9] = washAt;
	q[10] = s1At;
	q[11] = s2At;
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
