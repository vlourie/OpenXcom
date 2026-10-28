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
#include <vector>

namespace OpenXcom
{

class Canvas32;

/**
 * The battle canvas on the video card (option oxceHdGpu, stage 1 of docs/research/gpu-render-plan-2026-10-27.md).
 *
 * The commands Canvas32 recorded are drawn into a framebuffer of the canvas's size by one program, with the
 * same integer formulas the strips use, so the frame is the processor's byte for byte: palette sprites through
 * the palette and its shade rules, HD frames with their tone curves, light fields and night-vision recolour,
 * straight alpha by the card's blending, vapor and the blast flash reading a copy of what is under them.
 * The frames are kept in texture arrays (uploaded on first use, the least recently used layer emptied when
 * they are full); classic elements and vapor patterns go up every frame.
 *
 * The interface is still drawn by the processor over the map, so the frame comes back into the canvas's
 * surface: read into a pixel buffer at the end of the flush and taken a frame later (waiting for it at once
 * costs the processor as much as the drawing it saves), or at once when a test dump is due.
 * The mode-0 canvas (the classic picture, the reference of the checks) stays on the processor.
 * All calls are made on the thread of the GL context.
 */
class HdGpuCanvas
{
public:
	/// The process-wide instance.
	static HdGpuCanvas &instance();
	/// Draws the canvas's recorded commands on the video card and starts reading the frame back; false: the
	/// processor has to draw them (no video card, mode 0, a command or a frame it does not take).
	bool run(Canvas32 &canvas);
	/// Brings the canvas's pixels up to the frames read back: the last one (`latest`), or the one before it
	/// unless the last is already there (the frame shown a frame late).
	void take(Canvas32 &canvas, bool latest);
	/// The processor drew the canvas: the framebuffer does not hold its picture any more.
	void drawnByCpu(Canvas32 &canvas);
	/// OXCE_HD_GPU_VERIFY: the processor draws every flush the card drew too, and verify compares the two.
	bool verifying() const;
	/// Compares the card's frame of the last flush with the canvas's pixels (the processor's) and logs the
	/// flushes that differ; the frames on their way are dropped (the canvas keeps the processor's picture).
	void verify(Canvas32 &canvas);
	/// The canvas goes or changes its size: its framebuffer and the frames on their way are dropped.
	void forget(Canvas32 &canvas);
	/// Drops every GL object (the context goes).
	void release();
private:
	HdGpuCanvas() = default;
	struct Target;
	struct Prepared;
	/// The framebuffers of the canvases (the map, the hidden movement message of a zoomed view).
	std::vector<Target *> _targets;
	Target *targetFor(Canvas32 &canvas);
	/// Puts the frames the commands read into the texture arrays and encodes the commands; false: not on the card.
	bool prepare(Canvas32 &canvas, Target &target, Prepared &out);
	void draw(Canvas32 &canvas, Target &target, Prepared &prepared);
};

}
