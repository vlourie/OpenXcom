// The parsers of mod data on damaged and on valid files: the game's own functions, called directly (AUDIT-05, G).
// Linked into the game's executable (hook.cmake). Every case is a process of its own:
//
//   openxcom --parsers-test <case> <data folder> [repeat N]
//
// exit 0 - the file was handled (loaded, or refused with an exception or an empty result); anything else - a crash, a
// sanitizer report (the build is made with them) or a broken promise. `repeat N` runs the case N times and fails when
// the memory of the process keeps growing: a refusal must not leave half-made objects behind.
// The samples are written by run.py; the same file builds against the tree before the fixes (old_tree.py).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <new>
#include <sstream>
#include <string>
#include <vector>
#include <SDL.h>
#include <SDL_mixer.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#endif

// the tests reach a few private members (the map loader, the tables of a rule) - nothing else is opened up
#define private public
#define protected public
#include "Battlescape/BattlescapeGenerator.h"
#include "Engine/Game.h"
#include "Engine/InteractiveSurface.h"
#include "Mod/ExtraSounds.h"
#include "Mod/MapBlock.h"
#include "Mod/Mod.h"
#undef private
#undef protected
#include "Engine/Action.h"
#include "Engine/CatFile.h"
#include "Engine/Exception.h"
#include "Engine/FileMap.h"
#include "Engine/FlcPlayer.h"
#include "Engine/Font.h"
#include "Engine/GMCat.h"
#include "Engine/Language.h"
#include "Engine/Music.h"
#include "Engine/Options.h"
#include "Engine/Screen.h"
#include "Engine/Sound.h"
#include "Engine/SoundSet.h"
#include "Engine/State.h"
#include "Engine/SurfaceSet.h"
#include "Engine/Yaml.h"
#include "Mod/RuleInventory.h"
#include "Mod/RuleTerrain.h"
#include "Savegame/ResearchDiary.h"
#include "Savegame/SavedBattleGame.h"
#include "Savegame/SavedGame.h"
#include "Savegame/Tile.h"

extern "C" int oxce_game_main(int argc, char *argv[]);

using namespace OpenXcom;

