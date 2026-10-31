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
#include <ctime>
#include <string>
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class Window;
class Text;
class TextButton;
class TextList;

/**
 * "My reports" from the main menu: the F8 reports on this machine and what became of them.
 * The engine never goes online: it reads user/reports/<id>/report.json, and the launcher
 * (started with --refresh in the background) writes the ticket status and the team's
 * newest answer into those files. No pictures: after sending only report.json stays.
 */
class ReportsState : public State
{
private:
	struct Entry
	{
		std::string dir, number, title, state, ticketStatus, staffReply, ticketUrl, errorDetail;
		time_t created = 0, checked = 0;
	};

	Window *_window;
	Text *_txtTitle, *_txtDetails, *_txtChecked;
	TextList *_lstReports;
	TextButton *_btnOpen, *_btnRefresh, *_btnOk;
	std::vector<Entry> _entries;
	size_t _selected;
	void *_refresh;
	Uint32 _refreshStarted;
	bool _hasLauncher;

	/// Reads every report.json under the reports folder, newest first.
	void load();
	/// Fills the list from _entries and shows the selected one.
	void fill();
	/// The text of the selected report and the Open button that fits it.
	void showSelected();
	/// Starts the launcher's --refresh, if there is a launcher and none is running.
	void startRefresh();
	/// The line under the list: when the statuses were last checked, or why they could not be.
	void showChecked(int exitCode);
	/// The status column: the ticket's status once known, otherwise draft / not sent / sent.
	std::string statusText(const Entry &e) const;
public:
	ReportsState();
	~ReportsState();
	/// Rereads the reports: a form opened from here may have changed or sent one.
	void init() override;
	/// Picks up the launcher's answer when it is done.
	void think() override;
	void lstReportsClick(Action *action);
	void btnOpenClick(Action *action);
	void btnRefreshClick(Action *action);
	void btnOkClick(Action *action);
};

}
