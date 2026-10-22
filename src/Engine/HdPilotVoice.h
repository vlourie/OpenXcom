#pragma once
/*
 * Pilot voices on the geoscape (ticket XP-000246): the crew of a player craft answers over the radio when it is
 * picked, sent, recalled, hit or out of ammo. Sound only, on the unit response channel 4 (its own volume slider):
 * nothing about the craft, its route or the fight changes, and the line is picked by its own generator, never
 * by the game RNG.
 * Files: hd/PILOT/<air|ground>/<event>/<ru|en>_<N>.ogg in the HD mod, N from 1 up to the first gap
 * (tools/sfx/build_pilot_voices.py). Flying craft (maxAltitude unset or 2 and up) speak with the pilot, ground
 * ones (maxAltitude 0-1: bikes, trucks, tanks, parties on foot) with the driver.
 * Option oxceHdPilotVoice, on by default; off = silence.
 */

namespace OpenXcom
{

class Craft;

namespace HdPilotVoice
{

enum Event { SELECT, ORDER, ATTACK, ESCORT, RETURN, REBASE, WING, CANCEL, DAMAGED, NOAMMO, EVENT_COUNT };

/// The player gave an order: the line plays at once and cuts off the one still on the radio.
void order(const Craft *craft, Event ev);
/// The craft speaks up by itself (hit, guns empty): skipped while another line plays, and within
/// a pause after the last report of the same kind from this craft.
void report(const Craft *craft, Event ev);

}

}
