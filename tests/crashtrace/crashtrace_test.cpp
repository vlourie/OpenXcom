// The crash record and the trace of an exception (src/Engine/CrashTrace.cpp) in a process of its own, without the game.
//
//   crashtrace_test <mode> [log file]
//
//   exception       throws and catches: prints the frames taken where it was thrown, named (exit 0)
//   segv            reads a null pointer on the main thread
//   segv_thread     the same on a second thread (signal() never saw this one)
//   div0            integer division by zero
//   overflow        endless recursion: the record has to fit in what is left of the stack
//   second          a crash inside the notice: the process still ends, the first record stays
//   cost            the time of one capture() (what every thrown exception of the game pays)
//
// Every crash mode must leave "Crash record:" with frames in the log file and on the standard error stream, call the
// notice (prints "NOTICE ...") and end with exit code 1. run.py checks all of it and names the frames.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>
#include <windows.h>
#include "../../src/Engine/CrashTrace.h"

using namespace OpenXcom;

namespace
{

volatile int zero = 0;
volatile int *volatile nowhere = 0;
bool crashInNotice = false;

void notice(const char *what)
{
	// what the game does here: a line for the player (the game also opens a message box)
	fprintf(stderr, "NOTICE %s\n", what);
	fflush(stderr);
	if (crashInNotice)
		*nowhere = 1;
}

}

// not static: the game is linked with all its symbols exported, that is where the names of the frames come from
#define NOINLINE __attribute__((noinline))

NOINLINE int readNowhere(int a) { return *nowhere + a; }
NOINLINE int crashInner(int a) { return readNowhere(a) + 1; }
NOINLINE int crashOuter(int a) { return crashInner(a) + 1; }
NOINLINE int divide(int a) { return a / zero; }
NOINLINE int recurse(int a)
{
	volatile char pad[512];
	pad[0] = (char)a;
	return recurse(a + 1) + pad[0];
}

struct Traced : std::runtime_error
{
	void *frames[20];
	int count;
	NOINLINE Traced(const char *what) : std::runtime_error(what) { count = CrashTrace::capture(frames, 20, 0); }
};
NOINLINE void throwInner() { throw Traced("test exception"); }
NOINLINE void throwOuter() { throwInner(); zero = 1; }

int main(int argc, char **argv)
{
	const std::string mode = argc > 1 ? argv[1] : "";
	setvbuf(stdout, 0, _IONBF, 0);
	// no dialog of the system on a crash: the test is not to wait for a click
	SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
	CrashTrace::install(notice);
	if (argc > 2)
		CrashTrace::setLogFile(argv[2]);

	if (mode == "exception")
	{
		try
		{
			throwOuter();
		}
		catch (const Traced &e)
		{
			printf("caught: %s, %d frames\n%s", e.what(), e.count, CrashTrace::describe(e.frames, e.count).c_str());
			return e.count > 2 && !CrashTrace::recorded() ? 0 : 3;
		}
		return 3;
	}
	if (mode == "cost")
	{
		void *frames[20];
		LARGE_INTEGER f, a, b;
		QueryPerformanceFrequency(&f);
		const int n = 200000;
		int sum = 0;
		QueryPerformanceCounter(&a);
		for (int i = 0; i < n; ++i)
			sum += CrashTrace::capture(frames, 20, 0);
		QueryPerformanceCounter(&b);
		printf("capture: %.3f microseconds each (%d frames)\n", (double)(b.QuadPart - a.QuadPart) * 1e6 / (double)f.QuadPart / n, sum / n);
		return 0;
	}
	if (mode == "segv") return crashOuter(1);
	if (mode == "second") { crashInNotice = true; return crashOuter(1); }
	if (mode == "div0") return divide(7);
	if (mode == "overflow") return recurse(1);
	if (mode == "segv_thread")
	{
		std::thread t([] { zero = crashOuter(1); });
		t.join();
		return 4; // not reached
	}
	fprintf(stderr, "crashtrace_test exception | segv | segv_thread | div0 | overflow | second | cost [log file]\n");
	return 2;
}
