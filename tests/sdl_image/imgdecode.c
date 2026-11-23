/* Автономная проверка декодирования картинок через SDL_image, без игры.
   imgdecode <список.txt> <выход.tsv> [начать_с] [повторов]
   Список - пути в UTF-8, по одному в строке. На каждый файл одна строка свойств SDL_Surface.
   Файл читается в память и отдаётся IMG_Load_RW без подсказки типа - как это делает игра. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <psapi.h>
#include "SDL.h"
#include "SDL_image.h"
#undef main

static unsigned long long fnv(unsigned long long h, const unsigned char *p, size_t n)
{
	size_t i;
	for (i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ULL; }
	return h;
}

static unsigned char *slurp(const char *utf8, long *size)
{
	wchar_t w[2048];
	FILE *f;
	unsigned char *buf;
	if (!MultiByteToWideChar(CP_UTF8, 0, utf8, -1, w, 2048)) return NULL;
	f = _wfopen(w, L"rb");
	if (!f) return NULL;
	fseek(f, 0, SEEK_END);
	*size = ftell(f);
	fseek(f, 0, SEEK_SET);
	buf = (unsigned char *)malloc(*size ? *size : 1);
	if (fread(buf, 1, *size, f) != (size_t)*size) { fclose(f); free(buf); return NULL; }
	fclose(f);
	return buf;
}

int main(int argc, char **argv)
{
	FILE *list, *out;
	char line[4096];
	int idx = 0, start = 0, repeat = 1, ok = 0, bad = 0, r;
	LARGE_INTEGER fq, t0, t1;
	double decodeMs = 0;
	PROCESS_MEMORY_COUNTERS pmc;
	const SDL_version *v = IMG_Linked_Version();

	if (argc < 3) return 2;
	if (argc > 3) start = atoi(argv[3]);
	if (argc > 4) repeat = atoi(argv[4]);
	list = fopen(argv[1], "rb");
	out = fopen(argv[2], start ? "ab" : "wb");
	if (!list || !out) return 2;
	QueryPerformanceFrequency(&fq);
	while (fgets(line, sizeof(line), list))
	{
		long size = 0;
		unsigned char *data;
		SDL_Surface *s = NULL;
		size_t n = strlen(line);
		while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
		if (idx++ < start || !n) continue;
		/* метка до декодирования: по ней обвязка находит файл, на котором процесс умер */
		fprintf(stderr, "BEGIN %d\n", idx - 1);
		fflush(stderr);
		data = slurp(line, &size);
		if (!data) { fprintf(out, "%d\tNOFILE\n", idx - 1); continue; }
		for (r = 0; r < repeat; ++r)
		{
			SDL_RWops *rw = SDL_RWFromConstMem(data, size);
			if (s) SDL_FreeSurface(s);
			QueryPerformanceCounter(&t0);
			s = IMG_Load_RW(rw, 1);
			QueryPerformanceCounter(&t1);
			decodeMs += (double)(t1.QuadPart - t0.QuadPart) * 1000.0 / (double)fq.QuadPart;
		}
		if (!s)
		{
			++bad;
			fprintf(out, "%d\tERR\n", idx - 1);
		}
		else
		{
			unsigned long long ph = 14695981039346656037ULL, lh = 14695981039346656037ULL, uh = lh;
			int y, nc = 0, bytes = s->format->BytesPerPixel;
			++ok;
			if (SDL_MUSTLOCK(s)) SDL_LockSurface(s);
			for (y = 0; y < s->h; ++y)
				ph = fnv(ph, (unsigned char *)s->pixels + (size_t)y * s->pitch, (size_t)s->w * bytes);
			if (s->format->palette)
			{
				nc = s->format->palette->ncolors;
				for (y = 0; y < nc; ++y)
				{
					lh = fnv(lh, &s->format->palette->colors[y].r, 1);
					lh = fnv(lh, &s->format->palette->colors[y].g, 1);
					lh = fnv(lh, &s->format->palette->colors[y].b, 1);
					uh = fnv(uh, &s->format->palette->colors[y].unused, 1);
				}
			}
			fprintf(out, "%d\tOK\t%dx%d\tbpp%d\tmask%08x.%08x.%08x.%08x\tkey%d:%u\talpha%d:%u\tpal%d:%016llx:%016llx\tpix%016llx\n",
				idx - 1, s->w, s->h, s->format->BitsPerPixel,
				(unsigned)s->format->Rmask, (unsigned)s->format->Gmask, (unsigned)s->format->Bmask, (unsigned)s->format->Amask,
				(s->flags & SDL_SRCCOLORKEY) ? 1 : 0, (unsigned)s->format->colorkey,
				(s->flags & SDL_SRCALPHA) ? 1 : 0, (unsigned)s->format->alpha,
				nc, lh, uh, ph);
			SDL_FreeSurface(s);
		}
		fflush(out);
		free(data);
	}
	fclose(out);
	memset(&pmc, 0, sizeof(pmc));
	GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc));
	fprintf(stderr, "DONE lib=%d.%d.%d ok=%d err=%d decode_ms=%.1f peak_mb=%.1f\n", v->major, v->minor, v->patch,
		ok, bad, decodeMs, (double)pmc.PeakWorkingSetSize / 1048576.0);
	return 0;
}