namespace
{

/// A promise of the fixed code that is not a matter of memory safety (a default value, a fallback).
struct Broken : std::runtime_error { using std::runtime_error::runtime_error; };
void expect(bool ok, const char *what) { if (!ok) throw Broken(what); }

// --- sounds ---

void soundCat(const char *file)
{
	CatFile cat(file);
	SoundSet set;
	for (int i = 0; i < (int)cat.size(); ++i)
		set.loadCatByIndex(cat, i);
}

void gmCat()
{
	GMCatFile cat("SOUND/GMTEST.CAT");
	std::unique_ptr<Music> music(cat.loadMIDI(0));
}

void extraSoundsEmptyName()
{
	ExtraSounds extra;
	ModData mod = ModData();
	mod.name = "test";
	mod.offset = 1000;
	mod.size = 1000;
	extra._type = "TEST.CAT";
	extra._sounds[0] = ""; // files: { 0: "" }
	extra._current = &mod;
	SoundSet set;
	extra.loadSoundSet(&set);
}

// --- pictures ---

void surfaceSetDat(const char *file)
{
	SurfaceSet set(32, 40);
	set.loadDat(file);
}

void font(const char *yaml, bool draw)
{
	YAML::YamlRootNodeReader reader(YAML::YamlString(yaml), "font of the test");
	Font f;
	f.load(reader);
	if (draw)
	{
		// a character the font does not have is drawn as '?', and a font without '?' has to draw something too
		SurfaceCrop crop = f.getChar('Z');
		expect(crop.getCrop()->w >= 0, "the font gave no picture for a missing character");
		expect(f.getCharSize('Z').w >= 0 && f.getWidth() > 0 && f.getHeight() > 0, "the font has no size");
	}
}

// --- rules and saves ---

void terrainWithoutSets()
{
	RuleTerrain terrain("TEST");
	unsigned int id = 1;
	int set = 0;
	terrain.getMapData(&id, &set);
}

void diaryDefault()
{
	// the memory under the object is not zero: a member without a default keeps this garbage
	alignas(DiscoverySource) unsigned char raw[sizeof(DiscoverySource)];
	memset(raw, 0xCD, sizeof(raw));
	DiscoverySource *source = new (raw) DiscoverySource;
	const bool ok = source->type == DiscoverySourceType::BASE && !source->research && !source->event && !source->mission;
	source->~DiscoverySource();
	expect(ok, "DiscoverySource: a diary entry without sourceType has no defined type and pointers");
}

struct TestState : State { void released(Action *) {} };

void releaseWithoutState()
{
	// a pressed button hidden by setVisible(false): unpress() calls mouseRelease without a state
	InteractiveSurface surface(16, 16);
	surface.onMouseRelease((ActionHandler)&TestState::released);
	surface.onMouseRelease((ActionHandler)&TestState::released, SDL_BUTTON_LEFT);
	surface.setButtonPressed(SDL_BUTTON_LEFT, true);
	surface.setVisible(false);
	expect(!surface.isButtonPressed(SDL_BUTTON_LEFT), "the hidden button stayed pressed");
}

// --- the map of a battle ---

void mapBlock(const char *name)
{
	static Mod *mod = 0;
	static Game *game = 0;
	static Language *lang = 0;
	if (!mod)
	{
		mod = new Mod();
		mod->_invs["STR_GROUND"] = new RuleInventory("STR_GROUND", 0);
		lang = new Language();
		// only what the generator asks the game for: the rules and the save
		game = (Game *)calloc(1, sizeof(Game));
		game->_mod = mod;
		game->_save = new SavedGame();
	}
	SavedBattleGame *battle = new SavedBattleGame(mod, lang);
	battle->initMap(10, 10, 2);
	game->_save->setBattleGame(battle); // the save owns it and deletes the previous one
	BattlescapeGenerator generator(game);
	MapBlock block(name);
	block._size_x = 10;
	block._size_y = 10;
	RuleTerrain terrain("TEST");
	generator.loadMAP(&block, 0, 0, 0, &terrain, 0, false, false, -1);
}

// --- video ---

void flc(const char *file)
{
	static Game *game = 0;
	if (!game)
	{
		Options::create();
		Options::resetDefault(false);
		Options::mute = true; // the player is not to reopen the sound device of a game that is not there
		SDL_WM_SetCaption("parsers test", 0); // the screen copies the caption of the window, the dummy driver has none
		game =(Game *)calloc(1, sizeof(Game));
		game->_screen = new Screen();
	}
	FlcPlayer player;
	const bool ready = player.init(file, 0, game, false, 0, 0);
	player.deInit();
	expect(!ready, "a file that is not a video was taken for one");
}

struct Case { const char *name; std::function<void()> run; };

const Case cases[] = {
	{ "sound_valid",		[] { soundCat("SOUND/SNDVALID.CAT"); } },
	{ "sound_short_wav",	[] { soundCat("SOUND/SNDSHORT.CAT"); } },
	{ "gm",					[] { gmCat(); } }, // run.py puts one of its GM samples under this name
	{ "extrasounds_empty_name", [] { extraSoundsEmptyName(); } },
	{ "dat_valid",			[] { surfaceSetDat("GEODATA/DATVALID.DAT"); } },
	{ "dat_short",			[] { surfaceSetDat("GEODATA/DATSHORT.DAT"); } },
	{ "font_valid",			[] { font("images:\n  - file: FONTTEST.png\n    width: 8\n    height: 8\n    chars: \"AB?\"\n", true); } },
	{ "font_zero_width",	[] { font("images:\n  - file: FONTTEST.png\n    width: 0\n    height: 8\n    chars: \"AB?\"\n", true); } },
	{ "font_wider_than_image", [] { font("images:\n  - file: FONTTEST.png\n    width: 64\n    height: 8\n    chars: \"AB?\"\n", true); } },
	{ "font_no_question",	[] { font("images:\n  - file: FONTTEST.png\n    width: 8\n    height: 8\n    chars: \"AB\"\n", true); } },
	{ "font_no_images",		[] { font("width: 8\nheight: 8\n", true); } },
	{ "terrain_no_sets",	[] { terrainWithoutSets(); } },
	{ "diary_default",		[] { diaryDefault(); } },
	{ "release_without_state", [] { releaseWithoutState(); } },
	{ "map_valid",			[] { mapBlock("MAPVALID"); } },
	{ "map_extra_records",	[] { mapBlock("MAPEXTRA"); } },
	{ "map_no_height",		[] { mapBlock("MAPFLAT"); } },
	{ "flc_short",			[] { flc("FLC/SHORT.FLC"); } },
	{ "flc_not_video",		[] { flc("FLC/NOTFLC.FLC"); } },
};

/// One run: 0 handled, 1 a broken promise.
int runOnce(const Case &c, bool report)
{
	try
	{
		c.run();
		if (report) printf("RESULT handled: finished\n");
	}
	catch (const Broken &e)
	{
		printf("RESULT broken: %s\n", e.what());
		return 1;
	}
	catch (const std::exception &e)
	{
		if (report) printf("RESULT handled: refused - %s\n", e.what());
	}
	catch (const char *e)
	{
		if (report) printf("RESULT handled: refused - %s\n", e);
	}
	return 0;
}

size_t privateBytes()
{
#ifdef _WIN32
	PROCESS_MEMORY_COUNTERS_EX pmc;
	memset(&pmc, 0, sizeof(pmc));
	GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&pmc, sizeof(pmc));
	return pmc.PrivateUsage;
#else
	return 0;
#endif
}

}

