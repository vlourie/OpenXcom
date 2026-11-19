"""AI FORGE WP3: the isolated tree forge3/tree = forge21/tree (the frozen WP2.1 tree) plus, in the monitor's files only: the arena sets the game RNG after a legal intervention (OXCE_AI_FORGE_RESEED),
dumps at the horizons, tiles counted by kind. WP2.1's tree and exe stay as they are. CRLF kept in the tree. Everything here does nothing unless OXCE_AI_FORGE_BRANCH_* is set."""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "forge21"
TREE = HERE / "tree"
if TREE.exists():
    shutil.rmtree(TREE)
shutil.copytree(SRC / "tree", TREE)
root = TREE / "src"
(HERE / "mon").mkdir(exist_ok=True)


def subs(text, old, new):
    assert text.count(old) == 1, (old[:70], text.count(old))
    return text.replace(old, new)


hdr = (SRC / "mon" / "SchedulerIntegrityMonitor.h").read_text(encoding="utf-8").replace("\r\n", "\n")
cpp = (SRC / "mon" / "SchedulerIntegrityMonitor.cpp").read_text(encoding="utf-8").replace("\r\n", "\n")

hdr = subs(hdr, """ *   otherwise a VIOLATION line and the action stays. These lines stay out of the chain, so a run that changes nothing keeps its chain. Never in the living AI.
 */
""", """ *   otherwise a VIOLATION line and the action stays. These lines stay out of the chain, so a run that changes nothing keeps its chain. Never in the living AI.
 * AI FORGE WP3, the same arena: OXCE_AI_FORGE_RESEED=<number, not 0>: once the action has passed all of the above, the game RNG takes this state ([FORGEBRANCH] phase=reseed); only in mode act.
 *   Dumps with the tiles counted by kind: after_branch (the next decision), round0 and round1 (the first decision of turns t+1 and t+2), end.
 */
""")

cpp = subs(cpp, " * AI FORGE WP1, WP2, WP2.1 (bench, never in play). See SchedulerIntegrityMonitor.h. The only calls into the generators read their states.\n",
           " * AI FORGE WP1, WP2, WP2.1, WP3 (bench, never in play). See SchedulerIntegrityMonitor.h. The calls into the generators read their states; the one exception is the arena's OXCE_AI_FORGE_RESEED.\n")
cpp = subs(cpp, """Uint32 battleTicks = 0;
std::map<int, int> knownTu;
""", """Uint32 battleTicks = 0;
std::map<int, int> knownTu;
int branchTurn = -1;
bool roundDone[2] = { false, false };
""")
# the dump: who a unit fought for at the start; a mind control changes only fac
cpp = subs(cpp, """<< " fac=" << (int)bu->getFaction() << " st=" << (int)bu->getStatus()
				<< " pos=\"""", """<< " fac=" << (int)bu->getFaction() << " ofac=" << (int)bu->getOriginalFaction() << " st=" << (int)bu->getStatus()
				<< " pos=\"""")
