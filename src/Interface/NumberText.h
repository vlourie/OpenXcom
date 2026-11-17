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
#include "../Engine/Surface.h"

namespace OpenXcom
{

/**
 * Number digits displayed on the screen.
 * Takes a number and displays it using a simple hard-coded font.
 */
class NumberText : public Surface
{
private:
	unsigned int _value;
	Surface *_chars[10];
	Surface *_borderedChars[10];
	bool _bordered;
	Uint8 _color;
	int _hdBoxX = 0, _hdBoxY = 0, _hdBoxW = 0, _hdBoxH = 0;
	Surface *_hdPlate = nullptr;
public:
	/// HD interface, TrueType digits: the number stands in the middle of this box, given from the number's own
	/// corner (the spotted units' markers: the classic digit is put at a fixed corner of the button).
	void setHdBox(int dx, int dy, int w, int h) { _hdBoxX = dx; _hdBoxY = dy; _hdBoxW = w; _hdBoxH = h; }
	/// HD interface, modern skin: the marker under the number (a flat field in a black frame, the box of setHdBox) gets a
	/// relief - a gradient and a bevel in the field's own colour, read from this surface at (1, 1). Picture only.
	void setHdPlate(Surface *plate) { _hdPlate = plate; }
	/// Creates a new number text with the specified size and position.
	NumberText(int width, int height, int x = 0, int y = 0);
	/// Cleans up the number text.
	~NumberText();
	/// Sets the number text's value.
	void setValue(unsigned int value);
	/// Gets the number text's value.
	unsigned int getValue() const;
	/// Sets the number text's color.
	void setColor(Uint8 color) override;
	/// Gets the number text's color.
	Uint8 getColor() const;
	/// Sets the number text's palette.
	void setPalette(const SDL_Color *colors, int firstcolor = 0, int ncolors = 256) override;
	/// Draws the number text.
	void draw() override;
	/// HD interface, modern skin: the digits with the TrueType font.
	void hdMirror() override;
	/// sets this numbertext to have a border or not
	void setBordered(bool bordered);

};

}
