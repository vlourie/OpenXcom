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
#include "Feedback.h"
#include <cstdio>
#include <ctime>
#include <random>
#include <sstream>
#include <typeinfo>
#include <vector>
#ifdef __GNUC__
#include <cxxabi.h>
#include <cstdlib>
#endif
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif
#include "../version.h"
#include "Game.h"
#include "Screen.h"
#include "Options.h"
#include "ModInfo.h"
#include "CrossPlatform.h"
#include "HdTest.h"
#include "Logger.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/SavedBattleGame.h"
#include "Exception.h"
#include <SDL.h>

namespace OpenXcom
{

namespace
{

std::string randomUuid()
{
	std::random_device rd;
	unsigned char b[16];
	for (int i = 0; i < 16; i += 4)
	{
		unsigned int v = rd();
		for (int j = 0; j < 4; ++j) b[i + j] = (unsigned char)(v >> (8 * j));
	}
	b[6] = (unsigned char)((b[6] & 0x0F) | 0x40); // version 4
	b[8] = (unsigned char)((b[8] & 0x3F) | 0x80); // RFC 4122 variant
	char out[37];
	snprintf(out, sizeof(out), "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
		b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
	return out;
}

std::string utcNow()
{
	std::time_t t = std::time(nullptr);
	std::tm tm{};
#ifdef _WIN32
	gmtime_s(&tm, &t);
#else
	gmtime_r(&t, &tm);
#endif
	char buf[32];
	std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
	return buf;
}

/// "GeoscapeState" rather than "N8OpenXcom13GeoscapeStateE": which screen the player was on.
std::string stateName(const State *state)
{
	if (!state) return "";
	std::string name = typeid(*state).name();
#ifdef __GNUC__
	int status = 0;
	char *demangled = abi::__cxa_demangle(name.c_str(), nullptr, nullptr, &status);
	if (status == 0 && demangled)
	{
		name = demangled;
	}
	std::free(demangled);
#endif
	const std::string ns = "OpenXcom::";
	if (name.compare(0, ns.size(), ns) == 0) name = name.substr(ns.size());
	return name;
}

std::string osName()
{
#ifdef _WIN32
	// GetVersionEx lies to programs without a compatibility manifest; RtlGetVersion does not
	typedef LONG (WINAPI *RtlGetVersionFn)(OSVERSIONINFOW *);
	HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
	RtlGetVersionFn rtlGetVersion = ntdll ? (RtlGetVersionFn)(void *)GetProcAddress(ntdll, "RtlGetVersion") : nullptr;
	OSVERSIONINFOW v{};
	v.dwOSVersionInfoSize = sizeof(v);
	if (rtlGetVersion && rtlGetVersion(&v) == 0)
	{
		std::ostringstream ss;
		ss << "Windows " << v.dwMajorVersion << "." << v.dwMinorVersion << "." << v.dwBuildNumber;
		return ss.str();
	}
	return "Windows";
#elif defined(__APPLE__)
	return "macOS";
#else
	return "Linux";
#endif
}

std::string jsonBool(bool b) { return b ? "true" : "false"; }

std::string jsonInt(long long v)
{
	std::ostringstream ss;
	ss << v;
	return ss.str();
}

std::string modsJson()
{
	std::ostringstream ss;
	ss << "[";
	bool first = true;
	for (const ModInfo *mod : Options::getActiveMods())
	{
		ss << (first ? "" : ", ") << "{\"id\": " << HdTest::jsonString(mod->getId())
		   << ", \"version\": " << HdTest::jsonString(mod->getVersion()) << "}";
		first = false;
	}
	ss << "]";
	return ss.str();
}

#ifdef _WIN32
std::wstring widen(const std::string &s)
{
	if (s.empty()) return std::wstring();
	int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
	std::wstring w(n, L'\0');
	MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
	return w;
}

std::string narrow(const std::wstring &w)
{
	if (w.empty()) return std::string();
	int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
	std::string s(n, '\0');
	WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, nullptr, nullptr);
	return s;
}

std::string trimLine(std::string s)
{
	while (!s.empty() && (s.back() == '\r' || s.back() == '\n' || s.back() == ' ' || s.back() == '\t')) s.pop_back();
	size_t start = 0;
	if (s.size() >= 3 && (unsigned char)s[0] == 0xEF && (unsigned char)s[1] == 0xBB && (unsigned char)s[2] == 0xBF) start = 3;
	return s.substr(start);
}

/**
 * Where the launcher is: the one that started us says so in XP_LAUNCHER; otherwise the path
 * it left in <game>/launcher/launcher-path.txt; otherwise one lying next to the game.
 */
std::string findLauncher()
{
	wchar_t buf[MAX_PATH * 2];
	DWORD n = GetEnvironmentVariableW(L"XP_LAUNCHER", buf, sizeof(buf) / sizeof(buf[0]));
	if (n > 0 && n < sizeof(buf) / sizeof(buf[0]))
	{
		std::string path = narrow(std::wstring(buf, n));
		if (CrossPlatform::fileExists(path)) return path;
	}
	const std::string exeDir = CrossPlatform::getExeFolder();
	std::string recorded;
	if (CrossPlatform::fileExists(exeDir + "launcher/launcher-path.txt"))
	{
		auto file = CrossPlatform::readFile(exeDir + "launcher/launcher-path.txt");
		std::string line;
		std::getline(*file, line);
		recorded = trimLine(line);
		if (!recorded.empty() && CrossPlatform::fileExists(recorded)) return recorded;
	}
	if (CrossPlatform::fileExists(exeDir + "XPiratezLauncher.exe")) return exeDir + "XPiratezLauncher.exe";
	return "";
}

/// Starts the launcher as "<launcher> <key> "<folder>"" and returns its process handle, or nullptr.
void *startLauncher(const std::string &launcher, const char *key, const std::string &folder)
{
	// a trailing backslash would escape the closing quote of the argument
	std::string dir = folder;
	while (!dir.empty() && (dir.back() == '/' || dir.back() == '\\')) dir.pop_back();
	std::wstring cmd = L"\"" + widen(launcher) + L"\"";
	if (key) cmd += L" " + widen(key) + L" \"" + widen(dir) + L"\"";
	STARTUPINFOW si{};
	si.cb = sizeof(si);
	PROCESS_INFORMATION pi{};
	if (!CreateProcessW(nullptr, &cmd[0], nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi))
	{
		Log(LOG_ERROR) << "Feedback: cannot start the launcher (" << (key ? key : "window") << "), error " << GetLastError();
		return nullptr;
	}
	CloseHandle(pi.hThread);
	return pi.hProcess;
}
#endif

} // namespace

const std::string &Feedback::sessionId()
{
	static const std::string id = randomUuid();
	return id;
}

bool Feedback::open(Game *game, const State *top)
{
	const std::string id = randomUuid();
	const std::string root = Options::getUserFolder() + "reports/";
	const std::string dir = root + id + "/";
	if (!CrossPlatform::folderExists(root)) CrossPlatform::createFolder(root);
	if (!CrossPlatform::createFolder(dir))
	{
		Log(LOG_ERROR) << "Feedback: cannot create " << dir;
		return false;
	}

	// the frame the player is looking at, before anything of ours is on screen
	Screen *screen = game->getScreen();
	screen->screenshot(dir + "shot.png");

	// the game exactly as it is now, for staff to load; never in ironman, where it would be a way around it,
	// and not from a battle preview. save() is const and only reads, so the game goes on untouched
	std::string snapshot;
	SavedGame *saved = game->getSavedGame();
	if (saved && !saved->isIronman() && !(saved->getSavedBattle() && saved->getSavedBattle()->isPreview()))
	{
		const Uint32 t0 = SDL_GetTicks();
		try
		{
			// save() writes under the master's user folder, reports live one level up
			saved->save("../reports/" + id + "/snapshot.sav", game->getMod());
			snapshot = "snapshot.sav";
			Log(LOG_INFO) << "Feedback: snapshot written in " << (SDL_GetTicks() - t0) << " ms";
		}
		catch (const Exception &e) { Log(LOG_ERROR) << "Feedback: snapshot failed: " << e.what(); }
		catch (const std::exception &e) { Log(LOG_ERROR) << "Feedback: snapshot failed: " << e.what(); }
	}

	std::vector<std::pair<std::string, std::string> > f;
	f.emplace_back("format", "1");
	f.emplace_back("id", HdTest::jsonString(id));
	f.emplace_back("session", HdTest::jsonString(sessionId()));
	f.emplace_back("createdAt", HdTest::jsonString(utcNow()));
	f.emplace_back("engine", HdTest::jsonString(std::string(OPENXCOM_VERSION_SHORT) + OPENXCOM_VERSION_GIT));
	f.emplace_back("master", HdTest::jsonString(Options::getActiveMaster()));
	f.emplace_back("mods", modsJson());
	f.emplace_back("os", HdTest::jsonString(osName()));
	f.emplace_back("language", HdTest::jsonString(Options::language));
	f.emplace_back("state", HdTest::jsonString(stateName(top)));
	f.emplace_back("battle", jsonBool(game->getSavedGame() && game->getSavedGame()->getSavedBattle()));
	f.emplace_back("screenWidth", jsonInt(screen->getWidth()));
	f.emplace_back("screenHeight", jsonInt(screen->getHeight()));
	f.emplace_back("fullscreen", jsonBool(Options::fullscreen));
	f.emplace_back("borderless", jsonBool(Options::borderless));
	f.emplace_back("openGL", jsonBool(Options::useOpenGL));
	f.emplace_back("hdMode", jsonInt(Options::oxceHdMode));
	f.emplace_back("hdScale", jsonInt(Options::oxceHdScale));
	// local paths are for the launcher to offer the files; it never sends them
	f.emplace_back("shot", HdTest::jsonString("shot.png"));
	f.emplace_back("log", HdTest::jsonString(CrossPlatform::getLogFileName()));
	f.emplace_back("saveDir", HdTest::jsonString(Options::getMasterUserFolder()));
	f.emplace_back("save", HdTest::jsonString(snapshot));
	f.emplace_back("gameDir", HdTest::jsonString(CrossPlatform::getExeFolder()));
	HdTest::writeJson(dir + "context.json", f);
	Log(LOG_INFO) << "Feedback: report " << id << " written";

#ifdef _WIN32
	const std::string launcher = findLauncher();
	if (launcher.empty())
	{
		Log(LOG_WARNING) << "Feedback: launcher not found, the report stays in " << dir << " to be sent later";
		return false;
	}
	void *process = startLauncher(launcher, "--report", dir);
	if (!process) return false;
	game->pushState(new FeedbackState(process));
	return true;
#else
	Log(LOG_WARNING) << "Feedback: no launcher on this platform, the report stays in " << dir;
	return false;
#endif
}

std::string Feedback::reportsFolder()
{
	return Options::getUserFolder() + "reports/";
}

bool Feedback::hasLauncher()
{
#ifdef _WIN32
	return !findLauncher().empty();
#else
	return false;
#endif
}

bool Feedback::openLauncher()
{
#ifdef _WIN32
	const std::string launcher = findLauncher();
	if (launcher.empty()) return false;
	// the game keeps running: the launcher is an ordinary window beside it, nobody waits for it
	void *process = startLauncher(launcher, nullptr, "");
	if (!process) return false;
	CloseHandle(process);
	Log(LOG_INFO) << "Feedback: launcher window opened from the main menu";
	return true;
#else
	return false;
#endif
}

bool Feedback::openForm(Game *game, const std::string &dir)
{
#ifdef _WIN32
	const std::string launcher = findLauncher();
	void *process = launcher.empty() ? nullptr : startLauncher(launcher, "--report", dir);
	if (!process) return false;
	game->pushState(new FeedbackState(process));
	return true;
#else
	return false;
#endif
}

void *Feedback::startRefresh()
{
#ifdef _WIN32
	const std::string launcher = findLauncher();
	if (launcher.empty()) return nullptr;
	return startLauncher(launcher, "--refresh", reportsFolder());
#else
	return nullptr;
#endif
}

int Feedback::refreshResult(void *process)
{
#ifdef _WIN32
	if (!process) return -1;
	if (WaitForSingleObject((HANDLE)process, 0) == WAIT_TIMEOUT) return -2;
	DWORD code = 1;
	GetExitCodeProcess((HANDLE)process, &code);
	CloseHandle((HANDLE)process);
	return (int)code;
#else
	return -1;
#endif
}

void Feedback::abandonRefresh(void *process)
{
#ifdef _WIN32
	// the launcher finishes on its own within its 30 s bound; only our handle goes
	if (process) CloseHandle((HANDLE)process);
#endif
}

FeedbackState::FeedbackState(void *process) : _process(process)
{
	_screen = false;
}

FeedbackState::~FeedbackState()
{
#ifdef _WIN32
	if (_process) CloseHandle((HANDLE)_process);
#endif
}

void FeedbackState::init()
{
	// State::init would load this state's own (black) palette over the frame below
}

void FeedbackState::handle(Action *)
{
}

void FeedbackState::think()
{
#ifdef _WIN32
	if (_process && WaitForSingleObject((HANDLE)_process, 0) != WAIT_TIMEOUT)
	{
		Log(LOG_INFO) << "Feedback: report window closed";
		_game->popState();
	}
#else
	_game->popState();
#endif
}

}
