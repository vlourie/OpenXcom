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
#include "SurfaceSet.h"
#include "HdBlit.h"
#include "HdWorkers.h"
#include <climits>
#include "Surface.h"
#include "FileMap.h"
#include "Exception.h"
#include <atomic>
#include <mutex>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace OpenXcom
{

/**
 * Sets up a new empty surface set for frames of the specified size.
 * @param width Frame width in pixels.
 * @param height Frame height in pixels.
 */
SurfaceSet::SurfaceSet(int width, int height) : _width(width), _height(height), _sharedFrames(INT_MAX)
{

}

/**
 * Deletes the images from memory.
 */
/**
 * HD render: a scaled copy whose frames get their memory on first use. A battle touches a few hundred frames of the
 * thousands in the sets it opens (every item in hand, every pose of every armour), and scaled k times a frame is k*k
 * times its size: 130-200 MB of X-Piratez sat in frames nobody drew, in the battle and on the globe after it. The
 * addresses of all frames are reserved at once and never change - the HD packs are registered by them - and the pages
 * of a frame are committed and filled when the frame is first asked for.
 */
struct SurfaceSet::HdLazy
{
	const SurfaceSet *source = nullptr;
	int scale = 1;
	Uint8 *region = nullptr;
	std::vector<size_t> offset, bytes;
	std::unique_ptr<std::atomic<Uint8>[]> ready;
	std::mutex lock;
	~HdLazy()
	{
#ifdef _WIN32
		if (region)
		{
			VirtualFree(region, 0, MEM_RELEASE);
		}
#endif
	}
};

SurfaceSet::~SurfaceSet()
{
	if (_hdLazy && _hdLazy.use_count() == 1)
	{
		// the pixels are the region's, not the frames'
		for (Surface &frame : _frames)
		{
			if (frame)
			{
				frame.hdRelease();
			}
		}
	}
}

void SurfaceSet::hdFill(size_t i) const
{
	HdLazy &lazy = *_hdLazy;
	if (lazy.ready[i].load(std::memory_order_acquire))
	{
		return;
	}
	std::lock_guard<std::mutex> guard(lazy.lock);
	if (lazy.ready[i].load(std::memory_order_relaxed))
	{
		return;
	}
#ifdef _WIN32
	const Surface *src = lazy.source->getFrame((int)i);
	if (!VirtualAlloc(lazy.region + lazy.offset[i], lazy.bytes[i], MEM_COMMIT, PAGE_READWRITE))
	{
		throw Exception("Failed to allocate surface");
	}
	if (src)
	{
		// committed pages are zero, as a new frame's buffer is
		HdBlit::upscaleFrame(const_cast<Surface&>(_frames[i]).getSurface(), const_cast<Surface*>(src)->getSurface(), lazy.scale);
	}
#endif
	lazy.ready[i].store(1, std::memory_order_release);
}

/**
 * Loads the contents of an X-Com set of PCK/TAB image files
 * into the surface. The PCK file contains an RLE compressed
 * image, while the TAB file contains the offsets to each
 * frame in the image.
 * @param pck Filename of the PCK image.
 * @param tab Filename of the TAB offsets.
 * @sa http://www.ufopaedia.org/index.php?title=Image_Formats#PCK
 */
void SurfaceSet::loadPck(const std::string &pck, const std::string &tab)
{
	_frames.clear();

	int nframes = 0;

	// Load TAB and get image offsets
	if (!tab.empty())
	{
		auto offsetFile = FileMap::getIStream(tab);
		std::streampos begin, end;
		begin = offsetFile->tellg();
		int off;
		offsetFile->read((char*)&off, sizeof(off));
		offsetFile->seekg(0, std::ios::end);
		end = offsetFile->tellg();
		int size = end - begin;
		// 16-bit offsets
		if (off != 0)
		{
			nframes = size / 2;
		}
		// 32-bit offsets
		else
		{
			nframes = size / 4;
		}
		for (int frame = 0; frame < nframes; ++frame)
		{
			_frames.push_back(Surface(_width, _height));
		}
	}
	else
	{
		nframes = 1;
		_frames.push_back(Surface(_width, _height));
	}

	auto imgFile = FileMap::getIStream(pck);
	Uint8 value;

	for (int frame = 0; frame < nframes; ++frame)
	{
		int x = 0, y = 0;

		// Lock the surface
		_frames[frame].lock();

		imgFile->read((char*)&value, 1);
		for (int i = 0; i < value; ++i)
		{
			for (int j = 0; j < _width; ++j)
			{
				_frames[frame].setPixelIterative(&x, &y, 0);
			}
		}

		while (imgFile->read((char*)&value, 1) && value != 255)
		{
			if (value == 254)
			{
				imgFile->read((char*)&value, 1);
				for (int i = 0; i < value; ++i)
				{
					_frames[frame].setPixelIterative(&x, &y, 0);
				}
			}
			else
			{
				_frames[frame].setPixelIterative(&x, &y, value);
			}
		}

		// Unlock the surface
		_frames[frame].unlock();
	}
}

/**
 * Loads the contents of an X-Com DAT image file into the
 * surface. Unlike the PCK, a DAT file is an uncompressed
 * image with no offsets so these have to be figured out
 * manually, usually by splitting the image into equal portions.
 * @param filename Filename of the DAT image.
 * @sa http://www.ufopaedia.org/index.php?title=Image_Formats#SCR_.26_DAT
 */
void SurfaceSet::loadDat(const std::string &filename)
{
	int nframes = 0;

	auto imgFile = FileMap::getIStream(filename);
	imgFile->seekg(0, std::ios::end);
	std::streamoff size = imgFile->tellg();
	imgFile->seekg(0, std::ios::beg);

	nframes = (int)size / (_width * _height);

	_frames.resize(nframes);
	for (int i = 0; i < nframes; ++i)
	{
		_frames[i] = Surface(_width, _height);
	}

	if (nframes <= 0)
	{
		return; // the file is shorter than one frame
	}

	Uint8 value;
	int x = 0, y = 0, frame = 0;

	// Lock the surface
	_frames[frame].lock();

	while (imgFile->read((char*)&value, 1))
	{
		_frames[frame].setPixelIterative(&x, &y, value);

		if (y >= _height)
		{
			// Unlock the surface
			_frames[frame].unlock();

			frame++;
			x = 0;
			y = 0;

			if (frame >= nframes)
				break;
			else
				_frames[frame].lock();
		}
	}
	// the read stopped inside a frame (the stream failed): what it has is kept, the frame is left unlocked as the
	// others (the bytes past the last whole frame are never read: the loop ends at nframes)
	if (frame < nframes)
	{
		_frames[frame].unlock();
	}
}

/**
 * Returns a particular frame from the surface set.
 * @param i Frame number in the set.
 * @return Pointer to the respective surface.
 */
Surface *SurfaceSet::getFrame(int i)
{
	if ((size_t)i < _frames.size())
	{
		if (_frames[i])
		{
			if (_hdLazy)
			{
				hdFill((size_t)i);
			}
			return &_frames[i];
		}
	}
	return nullptr;
}

/**
 * Returns a particular frame from the surface set.
 * @param i Frame number in the set.
 * @return Pointer to the respective surface.
 */
const Surface *SurfaceSet::getFrame(int i) const
{
	if ((size_t)i < _frames.size())
	{
		if (_frames[i])
		{
			if (_hdLazy)
			{
				hdFill((size_t)i);
			}
			return &_frames[i];
		}
	}
	return nullptr;
}

/**
 * HD render: a frame as a key and a size only. The HD packs are registered by the address of a frame's pixels, and
 * asking for a frame of a lazy scaled copy through getFrame() would give it memory; this does not.
 * @param i Frame number in the set.
 * @return Pointer to the respective surface; its pixels must not be read or written.
 */
const Surface *SurfaceSet::frameKey(int i) const
{
	if ((size_t)i < _frames.size())
	{
		if (_frames[i])
		{
			return &_frames[i];
		}
	}
	return nullptr;
}

/**
 * Creates and returns a particular frame in the surface set.
 * @param i Frame number in the set.
 * @return Pointer to the respective surface.
 */
Surface *SurfaceSet::addFrame(int i)
{
	assert(i >= 0 && "Negative indexes are not supported in SurfaceSet");
	if ((size_t)i < _frames.size())
	{
		//nothing
	}
	else
	{
		_frames.resize(i + 1);
	}
	_frames[i] = Surface(_width, _height);
	return &_frames[i];
}

/**
 * HD render: scales every frame of the set in place by a nearest-neighbour
 * factor, so that a 32x40 set becomes a 32k x 40k set with identical content.
 * Frames of unusual sizes (mod PNGs) keep their own proportions.
 * @param scale k >= 1.
 */
void SurfaceSet::hdScaleInPlace(int scale)
{
	if (scale <= 1)
	{
		return;
	}
	// the new frames are made here (SDL keeps a shared counter of pixel formats), the pixels on all
	// cores: a set of a few thousand frames took 100 ms on the first frame of a battle
	std::vector<Surface> scaled(_frames.size());
	for (size_t i = 0; i < _frames.size(); ++i)
	{
		if (_frames[i])
		{
			scaled[i] = Surface(_frames[i].getWidth() * scale, _frames[i].getHeight() * scale, _frames[i].getX(), _frames[i].getY());
			if (_frames[i].getPalette())
			{
				scaled[i].setPalette(_frames[i].getPalette());
			}
		}
	}
	const int jobs = (int)std::min<size_t>(_frames.size(), 64);
	const bool whole = HdWorkers::instance().run(jobs, [&](int job)
	{
		for (size_t i = job; i < _frames.size(); i += jobs)
		{
			if (_frames[i])
			{
				HdBlit::upscaleFrame(scaled[i].getSurface(), _frames[i].getSurface(), scale);
			}
		}
	}, HdWorkers::ONCE); // the set is scaled once for the whole game: a hole here cannot be made good later
	if (!whole)
	{
		// which frames it was the pool does not say: each once more here, one at a time (a copy of pixels, the same
		// whether made once or twice), before the set takes the new frames
		for (size_t i = 0; i < _frames.size(); ++i)
		{
			if (_frames[i])
			{
				try { HdBlit::upscaleFrame(scaled[i].getSurface(), _frames[i].getSurface(), scale); } catch (...) {}
			}
		}
	}
	_frames.swap(scaled);
	_width *= scale;
	_height *= scale;
}

/**
 * HD render: makes a new set with every frame scaled by a nearest-neighbour factor.
 * @param scale k >= 1.
 * @return New set, owned by the caller.
 */
SurfaceSet *SurfaceSet::hdScaledCopy(int scale) const
{
#ifdef _WIN32
	// a set of frames of a page and more each is copied lazily (HdLazy); small frames (dots, cursors) and a set
	// that is itself lazy are copied whole, as before
	if (scale > 1 && !_hdLazy)
	{
		const size_t page = 4096;
		auto lazy = std::make_shared<HdLazy>();
		lazy->source = this;
		lazy->scale = scale;
		lazy->offset.resize(_frames.size());
		lazy->bytes.resize(_frames.size());
		size_t total = 0, count = 0;
		for (size_t i = 0; i < _frames.size(); ++i)
		{
			if (_frames[i])
			{
				const size_t bytes = Surface::hdFrameBytes(_frames[i].getWidth() * scale, _frames[i].getHeight() * scale);
				lazy->offset[i] = total;
				lazy->bytes[i] = (bytes + page - 1) / page * page;
				total += lazy->bytes[i];
				++count;
			}
		}
		if (count >= 16 && total / count >= 2 * page)
		{
			lazy->region = (Uint8*)VirtualAlloc(NULL, total, MEM_RESERVE, PAGE_READWRITE);
		}
		if (lazy->region)
		{
			lazy->ready.reset(new std::atomic<Uint8>[_frames.size()]);
			for (size_t i = 0; i < _frames.size(); ++i)
			{
				lazy->ready[i].store(0, std::memory_order_relaxed);
			}
			SurfaceSet *copy = new SurfaceSet(_width * scale, _height * scale);
			copy->_sharedFrames = _sharedFrames;
			copy->_frames.resize(_frames.size());
			copy->_hdLazy = lazy;
			for (size_t i = 0; i < _frames.size(); ++i)
			{
				if (_frames[i])
				{
					copy->_frames[i] = Surface::hdBorrowed(lazy->region + lazy->offset[i], _frames[i].getWidth() * scale, _frames[i].getHeight() * scale,
						_frames[i].getX(), _frames[i].getY());
					if (_frames[i].getPalette())
					{
						copy->_frames[i].setPalette(_frames[i].getPalette());
					}
				}
			}
			return copy;
		}
	}
#endif
	SurfaceSet *copy = new SurfaceSet(*this);
	copy->hdScaleInPlace(scale);
	return copy;
}

/**
 * Returns the full width of a frame in the set.
 * @return Width in pixels.
 */
int SurfaceSet::getWidth() const
{
	return _width;
}

/**
 * Returns the full height of a frame in the set.
 * @return Height in pixels.
 */
int SurfaceSet::getHeight() const
{
	return _height;
}

/**
 * Set number of shared frame indexes that are accessible for all mods.
 */
void SurfaceSet::setMaxSharedFrames(int i)
{
	if (i >= 0)
	{
		_sharedFrames = i;
	}
	else
	{
		_sharedFrames = 0;
	}
}

/**
 * Gets number of shared frame indexes that are accessible for all mods.
 */
int SurfaceSet::getMaxSharedFrames() const
{
	return _sharedFrames;
}

/**
 * Returns the total amount of frames currently
 * stored in the set.
 * @return Number of frames.
 */
size_t SurfaceSet::getTotalFrames() const
{
	return _frames.size();
}

/**
 * Replaces a certain amount of colors in all of the frames.
 * @param colors Pointer to the set of colors.
 * @param firstcolor Offset of the first color to replace.
 * @param ncolors Amount of colors to replace.
 */
void SurfaceSet::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	for (size_t i = 0; i < _frames.size(); ++i)
	{
		if (_frames[i])
			_frames[i].setPalette(colors, firstcolor, ncolors);
	}
}

}
