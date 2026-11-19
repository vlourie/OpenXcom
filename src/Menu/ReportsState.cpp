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
#include "ReportsState.h"
#include <algorithm>
#include <cstdio>
#include "../Engine/Game.h"
#include "../Engine/Action.h"
#include "../Engine/CrossPlatform.h"
#include "../Engine/Feedback.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/Yaml.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"

namespace OpenXcom
{

namespace
{

/// A launcher that hangs must not keep the list waiting forever; its own bound is 30 s.
const Uint32 REFRESH_TIMEOUT_MS = 45000;

/// A string field of report.json, or "" when it is missing or null.
std::string field(const YAML::YamlNodeReader &node, ryml::csubstr key)
{
	YAML::YamlNodeReader child = node[key];
	std::string value;
	if (!child || !child.hasVal() || child.hasNullVal() || !child.tryReadVal(value)) return "";
	return value;
}

/// "2026-09-23T10:37:24.123+00:00" as written by .NET's DateTimeOffset, into UTC seconds; 0 if unreadable.
time_t parseIso(const std::string &s)
{
	int y, mo, d, h, mi, sec;
	if (s.size() < 19 || sscanf(s.c_str(), "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &sec) != 6) return 0;
	struct tm t = {};
	t.tm_year = y - 1900; t.tm_mon = mo - 1; t.tm_mday = d;
	t.tm_hour = h; t.tm_min = mi; t.tm_sec = sec;
#ifdef _WIN32
	time_t utc = _mkgmtime(&t);
#else
	time_t utc = timegm(&t);
#endif
	if (utc == (time_t)-1) return 0;
	// the offset after the seconds and their fraction: Z, +hh:mm or -hh:mm
	size_t tz = s.find_first_of("Z+-", 19);
	if (tz != std::string::npos && s[tz] != 'Z')
	{
		int oh = 0, om = 0;
		if (sscanf(s.c_str() + tz + 1, "%d:%d", &oh, &om) >= 1)
		{
			int offset = (oh * 60 + om) * 60;
			utc -= s[tz] == '+' ? offset : -offset;
		}
	}
	return utc;
}

/// Local date, "23.09" or "23.09 12:40".
std::string localText(time_t t, bool withTime)
{
	if (t == 0) return "";
	struct tm local = *localtime(&t);
	char buf[32];
	strftime(buf, sizeof(buf), withTime ? "%d.%m %H:%M" : "%d.%m", &local);
	return buf;
}

}

/**
 * Initializes all the elements in the My Reports screen.
 */
ReportsState::ReportsState() : _selected(0), _refresh(nullptr), _refreshStarted(0), _hasLauncher(Feedback::hasLauncher())
{
	// Create objects
	_window = new Window(this, 320, 200, 0, 0);
	_txtTitle = new Text(304, 17, 8, 8);
	_lstReports = new TextList(288, 80, 8, 28);
	_txtDetails = new Text(304, 54, 8, 112);
	_txtChecked = new Text(304, 9, 8, 166);
	_btnOpen = new TextButton(100, 16, 8, 177);
	_btnRefresh = new TextButton(100, 16, 110, 177);
	_btnOk = new TextButton(100, 16, 212, 177);

	// Set palette
	setInterface("modsMenu");

	add(_window, "window", "modsMenu");
	add(_txtTitle, "text", "modsMenu");
	add(_lstReports, "optionLists", "modsMenu");
	add(_txtDetails, "text", "modsMenu");
	add(_txtChecked, "tooltip", "modsMenu");
	add(_btnOpen, "button2", "modsMenu");
	add(_btnRefresh, "button2", "modsMenu");
	add(_btnOk, "button2", "modsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "modsMenu");

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText(tr("STR_REPORTS_TITLE"));

	// number, date, title, status
	_lstReports->setColumns(4, 54, 30, 124, 80);
	_lstReports->setSelectable(true);
	_lstReports->setBackground(_window);
	_lstReports->onMouseClick((ActionHandler)&ReportsState::lstReportsClick);

	_txtDetails->setWordWrap(true);

	_btnOpen->onMouseClick((ActionHandler)&ReportsState::btnOpenClick);

	_btnRefresh->setText(tr("STR_REPORTS_REFRESH"));
	_btnRefresh->onMouseClick((ActionHandler)&ReportsState::btnRefreshClick);
	_btnRefresh->setVisible(_hasLauncher);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&ReportsState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&ReportsState::btnOkClick, Options::keyCancel);

	load();
	fill();
	if (_hasLauncher) startRefresh();
	else _txtChecked->setText(tr("STR_REPORTS_NO_LAUNCHER"));
}

ReportsState::~ReportsState()
{
	Feedback::abandonRefresh(_refresh);
}

void ReportsState::init()
{
	State::init();
	// back from the launcher's form: the report may be sent or deleted now
	load();
	fill();
}

void ReportsState::load()
{
	_entries.clear();
	const std::string root = Feedback::reportsFolder();
	if (!CrossPlatform::folderExists(root)) return;
	for (const auto &item : CrossPlatform::getFolderContents(root))
	{
		if (!std::get<1>(item)) continue;
		const std::string dir = root + std::get<0>(item) + "/";
		const std::string json = dir + "report.json";
		Entry e;
		e.dir = dir;
		if (CrossPlatform::fileExists(json))
		{
			try
			{
				YAML::YamlRootNodeReader reader(json, false, false);
				const YAML::YamlNodeReader r = reader.toBase();
				e.number = field(r, "displayNumber");
				e.title = field(r, "title");
				e.state = field(r, "status");
				e.ticketStatus = field(r, "ticketStatus");
				e.staffReply = field(r, "staffReply");
				e.ticketUrl = field(r, "ticketUrl");
				e.errorDetail = field(r, "lastErrorDetail");
				e.created = parseIso(field(r, "createdAt"));
				e.checked = parseIso(field(r, "checkedAt"));
			}
			catch (const std::exception &ex)
			{
				Log(LOG_WARNING) << "My reports: cannot read " << json << ": " << ex.what();
				continue;
			}
		}
		else if (CrossPlatform::fileExists(dir + "context.json"))
		{
			// F8 pressed, the form never opened (no launcher): a draft without text yet
			e.state = "Draft";
			e.created = std::get<2>(item);
		}
		else
		{
			continue;
		}
		_entries.push_back(e);
	}
	std::stable_sort(_entries.begin(), _entries.end(), [](const Entry &a, const Entry &b) { return a.created > b.created; });
	if (_selected >= _entries.size()) _selected = 0;
}

std::string ReportsState::statusText(const Entry &e) const
{
	if (e.state == "Sent")
	{
		static const char *const known[] = { "New", "Triaged", "InProgress", "NeedsInfo", "Resolved", "Closed", "Duplicate", "Rejected", "Gone" };
		for (const char *k : known)
		{
			if (e.ticketStatus == k) return tr(std::string("STR_REPORT_STATUS_") + k);
		}
		return tr("STR_REPORT_STATE_SENT");
	}
	return tr(e.state == "Queued" ? "STR_REPORT_STATE_QUEUED" : "STR_REPORT_STATE_DRAFT");
}

void ReportsState::fill()
{
	_lstReports->clearList();
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		const Entry &e = _entries[i];
		const std::string title = e.title.empty() ? tr("STR_REPORT_UNTITLED").c_str() : e.title;
		const std::string status = statusText(e);
		_lstReports->addRow(4, e.number.empty() ? "-" : e.number.c_str(), localText(e.created, false).c_str(), title.c_str(), status.c_str());
		if (i == _selected) _lstReports->setRowColor(i, _lstReports->getSecondaryColor());
	}
	showSelected();
}

void ReportsState::showSelected()
{
	if (_entries.empty())
	{
		_txtDetails->setText(tr("STR_REPORTS_EMPTY"));
		_btnOpen->setVisible(false);
		return;
	}
	const Entry &e = _entries[_selected];
	std::string text = (e.title.empty() ? std::string(tr("STR_REPORT_UNTITLED")) : e.title) + "\n" + tr("STR_REPORT_STAGE").arg(statusText(e)).c_str();
	if (!e.staffReply.empty())
	{
		std::string reply = e.staffReply;
		if (reply.size() > 400) reply = reply.substr(0, 400) + "...";
		text += "\n" + std::string(tr("STR_REPORT_TEAM_REPLY").arg(reply));
	}
	else if (e.state == "Queued" && !e.errorDetail.empty())
	{
		text += "\n" + std::string(tr("STR_REPORT_NOT_SENT_WHY").arg(e.errorDetail));
	}
	_txtDetails->setText(text);

	// a sent one lives on the site (its page shows the whole talk and takes answers); an unsent one in the form
	if (e.state == "Sent" && e.ticketUrl.compare(0, 8, "https://") == 0)
	{
		_btnOpen->setText(tr("STR_REPORTS_OPEN_SITE"));
		_btnOpen->setVisible(true);
	}
	else if (e.state != "Sent" && _hasLauncher)
	{
		_btnOpen->setText(tr("STR_REPORTS_OPEN_FORM"));
		_btnOpen->setVisible(true);
	}
	else
	{
		_btnOpen->setVisible(false);
	}
}

void ReportsState::startRefresh()
{
	if (_refresh) return;
	_refresh = Feedback::startRefresh();
	_refreshStarted = SDL_GetTicks();
	_txtChecked->setText(_refresh ? tr("STR_REPORTS_CHECKING") : tr("STR_REPORTS_NO_LAUNCHER"));
}

void ReportsState::showChecked(int exitCode)
{
	time_t newest = 0;
	for (const Entry &e : _entries) newest = std::max(newest, e.checked);
	if (exitCode == 0)
		_txtChecked->setText(tr("STR_REPORTS_CHECKED").arg(localText(time(nullptr), true)));
	else if (newest != 0)
		_txtChecked->setText(tr("STR_REPORTS_OFFLINE_SINCE").arg(localText(newest, true)));
	else
		_txtChecked->setText(tr("STR_REPORTS_OFFLINE"));
}

void ReportsState::think()
{
	State::think();
	if (!_refresh) return;
	int code = Feedback::refreshResult(_refresh);
	if (code == -2)
	{
		if (SDL_GetTicks() - _refreshStarted < REFRESH_TIMEOUT_MS) return;
		Feedback::abandonRefresh(_refresh);
		code = 3;
	}
	_refresh = nullptr;
	Log(LOG_INFO) << "My reports: launcher --refresh ended with " << code;
	load();
	fill();
	showChecked(code);
}

void ReportsState::lstReportsClick(Action *)
{
	const size_t row = _lstReports->getSelectedRow();
	if (row >= _entries.size()) return;
	_lstReports->setRowColor(_selected, _lstReports->getColor());
	_selected = row;
	_lstReports->setRowColor(_selected, _lstReports->getSecondaryColor());
	showSelected();
}

void ReportsState::btnOpenClick(Action *)
{
	if (_entries.empty()) return;
	const Entry &e = _entries[_selected];
	if (e.state == "Sent")
	{
		if (e.ticketUrl.compare(0, 8, "https://") == 0) CrossPlatform::openExplorer(e.ticketUrl);
	}
	else if (!Feedback::openForm(_game, e.dir))
	{
		_txtChecked->setText(tr("STR_REPORTS_NO_LAUNCHER"));
	}
}

void ReportsState::btnRefreshClick(Action *)
{
	startRefresh();
}

void ReportsState::btnOkClick(Action *)
{
	_game->popState();
}

}
