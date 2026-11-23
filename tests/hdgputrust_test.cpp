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
// HdGpuTrust: the world on the card after the driver's errors - one error, errors in a row, errors now and then,
// errors after every rest. A play of FRAME_MS a frame with an error every N frames of the card.
#include <cstdio>
#include "../src/Engine/HdGpuTrust.h"

using OpenXcom::HdGpuTrust;

namespace
{

int failures = 0;

void check(bool ok, const char *what, int line)
{
	if (!ok)
	{
		++failures;
		std::printf("FAILED line %d: %s\n", line, what);
	}
}

#define CHECK(x) check((x), #x, __LINE__)

const unsigned FRAME_MS = 16;

struct Play
{
	long long cardFrames = 0, cpuFrames = 0, anew = 0, rests = 0;
	bool off = false;
};

/// frames of the game with an error told of after every `every` frames the card drew (0: never), `errors` at most.
Play play(HdGpuTrust &trust, long long frames, long long every, long long errors, unsigned start = 0)
{
	Play p;
	long long sinceError = 0;
	unsigned now = start;
	for (long long f = 0; f < frames; ++f, now += FRAME_MS)
	{
		if (!trust.card(now))
		{
			++p.cpuFrames;
			continue;
		}
		if (every && errors > 0 && ++sinceError >= every)
		{
			sinceError = 0;
			--errors;
			++p.cpuFrames;
			switch (trust.error(now))
			{
			case HdGpuTrust::ANEW: ++p.anew; break;
			case HdGpuTrust::REST: ++p.rests; break;
			case HdGpuTrust::OFF: p.off = true; break;
			}
			continue;
		}
		++p.cardFrames;
		trust.frame();
	}
	p.off = trust.off();
	return p;
}

const long long HOUR = 3600 * 1000 / FRAME_MS;

void oneError()
{
	HdGpuTrust trust;
	const Play p = play(trust, HOUR, 100, 1);
	CHECK(p.anew == 1 && p.rests == 0 && !p.off);
	CHECK(p.cpuFrames == 1);
}

void rareErrors()
{
	// less often than FORGIVE: forgiven every time, the card for ever, never a rest
	HdGpuTrust trust;
	const Play p = play(trust, 10 * HOUR, HdGpuTrust::FORGIVE + 1, 1000000);
	CHECK(p.rests == 0 && !p.off);
	CHECK(p.anew >= 10 * HOUR / (HdGpuTrust::FORGIVE + 2) - 1);
	CHECK(p.cpuFrames == p.anew);
}

void errorsInARow()
{
	// every frame of the card: ERRORS errors to the first rest, one error after each rest, then off - and no more
	HdGpuTrust trust;
	const Play p = play(trust, 10 * HOUR, 1, 1000000);
	CHECK(p.off);
	CHECK(p.rests == HdGpuTrust::RESTS);
	CHECK(p.anew == HdGpuTrust::ERRORS - 1);
	CHECK(p.cardFrames == 0);
	// off holds: the card is not asked again, however long
	const Play later = play(trust, 100 * HOUR, 1, 1000000, 4000000000u);
	CHECK(later.cardFrames == 0 && later.anew == 0 && later.rests == 0 && later.off);
}

void frequentErrors()
{
	// more often than FORGIVE (twice): ends at the processor, the card made anew a few times only
	HdGpuTrust trust;
	const Play p = play(trust, 100 * HOUR, HdGpuTrust::FORGIVE / 2, 1000000);
	CHECK(p.off);
	CHECK(p.anew + p.rests <= 2 * (HdGpuTrust::ERRORS + HdGpuTrust::RESTS));
}

void burstThenQuiet()
{
	// a burst (the first rest), then quiet: the card comes back after the rest and stays; everything is forgiven
	HdGpuTrust trust;
	Play p = play(trust, HOUR, 1, HdGpuTrust::ERRORS);
	CHECK(p.rests == 1 && !p.off);
	CHECK(p.cpuFrames <= HdGpuTrust::ERRORS + HdGpuTrust::REST_MS / FRAME_MS + 1);
	CHECK(p.cardFrames > HOUR / 2);
	p = play(trust, 10 * HOUR, 0, 0, 3600 * 1000);
	CHECK(trust.rests() == 0);
	// and the next burst starts from nothing: ERRORS errors to a rest again
	p = play(trust, HOUR, 1, HdGpuTrust::ERRORS - 1, 11 * 3600 * 1000);
	CHECK(p.anew == HdGpuTrust::ERRORS - 1 && p.rests == 0);
}

void restsGrow()
{
	HdGpuTrust trust;
	unsigned now = 1000;
	for (int i = 0; i < HdGpuTrust::ERRORS - 1; ++i)
	{
		CHECK(trust.error(now) == HdGpuTrust::ANEW);
	}
	for (int rest = 0; rest < HdGpuTrust::RESTS; ++rest)
	{
		CHECK(trust.error(now) == HdGpuTrust::REST);
		const unsigned length = HdGpuTrust::REST_MS << rest;
		CHECK(!trust.card(now));
		CHECK(!trust.card(now + length - 1));
		CHECK(trust.card(now + length));
		now += length;
	}
	CHECK(trust.error(now) == HdGpuTrust::OFF);
	CHECK(!trust.card(now + 1000000000u));
	trust.reset();
	CHECK(trust.card(now) && !trust.off());
	CHECK(trust.error(now) == HdGpuTrust::ANEW);
}

void clockWraps()
{
	// SDL_GetTicks goes round after 49 days: a rest that started just before is as long as any
	HdGpuTrust trust;
	const unsigned now = 0xFFFFFFF0u;
	for (int i = 0; i < HdGpuTrust::ERRORS; ++i)
	{
		trust.error(now);
	}
	CHECK(!trust.card(now + 100));
	CHECK(!trust.card(now + HdGpuTrust::REST_MS - 1));
	CHECK(trust.card(now + HdGpuTrust::REST_MS));
}

}

int main()
{
	oneError();
	rareErrors();
	errorsInARow();
	frequentErrors();
	burstThenQuiet();
	restsGrow();
	clockWraps();
	std::printf(failures ? "hdgputrust_test: %d FAILED\n" : "hdgputrust_test: ok\n", failures);
	return failures ? 1 : 0;
}
