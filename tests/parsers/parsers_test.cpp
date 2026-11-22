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
#include "Mod/MapData.h"
#include "Mod/MapDataSet.h"
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
#include "Savegame/Base.h"
#include "Savegame/ItemContainer.h"
#include "Savegame/Soldier.h"
#include "Savegame/Transfer.h"
#include "Mod/Armor.h"
#include "Mod/RuleItem.h"
#include "Mod/RuleSoldier.h"
#include "Engine/HdUiArt.h"
#include "Engine/ModInfo.h"
#include "Engine/Surface.h"
#include <climits>

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
	expect(set.getSound(0) == nullptr, "an empty file name made a sound");
}

// --- pictures ---

void surfaceSetDat(const char *file)
{
	SurfaceSet set(32, 40);
	set.loadDat(file);
}

/// One whole frame and half of the next: the whole one is read, the half left out, no frame stays locked.
void surfaceSetDatPartial()
{
	SurfaceSet set(32, 40);
	set.loadDat("GEODATA/DATPARTIAL.DAT");
	expect(set.getTotalFrames() == 1, "a set of one and a half frames has not one frame");
	expect(set.getFrame(0)->getSurface()->locked == 0, "the frame is left locked");
	expect(set.getFrame(0)->getPixel(0, 0) == 7 && set.getFrame(0)->getPixel(31, 39) == 7, "the frame is not the file's");
}

