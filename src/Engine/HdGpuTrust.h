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

namespace OpenXcom
{

/**
 * How far the world on the video card is trusted after the errors its driver told of (HdGpuWorld::begin).
 *
 * An error alone: what is on the card is made anew, the card goes on. ERRORS errors not yet forgiven: the
 * processor draws for a rest, then the card gets one try - one more error and the next rest, twice as long.
 * After RESTS rests the card is left alone until reset(): the context made anew (the player changed the display
 * or switched the option) or the game started again. FORGIVE frames of the card without an error forgive one
 * error, then one rest - so a card that fails more often than that ends at the processor, and one that fails
 * less often is made anew at most once in FORGIVE frames.
 *
 * Nothing of the card here: frames and milliseconds come from the caller (tests/hdgputrust_test.cpp).
 */
class HdGpuTrust
{
public:
	enum Answer { ANEW, REST, OFF };
	// measured (AUDIT-05, evidence/HD/gpu_fault_test.py): making anew costs about 30 frames of the processor and
	// no frame of 33 ms; FORGIVE keeps such frames under 1 % even with an error right after every forgiving
	static const int ERRORS = 3, RESTS = 3, FORGIVE = 3600;
	static const unsigned REST_MS = 60000;
private:
	int _errors = 0, _rests = 0, _clean = 0;
	unsigned _restFrom = 0, _restFor = 0;
	bool _off = false;
public:
	/// The driver told of an error at the time now (ms): what the world does.
	Answer error(unsigned now)
	{
		_clean = 0;
		if (_off)
		{
			return OFF;
		}
		if (++_errors < ERRORS)
		{
			return ANEW;
		}
		if (_rests >= RESTS)
		{
			_off = true;
			return OFF;
		}
		// after the rest the card has one try
		_errors = ERRORS - 1;
		_restFrom = now;
		_restFor = REST_MS << _rests++;
		return REST;
	}
	/// May the card draw the world at the time now (ms)?
	bool card(unsigned now)
	{
		if (_off)
		{
			return false;
		}
		if (_restFor && now - _restFrom < _restFor)
		{
			return false;
		}
		_restFor = 0;
		return true;
	}
	/// The card drew a frame of the world and no error was told of.
	void frame()
	{
		if (++_clean >= FORGIVE)
		{
			_clean = 0;
			if (_errors > 0)
			{
				--_errors;
			}
			else if (_rests > 0)
			{
				--_rests;
			}
		}
	}
	/// The context is made anew: everything is forgotten.
	void reset()
	{
		*this = HdGpuTrust();
	}
	bool off() const { return _off; }
	int rests() const { return _rests; }
};

}
