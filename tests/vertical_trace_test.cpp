// vertical_trace_test.cpp: the rays of the battle's line of fire when the target is straight above or straight
// below the shooter (audit AUDIT-04 9). A test only: nothing of the game is changed by it.
//
// TileEngine::checkVoxelExposure() and canTargetUnit() send, besides the central ray, side rays to
// target + (relX, relY). With the shooter and the target in one column of voxels relX and relY are INT_MIN (the
// value x86 gave for the 0/0 of the formula), so a side ray goes to (x + INT_MIN, y + INT_MIN, z). In
// calculateLineHelper() that was abs(INT_MIN) and then a signed overflow of the drift: undefined behaviour, and
// compilers answered differently. The helper's arithmetic wraps now, as x86 gcc always made it; the rays below
// were recorded BEFORE that fix, so the test holds that the fix moved nothing.
//
// The helper is the game's own text: tests/cut_line_helper.cmake cuts it out of src/Battlescape/TileEngine.cpp
// when the test is built. Only Position is a stand-in here (three numbers; the helper uses nothing else of it).
//
//   vertical_trace_test plain    the rays without undefined behaviour (an ordinary line, the central vertical ray):
//                                must give the recorded answers under every compiler and sanitizer
//   vertical_trace_test intmin   the side rays, compared with what the game's compiler (x86-64 gcc) gave on
//                                18.11.2026 before the fix: the same under every compiler and sanitizer
//   vertical_trace_test print    prints every ray (to record the answers anew)
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

namespace OpenXcom
{

struct Position
{
	int x, y, z;
	Position(int x_, int y_, int z_) : x(x_), y(y_), z(z_) {}
};

namespace
{
#include "calc_line_helper.inc"
}

}

using OpenXcom::Position;

