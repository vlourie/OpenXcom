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
#include "CrashTrace.h"

#if defined(_WIN64) && !defined(__NO_DBGHELP)

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <dbghelp.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#ifdef __GNUG__
#include <cxxabi.h>
#endif

namespace OpenXcom
{
namespace CrashTrace
{

namespace
{

const int MAX_FRAMES = 48;
wchar_t logPath[1024];			// set before any crash, read by the filter
volatile LONG logPathSet = 0;
volatile LONG owner = 0;		// the thread the filter runs on
volatile LONG written = 0;
Notice notice = 0;
char text[6144];				// the record; the filter runs once, so one buffer is enough
char what[96];
size_t used = 0;

// --- formatting without the C library's streams or the heap ---

void put(const char *s)
{
	while (*s && used + 1 < sizeof(text))
		text[used++] = *s++;
}

void putHex(unsigned long long v)
{
	char b[19];
	int n = 0;
	do { b[n++] = "0123456789abcdef"[v & 15]; v >>= 4; } while (v);
	put("0x");
	while (n && used + 1 < sizeof(text))
		text[used++] = b[--n];
}

void putDec(unsigned long long v)
{
	char b[21];
	int n = 0;
	do { b[n++] = (char)('0' + v % 10); v /= 10; } while (v);
	while (n && used + 1 < sizeof(text))
		text[used++] = b[--n];
}

/// An address as module+offset: "exe" for the game itself, the base of the module otherwise.
void putAddress(DWORD64 pc, DWORD64 base)
{
	static const DWORD64 exe = (DWORD64)GetModuleHandleW(0);
	if (base == 0)
	{
		putHex(pc);
	}
	else
	{
		if (base == exe) put("exe");
		else { put("module@"); putHex(base); }
		put("+");
		putHex(pc - base);
	}
}

const char *codeName(DWORD code)
{
	switch (code)
	{
	case EXCEPTION_ACCESS_VIOLATION: return "Segmentation fault.";
	case EXCEPTION_INT_DIVIDE_BY_ZERO: return "Integer division by zero.";
	case EXCEPTION_STACK_OVERFLOW: return "Stack overflow.";
	case EXCEPTION_ILLEGAL_INSTRUCTION: return "Illegal instruction.";
	case EXCEPTION_IN_PAGE_ERROR: return "Page of the file or of the memory could not be read.";
	case EXCEPTION_ARRAY_BOUNDS_EXCEEDED: return "Array bounds exceeded.";
	case EXCEPTION_FLT_DIVIDE_BY_ZERO: return "Floating point division by zero.";
	case EXCEPTION_PRIV_INSTRUCTION: return "Privileged instruction.";
	default: return 0;
	}
}

void flush()
{
	DWORD done = 0;
	HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
	if (err && err != INVALID_HANDLE_VALUE)
		WriteFile(err, text, (DWORD)used, &done, 0);
	if (logPathSet)
	{
		HANDLE f = CreateFileW(logPath, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, 0, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
		if (f != INVALID_HANDLE_VALUE)
		{
			WriteFile(f, text, (DWORD)used, &done, 0);
			FlushFileBuffers(f);
			CloseHandle(f);
		}
	}
}

LONG WINAPI filter(EXCEPTION_POINTERS *ep)
{
	const LONG first = InterlockedCompareExchange(&owner, (LONG)GetCurrentThreadId(), 0);
	if (first != 0)
	{
		// a second crash: the record of the first is what matters. Another thread waits for the first to finish;
		// the filter itself or the notice crashed - nothing more can be done
		if (first != (LONG)GetCurrentThreadId())
			Sleep(INFINITE);
		TerminateProcess(GetCurrentProcess(), EXIT_FAILURE);
	}
	const EXCEPTION_RECORD *er = ep->ExceptionRecord;
	const char *name = codeName(er->ExceptionCode);

	used = 0;
	put("[FATAL]\tCrash record: ");
	if (name) put(name); else { put("code "); putHex(er->ExceptionCode); }
	if ((er->ExceptionCode == EXCEPTION_ACCESS_VIOLATION || er->ExceptionCode == EXCEPTION_IN_PAGE_ERROR) && er->NumberParameters >= 2)
	{
		put(er->ExceptionInformation[0] == 0 ? " Reading " : er->ExceptionInformation[0] == 1 ? " Writing " : " Executing ");
		putHex(er->ExceptionInformation[1]);
		put(".");
	}
	put(" Thread ");
	putDec(GetCurrentThreadId());
	put(". Frames (tools/crash_symbolize.py names them):\r\n");

	// the unwinder of the system over a copy of the context: it reads the tables of the modules, no heap, no symbols
	CONTEXT c = *ep->ContextRecord;
	for (int i = 0; i < MAX_FRAMES && c.Rip; ++i)
	{
		DWORD64 base = 0;
		PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry(c.Rip, &base, 0);
		put("[FATAL]\t  #");
		putDec(i);
		put(" ");
		if (!fn)
		{
			PVOID m = 0;
			if (RtlPcToFileHeader((PVOID)c.Rip, &m))
				base = (DWORD64)m;
		}
		putAddress(c.Rip, base);
		put("\r\n");
		if (fn)
		{
			void *handlerData = 0;
			DWORD64 frame = 0;
			RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, fn, &c, &handlerData, &frame, 0);
		}
		else
		{
			// a leaf function: the return address is on the top of the stack
			if (IsBadReadPtr((void *)c.Rsp, sizeof(DWORD64)))
				break;
			c.Rip = *(DWORD64 *)c.Rsp;
			c.Rsp += sizeof(DWORD64);
		}
	}
	flush();

	// from here on the record is safe; the rest is a courtesy to the player and may fail
	if (name) { strncpy(what, name, sizeof(what) - 1); }
	else { used = 0; put("code "); putHex(er->ExceptionCode); text[used] = 0; strncpy(what, text, sizeof(what) - 1); }
	InterlockedExchange(&written, 1);
	if (notice && er->ExceptionCode != EXCEPTION_STACK_OVERFLOW)
		notice(what);
	TerminateProcess(GetCurrentProcess(), EXIT_FAILURE);
	return EXCEPTION_EXECUTE_HANDLER;
}

}

void install(Notice n)
{
	notice = n;
	// a stack overflow leaves the filter only what is guaranteed below the guard page; the default (about a page) is
	// not enough for the dispatcher of the system and the record on every Windows (the GitHub runner ended with
	// 0xC0000005 and no record). The guarantee is per thread: this covers the thread that installs - the main one
	ULONG guarantee = 64 * 1024;
	SetThreadStackGuarantee(&guarantee);
	SetUnhandledExceptionFilter(filter);
}

void setLogFile(const std::string &utf8Path)
{
	InterlockedExchange(&logPathSet, 0);
	int n = MultiByteToWideChar(CP_UTF8, 0, utf8Path.c_str(), -1, logPath, (int)(sizeof(logPath) / sizeof(logPath[0])));
	if (n > 0)
		InterlockedExchange(&logPathSet, 1);
}

bool recorded()
{
	return written != 0;
}

int capture(void **frames, int max, int skip)
{
	return (int)CaptureStackBackTrace((DWORD)(skip + 1), (DWORD)max, frames, 0);
}

std::string describe(void *const *frames, int count)
{
	std::string out;
	if (count <= 0)
		return out;
	HANDLE process = GetCurrentProcess();
	SymInitialize(process, 0, TRUE);
	const DWORD64 exe = (DWORD64)GetModuleHandleW(0);
	char buffer[sizeof(SYMBOL_INFO) + 1024];
	char number[64];
	for (int i = 0; i < count; ++i)
	{
		const DWORD64 pc = (DWORD64)frames[i];
		HMODULE m = 0;
		GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)pc, &m);
		const DWORD64 base = (DWORD64)m;
		if (base == exe && base)
			snprintf(number, sizeof(number), "  #%d exe+0x%llx", i, (unsigned long long)(pc - base));
		else if (base)
			snprintf(number, sizeof(number), "  #%d module@0x%llx+0x%llx", i, (unsigned long long)base, (unsigned long long)(pc - base));
		else
			snprintf(number, sizeof(number), "  #%d 0x%llx", i, (unsigned long long)pc);
		out += number;

		SYMBOL_INFO *symbol = (SYMBOL_INFO *)buffer;
		memset(symbol, 0, sizeof(SYMBOL_INFO));
		symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
		symbol->MaxNameLen = 1023;
		DWORD64 off = 0;
		// the address is the one AFTER the call: one byte back is inside the calling instruction
		if (SymFromAddr(process, pc - 1, &off, symbol))
		{
			std::string name = symbol->Name;
#ifdef __GNUG__
			int status = 0;
			char *demangled = abi::__cxa_demangle(("_" + name).c_str(), 0, 0, &status);
			if (status == 0 && demangled)
				name = demangled;
			free(demangled);
#endif
			snprintf(number, sizeof(number), "+0x%llx", (unsigned long long)(off + 1));
			out += " " + name + number;
		}
		out += "\n";
	}
	SymCleanup(process);
	return out;
}

}
}

#else

namespace OpenXcom
{
namespace CrashTrace
{
void install(Notice) {}
void setLogFile(const std::string &) {}
bool recorded() { return false; }
int capture(void **, int, int) { return 0; }
std::string describe(void *const *, int) { return std::string(); }
}
}

#endif
