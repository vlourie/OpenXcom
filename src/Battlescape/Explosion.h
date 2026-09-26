#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "Position.h"

namespace OpenXcom
{

/**
 * A class that represents an explosion animation. Map is the owner of an instance of this class during its short life.
 * It represents both a bullet hit, as a real explosion animation.
 */
class Explosion
{
private:
	Position _position;
	int _currentFrame, _startFrame, _frameDelay;
	bool _big, _hit, _onUnit;
	int _frames;
	std::string _hdFx;
public:
	static const int HIT_FRAMES;
	static const int EXPLODE_FRAMES;
	static const int BULLET_FRAMES;
	/// Creates a new Explosion.
	Explosion(Position _position, int startFrame, int frameDelay = 0, bool big = false, bool hit = false, int frames = -1, bool onUnit = false);
	/// Cleans up the Explosion.
	~Explosion();
	/// Moves the Explosion on one frame.
	bool animate();
	/// Gets the current position in voxel space.
	Position getPosition() const;
	/// Gets the current frame.
	int getCurrentFrame() const;
	/// Checks if this is a real explosion.
	bool isBig() const;
	/// Checks if this is a melee or psi hit.
	bool isHit() const;
	/// Checks if the hit landed on a unit (the HD pack's other picture of the frame: blood).
	bool isOnUnit() const;
	/// HD render: the combat effect clip drawn instead of the classic frames (see HdFx; empty: none).
	const std::string &getHdFx() const { return _hdFx; }
	/// HD render: sets the combat effect clip.
	void setHdFx(const std::string &clip) { _hdFx = clip; }
	/// The first frame of the animation.
	int getStartFrame() const { return _startFrame; }
	/// The number of frames the animation runs (the default of its kind until it has started).
	int getFrameCount() const { return _frames > 0 ? _frames : (_hit ? HIT_FRAMES : _big ? EXPLODE_FRAMES : BULLET_FRAMES); }
};

}
