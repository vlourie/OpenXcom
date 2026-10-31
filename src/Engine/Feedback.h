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
#include "State.h"

namespace OpenXcom
{

class Game;

/**
 * Player feedback (F8). The engine never goes online: it captures the frame, writes what it
 * knows about itself into user/reports/<id>/context.json and starts the launcher, which shows
 * the form and does the sending. See docs/portal/ARCHITECTURE.md, section 3.3.
 */
namespace Feedback
{
	/// Random id of this game process, the same in every report it writes.
	const std::string &sessionId();
	/// Captures the frame now on screen, writes the report folder and opens the form.
	/// Returns false (and logs why) if the form could not be opened; the folder stays on disk.
	bool open(Game *game, const State *top);
	/// Where F8 reports live: <user folder>/reports/.
	std::string reportsFolder();
	/// Is there a launcher to open forms and ask the portal? (Windows only.)
	bool hasLauncher();
	/// Opens the launcher's own window (updates, reports, support) beside the running game.
	bool openLauncher();
	/// Opens the launcher's form for a report already on disk (a draft or a queued one).
	bool openForm(Game *game, const std::string &dir);
	/// Starts "launcher --refresh" in the background: ticket statuses go into each report.json.
	/// Returns the process handle, or nullptr when there is no launcher.
	void *startRefresh();
	/// -2 still running, -1 no process, otherwise the launcher's exit code (0 fresh, 3 portal unreachable);
	/// once it returned an exit code the handle is closed and must not be used again.
	int refreshResult(void *process);
	/// Lets go of a refresh still running (the list is closed before it ended).
	void abandonRefresh(void *process);
}

/**
 * Sits on top of the state stack while the launcher's report window is open.
 * Game::run thinks only for the top state, so geoscape time, battle animations, AI and timers
 * stand still and no input reaches the world; the pause flags of the states below are never
 * touched, so the game resumes exactly as paused or unpaused as it was.
 */
class FeedbackState : public State
{
private:
	void *_process;
public:
	/// Takes ownership of the launcher's process handle.
	FeedbackState(void *process);
	~FeedbackState();
	/// Keeps the palette of the state below: this state draws nothing.
	void init() override;
	/// Swallows input meant for the world below.
	void handle(Action *action) override;
	/// Leaves as soon as the report window is closed.
	void think() override;
};

}
