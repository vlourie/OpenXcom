/*
 * The contract of the HD render pool (src/Engine/HdWorkers.h) without the game: every job once, a job that throws
 * run again by the caller, the answer of run() and the Whole of whoever keeps the result. Built by tests/CMakeLists.txt
 * (also with the sanitizers: address + undefined anywhere, thread on Linux); needs no data of the game.
 */
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <new>
#include <stdexcept>
#include <thread>
#include <vector>
#include "../src/Engine/HdWorkers.h"

using OpenXcom::HdWorkers;

// The memory of the test goes through here so that one request of one thread can be refused (noMemoryForTheNote):
// 1 - the next operator new of this thread throws std::bad_alloc, and the counter falls to 0.
static thread_local int refuseNew = 0;

// The thread sanitizer has its own operator new, and a second one does not link: there the refusal of memory is
// not played (noMemoryForTheNote runs under gcc and under ASan + UBSan).
#if defined(__SANITIZE_THREAD__)
#define OWN_NEW 0
#elif defined(__has_feature)
#if __has_feature(thread_sanitizer)
#define OWN_NEW 0
#endif
#endif
#ifndef OWN_NEW
#define OWN_NEW 1
#endif

#if OWN_NEW
void *operator new(std::size_t size)
{
	if (refuseNew > 0 && --refuseNew == 0)
	{
		throw std::bad_alloc();
	}
	if (void *p = std::malloc(size ? size : 1))
	{
		return p;
	}
	throw std::bad_alloc();
}

void operator delete(void *p) noexcept
{
	std::free(p);
}

void operator delete(void *p, std::size_t) noexcept
{
	std::free(p);
}
#endif

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

/// Every job of a batch runs exactly once, whatever the size of the batch.
void everyJobOnce()
{
	HdWorkers &pool = HdWorkers::instance();
	for (int jobs : { 0, 1, 2, 7, 64, 1000 })
	{
		std::vector<std::atomic<int>> ran(jobs);
		const bool whole = pool.run(jobs, [&](int i) { ++ran[i]; });
		CHECK(whole);
		int wrong = 0;
		for (auto &n : ran)
		{
			wrong += n != 1;
		}
		CHECK(wrong == 0);
	}
}

/// A job that throws once is run again by the caller: the batch is whole.
void failedJobRunAgain()
{
	HdWorkers &pool = HdWorkers::instance();
	const HdWorkers::Whole whole;
	std::vector<std::atomic<int>> ran(100);
	std::atomic<int> thrown { 0 };
	const bool ok = pool.run(100, [&](int i)
	{
		if (i % 10 == 3 && ran[i]++ == 0)
		{
			++thrown;
			throw std::runtime_error("once");
		}
		if (i % 10 != 3)
		{
			++ran[i];
		}
	});
	CHECK(ok);
	CHECK(thrown == 10);
	CHECK(whole.ok());
	int wrong = 0;
	for (int i = 0; i < 100; ++i)
	{
		wrong += ran[i] != (i % 10 == 3 ? 2 : 1);
	}
	CHECK(wrong == 0);
}

/// A job that always throws: the answer is false, the Whole standing over it says so, the other jobs still ran.
void failedTwiceIsNotWhole()
{
	HdWorkers &pool = HdWorkers::instance();
	HdWorkers::Whole whole;
	std::vector<std::atomic<int>> ran(50);
	std::atomic<int> tried { 0 };
	const bool ok = pool.run(50, [&](int i)
	{
		if (i == 17)
		{
			++tried;
			throw std::bad_alloc();
		}
		++ran[i];
	});
	CHECK(!ok);
	CHECK(tried == 2);
	CHECK(!whole.ok());
	int wrong = 0;
	for (int i = 0; i < 50; ++i)
	{
		wrong += ran[i] != (i == 17 ? 0 : 1);
	}
	CHECK(wrong == 0);
	whole.reset();
	CHECK(whole.ok());
}

/// NO_RETRY: a job that cannot start anew is not run again. ONCE: a batch made once gets six more tries.
void triesAreKept()
{
	HdWorkers &pool = HdWorkers::instance();
	std::atomic<int> tried { 0 };
	bool ok = pool.run(8, [&](int i)
	{
		if (i == 5)
		{
			++tried;
			throw std::runtime_error("no retry");
		}
	}, HdWorkers::NO_RETRY);
	CHECK(!ok);
	CHECK(tried == 1);

	tried = 0;
	ok = pool.run(8, [&](int i)
	{
		if (i == 5 && ++tried <= 5)
		{
			throw std::runtime_error("five times");
		}
	}, HdWorkers::ONCE);
	CHECK(ok);
	CHECK(tried == 6);
}

/// runCounted(): the answer is not asked for where it is called, the Whole of the keeper still sees the failure.
void countedFailureReachesTheKeeper()
{
	HdWorkers &pool = HdWorkers::instance();
	const HdWorkers::Whole clean;
	pool.runCounted(16, [](int) {});
	CHECK(clean.ok());
	const HdWorkers::Whole whole;
	pool.runCounted(16, [](int i)
	{
		if (i == 0)
		{
			throw 1; // not a std::exception either
		}
	});
	CHECK(!whole.ok());
}

