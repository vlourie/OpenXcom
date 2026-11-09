"""U0 driver, part 2: under OXCE_U0_SAVE nobody presses OK - the message boxes of the enemy turn close themselves and
the next turn screen goes by its timer, as the fork's stand does (AiProbe::autoClose). usage: patch_u0_popups.py <src/Battlescape>"""
import sys
from pathlib import Path

B = Path(sys.argv[1])


def edit(name, pairs):
    p = B / name
    raw = p.read_bytes()
    crlf = b"\r\n" in raw
    t = raw.decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        assert t.count(old) == 1, (name, old[:50])
        t = t.replace(old, new)
    p.write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    print("patched", p)


edit("InfoboxOKState.h", [("""	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
""", """	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Stage 0B driver: closes itself under OXCE_U0_SAVE.
	void think() override;
""")])
edit("InfoboxOKState.cpp", [("""#include "../Savegame/SavedBattleGame.h"
""", """#include "../Savegame/SavedBattleGame.h"
#include "../Engine/Logger.h"
#include <cstdlib>
"""), ("""void InfoboxOKState::btnOkClick(Action *)""", """void InfoboxOKState::think()
{
	State::think();
	const char *u0 = getenv("OXCE_U0_SAVE");
	if (u0 && *u0)
	{
		Log(LOG_INFO) << "[U0] closed: " << _txtTitle->getText();
		btnOkClick(nullptr);
	}
}

void InfoboxOKState::btnOkClick(Action *)""")])
edit("NextTurnState.cpp", [("""	if (Options::skipNextTurnScreen && message.empty() && messageReinforcements.empty())""",
                            """	if ((getenv("OXCE_U0_SAVE") && *getenv("OXCE_U0_SAVE")) || (Options::skipNextTurnScreen && message.empty() && messageReinforcements.empty()))""")])
