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
#include "SelectMusicTrackState.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/HdPlateCanvas.h"
#include "../Engine/HdUi.h"
#include "../Engine/InteractiveSurface.h"
#include "../Engine/Language.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Music.h"
#include "../Engine/Options.h"
#include "../Interface/MusicNoteButton.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace
{

// The size of the two windows (base pixels): the player, a gap of two, the playlist.
const int VIEW_W = 240, MAIN_H = 79, PL_Y = 81, PL_H = 107, VIEW_H = PL_Y + PL_H;
const int LIST_ROWS = 8, ROW_H = 9;

// The colours of the grey skin of the mock that Vitali accepted (.amp.a).
const Uint32 C_OUT = 0xFF000000, C_BODY = 0xFF2B2B3A, C_TBAR = 0xFF1B1B28, C_TTXT = 0xFFD6D6E6, C_STRIPE = 0xFFE8C060;
const Uint32 C_LCD = 0xFF000000, C_BEV_L = 0xFF50506A, C_BEV_D = 0xFF8A8AA0, C_GREEN = 0xFF00E800, C_GREEN_ON = 0xFF00B000;
const Uint32 C_SLOT = 0xFF14141E, C_KNOB_T = 0xFFE6E6F0, C_KNOB_B = 0xFF8A8A9E;
const Uint32 C_BTN_T = 0xFFD4D4E0, C_BTN_B = 0xFF8E8EA2, C_BTN_LIGHT = 0xFFFFFFFF, C_BTN_DARK = 0xFF404050, C_INK = 0xFF10101A, C_INK_OFF = 0xFF6C6C80;
const Uint32 C_CUR_BG = 0xFF0000C6, C_WHITE = 0xFFFFFFFF, C_DIM = 0xFF008A00;
const Uint32 C_BAR_G = 0xFF00D000, C_BAR_Y = 0xFFFFD800, C_BAR_R = 0xFFFF3A1A;

struct Box
{
	int x, y, w, h;
	bool has(int px, int py) const { return px >= x && px < x + w && py >= y && py < y + h; }
};

enum Id
{
	ID_NONE, ID_PREV, ID_BACK, ID_PLAY, ID_PAUSE, ID_STOP, ID_FWD, ID_NEXT, ID_SHUF, ID_REP, ID_PL,
	ID_SEEK, ID_VOL, ID_LIST, ID_SCROLL, ID_ADD, ID_DEL, ID_ALL, ID_CLEAR, ID_DONE, ID_REFRESH
};

Box transportBox(int i) { return Box{ 6 + i * 20, 63, 19, 13 }; }
Box toggleBox(int i) { return Box{ i == 0 ? 154 : i == 1 ? 181 : 208, 63, i == 2 ? 26 : 25, 13 }; }
const Box LCD_BOX = { 6, 15, 84, 34 };
const Box TICKER_BOX = { 96, 15, 138, 12 };
const Box SEEK_BOX = { 6, 53, 228, 7 };
const Box VOL_BOX = { 150, 42, 84, 7 };
const Box LIST_BOX = { 4, PL_Y + 14, 232, 76 };
Box listButton(int i, bool add)
{
	static const int px[] = { 5, 41, 77, 105 }, pw[] = { 34, 34, 26, 34 };
	if (add)
	{
		return i == 0 ? Box{ 5, PL_Y + 91, 44, 13 } : Box{ 51, PL_Y + 91, 56, 13 };
	}
	return Box{ px[i], PL_Y + 91, pw[i], 13 };
}
const Box COUNT_BOX = { 141, PL_Y + 91, 95, 13 };

std::string mmss(double seconds)
{
	const int s = std::max(0, (int)seconds);
	char buf[32];
	if (s >= 3600)
	{
		snprintf(buf, sizeof(buf), "%d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60);
	}
	else
	{
		snprintf(buf, sizeof(buf), "%d:%02d", s / 60, s % 60);
	}
	return buf;
}

}

/**
 * The picture and the behaviour of the player: one surface for both windows. The layout is written once
 * (paint) over a PlateCanvas, so the classic 8-bit picture and the HD one in vectors are the same window.
 */
class MusicPlayerView : public InteractiveSurface
{
private:
	struct Row
	{
		std::string key, title;
	};
	Game *_game;
	int _side;
	std::vector<Row> _all, _pl;
	double _plTotal = 0.0;
	bool _addMode = false;
	int _scroll = 0;
	std::string _sel;
	int _pressed = ID_NONE, _drag = ID_NONE;
	double _dragFrac = -1.0;
	bool _dirty = true;
	int _serialSeen = -1, _secsSeen = -1;
	ClassicPlateCanvas *_classic = 0;
	double _phase = 0.0;
	static bool s_showPlaylist;
	// what is shown now, collected by refresh()
	struct Cur
	{
		bool on = false, paused = false, canSeek = false;
		double pos = 0.0, len = -1.0;
		std::string ticker, tag, count, header;
		int curRow = -1;
		std::vector<std::string> rowTitle, rowLen;
		std::vector<int> rowIndex;
	} _cur;

	std::string tr(const char *id) const
	{
		return _game->getLanguage() ? std::string(_game->getLanguage()->getString(id)) : std::string(id);
	}
	const std::vector<Row> &shown() const { return (_addMode || _pl.empty()) ? _all : _pl; }
	bool inPlaylist(const std::string &key) const
	{
		for (const Row &row : _pl)
		{
			if (row.key == key)
			{
				return true;
			}
		}
		return false;
	}
	int maxScroll() const { return std::max(0, (int)shown().size() - LIST_ROWS); }
	/// XP-000577: the scroll bar's runner - its height and its top (base pixels)
	float thumbH() const { return std::max(6.0f, 74.0f * LIST_ROWS / std::max(1.0f, (float)shown().size())); }
	float thumbY() const { return PL_Y + 15 + (maxScroll() > 0 ? (74.0f - thumbH()) * (float)_scroll / (float)maxScroll() : 0.0f); }
	float _grab = 0.0f;
	void dragScroll(int my)
	{
		const float span = 74.0f - thumbH();
		const float frac = span > 0 ? (my - _grab - (PL_Y + 15)) / span : 0.0f;
		_scroll = std::max(0, std::min((int)std::floor(frac * maxScroll() + 0.5f), maxScroll()));
	}
	void setPlaylist(const std::vector<Row> &rows);
	void reload();
	void refresh();
	int hit(int mx, int my, int &row) const;
	void activate(int id, int row);
	void applyVolume(int mx);
	double seekFraction(int mx) const { return std::max(0.0, std::min(1.0, (mx - SEEK_BOX.x) / (double)SEEK_BOX.w)); }
	void paint(PlateCanvas &c);
	void button(PlateCanvas &c, const Box &b, bool pressed);
	void glyph(PlateCanvas &c, int id, const Box &b, Uint32 ink);
	void slot(PlateCanvas &c, const Box &b);
	void recess(PlateCanvas &c, const Box &b);
	void titleBar(PlateCanvas &c, int y, const std::string &text);
public:
	MusicPlayerView(Game *game, int side) : InteractiveSurface(VIEW_W, VIEW_H, 0, 0), _game(game), _side(side)
	{
		reload();
		_scroll = 0;
		refresh();
		const int r = _cur.curRow;
		if (r >= LIST_ROWS)
		{
			_scroll = std::min(maxScroll(), std::max(0, r - LIST_ROWS / 2));
			refresh();
		}
	}
	~MusicPlayerView() { delete _classic; }
	/// Makes the classic canvas once the palette is in place.
	void init()
	{
		Mod *mod = _game->getMod();
		_classic = new ClassicPlateCanvas(this, mod->getFont("FONT_BIG"), mod->getFont("FONT_SMALL"), _game->getLanguage());
	}
	/// Once a frame: the picture is redone when the second changes, or the track, or something was done.
	void tick()
	{
		const int secs = (int)(Music::position() * 1.0) * 4 + (Music::isOn() ? (Music::isPaused() ? 1 : 2) : 0);
		const int serial = _game->getMod()->getMusicSerial();
		if (_dirty || secs != _secsSeen || serial != _serialSeen)
		{
			_secsSeen = secs;
			_serialSeen = serial;
			_dirty = false;
			refresh();
			_phase = (double)(SDL_GetTicks() / 1000);
			_redraw = true;
		}
	}
	void draw() override
	{
		Surface::draw();
		if (!_classic || (HdUi::active() && HdUi::instance().hasFonts()))
		{
			return;
		}
		_classic->begin();
		paint(*_classic);
	}
	void hdMirror() override
	{
		HdUi &ui = HdUi::instance();
		if (!ui.hasFonts())
		{
			Surface::hdMirror();
			return;
		}
		_phase = SDL_GetTicks() / 1000.0;
		Mod *mod = _game->getMod();
		HdPlateCanvas canvas((float)getX(), (float)getY(), mod->getFont("FONT_BIG"), mod->getFont("FONT_SMALL"));
		paint(canvas);
	}
	/// The place the windows take (the right click outside it closes the player).
	bool covers(int ax, int ay) const
	{
		const int mx = ax - getX(), my = ay - getY();
		return Box{ 0, 0, VIEW_W, MAIN_H }.has(mx, my) || (s_showPlaylist && Box{ 0, PL_Y, VIEW_W, PL_H }.has(mx, my));
	}
	void mousePress(Action *action, State *state) override;
	void mouseRelease(Action *action, State *state) override;
	void mouseClick(Action *action, State *state) override;
	void mouseOver(Action *action, State *state) override;
};

bool MusicPlayerView::s_showPlaylist = true;

void MusicPlayerView::setPlaylist(const std::vector<Row> &rows)
{
	std::vector<std::string> keys;
	for (const Row &row : rows)
	{
		keys.push_back(row.key);
	}
	_game->getMod()->setMusicPlaylist(_side, keys);
	reload();
}

/**
 * Reads the tracks of the side and its playlist; a key of the playlist whose file is gone leaves it, quietly.
 */
void MusicPlayerView::reload()
{
	Mod *mod = _game->getMod();
	const Language *lang = _game->getLanguage();
	const std::string search = _side == 1 ? "GMTAC" : "GMGEO";
	const std::string category = _side == 1 ? "GMTACTIC" : "GMGEO";
	_all.clear();
	const bool onlyOwn = mod->userMusicOnly(category);
	for (const auto &pair : mod->getMusicTrackList())
	{
		if (!onlyOwn && pair.first.find(search) != std::string::npos)
		{
			_all.push_back(Row{ pair.first, mod->getMusicTitle(pair.first, lang) });
		}
	}
	for (const auto &own : mod->getUserMusicList(category))
	{
		_all.push_back(Row{ own.first, mod->getMusicTitle(own.first, lang) });
	}
	const std::vector<std::string> keys = mod->getMusicPlaylist(_side);
	std::vector<std::string> kept;
	_pl.clear();
	_plTotal = 0.0;
	for (const std::string &key : keys)
	{
		if (mod->musicKeyKnown(key))
		{
			kept.push_back(key);
			_pl.push_back(Row{ key, mod->getMusicTitle(key, lang) });
			const double len = mod->getMusicLength(key);
			_plTotal += len > 0 ? len : 0.0;
		}
	}
	if (kept.size() != keys.size())
	{
		mod->setMusicPlaylist(_side, kept);
	}
	_scroll = std::max(0, std::min(_scroll, maxScroll()));
	_dirty = true;
}

/**
 * Collects what the picture shows: the state of the music, the time, the line that runs, the rows in view.
 */
void MusicPlayerView::refresh()
{
	Mod *mod = _game->getMod();
	const Language *lang = _game->getLanguage();
	_cur.on = Music::isOn();
	_cur.paused = Music::isPaused();
	_cur.canSeek = Music::canSeek();
	_cur.pos = Music::position();
	_cur.len = Music::currentLength();
	const std::string &key = mod->getCurrentMusicTrack();
	const std::vector<Row> &rows = shown();
	_cur.curRow = -1;
	for (size_t i = 0; i < rows.size(); ++i)
	{
		if (rows[i].key == key)
		{
			_cur.curRow = (int)i;
		}
	}
	if (key.empty())
	{
		_cur.ticker = tr("STR_MP_NOTHING");
	}
	else
	{
		_cur.ticker = (_cur.curRow >= 0 ? std::to_string(_cur.curRow + 1) + ". " : std::string()) + mod->getMusicTitle(key, lang);
		const double len = mod->getMusicLength(key);
		if (len > 0)
		{
			_cur.ticker += " (" + mmss(len) + ")";
		}
	}
	_cur.tag = tr(_side == 1 ? "STR_MP_BATTLE" : "STR_MP_GEOSCAPE");
	_cur.header = tr(_addMode ? "STR_MP_ADD_TRACKS" : _pl.empty() ? "STR_MP_ALL_TRACKS" : "STR_MP_PLAYLIST");
	if (_addMode)
	{
		_cur.count = std::to_string(_pl.size()) + "/" + std::to_string(_all.size());
	}
	else if (_pl.empty())
	{
		_cur.count = std::to_string(_all.size());
	}
	else
	{
		int at = 0;
		for (size_t i = 0; i < _pl.size(); ++i)
		{
			if (_pl[i].key == key)
			{
				at = (int)i + 1;
			}
		}
		_cur.count = std::to_string(at) + "/" + std::to_string(_pl.size()) + " " + mmss(_plTotal);
	}
	// the dash for a length that is not known: the HD faces have it, the classic font may not
	const std::string dash = (HdUi::active() && HdUi::instance().hasFonts()) ? "\xE2\x80\x94" : "-";
	_cur.rowTitle.clear();
	_cur.rowLen.clear();
	_cur.rowIndex.clear();
	for (int r = 0; r < LIST_ROWS; ++r)
	{
		const int idx = _scroll + r;
		if (idx >= (int)rows.size())
		{
			break;
		}
		const double len = mod->getMusicLength(rows[idx].key);
		_cur.rowIndex.push_back(idx);
		_cur.rowTitle.push_back(rows[idx].title);
		_cur.rowLen.push_back(len > 0 ? mmss(len) : dash);
	}
}

int MusicPlayerView::hit(int mx, int my, int &row) const
{
	row = -1;
	for (int i = 0; i < 7; ++i)
	{
		if (transportBox(i).has(mx, my))
		{
			return ID_PREV + i;
		}
	}
	for (int i = 0; i < 3; ++i)
	{
		if (toggleBox(i).has(mx, my))
		{
			return ID_SHUF + i;
		}
	}
	if (Box{ SEEK_BOX.x, SEEK_BOX.y - 2, SEEK_BOX.w, SEEK_BOX.h + 4 }.has(mx, my))
	{
		return ID_SEEK;
	}
	if (Box{ VOL_BOX.x - 3, VOL_BOX.y - 2, VOL_BOX.w + 6, VOL_BOX.h + 4 }.has(mx, my))
	{
		return ID_VOL;
	}
	if (s_showPlaylist)
	{
		if (Box{ 230, PL_Y + 15, 6, 74 }.has(mx, my) && maxScroll() > 0)
		{
			return ID_SCROLL;
		}
		if (Box{ 5, PL_Y + 16, 228, LIST_ROWS * ROW_H }.has(mx, my))
		{
			const int r = (my - (PL_Y + 16)) / ROW_H;
			if (r < (int)_cur.rowIndex.size())
			{
				row = _cur.rowIndex[r];
				return ID_LIST;
			}
			return ID_NONE;
		}
		if (_addMode)
		{
			if (listButton(0, true).has(mx, my)) return ID_DONE;
			if (listButton(1, true).has(mx, my)) return ID_REFRESH;
		}
		else
		{
			for (int i = 0; i < 4; ++i)
			{
				if (listButton(i, false).has(mx, my))
				{
					return ID_ADD + i;
				}
			}
		}
	}
	return ID_NONE;
}

void MusicPlayerView::applyVolume(int mx)
{
	const double frac = std::max(0.0, std::min(1.0, (mx - VOL_BOX.x) / (double)VOL_BOX.w));
	Options::musicVolume = (int)std::floor(frac * SDL_MIX_MAXVOLUME + 0.5);
	_game->setVolume(Options::soundVolume, Options::musicVolume, Options::uiVolume);
}

void MusicPlayerView::activate(int id, int row)
{
	Mod *mod = _game->getMod();
	switch (id)
	{
	case ID_PREV: mod->musicStep(-1, true); break;
	case ID_NEXT: mod->musicStep(1, true); break;
	case ID_BACK: if (Music::canSeek()) Music::seek(Music::position() - 10.0); break;
	case ID_FWD: if (Music::canSeek()) Music::seek(Music::position() + 10.0); break;
	case ID_PLAY: mod->musicPlay(); break;
	case ID_PAUSE:
		if (Music::isOn())
		{
			mod->musicTogglePause();
		}
		break;
	case ID_STOP: mod->musicStopNow(); break;
	case ID_SHUF: Options::oxceMusicShuffle = !Options::oxceMusicShuffle; mod->resetPlaylistOrder(); break;
	case ID_REP: Options::oxceMusicRepeat = !Options::oxceMusicRepeat; break;
	case ID_PL:
		s_showPlaylist = !s_showPlaylist;
		_addMode = false;
		break;
	case ID_LIST:
	{
		const std::vector<Row> &rows = shown();
		if (row < 0 || row >= (int)rows.size())
		{
			break;
		}
		const std::string key = rows[row].key;
		if (_addMode)
		{
			std::vector<Row> next;
			bool had = false;
			for (const Row &r : _pl)
			{
				if (r.key == key)
				{
					had = true;
				}
				else
				{
					next.push_back(r);
				}
			}
			if (!had)
			{
				next.push_back(rows[row]);
			}
			setPlaylist(next);
		}
		else
		{
			_sel = key;
			if (!mod->musicPlayKey(key, _side))
			{
				reload();
			}
		}
		break;
	}
	case ID_ADD: _addMode = true; _scroll = 0; break;
	case ID_DONE: _addMode = false; _scroll = 0; break;
	case ID_REFRESH: mod->refreshUserMusic(); reload(); break;
	case ID_DEL:
	{
		const std::string key = _sel.empty() ? mod->getCurrentMusicTrack() : _sel;
		std::vector<Row> next;
		for (const Row &r : _pl)
		{
			if (r.key != key)
			{
				next.push_back(r);
			}
		}
		_sel.clear();
		if (next.size() != _pl.size())
		{
			setPlaylist(next);
		}
		break;
	}
	case ID_ALL: setPlaylist(_all); break;
	case ID_CLEAR: setPlaylist(std::vector<Row>()); break;
	default: break;
	}
	_scroll = std::max(0, std::min(_scroll, maxScroll()));
	_dirty = true;
}

void MusicPlayerView::mousePress(Action *action, State *)
{
	const int mx = (int)action->getAbsoluteXMouse() - getX(), my = (int)action->getAbsoluteYMouse() - getY();
	const Uint8 button = action->getDetails()->button.button;
	if (button == SDL_BUTTON_WHEELUP || button == SDL_BUTTON_WHEELDOWN)
	{
		if (s_showPlaylist && Box{ 0, PL_Y, VIEW_W, PL_H }.has(mx, my))
		{
			_scroll = std::max(0, std::min(_scroll + (button == SDL_BUTTON_WHEELUP ? -3 : 3), maxScroll()));
			_dirty = true;
		}
		return;
	}
	if (button != SDL_BUTTON_LEFT)
	{
		return;
	}
	int row;
	const int id = hit(mx, my, row);
	_pressed = id;
	if (id == ID_VOL)
	{
		_drag = id;
		applyVolume(mx);
	}
	else if (id == ID_SEEK)
	{
		_drag = id;
		_dragFrac = seekFraction(mx);
	}
	else if (id == ID_SCROLL)
	{
		// XP-000577: the runner is pulled; a press beside it brings its middle there
		_drag = id;
		const float top = thumbY(), h = thumbH();
		_grab = (my >= top && my < top + h) ? my - top : h / 2.0f;
		dragScroll(my);
	}
	_dirty = true;
}

void MusicPlayerView::mouseOver(Action *action, State *)
{
	if (_drag != ID_NONE && isButtonPressed(SDL_BUTTON_LEFT))
	{
		const int mx = (int)action->getAbsoluteXMouse() - getX();
		if (_drag == ID_VOL)
		{
			applyVolume(mx);
		}
		else if (_drag == ID_SCROLL)
		{
			dragScroll((int)action->getAbsoluteYMouse() - getY());
		}
		else
		{
			_dragFrac = seekFraction(mx);
		}
		_dirty = true;
	}
}

void MusicPlayerView::mouseRelease(Action *action, State *)
{
	if (action->getDetails()->button.button != SDL_BUTTON_LEFT)
	{
		return;
	}
	if (_drag == ID_SEEK && _dragFrac >= 0.0)
	{
		const double len = Music::currentLength();
		if (len > 0 && Music::canSeek())
		{
			Music::seek(_dragFrac * len);
		}
	}
	_drag = ID_NONE;
	_dragFrac = -1.0;
	_pressed = ID_NONE;
	_dirty = true;
}

void MusicPlayerView::mouseClick(Action *action, State *)
{
	if (action->getDetails()->button.button != SDL_BUTTON_LEFT)
	{
		return;
	}
	const int mx = (int)action->getAbsoluteXMouse() - getX(), my = (int)action->getAbsoluteYMouse() - getY();
	int row;
	const int id = hit(mx, my, row);
	if (id != ID_NONE && id != ID_SEEK && id != ID_VOL && id != ID_SCROLL)
	{
		activate(id, row);
	}
}

// ---- the picture ----

/// A field sunk into the body: the dark inside with the edge of the skin (light on its bottom and right).
void MusicPlayerView::recess(PlateCanvas &c, const Box &b)
{
	c.fill((float)b.x, (float)b.y, (float)b.w, (float)b.h, C_BEV_D);
	c.fill((float)b.x, (float)b.y, (float)b.w - 1, 1, C_BEV_L);
	c.fill((float)b.x, (float)b.y, 1, (float)b.h - 1, C_BEV_L);
	c.fill((float)b.x + 1, (float)b.y + 1, (float)b.w - 2, (float)b.h - 2, C_LCD);
}

/// The track of a slider: a thin dark slot.
void MusicPlayerView::slot(PlateCanvas &c, const Box &b)
{
	c.fill((float)b.x, (float)b.y, (float)b.w, (float)b.h, C_BEV_L);
	c.fill((float)b.x + 1, (float)b.y + 1, (float)b.w - 2, (float)b.h - 2, C_SLOT);
}

void MusicPlayerView::button(PlateCanvas &c, const Box &b, bool pressed)
{
	c.fill((float)b.x, (float)b.y, (float)b.w, (float)b.h, C_OUT);
	c.gradient((float)b.x + 1, (float)b.y + 1, (float)b.w - 2, (float)b.h - 2, pressed ? C_BTN_B : C_BTN_T, pressed ? C_BTN_T : C_BTN_B);
	const Uint32 hi = pressed ? C_BTN_DARK : C_BTN_LIGHT, lo = pressed ? C_BTN_LIGHT : C_BTN_DARK;
	c.fill((float)b.x + 1, (float)b.y + 1, (float)b.w - 2, 1, hi);
	c.fill((float)b.x + 1, (float)b.y + 1, 1, (float)b.h - 2, hi);
	c.fill((float)b.x + 1, (float)b.y + b.h - 2, (float)b.w - 2, 1, lo);
	c.fill((float)b.x + b.w - 2, (float)b.y + 1, 1, (float)b.h - 2, lo);
}

/// The pictures on the transport buttons: triangles and bars (the fonts have none).
void MusicPlayerView::glyph(PlateCanvas &c, int id, const Box &b, Uint32 ink)
{
	const float cx = b.x + b.w / 2.0f, cy = b.y + b.h / 2.0f;
	const auto left = [&](float tip, float base) { c.triangle(base, cy - 3.0f, base, cy + 3.0f, tip, cy, ink); };
	const auto right = [&](float tip, float base) { c.triangle(base, cy - 3.0f, base, cy + 3.0f, tip, cy, ink); };
	switch (id)
	{
	case ID_PREV: c.fill(cx - 4.0f, cy - 3.0f, 1.5f, 6.0f, ink); left(cx - 2.5f, cx + 3.5f); break;
	case ID_BACK: left(cx - 4.5f, cx - 0.5f); left(cx - 0.5f, cx + 3.5f); break;
	case ID_PLAY: right(cx + 3.0f, cx - 2.5f); break;
	case ID_PAUSE: c.fill(cx - 3.0f, cy - 3.0f, 2.0f, 6.0f, ink); c.fill(cx + 1.0f, cy - 3.0f, 2.0f, 6.0f, ink); break;
	case ID_STOP: c.fill(cx - 3.0f, cy - 3.0f, 6.0f, 6.0f, ink); break;
	case ID_FWD: right(cx + 4.5f, cx + 0.5f); right(cx + 0.5f, cx - 3.5f); break;
	case ID_NEXT: right(cx + 2.5f, cx - 3.5f); c.fill(cx + 2.5f, cy - 3.0f, 1.5f, 6.0f, ink); break;
	default: break;
	}
}

void MusicPlayerView::titleBar(PlateCanvas &c, int y, const std::string &text)
{
	c.fill(1, (float)y + 1, VIEW_W - 2, 11, C_TBAR);
	const float tw = c.textWidth(text, false);
	const float tx = std::floor((VIEW_W - tw) / 2.0f);
	c.text(text, tx, (float)y + 2, C_TTXT, false);
	for (int line = 0; line < 3; ++line)
	{
		const float ly = (float)y + 4 + line * 2;
		c.fill(6, ly, tx - 4 - 6, 1, C_STRIPE);
		c.fill(tx + tw + 4, ly, VIEW_W - 6 - (tx + tw + 4), 1, C_STRIPE);
	}
}

void MusicPlayerView::paint(PlateCanvas &c)
{
	const bool playing = _cur.on && !_cur.paused;
	// ---- the player ----
	c.fill(0, 0, VIEW_W, MAIN_H, C_OUT);
	c.fill(1, 1, VIEW_W - 2, MAIN_H - 2, C_BODY);
	titleBar(c, 0, "XP-AMP");

	// the screen: the state, the time, the bars
	recess(c, LCD_BOX);
	const float gx = (float)LCD_BOX.x + 5, gy = (float)LCD_BOX.y + 5;
	if (!_cur.on)
	{
		c.fill(gx, gy, 6, 6, C_GREEN);
	}
	else if (_cur.paused)
	{
		c.fill(gx, gy, 2, 7, C_GREEN);
		c.fill(gx + 4, gy, 2, 7, C_GREEN);
	}
	else
	{
		c.triangle(gx, gy, gx, gy + 7, gx + 6, gy + 3.5f, C_GREEN);
	}
	const std::string clockText = [&]
	{
		const int s = std::max(0, (int)_cur.pos);
		char buf[16];
		snprintf(buf, sizeof(buf), "%02d:%02d", s / 60, s % 60);
		return std::string(buf);
	}();
	// XP-000577: the time in the middle of the screen
	c.text(clockText, std::floor((float)LCD_BOX.x + (LCD_BOX.w - c.textWidth(clockText, true)) / 2.0f), (float)LCD_BOX.y + 2, C_GREEN, true);
	// bars for show: they follow the time, not the sound (the mixer gives no levels)
	for (int i = 0; i < 15; ++i)
	{
		const double v = (std::sin(i * 1.9 + _phase * 5.1) + std::sin(i * 0.7 - _phase * 3.3) + 2.0) / 4.0;
		float h = playing ? (float)(1.0 + v * 10.0) : 1.0f;
		if (!HdUi::active())
		{
			h = std::floor(h);
		}
		const float bx = (float)LCD_BOX.x + 5 + i * 5, base = (float)LCD_BOX.y + LCD_BOX.h - 3;
		const float g = std::min(h, 5.0f), y = std::min(std::max(h - 5.0f, 0.0f), 3.0f), r = std::max(h - 8.0f, 0.0f);
		c.fill(bx, base - g, 4, g, C_BAR_G);
		if (y > 0)
		{
			c.fill(bx, base - g - y, 4, y, C_BAR_Y);
		}
		if (r > 0)
		{
			c.fill(bx, base - g - y - r, 4, r, C_BAR_R);
		}
	}

	// the line that runs
	recess(c, TICKER_BOX);
	{
		const float inX = (float)TICKER_BOX.x + 1, inW = (float)TICKER_BOX.w - 2;
		const float tw = c.textWidth(_cur.ticker, false);
		c.clip(inX, (float)TICKER_BOX.y + 1, inW, (float)TICKER_BOX.h - 2);
		if (tw <= inW - 6)
		{
			c.text(_cur.ticker, inX + 3, (float)TICKER_BOX.y + 2, C_GREEN, false);
		}
		else
		{
			const float run = tw + 30.0f;
			const float off = (float)std::fmod(_phase * 8.0, (double)run);
			c.text(_cur.ticker, inX + 3 - off, (float)TICKER_BOX.y + 2, C_GREEN, false);
			c.text(_cur.ticker, inX + 3 - off + run, (float)TICKER_BOX.y + 2, C_GREEN, false);
		}
		c.unclip();
	}
	// the side's name in a box, and the volume
	{
		const float tw = c.textWidth(_cur.tag, false);
		const Box tag = { 96, 29, (int)tw + 8, 11 };
		recess(c, tag);
		c.text(_cur.tag, (float)tag.x + 4, (float)tag.y + 1, C_GREEN, false);
		c.text(tr("STR_MP_VOLUME"), 96, 41, C_GREEN, false);
		slot(c, VOL_BOX);
		const float frac = (float)std::max(0, std::min(Options::musicVolume, (int)SDL_MIX_MAXVOLUME)) / (float)SDL_MIX_MAXVOLUME;
		const float kx = std::floor((float)VOL_BOX.x + (VOL_BOX.w - 6) * frac);
		c.fill(kx, (float)VOL_BOX.y - 1, 6, 9, C_OUT);
		c.gradient(kx + 1, (float)VOL_BOX.y, 4, 7, C_KNOB_T, C_KNOB_B);
	}
	// the move in the track
	slot(c, SEEK_BOX);
	{
		double frac = -1.0;
		if (_dragFrac >= 0.0)
		{
			frac = _dragFrac;
		}
		else if (_cur.on && _cur.len > 0)
		{
			frac = std::min(1.0, _cur.pos / _cur.len);
		}
		if (frac >= 0.0)
		{
			const float kx = std::floor((float)SEEK_BOX.x + (SEEK_BOX.w - 10) * (float)frac);
			c.fill(kx, (float)SEEK_BOX.y - 1, 10, 9, C_OUT);
			c.gradient(kx + 1, (float)SEEK_BOX.y, 8, 7, C_KNOB_T, C_KNOB_B);
		}
	}
	// the buttons
	for (int i = 0; i < 7; ++i)
	{
		const int id = ID_PREV + i;
		const Box b = transportBox(i);
		button(c, b, _pressed == id);
		const bool off = (id == ID_BACK || id == ID_FWD) && !_cur.canSeek;
		glyph(c, id, Box{ b.x + (_pressed == id ? 1 : 0), b.y + (_pressed == id ? 1 : 0), b.w, b.h }, off ? C_INK_OFF : C_INK);
	}
	const char *toggles[3] = { "SHUF", "REP", "PL" };
	const bool on[3] = { Options::oxceMusicShuffle, Options::oxceMusicRepeat, s_showPlaylist };
	for (int i = 0; i < 3; ++i)
	{
		const Box b = toggleBox(i);
		button(c, b, _pressed == ID_SHUF + i);
		const std::string label = toggles[i];
		const float tw = c.textWidth(label, false);
		c.text(label, std::floor(b.x + (b.w - tw) / 2.0f), (float)b.y + 3, on[i] ? C_GREEN_ON : C_INK, false);
	}

	if (!s_showPlaylist)
	{
		return;
	}
	// ---- the playlist ----
	c.fill(0, PL_Y, VIEW_W, PL_H, C_OUT);
	c.fill(1, PL_Y + 1, VIEW_W - 2, PL_H - 2, C_BODY);
	titleBar(c, PL_Y, _cur.header);
	recess(c, LIST_BOX);
	const std::vector<Row> &rows = shown();
	// XP-000577: the numbers' column as wide as the longest number of the list (three digits went over the edge)
	const float numRight = std::max(20.0f, 8.0f + c.textWidth(std::to_string(rows.size()) + ".", false));
	const float titleX = numRight + 4.0f;
	for (size_t r = 0; r < _cur.rowIndex.size(); ++r)
	{
		const int idx = _cur.rowIndex[r];
		const float ry = (float)(PL_Y + 16 + (int)r * ROW_H);
		const bool cur = idx == _cur.curRow;
		const bool dim = _addMode && inPlaylist(rows[idx].key);
		const bool picked = !_addMode && !_sel.empty() && rows[idx].key == _sel && !cur;
		if (cur)
		{
			c.fill(5, ry, 227, ROW_H, C_CUR_BG);
		}
		else if (picked)
		{
			c.fill(5, ry, 227, ROW_H, C_BEV_L);
		}
		const Uint32 ink = cur ? C_WHITE : dim ? C_DIM : C_GREEN;
		const std::string num = std::to_string(idx + 1) + ".";
		c.text(num, numRight - c.textWidth(num, false), ry + 1, ink, false);
		const float lw = c.textWidth(_cur.rowLen[r], false);
		const float lx = 229 - lw;
		c.clip(titleX, ry, lx - 4 - titleX, (float)ROW_H);
		c.text(_cur.rowTitle[r], titleX, ry + 1, ink, false);
		c.unclip();
		c.text(_cur.rowLen[r], lx, ry + 1, ink, false);
	}
	if (maxScroll() > 0)
	{
		c.fill(233, PL_Y + 15, 2, 74, C_SLOT);
		c.fill(233, thumbY(), 2, thumbH(), C_BEV_D);
	}
	// the buttons under the list
	const auto label = [&](const Box &b, const std::string &text, bool pressed, bool enabled)
	{
		button(c, b, pressed);
		const float tw = c.textWidth(text, false);
		c.text(text, std::floor(b.x + (b.w - tw) / 2.0f) + (pressed ? 1 : 0), (float)b.y + 3 + (pressed ? 1 : 0), enabled ? C_INK : C_INK_OFF, false);
	};
	if (_addMode)
	{
		label(listButton(0, true), tr("STR_MP_BACK"), _pressed == ID_DONE, true);
		label(listButton(1, true), tr("STR_MP_REFRESH"), _pressed == ID_REFRESH, Options::oxceUserMusic > 0);
	}
	else
	{
		label(listButton(0, false), tr("STR_MP_ADD"), _pressed == ID_ADD, true);
		label(listButton(1, false), tr("STR_MP_REMOVE"), _pressed == ID_DEL, !_pl.empty());
		label(listButton(2, false), tr("STR_MP_ALL"), _pressed == ID_ALL, true);
		label(listButton(3, false), tr("STR_MP_CLEAR"), _pressed == ID_CLEAR, !_pl.empty());
	}
	recess(c, COUNT_BOX);
	c.text(_cur.count, (float)COUNT_BOX.x + 4, (float)COUNT_BOX.y + 3, C_GREEN, false);
}

// ---- the state ----

/**
 * Creates the player.
 * @param origin Where is the dialog called from? (the side of the playlist it works with)
 */
SelectMusicTrackState::SelectMusicTrackState(SelectMusicTrackOrigin origin) : _origin(origin)
{
	_screen = false;
	// the palette of the old window (the battle's when the battle is on), the player's colours are the nearest of it
	setInterface("selectMusicTrack", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	_view = new MusicPlayerView(_game, _origin == SMT_BATTLESCAPE ? 1 : 0);
	_view->setX((320 - VIEW_W) / 2);
	_view->setY((200 - VIEW_H) / 2);
	add(_view);
	centerAllSurfaces();
	_view->init();
}

SelectMusicTrackState::~SelectMusicTrackState()
{
}

void SelectMusicTrackState::think()
{
	State::think();
	_view->tick();
}

void SelectMusicTrackState::handle(Action *action)
{
	const SDL_Event *ev = action->getDetails();
	if (ev->type == SDL_KEYDOWN && (ev->key.keysym.sym == Options::keyCancel || ev->key.keysym.sym == Options::keySelectMusicTrack))
	{
		_game->popState();
		return;
	}
	State::handle(action);
	// a right click outside the windows closes them (on the release: the press never reaches the screen below);
	// XP-000577: so does a left click on the note that opens them
	const int ax = (int)action->getAbsoluteXMouse(), ay = (int)action->getAbsoluteYMouse();
	if (ev->type == SDL_MOUSEBUTTONUP && !_view->covers(ax, ay)
		&& (ev->button.button == SDL_BUTTON_RIGHT || (ev->button.button == SDL_BUTTON_LEFT && MusicNoteButton::latestAt(ax, ay))))
	{
		_game->popState();
	}
}

}
