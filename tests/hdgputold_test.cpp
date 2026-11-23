/*
 * What the video driver tells of its errors (src/Engine/HdGpuTold.h) without a video card: several threads tell
 * at once, as a driver with threads of its own does, while one thread takes - no error is lost, and the text taken
 * is always one whole message, never a mix of two (AUDIT-04 3). The run the thread sanitizer looks at.
 */
#include <atomic>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>
#include "../src/Engine/HdGpuTold.h"

using OpenXcom::HdGpuTold;

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

const int THREADS = 8, EACH = 20000;

/// The message of thread t: one letter all along, so that a mix of two shows.
std::string messageOf(int t)
{
	return std::string(40 + t * 20, (char)('a' + t));
}

bool wholeMessage(const std::string &text)
{
	for (int t = 0; t < THREADS; ++t)
	{
		if (text == messageOf(t))
		{
			return true;
		}
	}
	return false;
}

void manyTellOneTakes()
{
	HdGpuTold told;
	std::atomic<int> running { THREADS };
	std::vector<std::thread> drivers;
	for (int t = 0; t < THREADS; ++t)
	{
		drivers.emplace_back([&, t]
		{
			const std::string message = messageOf(t);
			for (int i = 0; i < EACH; ++i)
			{
				told.tell(message.c_str());
			}
			--running;
		});
	}
	unsigned long long taken = 0;
	int mixed = 0, takes = 0;
	for (;;)
	{
		const bool last = running == 0; // read before the take: what was told before it is taken by it
		std::string first = "untouched";
		const unsigned n = told.take(first);
		if (n)
		{
			++takes;
			taken += n;
			mixed += !wholeMessage(first);
		}
		else
		{
			mixed += first != "untouched";
		}
		if (last)
		{
			break;
		}
	}
	for (auto &d : drivers)
	{
		d.join();
	}
	CHECK(taken == (unsigned long long)THREADS * EACH);
	CHECK(mixed == 0);
	std::printf("%d thread(s) told %llu error(s), taken in %d take(s)\n", THREADS, taken, takes);
}

void edges()
{
	HdGpuTold told;
	std::string first = "as it was";
	CHECK(told.take(first) == 0);
	CHECK(first == "as it was");
	told.tell(nullptr); // a driver may give no text
	told.tell("second");
	CHECK(told.take(first) == 2);
	CHECK(first.empty());
	const std::string longText(1000, 'x'); // longer than the buffer: cut, ended
	told.tell(longText.c_str());
	CHECK(told.take(first) == 1);
	CHECK(first.size() == 239 && first.find_first_not_of('x') == std::string::npos);
	CHECK(told.take(first) == 0);
}

}

int main()
{
	try
	{
		edges();
		manyTellOneTakes();
	}
	catch (...)
	{
		++failures;
		std::printf("FAILED: an exception\n");
	}
	std::printf(failures ? "%d check(s) FAILED\n" : "all checks passed\n", failures);
	return failures ? 1 : 0;
}