/// The font has no '?': every character it lacks is drawn as the first character of its first image.
void fontNoQuestionFirst()
{
	const char *yaml = "width: 8\nheight: 8\nimages:\n  - file: FONTTEST.png\n    chars: \"BA\"\n";
	YAML::YamlRootNodeReader reader(YAML::YamlString(yaml), "font of the test");
	Font f;
	f.load(reader);
	expect(f.getChar('Z').getCrop()->x == f.getChar('B').getCrop()->x && f.getCharSize('Z').w == f.getCharSize('B').w, "a missing character is not drawn as the first one of the file");
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

/// A block put somewhere in a battle of its own; a refused block must leave every tile as it was (here: not discovered).
void mapBlockAt(const char *name, int xoff, int zoff, int mapZ, bool refused, const char *what)
{
	static Mod *mod = 0;
	static Game *game = 0;
	static Language *lang = 0;
	if (!mod)
	{
		mod = new Mod();
		mod->_invs["STR_GROUND"] = new RuleInventory("STR_GROUND", 0);
		lang = new Language();
		game = (Game *)calloc(1, sizeof(Game));
		game->_mod = mod;
		game->_save = new SavedGame();
	}
	SavedBattleGame *battle = new SavedBattleGame(mod, lang);
	battle->initMap(10, 10, mapZ);
	game->_save->setBattleGame(battle);
	BattlescapeGenerator generator(game);
	MapBlock block(name);
	block._size_x = 10;
	block._size_y = 10;
	RuleTerrain terrain("TEST");
	bool threw = false;
	try { generator.loadMAP(&block, xoff, 0, zoff, &terrain, 0, true, false, -1); } catch (const std::exception &) { threw = true; }
	int discovered = 0;
	for (int i = 0; i < battle->getMapSizeXYZ(); ++i)
		discovered += battle->getTile(i)->isDiscovered(O_FLOOR) ? 1 : 0;
	expect(threw == refused, what);
	expect(!threw || discovered == 0, "a refused block changed tiles of the map");
	expect(threw || discovered > 0, "a loaded block changed no tile");
}

// --- terrain sets: the two tiles of BLANKS (MapDataSet::getBlankFloorTile, getScorchedEarthTile) ---

std::string dataRoot; // the data folder of the run, with the slash

/// The PCK of BLANKS is taken away on disk (the file map still lists it): reading it fails.
struct NoBlanksPck
{
	std::string path = dataRoot + "common/TERRAIN/BLANKS.PCK";
	NoBlanksPck() { rename(path.c_str(), (path + ".away").c_str()); }
	~NoBlanksPck() { rename((path + ".away").c_str(), path.c_str()); }
};

/// The tile is a record that lives: its fields are read (a freed one is a report of the sanitizer).
int touch(const MapData *tile)
{
	return tile ? tile->getArmor() + tile->getTUCost(MT_WALK) : 0;
}

void blanksValid()
{
	MapDataSet set("BLANKS");
	set.loadData(nullptr, true, 1);
	expect(MapDataSet::getBlankFloorTile() == set.getObject(0), "the blank tile is not the first record of BLANKS");
	expect(MapDataSet::getScorchedEarthTile() == set.getObject(1), "the scorched tile is not the second record of BLANKS");
	touch(MapDataSet::getBlankFloorTile());
	touch(MapDataSet::getScorchedEarthTile());
	set.unloadData();
	expect(!MapDataSet::getBlankFloorTile() && !MapDataSet::getScorchedEarthTile(), "the tiles of BLANKS point into an unloaded set");
	// the next battle loads it again
	set.loadData(nullptr, true, 1);
	expect(MapDataSet::getScorchedEarthTile() == set.getObject(1), "BLANKS loaded again does not give its tiles");
	touch(MapDataSet::getScorchedEarthTile());
}

void blanksNoPck()
{
	MapDataSet set("BLANKS");
	{
		NoBlanksPck away;
		bool refused = false;
		try { set.loadData(nullptr, true, 1); } catch (const std::exception &) { refused = true; }
		expect(refused, "BLANKS without its PCK was loaded");
	}
	expect(!set.isLoaded(), "a refused set stays loaded");
	touch(MapDataSet::getBlankFloorTile()); // the old code left both pointing into the deleted records
	touch(MapDataSet::getScorchedEarthTile());
	expect(!MapDataSet::getBlankFloorTile() && !MapDataSet::getScorchedEarthTile(), "a refused BLANKS published its tiles");
	// the next battle, with the file back, starts
	set.loadData(nullptr, true, 1);
	expect(MapDataSet::getBlankFloorTile() == set.getObject(0), "BLANKS after a refusal does not give its tiles");
	touch(MapDataSet::getBlankFloorTile());
}

void blanksScale()
{
	static Mod *mod = 0;
	if (!mod)
	{
		Options::create();
		Options::resetDefault(false);
		mod = new Mod();
	}
	MapDataSet *set = new MapDataSet("BLANKS");
	mod->_mapDataSets["BLANKS"] = set;
	set->loadData(nullptr, true, 1);
	MapData *blank = set->getObject(0), *scorched = set->getObject(1);

	// a battle at another scale is refused: the parked battle comes back with its tiles
	Mod::HdScalePark *park = mod->parkHdScale();
	{
		NoBlanksPck away;
		bool refused = false;
		try { set->loadData(nullptr, true, 2); } catch (const std::exception &) { refused = true; }
		expect(refused, "BLANKS without its PCK was loaded at scale 2");
	}
	mod->unparkHdScale(park);
	expect(set->isLoaded() && set->getObject(0) == blank, "the parked set did not come back");
	expect(MapDataSet::getBlankFloorTile() == blank && MapDataSet::getScorchedEarthTile() == scorched, "the tiles of BLANKS are not the parked ones after a refusal");
	touch(MapDataSet::getBlankFloorTile());
	touch(MapDataSet::getScorchedEarthTile());

	// the same at scale 2 with the file there: the new set, the parked one is freed
	park = mod->parkHdScale();
	set->loadData(nullptr, true, 2);
	MapData *blank2 = set->getObject(0), *scorched2 = set->getObject(1);
	mod->dropHdScale(park);
	expect(MapDataSet::getBlankFloorTile() == blank2 && MapDataSet::getScorchedEarthTile() == scorched2, "the tiles of BLANKS are not those of the new scale");
	touch(MapDataSet::getBlankFloorTile());
	touch(MapDataSet::getScorchedEarthTile());

	// the battle ends, the set goes
	mod->_mapDataSets.erase("BLANKS");
	delete set;
	expect(!MapDataSet::getBlankFloorTile() && !MapDataSet::getScorchedEarthTile(), "the tiles of BLANKS outlive their set");
}

// --- saves ---

/// A mod with nothing in it but one item, one soldier and one armor of the test.
Mod *plainMod()
{
	static Mod *mod = 0;
	if (!mod)
	{
		Options::create();
		Options::resetDefault(false);
		mod = new Mod();
		mod->_items["TEST_ITEM"] = new RuleItem("TEST_ITEM", 0);
		mod->_soldiers["TEST_SOLDIER"] = new RuleSoldier("TEST_SOLDIER", 0);
		mod->_armors["TEST_ARMOR"] = new Armor("TEST_ARMOR", 0);
	}
	return mod;
}

/// A transfer arrives once whatever its hours (a save, transferTime: 0, a damaged INT_MIN), and once more after a save.
void transferHours()
{
	Mod *mod = plainMod();
	const RuleItem *item = mod->getItem("TEST_ITEM");
	for (int hours : { 2, 1, 0, -5, INT_MIN })
	{
		Base base(mod);
		Transfer people(hours), things(hours);
		people.setEngineers(3);
		things.setItems(item, 4);
		for (int hour = 0; hour < 6; ++hour)
		{
			people.advance(&base);
			things.advance(&base);
			expect(people.getHours() >= 0 && things.getHours() >= 0, "a transfer has hours below zero");
		}
		expect(base.getEngineers() == 3, "the engineers did not arrive once");
		expect(base.getStorageItems()->getItem(item) == 4, "the items did not arrive once");
	}
	// delivered, saved and loaded: the next hours bring nothing more
	Base base(mod);
	Transfer things(0);
	things.setItems(item, 2);
	things.advance(&base);
	YAML::YamlRootNodeWriter writer;
	things.save(writer.toBase(), &base, mod);
	const std::string yaml = writer.emit().yaml;
	YAML::YamlRootNodeReader reader(YAML::YamlString(yaml), "transfer of the test");
	Transfer *loaded = new Transfer(0);
	expect(loaded->load(reader, &base, mod, nullptr), "the saved transfer was not loaded");
	for (int hour = 0; hour < 3; ++hour)
		loaded->advance(&base);
	delete loaded;
	expect(base.getStorageItems()->getItem(item) == 2, "a delivered transfer came again after a save");
}

/// The rank of a save: 0..5 is taken, anything else refused (as an int, 4294967300 was rank 4), no rank keeps the old one.
void soldierRank()
{
	Mod *mod = plainMod();
	auto load = [&](const std::string &rank, bool &refused) -> int
	{
		Soldier soldier(mod->getSoldier("TEST_SOLDIER"), nullptr, 0);
		std::string yaml = "armor: TEST_ARMOR";
		if (!rank.empty())
			yaml += std::string(1, (char)10) + "rank: " + rank;
		YAML::YamlRootNodeReader reader(YAML::YamlString(yaml), "soldier of the test");
		refused = false;
		try { soldier.load(reader, mod, nullptr, mod->getScriptGlobal()); } catch (const std::exception &) { refused = true; }
		return soldier.getRank();
	};
	bool refused;
	expect(load("4", refused) == RANK_COLONEL && !refused, "rank 4 was not read");
	expect(load("", refused) == RANK_ROOKIE && !refused, "a soldier without a rank does not keep the one it has");
	for (const char *bad : { "4294967300", "6", "-1", "99999999999999999999", "abc" })
	{
		load(bad, refused);
		expect(refused, "a rank out of the tables was taken");
	}
}

/// The HD interface pictures of a mod in a .zip (run.py: hd/UI of the mod 'hdzip', 300 pictures with their palettes).
/// Their sizes and palettes are read on the worker threads (61585af33); a .zip is one reader for all of its files:
/// every picture must come in, of its size and with its own palette, in every one of ten loads.
void hdUiZip()
{
	static bool mapped = false;
	static std::map<std::string, ModInfo> infos;
	Mod *mod = plainMod();
	const int PICTURES = 300;
	if (!mapped)
	{
		FileMap::scanModDir(dataRoot, "mods", false);
		infos = FileMap::getModInfos();
		auto it = infos.find("hdzip");
		expect(it != infos.end(), "the mod of the test in a .zip was not found");
		FileMap::setup({ &it->second }, false);
		expect(FileMap::fileExists("hd/UI/hdzip_000.png"), "the pictures of the .zip are not in the files of the game");
		char name[32];
		for (int i = 0; i < PICTURES; ++i)
		{
			snprintf(name, sizeof(name), "HDZIP_%03d", i);
			mod->_surfaces[name] = new Surface(8, 8);
		}
		mapped = true;
	}
	char name[32];
	for (int load = 0; load < 10; ++load)
	{
		mod->loadHdUiArt();
		for (int i = 0; i < PICTURES; ++i)
		{
			snprintf(name, sizeof(name), "HDZIP_%03d", i);
			const HdUiArt::Art *art = HdUiArt::find(mod->_surfaces[name]);
			expect(art != nullptr, "a picture of the .zip did not come in");
			expect(art->scale == 2 + i % 3, "a picture of the .zip came in of another size");
			expect(art->palette.size() == 256 && art->palette[7].r == i % 256 && art->palette[7].g == 7
				&& art->palette[255].b == 0, "a picture of the .zip came in without its own palette");
		}
	}
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
	{ "dat_partial_frame",	[] { surfaceSetDatPartial(); } },
	{ "font_no_question_first", [] { fontNoQuestionFirst(); } },
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
	// a byte past the last record: 1708 maps of X-Piratez end so, they load as they always did
	{ "map_tail_byte",		[] { mapBlockAt("MAPTAIL", 0, 0, 2, false, "a map with a byte past its records was refused"); } },
	{ "map_short_header",	[] { mapBlockAt("MAPSHORT", 0, 0, 2, true, "a map without its header was loaded"); } },
	{ "map_outside",		[] { mapBlockAt("MAPVALID", 5, 0, 2, true, "a block past the edge of the map was loaded"); } },
	{ "map_below_bottom",	[] { mapBlockAt("MAPVALID", 0, -1, 2, true, "a block below the bottom of the map was loaded"); } },
	// a block of one layer with the records of two, put on layer 1 (a craft, a vertical level): the second layer is the ground
	{ "map_extra_over_ground", [] { mapBlockAt("MAPONEEXTRA", 0, 1, 3, true, "a block wrote its extra records over the layer below"); } },
	{ "map_upper_layer",	[] { mapBlockAt("MAPONE", 0, 1, 3, false, "a block of one layer on layer 1 was refused"); } },
	{ "blanks_valid",		[] { blanksValid(); } },
	{ "blanks_no_pck",		[] { blanksNoPck(); } },
	{ "blanks_scale",		[] { blanksScale(); } },
	{ "transfer_hours",		[] { transferHours(); } },
	{ "soldier_rank",		[] { soldierRank(); } },
	{ "hdui_zip",			[] { hdUiZip(); } },
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
	dataRoot = data;
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
