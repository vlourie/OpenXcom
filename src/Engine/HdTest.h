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
#include <utility>
#include <SDL.h>

namespace OpenXcom
{

/**
 * Helpers for the HD-render regression test dumps.
 *
 * A "test dump" is a deterministic capture of what the engine drew in one
 * frame, taken *before* any display scaling (xBRZ, OpenGL shaders, ...):
 * the battlescape map surface, the whole base-resolution frame, and a JSON
 * sidecar describing the state that produced them (camera, animation frame,
 * resolution, scale factor, mods). Two dumps of the same save must be
 * byte-identical; that is the acceptance criterion of the renderer work.
 */
namespace HdTest
{
	/// Finds a free "hdtestNNN" prefix (full path, without extension) in the user folder.
	std::string nextDumpPrefix();
	/// Saves any SDL surface (8-bit paletted or true color) as an RGB PNG. Index 0 is NOT treated as transparent.
	bool savePngRgb(const std::string &filename, SDL_Surface *surface);
	/// Writes a flat JSON object; values are written verbatim, so quote strings with jsonString().
	void writeJson(const std::string &filename, const std::vector<std::pair<std::string, std::string> > &fields);
	/// Quotes and escapes a string for JSON.
	std::string jsonString(const std::string &s);
}

}
