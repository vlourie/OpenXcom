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
#include <cstdint>
#include <cstdio>
#include <string>
#include "Options.h"

namespace OpenXcom
{

/**
 * The HD lab: features still on trial (the battle map turned to its other sides, see
 * docs/research/map-rotation-2026-10-20.md), behind a password on the HD tab ("New features"),
 * so that a player does not turn them on by chance. It is no lock against someone reading the
 * code: the password is kept only as a hash, and the options file keeps a token made from it
 * (another hash), so neither of them shows the password itself.
 * Picture only, like the rest of the tab: nothing here may be read by the game rules.
 */
namespace HdLab
{
	/// FNV-1a, 64 bits.
	inline uint64_t hash(const std::string &s)
	{
		uint64_t h = 0xcbf29ce484222325ULL;
		for (unsigned char c : s)
		{
			h ^= c;
			h *= 0x100000001b3ULL;
		}
		return h;
	}

	/// The typed password as it is compared: no spaces around it, ASCII in lower case,
	/// no "http://", "https://" or "www." in front and no "/" at the end (an address typed whole).
	inline std::string normalize(const std::string &typed)
	{
		std::string s;
		for (char c : typed)
		{
			s += (c >= 'A' && c <= 'Z') ? (char)(c - 'A' + 'a') : c;
		}
		const size_t first = s.find_first_not_of(" \t");
		s = first == std::string::npos ? std::string() : s.substr(first, s.find_last_not_of(" \t") - first + 1);
		for (const char *prefix : { "https://", "http://", "www." })
		{
			const std::string p = prefix;
			if (s.compare(0, p.size(), p) == 0)
			{
				s = s.substr(p.size());
			}
		}
		while (!s.empty() && s.back() == '/')
		{
			s.pop_back();
		}
		return s;
	}

	/// The hash of the password, and the token the options file keeps once it was typed right.
	const uint64_t PASSWORD_HASH = 0x1841fdd87c25fafeULL;
	const char *const TOKEN = "7309b580d5a6cf0a";

	/// Is the lab open (the password was typed right and the options file keeps its token)?
	inline bool unlocked()
	{
		return Options::oxceHdLabKey == TOKEN;
	}

	/// Opens the lab if this is the password: keeps its token in the options. Returns whether it was.
	inline bool tryUnlock(const std::string &typed)
	{
		const std::string s = normalize(typed);
		if (hash("oxce-hd-lab:" + s) != PASSWORD_HASH)
		{
			return false;
		}
		char token[17];
		snprintf(token, sizeof(token), "%016llx", (unsigned long long)hash("oxce-hd-lab-token:" + s));
		Options::oxceHdLabKey = token;
		return unlocked();
	}

	/// Closes the lab again: its options stay as they are, but have no effect.
	inline void lock()
	{
		Options::oxceHdLabKey.clear();
	}

	/// The battle map rotation in quarter turns (0..3); 0 while the lab is closed.
	inline int mapRotation()
	{
		return unlocked() ? ((Options::oxceHdMapRotation % 4) + 4) % 4 : 0;
	}
}

}