int main(int argc, char *argv[])
{
	if (argc < 4 || strcmp(argv[1], "--parsers-test") != 0)
		return oxce_game_main(argc, argv);

	setvbuf(stdout, 0, _IONBF, 0);
	SDL_Init(SDL_INIT_AUDIO | SDL_INIT_VIDEO | SDL_INIT_NOPARACHUTE); // a crash is to reach the sanitizer, not SDL
	Mix_OpenAudio(22050, AUDIO_S16SYS, 2, 1024);
	std::string data = argv[3];
	if (!data.empty() && data.back() != '/')
		data += '/';
	Options::setDataFolder(data);
	FileMap::clear(false, false);

	const Case *c = 0;
	for (const Case &one : cases)
		if (!strcmp(one.name, argv[2]))
			c = &one;
	if (!c)
	{
		if (!strcmp(argv[2], "list"))
		{
			for (const Case &one : cases) printf("%s\n", one.name);
			return 0;
		}
		printf("no such case: %s\n", argv[2]);
		return 2;
	}
	int rc = runOnce(*c, true);
	if (rc == 0 && argc > 5 && !strcmp(argv[4], "repeat"))
	{
		const int n = atoi(argv[5]);
		// the first third warms the allocator up; after it the memory of the process must not keep growing
		size_t warm = 0;
		for (int i = 0; i < n && rc == 0; ++i)
		{
			rc = runOnce(*c, false);
			if (i == n / 3) warm = privateBytes();
		}
		const size_t end = privateBytes();
		const long long grown = (long long)end - (long long)warm;
		printf("REPEAT %d runs: %lld KiB grown over the last two thirds\n", n, grown / 1024);
		if (grown > 4 * 1024 * 1024)
		{
			printf("RESULT broken: the memory keeps growing\n");
			rc = 1;
		}
	}
	fflush(stdout);
	// no destructors of the game's globals: the case is over, the sanitizer has seen what it had to
	_exit(rc);
}