namespace
{

/// A ray may not end where it should once its arithmetic is undefined: it is cut here, and the cut is told.
const int STEP_LIMIT = 4096;

std::string ray(const Position &origin, const Position &target)
{
	std::string out;
	int steps = 0;
	const auto note = [&](char kind, const Position &p)
	{
		char text[64];
		std::snprintf(text, sizeof(text), "%s%c%d,%d,%d", out.empty() ? "" : " ", kind, p.x, p.y, p.z);
		out += text;
		return ++steps >= STEP_LIMIT;
	};
	const bool stopped = OpenXcom::calculateLineHelper(origin, target,
		[&](const Position &p) { return note('p', p); }, [&](const Position &p) { return note('d', p); });
	if (stopped)
	{
		out += " CUT";
	}
	return out;
}

struct Case
{
	const char *name;
	Position origin, target;
	bool undefined; // a side ray: the target is moved by INT_MIN as the game moves it
	const char *recorded;
};

// The voxels of a soldier on tile (10, 6): the middle of the tile, the eyes at 20 of the level. The target stands
// on the same tile a level above (z 24..47) or a level below; the scan takes several heights of its body.
const Case CASES[] = {
	{"ordinary line", {168, 104, 20}, {174, 101, 22}, false,
		"p168,104,20 p169,104,20 d169,103,20 d169,103,21 p170,103,21 p171,103,21 d171,102,21 p172,102,21 "
		"d172,102,22 p173,102,22 d173,101,22 p174,101,22"},
	{"central ray, target above", {168, 104, 20}, {168, 104, 36}, false,
		"p168,104,20 p168,104,21 p168,104,22 p168,104,23 p168,104,24 p168,104,25 p168,104,26 p168,104,27 "
		"p168,104,28 p168,104,29 p168,104,30 p168,104,31 p168,104,32 p168,104,33 p168,104,34 p168,104,35 "
		"p168,104,36"},
	{"central ray, target below", {168, 104, 44}, {168, 104, 12}, false,
		"p168,104,44 p168,104,43 p168,104,42 p168,104,41 p168,104,40 p168,104,39 p168,104,38 p168,104,37 "
		"p168,104,36 p168,104,35 p168,104,34 p168,104,33 p168,104,32 p168,104,31 p168,104,30 p168,104,29 "
		"p168,104,28 p168,104,27 p168,104,26 p168,104,25 p168,104,24 p168,104,23 p168,104,22 p168,104,21 "
		"p168,104,20 p168,104,19 p168,104,18 p168,104,17 p168,104,16 p168,104,15 p168,104,14 p168,104,13 "
		"p168,104,12"},
	{"side ray, target above", {168, 104, 20}, {168, 104, 36}, true,
		"p168,104,20 d168,103,20 d167,103,20 p167,103,21 p167,103,22 d167,102,22 d166,102,22 p166,102,23 "
		"p166,102,24 d166,101,24 d165,101,24 p165,101,25 p165,101,26 d165,100,26 d164,100,26 p164,100,27 "
		"p164,100,28 d164,99,28 d163,99,28 p163,99,29 p163,99,30 d163,98,30 d162,98,30 p162,98,31 "
		"p162,98,32 d162,97,32 d161,97,32 p161,97,33 p161,97,34 d161,96,34 d160,96,34 p160,96,35 "
		"p160,96,36"},
	{"side ray, target above, its top", {168, 104, 20}, {168, 104, 46}, true,
		"p168,104,20 d168,103,20 d167,103,20 p167,103,21 p167,103,22 d167,102,22 d166,102,22 p166,102,23 "
		"p166,102,24 d166,101,24 d165,101,24 p165,101,25 p165,101,26 d165,100,26 d164,100,26 p164,100,27 "
		"p164,100,28 d164,99,28 d163,99,28 p163,99,29 p163,99,30 d163,98,30 d162,98,30 p162,98,31 "
		"p162,98,32 d162,97,32 d161,97,32 p161,97,33 p161,97,34 d161,96,34 d160,96,34 p160,96,35 "
		"p160,96,36 d160,95,36 d159,95,36 p159,95,37 p159,95,38 d159,94,38 d158,94,38 p158,94,39 "
		"p158,94,40 d158,93,40 d157,93,40 p157,93,41 p157,93,42 d157,92,42 d156,92,42 p156,92,43 "
		"p156,92,44 d156,91,44 d155,91,44 p155,91,45 p155,91,46"},
	{"side ray, target below", {168, 104, 44}, {168, 104, 12}, true,
		"p168,104,44 d168,103,44 d167,103,44 p167,103,43 p167,103,42 d167,102,42 d166,102,42 p166,102,41 "
		"p166,102,40 d166,101,40 d165,101,40 p165,101,39 p165,101,38 d165,100,38 d164,100,38 p164,100,37 "
		"p164,100,36 d164,99,36 d163,99,36 p163,99,35 p163,99,34 d163,98,34 d162,98,34 p162,98,33 "
		"p162,98,32 d162,97,32 d161,97,32 p161,97,31 p161,97,30 d161,96,30 d160,96,30 p160,96,29 "
		"p160,96,28 d160,95,28 d159,95,28 p159,95,27 p159,95,26 d159,94,26 d158,94,26 p158,94,25 "
		"p158,94,24 d158,93,24 d157,93,24 p157,93,23 p157,93,22 d157,92,22 d156,92,22 p156,92,21 "
		"p156,92,20 d156,91,20 d155,91,20 p155,91,19 p155,91,18 d155,90,18 d154,90,18 p154,90,17 "
		"p154,90,16 d154,89,16 d153,89,16 p153,89,15 p153,89,14 d153,88,14 d152,88,14 p152,88,13 "
		"p152,88,12"},
	{"side ray, target below, its top", {168, 104, 44}, {168, 104, 22}, true,
		"p168,104,44 d168,103,44 d167,103,44 p167,103,43 p167,103,42 d167,102,42 d166,102,42 p166,102,41 "
		"p166,102,40 d166,101,40 d165,101,40 p165,101,39 p165,101,38 d165,100,38 d164,100,38 p164,100,37 "
		"p164,100,36 d164,99,36 d163,99,36 p163,99,35 p163,99,34 d163,98,34 d162,98,34 p162,98,33 "
		"p162,98,32 d162,97,32 d161,97,32 p161,97,31 p161,97,30 d161,96,30 d160,96,30 p160,96,29 "
		"p160,96,28 d160,95,28 d159,95,28 p159,95,27 p159,95,26 d159,94,26 d158,94,26 p158,94,25 "
		"p158,94,24 d158,93,24 d157,93,24 p157,93,23 p157,93,22"},
};

}

int main(int argc, char **argv)
{
	const std::string mode = argc > 1 ? argv[1] : "";
	if (mode != "plain" && mode != "intmin" && mode != "print")
	{
		std::printf("usage: vertical_trace_test plain|intmin|print\n");
		return 2;
	}
	int failures = 0, played = 0;
	for (const Case &c : CASES)
	{
		if (mode != "print" && c.undefined != (mode == "intmin"))
		{
			continue;
		}
		Position target = c.target;
		if (c.undefined)
		{
			// as TileEngine does it: scanVoxel.x = targetVoxel.x + sliceTargets[...], the slice being INT_MIN
			target.x += INT_MIN;
			target.y += INT_MIN;
		}
		const std::string got = ray(c.origin, target);
		++played;
		if (mode == "print")
		{
			std::printf("%s:\n%s\n", c.name, got.c_str());
		}
		else if (got != c.recorded)
		{
			++failures;
			std::printf("FAILED %s: the ray is not the recorded one\n  now:      %s\n  recorded: %s\n", c.name, got.c_str(), c.recorded);
		}
		else
		{
			std::printf("ok     %s: %d voxel(s), as recorded\n", c.name, (int)std::count(got.begin(), got.end(), ',') / 2);
		}
	}
	if (mode != "print")
	{
		std::printf("%s: %d ray(s), %d not as recorded\n", mode.c_str(), played, failures);
	}
	return failures ? 1 : 0;
}
