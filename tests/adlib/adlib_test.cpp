// The Adlib player of the game (src/Engine/Adlib) on real and on damaged tracks, without the game.
//
//   adlib_test bad [n | count]      damaged tracks made here (no game data needed): must end without a sanitizer report;
//                                   n - one of them as a process of its own, count - how many there are
//   adlib_test hash <ADLIB.CAT>     a hash of the sound of every track of the file: the same before and after a change
//                                   of the player means the music of the game did not change
//   adlib_test fuzz <ADLIB.CAT> <seed> <count>   tracks of the file cut and damaged at random: no report, no hang
//
// The player and the synthesizer are the game's own sources; ADLIB_SRC (CMake) may name another tree to compare with.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "adlplayer.h"
#include "fmopl.h"

extern FM_OPL *opl[2];

namespace OpenXcom { namespace RNG {
// the synthesizer takes its noise from here; a fixed sequence makes the sound repeatable
int seedless(int min, int max)
{
	static uint32_t x = 2463534242u;
	x ^= x << 13; x ^= x >> 17; x ^= x << 5;
	return min + (int)(x % (uint32_t)(max - min + 1));
}
} }

typedef std::vector<unsigned char> Bytes;

static const int RATE = 44100, TICK_BYTES = 629 * 4; // AdlibMusic.cpp: the length of one tick at this rate

/// Plays the track for `ticks` ticks the way AdlibMusic::player does; returns the hash of the sound.
static uint64_t playTrack(Bytes track, int ticks)
{
	for (int i = 0; i < 2; ++i)
	{
		if (opl[i]) OPLDestroy(opl[i]);
		opl[i] = OPLCreate(OPL_TYPE_YM3812, 3579545, RATE);
	}
	// exactly the size of the track: a read past it is a read past the allocation, the sanitizer sees it
	unsigned char *data = (unsigned char *)malloc(track.size() ? track.size() : 1);
	if (!track.empty()) memcpy(data, track.data(), track.size());
	func_setup_music(data, (int)track.size());
	func_set_music_volume(127);
	std::vector<int16_t> pcm(TICK_BYTES / 2);
	uint64_t h = 1469598103934665603ull;
	for (int t = 0; t < ticks; ++t)
	{
		std::fill(pcm.begin(), pcm.end(), (int16_t)0);
		YM3812UpdateOne(opl[0], pcm.data(), TICK_BYTES / 4, 2, 1.0f);
		YM3812UpdateOne(opl[1], pcm.data() + 1, TICK_BYTES / 4, 2, 1.0f);
		for (int16_t v : pcm) { h ^= (uint16_t)v; h *= 1099511628211ull; }
		func_play_tick();
	}
	func_mute();
	free(data);
	return h;
}

static std::vector<Bytes> readCat(const char *path)
{
	std::vector<Bytes> out;
	FILE *f = fopen(path, "rb");
	if (!f) return out;
	Bytes all;
	unsigned char buf[65536];
	size_t n;
	while ((n = fread(buf, 1, sizeof(buf), f)) > 0) all.insert(all.end(), buf, buf + n);
	fclose(f);
	auto u32 = [&](size_t at) { return (uint32_t)all[at] | (uint32_t)all[at + 1] << 8 | (uint32_t)all[at + 2] << 16 | (uint32_t)all[at + 3] << 24; };
	if (all.size() < 8) return out;
	const uint32_t count = u32(0) / 8;
	// as CatFile does: the size field of a record may leave out its name, the true size is the distance to the next one
	for (uint32_t i = 0; i < count && (size_t)i * 8 + 8 <= all.size(); ++i)
	{
		const uint32_t off = u32(i * 8);
		const uint32_t next = (i + 1 < count && (size_t)i * 8 + 16 <= all.size()) ? u32(i * 8 + 8) : (uint32_t)all.size();
		if (off >= all.size() || next > all.size() || next < off) break;
		out.emplace_back(all.begin() + off, all.begin() + next);
	}
	return out;
}

// --- damaged tracks made by hand ---

/// A track of the new format: a name, the tempo, samples, subtracks, instruments (channel + commands).
static Bytes make(int samples, const std::vector<Bytes> &subtracks, const std::vector<Bytes> &instruments)
{
	Bytes t = { 1, 'T', 120, (unsigned char)samples };
	t.insert(t.end(), (size_t)samples * 24, 0x11);
	t.push_back((unsigned char)subtracks.size());
	for (const Bytes &s : subtracks)
	{
		const size_t len = s.size() + 4;
		t.push_back((unsigned char)len); t.push_back((unsigned char)(len >> 8)); t.push_back(0); t.push_back(0);
		t.insert(t.end(), s.begin(), s.end());
	}
	t.push_back((unsigned char)instruments.size());
	for (size_t i = 0; i < instruments.size(); ++i)
	{
		const size_t len = instruments[i].size() + 5;
		t.push_back((unsigned char)len); t.push_back((unsigned char)(len >> 8)); t.push_back(0); t.push_back(0);
		t.push_back((unsigned char)i);
		t.insert(t.end(), instruments[i].begin(), instruments[i].end());
	}
	return t;
}

