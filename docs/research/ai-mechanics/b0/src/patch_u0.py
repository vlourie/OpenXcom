"""U0 driver for upstream OXCE v8.7.1 (stage 0B): with OXCE_U0_SAVE=<file> set, the loaded battle ends the player's turn
once it is ready, lets the other sides play, saves the battle at the next ready player turn to <file> and quits.
Without the variable nothing changes."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")

def rep(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)

rep("""void BattlescapeState::think()
{
	static bool popped = false;
""", """// Stage 0B driver (OXCE_U0_SAVE): end the loaded player turn, save at the next one, quit
static void u0Drive(Game *game, SavedBattleGame *save, BattlescapeGame *bg, bool ready)
{
	static const char *saveAs = getenv("OXCE_U0_SAVE");
	static int endedAt = -1;
	static bool done = false;
	if (!saveAs || !*saveAs || done || save->getSide() != FACTION_PLAYER || bg->isBusy() || !ready)
	{
		return;
	}
	if (endedAt < 0)
	{
		endedAt = save->getTurn();
		Log(LOG_INFO) << "[U0] end turn " << endedAt;
		bg->requestEndTurn(false);
	}
	else if (save->getTurn() > endedAt)
	{
		game->getSavedGame()->save(saveAs, game->getMod());
		Log(LOG_INFO) << "[U0] saved: " << saveAs << " turn " << save->getTurn();
		done = true;
		game->quit();
	}
}

void BattlescapeState::think()
{
	static bool popped = false;
""")
rep("""			State::think();
			int ret = _battleGame->think();""", """			State::think();
			u0Drive(_game, _save, _battleGame, allowButtons());
			int ret = _battleGame->think();""")
p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
print("patched", p)
