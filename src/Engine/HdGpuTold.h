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
#include <cstring>
#include <mutex>
#include <string>

namespace OpenXcom
{

/**
 * What the video driver told of its errors (HdGpu::takeErrors): how many, and the text of the first one.
 * The driver calls tell() from threads of its own, several at once; the drawing thread calls take(). The count
 * and the text are one state under one lock - a text half written was read before (AUDIT-04 3). Nothing here
 * asks for memory in tell(): the driver's thread must not throw.
 */
class HdGpuTold
{
private:
	std::mutex _mutex;
	unsigned _count = 0;
	char _text[240] = {};
public:
	/// An error of the driver; the text of the first one since take() is kept (cut to the buffer).
	void tell(const char *message) noexcept
	{
		std::lock_guard<std::mutex> lock(_mutex);
		if (_count == 0)
		{
			std::strncpy(_text, message ? message : "", sizeof(_text) - 1);
			_text[sizeof(_text) - 1] = 0;
		}
		++_count;
	}
	/// How many errors since the last call, with the text of the first one; first is left as it is when none.
	unsigned take(std::string &first)
	{
		char text[sizeof(_text)];
		unsigned n;
		{
			std::lock_guard<std::mutex> lock(_mutex);
			n = _count;
			if (n == 0)
			{
				return 0;
			}
			std::memcpy(text, _text, sizeof(text));
			_count = 0;
			_text[0] = 0;
		}
		first = text; // the copy outside the lock: it may ask for memory
		return n;
	}
};

}