/// @param only -1 all the cases, -2 prints their number, else the one case (a process of its own: the old player dies on it).
static int runBad(int only)
{
	struct Case { const char *name; Bytes track; };
	std::vector<Case> cases;
	// 0: the first delay of an instrument, then its commands
	cases.push_back({ "valid: one note and the end", make(1, {}, { { 0, 0xC0, 0, 0, 0x90, 40, 100, 10, 0x80, 40, 0, 1, 0xFF } }) });
	cases.push_back({ "empty", {} });
	cases.push_back({ "one byte", { 1 } });
	cases.push_back({ "name longer than the data", { 50, 'A', 'B' } });
	cases.push_back({ "more samples than data", { 1, 'T', 120, 200, 1, 2, 3 } });
	cases.push_back({ "200 subtracks", { 1, 'T', 120, 0, 200, 4, 0, 0, 0 } });
	cases.push_back({ "subtrack longer than the data", { 1, 'T', 120, 0, 1, 0xFF, 0xFF, 0, 0 } });
	cases.push_back({ "instrument longer than the data", { 1, 'T', 120, 0, 0, 1, 0xFF, 0xFF, 0, 0, 0, 0 } });
	cases.push_back({ "commands run to the end of the data", make(1, {}, { { 0, 0x90, 40, 100, 0 } }) });
	cases.push_back({ "number cut by the end of the data", make(1, {}, { { 0, 0x90, 40, 100, 0x81, 0x81 } }) });
	cases.push_back({ "call of a subtrack that does not exist", make(1, {}, { { 0, 0xFE, 99 } }) });
	cases.push_back({ "subtrack that calls itself", make(1, { { 0xFE, 0, 0 } }, { { 0, 0xFE, 0, 0 } }) });
	cases.push_back({ "loop command without a delay", make(1, {}, { { 0, 0xC0, 0x7E, 0 } }) });
	cases.push_back({ "chorus instrument 0 (index -1)", make(1, {}, { { 0, 0xB0, 0x7E, 0, 0, 0x90, 40, 100, 5, 0xFF } }) });
	cases.push_back({ "chorus instrument 127", make(1, {}, { { 0, 0xB0, 0x7E, 127, 0, 0x90, 40, 100, 5, 0xFF } }) });
	cases.push_back({ "note 0 with a pitch bend down", make(1, {}, { { 0, 0xE0, 0, 0, 0x90, 0, 100, 5, 0x90, 1, 100, 5, 0xFF } }) });
	cases.push_back({ "note 127", make(1, {}, { { 0, 0x90, 127, 100, 5, 0xFF } }) });
	cases.push_back({ "sample 100 of 1", make(1, {}, { { 0, 0xC0, 100, 0, 0x90, 40, 100, 5, 0xFF } }) });
	cases.push_back({ "16 instruments of the old format and one more", Bytes() });
	{
		Bytes t = { 120, 0, 0, 17 }; // old format: the tempo first (> 56), no samples, no subtracks, 17 instruments
		for (int i = 0; i < 17; ++i) { const unsigned char one[] = { 6, 0, 0, 0, 0, 0xFF }; t.insert(t.end(), one, one + 6); }
		cases.back().track = t;
	}
	if (only >= (int)cases.size())
		return 2;
	if (only == -2) { printf("%zu\n", cases.size()); return 0; }
	for (size_t i = 0; i < cases.size(); ++i)
	{
		if (only >= 0 && (int)i != only) continue;
		playTrack(cases[i].track, 200);
		printf("ok   %s\n", cases[i].name);
		fflush(stdout);
	}
	return 0;
}

int main(int argc, char **argv)
{
	const std::string mode = argc > 1 ? argv[1] : "";
	if (mode == "bad")
		return runBad(argc > 2 ? (strcmp(argv[2], "count") ? atoi(argv[2]) : -2) : -1);
	if ((mode == "hash" || mode == "fuzz") && argc > 2)
	{
		const std::vector<Bytes> tracks = readCat(argv[2]);
		if (tracks.empty()) { fprintf(stderr, "no tracks in %s\n", argv[2]); return 2; }
		if (mode == "hash")
		{
			for (size_t i = 0; i < tracks.size(); ++i)
				printf("%zu %zu %016llx\n", i, tracks[i].size(), (unsigned long long)playTrack(tracks[i], 3000));
			return 0;
		}
		uint32_t x = argc > 3 ? (uint32_t)strtoul(argv[3], 0, 10) : 1;
		const int count = argc > 4 ? atoi(argv[4]) : 200;
		auto rnd = [&]() { x ^= x << 13; x ^= x >> 17; x ^= x << 5; return x; };
		for (int n = 0; n < count; ++n)
		{
			Bytes t = tracks[rnd() % tracks.size()];
			switch (rnd() % 4)
			{
			case 0: t.resize(rnd() % (t.size() + 1)); break;						// cut
			case 1: for (int k = 0; k < 8; ++k) t[rnd() % t.size()] = (unsigned char)rnd(); break;	// a few bytes
			case 2: for (int k = 0; k < 200; ++k) t[rnd() % t.size()] = (unsigned char)(0xF8 + rnd() % 8); break; // calls, returns, ends
			default: t[rnd() % 64 % t.size()] = (unsigned char)rnd(); t.resize(t.size() - rnd() % 16 % t.size()); break; // the header
			}
			playTrack(t, 300);
		}
		printf("fuzz: %d tracks played\n", count);
		return 0;
	}
	fprintf(stderr, "adlib_test bad | hash <ADLIB.CAT> | fuzz <ADLIB.CAT> <seed> <count>\n");
	return 2;
}
