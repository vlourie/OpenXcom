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
#include <SDL.h>

namespace OpenXcom
{

/**
 * The HD layer on the video card (option oxceHdGpu, docs/research/gpu-render-plan-2026-10-27.md).
 * The world lives in a framebuffer texture of its size and reaches the display as one quad drawn by
 * an OpenGL 3.3 program. Stage 0: the world is still drawn by the processor and uploaded every frame;
 * the later stages draw into the framebuffer directly. All calls are made on the main thread.
 */
class HdGpu
{
private:
	unsigned _texture = 0, _fbo = 0, _vao = 0, _program = 0;
	int _w = 0, _h = 0;
	bool _linear = false;
	HdGpu() = default;
	bool load();
	bool build();
public:
	/// The process-wide instance.
	static HdGpu &instance();
	/// Loads the GL 3.3 functions and (re)creates the world framebuffer of w x h in the current context;
	/// false (and a line in the log) when the video card or its driver cannot do it.
	bool setup(int w, int h);
	/// Drops every GL object while the old context is still there (before the display is set again).
	void release();
	/// The framebuffer is there.
	bool ready() const { return _fbo != 0; }
	/// Uploads a 32-bit surface of the world's size into the framebuffer texture.
	void upload(const SDL_Surface *world);
	/// Draws the framebuffer texture onto the display between the black bands and swaps the buffers.
	void present(int displayW, int displayH, int top, int bottom, int left, int right, bool linear);
	/// Reads the framebuffer back into a 32-bit surface of the world's size (the HD test dump).
	bool readBack(SDL_Surface *out);
};

}