# the tiles, by kind: a lit tile is not an event of the same weight as a destroyed object
start = cpp.index("std::vector<std::string> tilesAtIntervention;\n")
end = cpp.index("/// A numbered line of the chain:")
cpp = cpp[:start] + """/// What stands on the tile, without doors and what has been seen of it.
std::string objectsText(Tile *tile)
{
	std::ostringstream s;
	for (int part = O_FLOOR; part < O_MAX; ++part)
	{
		int id = -1, set = -1;
		tile->getMapData(&id, &set, (TilePart)part);
		s << id << "." << set << "/";
	}
	return s.str();
}

struct TileMark
{
	std::string text, objects;
	int fire = 0, smoke = 0;
};

std::vector<TileMark> tilesAtIntervention;

void rememberTiles()
{
	tilesAtIntervention.clear();
	for (int i = 0; i < battle->getMapSizeXYZ(); ++i)
	{
		Tile *tile = battle->getTile(i);
		TileMark mark;
		mark.text = tileText(tile);
		mark.objects = objectsText(tile);
		mark.fire = tile->getFire();
		mark.smoke = tile->getSmoke();
		tilesAtIntervention.push_back(mark);
	}
}

/// What changed on the map since the intervention, by kind: every changed object by name, the light only as a number.
void tilesSince()
{
	int changed = 0, objects = 0, fireNow = 0, fireNew = 0, smokeNow = 0, smokeNew = 0, lightOnly = 0;
	for (int i = 0; i < (int)tilesAtIntervention.size(); ++i)
	{
		Tile *tile = battle->getTile(i);
		const TileMark &mark = tilesAtIntervention[i];
		fireNow += tile->getFire() > 0;
		smokeNow += tile->getSmoke() > 0;
		fireNew += tile->getFire() > 0 && mark.fire == 0;
		smokeNew += tile->getSmoke() > 0 && mark.smoke == 0;
		const std::string now = tileText(tile);
		if (now == mark.text)
		{
			continue;
		}
		++changed;
		const std::string nowObjects = objectsText(tile);
		if (nowObjects != mark.objects)
		{
			++objects;
			const Position p = tile->getPosition();
			Log(LOG_INFO) << "[FORGEDUMP] at=" << eventNo << " tile=" << p.x << "," << p.y << "," << p.z << " was=" << mark.objects << " now=" << nowObjects;
		}
		lightOnly += now.substr(0, now.find(",l:")) == mark.text.substr(0, mark.text.find(",l:"));
	}
	Log(LOG_INFO) << "[FORGEDUMP] at=" << eventNo << " tiles_changed=" << changed << " objects=" << objects << " fire_now=" << fireNow << " fire_new=" << fireNew
		<< " smoke_now=" << smokeNow << " smoke_new=" << smokeNew << " light_only=" << lightOnly;
}

/// One horizon: the state, the tiles, and how much real time it took to get here.
void horizon(const char *why)
{
	Log(LOG_INFO) << "[FORGETIME] at=" << why << " turn=" << battle->getTurn() << " side=" << (int)battle->getSide() << " real_ms=" << SDL_GetTicks() << " battle_real_ms=" << (SDL_GetTicks() - battleTicks) << " clock=" << clockNow();
	dumpNow(why);
	tilesSince();
}

""" + cpp[end:]
cpp = subs(cpp, """		dumpAfterBranch = false;
		dumpNow("after_branch");
		tilesSince();
	}
}
""", """		dumpAfterBranch = false;
		horizon("after_branch");
	}
	// the round the action stood in, and the next full one: the first decision of the turns after them
	if (branchTurn >= 0)
	{
		const char *names[2] = { "round0", "round1" };
		for (int k = 0; k < 2; ++k)
		{
			if (!roundDone[k] && save->getTurn() >= branchTurn + k + 1)
			{
				roundDone[k] = true;
				horizon(names[k]);
			}
		}
	}
}
""")
cpp = subs(cpp, """	rememberTiles();
	dumpAfterBranch = true;
""", """	rememberTiles();
	dumpAfterBranch = true;
	branchTurn = save->getTurn();
""")
cpp = subs(cpp, """	if (RNG::getSeed() != before)
	{
		write("ev=VIOLATION kind=rng_touched where=intervene");
	}
}
""", """	if (RNG::getSeed() != before)
	{
		write("ev=VIOLATION kind=rng_touched where=intervene");
		return;
	}
	// WP3: the new state of the game RNG, the same in both branches of a pair; nothing above read it
	if (const char *reseed = getenv("OXCE_AI_FORGE_RESEED"))
	{
		const uint64_t seed = strtoull(reseed, nullptr, 10);
		if (seed == 0)
		{
			write("ev=VIOLATION kind=reseed_zero " + who(unit));
			return;
		}
		RNG::setSeed(seed);
		Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " phase=reseed seed=" << seed << " was=" << hex(before) << " now=" << hex(RNG::getSeed());
	}
}
""")
cpp = subs(cpp, """	fingerprint("end");
	write(std::string("ev=end how=") + how);
""", """	fingerprint("end");
	if (dumpAfterBranch)
	{
		dumpAfterBranch = false;
		horizon("after_branch");
	}
	if (branchTurn >= 0)
	{
		horizon("end");
	}
	write(std::string("ev=end how=") + how);
""")
(HERE / "mon" / "SchedulerIntegrityMonitor.h").write_text(hdr, encoding="utf-8")
(HERE / "mon" / "SchedulerIntegrityMonitor.cpp").write_text(cpp, encoding="utf-8")
for f, t in (("SchedulerIntegrityMonitor.h", hdr), ("SchedulerIntegrityMonitor.cpp", cpp)):
    (root / "Battlescape" / f).write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
shutil.copy2(SRC / "ForgeLegal.h", HERE / "ForgeLegal.h")
shutil.copy2(SRC / "test_legal.cpp", HERE / "test_legal.cpp")
print("tree ready", TREE)
