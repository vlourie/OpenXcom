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
#include "CollapsePilotData.h"
#include <cstring>
#include <string>
#include <vector>
#include "../Engine/Logger.h"
#include "../../libs/miniz/miniz.h"

/// The packed table, written into a C source by cmake/bin2c.cmake from CollapsePilotData(.player).bin.
extern "C" const unsigned char collapse_blob[];
extern "C" const unsigned long collapse_blob_size;

namespace OpenXcom
{
namespace CollapsePilotData
{

namespace
{

const int MAGIC = 0x42435058; // "XPCB"
const int VERSION = 1;
const int FIELDS = 17;        // CollapsePart fields, in the order of the struct

/// What a block points to: the CollapseBlock keeps raw pointers into these.
struct Owned
{
	std::string label, name;
	std::vector<std::string> sets;
	std::vector<const char *> setNames;
	std::vector<CollapsePart> parts, keep;
	std::vector<int> targets, treeCols, crowns;
	bool hasKeep = false, hasTreeCols = false, hasCrowns = false;
};

struct Table
{
	std::vector<Owned> owned;
	std::vector<CollapseBlock> blocks;
};

/// The int32 stream of the table (tools/collapse_blob.py, format v1).
class Reader
{
	const std::vector<int> &_v;
	size_t _pos = 0;
	bool _bad = false;
public:
	explicit Reader(const std::vector<int> &v) : _v(v) {}
	bool bad() const { return _bad; }
	bool done() const { return !_bad && _pos == _v.size(); }
	int one()
	{
		if (_pos >= _v.size()) { _bad = true; return 0; }
		return _v[_pos++];
	}
	std::string str()
	{
		int n = one();
		size_t words = n < 0 ? 0 : (size_t(n) + 3) / 4;
		if (n < 0 || _pos + words > _v.size()) { _bad = true; return std::string(); }
		if (n == 0) return std::string();
		std::string s(reinterpret_cast<const char *>(&_v[_pos]), n);
		_pos += words;
		return s;
	}
	/// An int array; false when the block has none (nullptr in the old header).
	bool ints(std::vector<int> &out)
	{
		int n = one();
		if (n < 0) return false;
		if (_pos + n > _v.size()) { _bad = true; return false; }
		out.assign(_v.begin() + _pos, _v.begin() + _pos + n);
		_pos += n;
		return true;
	}
	/// Parts stored column by column: all kinds, all x, ...
	bool parts(std::vector<CollapsePart> &out)
	{
		int n = one();
		if (n < 0) return false;
		if (_pos + size_t(n) * FIELDS > _v.size()) { _bad = true; return false; }
		out.resize(n);
		for (int f = 0; f < FIELDS; ++f)
			for (int i = 0; i < n; ++i)
				reinterpret_cast<int *>(&out[i])[f] = _v[_pos + size_t(f) * n + i];
		_pos += size_t(n) * FIELDS;
		return true;
	}
};

static_assert(sizeof(CollapsePart) == FIELDS * sizeof(int), "CollapsePart is read as 17 ints");

bool unpack(Table &t)
{
	if (collapse_blob_size < 4) return false;
	uint32_t raw = 0;
	memcpy(&raw, collapse_blob, 4);
	std::vector<int> v(raw / 4);
	mz_ulong got = raw;
	if (raw % 4 || mz_uncompress(reinterpret_cast<unsigned char *>(v.data()), &got, collapse_blob + 4, collapse_blob_size - 4) != MZ_OK || got != raw)
		return false;
	Reader r(v);
	if (r.one() != MAGIC || r.one() != VERSION) return false;
	int count = r.one();
	if (count < 0) return false;
	t.owned.resize(count);
	for (Owned &o : t.owned)
	{
		o.label = r.str();
		o.name = r.str();
		int head[8];
		for (int &h : head) h = r.one();
		int nSets = r.one();
		for (int k = 0; k < nSets && !r.bad(); ++k) o.sets.push_back(r.str());
		r.parts(o.parts);
		r.ints(o.targets);
		o.hasKeep = r.parts(o.keep);
		o.hasTreeCols = r.ints(o.treeCols);
		int nTreeCols = r.one();
		o.hasCrowns = r.ints(o.crowns);
		int nCrowns = r.one();
		if (r.bad()) return false;
#ifndef OXCE_AI_DEV
		if (head[7]) return false; // the player data has no experimental buildings
#endif
		CollapseBlock b = {};
		b.sx = head[0]; b.sy = head[1]; b.sz = head[2];
		b.x0 = head[3]; b.x1 = head[4]; b.y0 = head[5]; b.y1 = head[6];
		b.experimental = head[7];
		b.nSets = (int)o.sets.size();
		b.nParts = (int)o.parts.size();
		b.nKeep = (int)o.keep.size();
		b.nTreeCols = nTreeCols;
		b.nCrowns = nCrowns;
		t.blocks.push_back(b);
	}
	if (!r.done()) return false;
	// pointers only now: the owned strings and vectors stay where they are from here on
	for (int i = 0; i < count; ++i)
	{
		Owned &o = t.owned[i];
		CollapseBlock &b = t.blocks[i];
		for (const std::string &s : o.sets) o.setNames.push_back(s.c_str());
		b.label = o.label.c_str();
		b.name = o.name.c_str();
		b.sets = o.setNames.data();
		b.parts = o.parts.data();
		b.targets = o.targets.data();
		b.keep = o.hasKeep ? o.keep.data() : nullptr;
		b.treeCols = o.hasTreeCols ? o.treeCols.data() : nullptr;
		b.crowns = o.hasCrowns ? o.crowns.data() : nullptr;
	}
	return true;
}

const Table &table()
{
	static Table t;
	static bool ready = false;
	if (!ready)
	{
		ready = true;
		if (!unpack(t))
		{
			Log(LOG_ERROR) << "[COLLAPSE] the built-in pilot data does not unpack: no building collapses in this run";
			t = Table();
		}
	}
	return t;
}

}

const CollapseBlock *blocks()
{
	return table().blocks.data();
}

int blockCount()
{
	return (int)table().blocks.size();
}

}
}
