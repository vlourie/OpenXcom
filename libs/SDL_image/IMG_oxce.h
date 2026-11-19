/*
  OXCE: every surface of the decoders is created here (not a part of upstream SDL_image, see README_OXCE.md).

  SDL 1.2 takes the size and the depth of a new surface as they come: a negative width passes its only check
  ("width >= 16384"), a depth over 255 is cut to its low byte in SDL_PixelFormat while the pitch is counted from
  the whole number. A decoder that hands over what it has read from a damaged file gets a surface whose w, h,
  pitch and pixels do not agree, and then writes rows past the pixels (or the caller reads them past the end).
  The decoders of this branch check their sizes each in its own way and some not at all, so the check is one,
  at the only door.
*/
#ifndef IMG_OXCE_H_
#define IMG_OXCE_H_

#include "SDL_video.h"
#include "SDL_error.h"

static SDL_Surface *IMG_OxceCreateSurface(Uint32 flags, int width, int height, int depth,
                                          Uint32 Rmask, Uint32 Gmask, Uint32 Bmask, Uint32 Amask)
{
	/* (the upper limits of the size are the ones of SDL_CreateRGBSurface itself: its pitch is 16 bits) */
	if ( width <= 0 || height <= 0 || width >= 16384 || height >= 65536 ) {
		SDL_SetError("Invalid image size (%d x %d)", width, height);
		return NULL;
	}
	if ( depth < 1 || depth > 32 ) {
		SDL_SetError("Invalid image depth (%d bits)", depth);
		return NULL;
	}
	/* (SDL counts the bytes of the pixels in an int) */
	if ( (Uint64)width * (Uint64)((depth + 7) / 8) * (Uint64)height > 0x7FFFFFFF ) {
		SDL_SetError("Image is too large (%d x %d)", width, height);
		return NULL;
	}
	return SDL_CreateRGBSurface(flags, width, height, depth, Rmask, Gmask, Bmask, Amask);
}

#undef SDL_AllocSurface
#define SDL_AllocSurface     IMG_OxceCreateSurface
#define SDL_CreateRGBSurface IMG_OxceCreateSurface

#endif /* IMG_OXCE_H_ */
