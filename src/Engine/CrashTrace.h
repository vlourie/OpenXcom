#pragma once
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
#include <string>

namespace OpenXcom
{

/**
 * Where a crash or an exception came from (Windows, 64 bit; elsewhere every function is empty).
 *
 * A crash (access violation, division by zero, stack overflow... on ANY thread): the filter of the process writes a
 * record - the code, the address, the frames as module+offset - straight to the log file. It runs inside the broken
 * process, so it takes no memory from the heap, no lock, no stream and no symbol library: static buffers, the unwinder
 * of the system and WriteFile only. The names are found afterwards from the same exe: tools/crash_symbolize.py.
 *
 * An exception (a normal context): the addresses are taken where it is thrown (capture, about a microsecond) and
 * named only if it turns out to be fatal (describe).
 */
namespace CrashTrace
{
	/// Called after the record is on disk, still inside the crashed process: tells the player; the process ends after it.
	typedef void (*Notice)(const char *what);
	/// Installs the filter of the process. Until setLogFile the record goes to the standard error stream only.
	void install(Notice notice);
	/// The log file the record is appended to (UTF-8 path).
	void setLogFile(const std::string &utf8Path);
	/// True once the filter has written a record: the frames are already in the log.
	bool recorded();
	/// Return addresses of the caller, the nearest first. No allocation.
	int capture(void **frames, int max, int skip);
	/// The frames as lines "module+0xoffset name+0xoffset". Allocates, loads symbols: never from the crash filter.
	std::string describe(void *const *frames, int count);
}

}
