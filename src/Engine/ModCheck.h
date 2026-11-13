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
#include <vector>

namespace OpenXcom
{

/**
 * "-modcheck <folder> <report>": what the game's own parsers make of a mod, for the launcher's "Submit" and
 * tools/lua_mod_check.py (docs/portal/LUA_MODS.md §8). Lua is compiled and never run, YAML is read and never applied.
 */
namespace ModCheck
{
	/// The exit code of the check, or -1 when the command line asks for something else.
	int run(const std::vector<std::string> &args);
}

}