/// Many batches of many sizes one after another, with failures among them: sums are whole, nothing hangs
/// (the run the thread sanitizer looks at).
void manyBatches()
{
	HdWorkers &pool = HdWorkers::instance();
	long long expected = 0;
	std::atomic<long long> sum { 0 };
	int notWhole = 0;
	for (int batch = 0; batch < 3000; ++batch)
	{
		const int jobs = 1 + batch % 37;
		std::vector<std::atomic<int>> first(jobs);
		const bool ok = pool.run(jobs, [&](int i)
		{
			if (batch % 50 == 7 && i == jobs / 2 && first[i]++ == 0)
			{
				throw std::runtime_error("now and then");
			}
			volatile int spin = 0;
			for (int n = 0; n < (batch % 5) * 200; ++n)
			{
				spin = spin + n;
			}
			sum += i + 1;
		});
		notWhole += !ok;
		expected += (long long)jobs * (jobs + 1) / 2;
	}
	CHECK(notWhole == 0);
	CHECK(sum == expected);
}

/// Two threads run batches at the same time (the pool serves one, the other runs its own jobs itself), one of
/// them with jobs that always throw. The count of holes is one for the whole program (AUDIT-04 1), so:
/// - the answer of run() is each batch's own: the clean thread never gets false;
/// - a Whole over a batch that was left not whole never says ok;
/// - a Whole over a clean batch MAY say "not ok" because of the other thread (the thing is then made once more) -
///   that is counted and printed, not failed.
void twoThreadsAtOnce()
{
	HdWorkers &pool = HdWorkers::instance();
	std::atomic<int> cleanFalse { 0 }, cleanWrongJobs { 0 }, foreign { 0 }, brokenTrue { 0 }, brokenWholeOk { 0 };
	std::atomic<bool> stop { false };
	std::thread breaker([&]
	{
		for (int batch = 0; batch < 400; ++batch)
		{
			const HdWorkers::Whole whole;
			const bool ok = pool.run(12, [&](int i)
			{
				if (i == batch % 12)
				{
					throw std::runtime_error("always");
				}
			});
			brokenTrue += ok;
			brokenWholeOk += whole.ok();
		}
		stop = true;
	});
	int batches = 0;
	while (!stop)
	{
		++batches;
		std::vector<std::atomic<int>> ran(24);
		const HdWorkers::Whole whole;
		const bool ok = pool.run(24, [&](int i) { ++ran[i]; });
		cleanFalse += !ok;
		foreign += !whole.ok();
		for (auto &n : ran)
		{
			cleanWrongJobs += n != 1;
		}
	}
	breaker.join();
	CHECK(cleanFalse == 0);
	CHECK(cleanWrongJobs == 0);
	CHECK(brokenTrue == 0);
	CHECK(brokenWholeOk == 0);
	std::printf("two threads at once: %d clean batch(es), %d of them saw a hole of the other thread\n", batches, foreign.load());
}

/// No memory for the pool's note of a call site (its cost, kept to wake fewer threads): a help only - the batch
/// must still run whole, and no exception may leave run() (AUDIT-04 2).
void noMemoryForTheNote()
{
	if (!OWN_NEW)
	{
		std::printf("no memory for the note: not played under the thread sanitizer\n");
		return;
	}
	HdWorkers &pool = HdWorkers::instance();
	if (pool.threads() < 2)
	{
		return; // a pool of the caller alone keeps no notes
	}
	std::vector<std::atomic<int>> ran(8);
	// a call site the pool has not seen (a type of its own); made before the refusal is armed
	const std::function<void(int)> fresh = [&ran](int i) { ++ran[i]; };
	bool ok = false, thrown = false;
	refuseNew = 1;
	try
	{
		ok = pool.run(8, fresh);
	}
	catch (...)
	{
		thrown = true;
	}
	const bool refused = refuseNew == 0;
	refuseNew = 0;
	CHECK(refused); // the note was the request refused: otherwise this test proves nothing
	CHECK(!thrown);
	CHECK(ok);
	int wrong = 0;
	for (auto &n : ran)
	{
		wrong += n != 1;
	}
	CHECK(wrong == 0);
}

void budgetFitsTheMachine()
{
	const size_t bytes = (size_t)384 << 20;
	const size_t got = HdWorkers::cacheBudget(bytes);
	CHECK(got <= bytes);
	CHECK(got >= bytes / 4);
}

}

int main()
{
	try
	{
		std::printf("pool of %d thread(s)\n", HdWorkers::instance().threads());
		everyJobOnce();
		failedJobRunAgain();
		failedTwiceIsNotWhole();
		triesAreKept();
		countedFailureReachesTheKeeper();
		manyBatches();
		noMemoryForTheNote();
		twoThreadsAtOnce();
		budgetFitsTheMachine();
	}
	catch (...)
	{
		// run() lets no exception of a job out: one that came here is a failure of the contract
		++failures;
		std::printf("FAILED: an exception left the pool\n");
	}
	std::printf(failures ? "%d check(s) FAILED\n" : "all checks passed\n", failures);
	return failures ? 1 : 0;
}
