/*
 * What src/Engine/HdWorkers.cpp takes from the rest of the game, for the tests built without it: the options
 * (all of them, at their zero values - the pool reads its thread count and prints the display's) and the log.
 */
#include "../src/Engine/Options.h"
#include "../src/Engine/Logger.h"

namespace OpenXcom
{

namespace Options
{
#define OPT
#include "../src/Engine/Options.inc.h"
#undef OPT
}

namespace CrossPlatform
{

/// The lines of the pool ("job 17 failed") are part of what the tests provoke: not printed.
void log(int, const std::ostringstream &)
{
}

}

}
