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
#include <memory>
#include <string>
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class Base;
class BaseView;
class Craft;
class HdVideo;
class Sound;

/**
 * HD render: a craft leaving its base or coming back, over the whole screen, the geoscape standing
 * still under it. Leaving: the camera comes down on the craft's own hangar in the player's base,
 * then the clip of this type of craft going out. Coming back: the clip backwards, then the camera
 * pulls back from the hangar to the whole base.
 *
 * Only a picture: the craft has already been sent (or has landed) when the scene starts, nothing
 * of the game is read back from it, and what the base view writes into the facilities while it
 * draws (the craft each hangar holds, see BaseFacility::setCraftForDrawing) is put back after every
 * frame. Any key or click ends the scene. Clips live in the HD mod as hd/LAUNCH/<craft type>.mpg
 * and .land.mpg: no clip, no scene.
 */
class CraftLaunchState : public State
{
private:
	enum Phase { PHASE_BASE_IN, PHASE_CLIP, PHASE_BASE_OUT };
	std::unique_ptr<HdVideo> _video;
	const Craft *_craft;
	Base *_base;
	bool _landing;
	BaseView *_view = nullptr;
	Phase _phase;
	Uint32 _phaseStart = 0, _lastTicks = 0, _startTicks = 0;
	bool _cursorWasVisible = true;
	bool _done = false;
	/// The craft's hangar in the view's own pixels; found at the first frame of the base.
	bool _hangarKnown = false;
	double _hangarX = 0.0, _hangarY = 0.0, _hangarW = 0.0, _hangarH = 0.0;
	/// The base view of this frame, read back from the world layer to be enlarged.
	std::vector<Uint32> _shot;
	/// Headless checks (OXCE_HD_DUMP_LAUNCH): the next moment of the scene to dump.
	size_t _testNext = 0;
	CraftLaunchState(std::unique_ptr<HdVideo> video, const Craft *craft, Base *base, bool landing);
	/// The scene, the craft known or not.
	static State *create(const std::string &craftType, int soldiers, bool landing, const Craft *craft);
	/// Starts a phase (now).
	void enter(Phase phase);
	/// The order to start (hd/LAUNCH/start.wav; none without a mixer or the file), once.
	std::unique_ptr<Sound> _alarm;
	bool _alarmSounded = false;
	/// Draws the base and enlarges it: `zoom` 0 the whole base, 1 the hangar; `bright` of 256;
	/// `alarmMs` since the order to start was given, below 0 none.
	void drawBase(double zoom, int bright, int alarmMs = -1);
	/// The alarm over the hangar in the shot of the base, `ms` since it began; `k` the world scale.
	void drawAlarm(int ms, int k);
	/// Closes the scene (once).
	void close();
public:
	~CraftLaunchState();
	/// The scene for the craft, or null when it is not to be played (option, no HD layer or k 1, no clip).
	static State *create(const Craft *craft, bool landing);
	/// The clip alone for a craft type by name, `soldiers` aboard (the test hook: no base, no hangar).
	static State *create(const std::string &craftType, int soldiers, bool landing);
	void init() override;
	void handle(Action *action) override;
	void think() override;
	void blit() override;
};

}
