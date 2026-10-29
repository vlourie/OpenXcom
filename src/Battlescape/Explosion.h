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
	Position _hdFrom;
	int _hdLoss = 0;
	unsigned int _hdSeed = 0;
	int _hdBlood = -1;
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
	/// HD render (Options::oxceHdBloodSpray, XP-000298): a bullet hit that cost the unit health - `from` is a voxel back along the bullet's
	/// way, `loss` the part of the unit's full health lost, percent (1-100), `seed` a hash of the hit (HdFx::hitHash), not the battle's random numbers.
	void setHdSpray(Position from, int loss, unsigned int seed) { _hdFrom = from; _hdLoss = loss; _hdSeed = seed; }
	/// The voxel back along the bullet's way (valid when getHdLoss() > 0).
	Position getHdFrom() const { return _hdFrom; }
	/// The part of the unit's full health the hit took, percent (0: the hit is not a spray's).
	int getHdLoss() const { return _hdLoss; }
	/// A hash of the hit, to pick a variant of the spray.
	unsigned int getHdSeed() const { return _hdSeed; }
	/// HD render (Options::oxceHdBloodColor, XP-000366): the colour 0xRRGGBB of the blood of the unit this hit landed on, by its armour
	/// (hd/blood.txt, HdFx::bloodRgb); -1: red as it was.
	int getHdBlood() const { return _hdBlood; }
	/// HD render: sets the blood colour.
	void setHdBlood(int rgb) { _hdBlood = rgb; }
	/// The first frame of the animation.
	int getStartFrame() const { return _startFrame; }
	/// The number of frames the animation runs (the default of its kind until it has started).
	int getFrameCount() const { return _frames > 0 ? _frames : (_hit ? HIT_FRAMES : _big ? EXPLODE_FRAMES : BULLET_FRAMES); }
};

}
