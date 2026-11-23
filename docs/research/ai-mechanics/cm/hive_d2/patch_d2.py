"""HIVE D2 CORRECTION: to a clean copy of hive/us/tree. An offer the soldier's own search refuses costs no try: the same try goes on with the soldier's own node. The kept node is no longer taken away (dropKept only writes). Timings only written."""
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "hive" / "d2" / "tree" / "src"


def sub(rel, pairs):
    p = T / rel
    text = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    for a, b in pairs:
        if text.count(a) != 1:
            raise SystemExit(f"{rel}: {text.count(a)} of {a[:70]!r}")
        text = text.replace(a, b)
    if crlf:
        text = text.replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8"))


sub("Battlescape/AIModule.h", [(
    "\tNode *hivePatrolNode(bool scout, int triesLeft);\n",
    "\tNode *hivePatrolNode(bool scout, int triesLeft, HiveCommand::PatrolTally &tally);\n",
), (
    "class SavedBattleGame;\nclass BattleUnit;\n",
    "namespace HiveCommand { struct PatrolTally; }\nclass SavedBattleGame;\nclass BattleUnit;\n",
)])

sub("Battlescape/AIModule.cpp", [
    (
        "\t// UNIFIED ARMY CONTROL V0 (bench): a node kept from before that no longer serves the squad's task goes back to the choice below, once a turn; with nothing else to go to, the unit keeps it\n",
        "\t// HIVE D2 (bench): the node a soldier keeps stays its own; dropKept only writes where the task would have taken it away\n",
    ),
    (
        "\tNode *hiveDropped = 0;\n"
        "\tif (_toNode != 0 && HiveCommand::dropKept(_save, _unit, _toNode))\n"
        "\t{\n"
        "\t\thiveDropped = _toNode;\n"
        "\t\tfreePatrolTarget();\n"
        "\t\t_toNode = 0;\n"
        "\t}\n",
        "\tif (_toNode != 0)\n"
        "\t{\n"
        "\t\tHiveCommand::dropKept(_save, _unit, _toNode);\n"
        "\t}\n",
    ),
    (
        "\tconst bool oxceFixes = AiProbe::oxceFixes();\n\n"
        "\twhile (_toNode == 0 && triesLeft)\n",
        "\tconst bool oxceFixes = AiProbe::oxceFixes();\n"
        "\tHiveCommand::PatrolTally hiveTally;\n\n"
        "\twhile (_toNode == 0 && triesLeft)\n",
    ),
    (
        "\t\t\t_toNode = hivePatrolNode(scout, triesLeft);\n",
        "\t\t\t_toNode = hivePatrolNode(scout, triesLeft, hiveTally);\n",
    ),
    (
        "\t\t\tconst auto hiveT0 = std::chrono::steady_clock::now();\n"
        "\t\t\t_save->getPathfinding()->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);\n"
        "\t\t\tHiveCommand::perfPath(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - hiveT0).count(), _save->getPathfinding()->getStartDirection() == -1);\n"
        "\t\t\tif (_save->getPathfinding()->getStartDirection() == -1)\n"
        "\t\t\t{\n"
        "\t\t\t\tif (oxceFixes && !_toNode->isAllocated())\n",
        "\t\t\tconst uint64_t hiveSeed = RNG::getSeed();\n"
        "\t\t\tconst auto hiveT0 = std::chrono::steady_clock::now();\n"
        "\t\t\t_save->getPathfinding()->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);\n"
        "\t\t\tconst long long hiveNs = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - hiveT0).count();\n"
        "\t\t\tHiveCommand::perfPath(hiveNs, _save->getPathfinding()->getStartDirection() == -1);\n"
        "\t\t\t// HIVE D2 (bench): an offer the soldier's own search refuses costs no try: this same try goes on with the soldier's own node, as if nothing had been offered\n"
        "\t\t\tif (hiveTally.offer && _save->getPathfinding()->getStartDirection() == -1)\n"
        "\t\t\t{\n"
        "\t\t\t\tHiveCommand::offerRefused(_save, _unit, _toNode, hiveTally, 5 - triesLeft, hiveNs, _save->getPathfinding()->getExpanded(), RNG::getSeed() != hiveSeed);\n"
        "\t\t\t\t_save->getPathfinding()->abortPath();\n"
        "\t\t\t\t_toNode = hiveTally.free;\n"
        "\t\t\t\tif (_toNode != 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\thiveTally.freeChecked++;\n"
        "\t\t\t\t\tconst auto hiveT1 = std::chrono::steady_clock::now();\n"
        "\t\t\t\t\t_save->getPathfinding()->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);\n"
        "\t\t\t\t\tHiveCommand::perfPath(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - hiveT1).count(), _save->getPathfinding()->getStartDirection() == -1);\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\telse if (hiveTally.offer)\n"
        "\t\t\t{\n"
        "\t\t\t\tHiveCommand::offerTaken(hiveTally, hiveNs);\n"
        "\t\t\t}\n"
        "\t\t\telse if (hiveTally.asked)\n"
        "\t\t\t{\n"
        "\t\t\t\thiveTally.freeChecked++;\n"
        "\t\t\t}\n"
        "\t\t\thiveTally.offer = false;\n"
        "\t\t\tif (_toNode != 0 && _save->getPathfinding()->getStartDirection() == -1)\n"
        "\t\t\t{\n"
        "\t\t\t\tif (oxceFixes && !_toNode->isAllocated())\n",
    ),
    (
        "\tif (_toNode == 0 && hiveDropped != 0)\n"
        "\t{\n"
        "\t\t_toNode = hiveDropped;\n"
        "\t\tLog(LOG_INFO) << \"[HIVEUA] event=KEPT_BACK turn=\" << _save->getTurn() << \" unit=\" << _unit->getId();\n"
        "\t}\n",
        "\tif (hiveTally.asked)\n"
        "\t{\n"
        "\t\tHiveCommand::patrolEnded(_save, _unit, hiveTally, _toNode);\n"
        "\t}\n",
    ),
    (
        " * UNIFIED ARMY SAFETY: the condition only narrows",
        " * HIVE D2: what this returns in place of the free choice is an offer: setupPatrol checks it and, refused, goes on with tally.free in the same try.\n"
        " * UNIFIED ARMY SAFETY: the condition only narrows",
    ),
    (
        "Node *AIModule::hivePatrolNode(bool scout, int triesLeft)\n",
        "Node *AIModule::hivePatrolNode(bool scout, int triesLeft, HiveCommand::PatrolTally &tally)\n",
    ),
    (
        "\tconst auto t0 = std::chrono::steady_clock::now();\n"
        "\tconst uint64_t seedBefore = RNG::getSeed();\n"
        "\tNode *freeNode = freeChoice();\n",
        "\tfit.refused = &tally.refused;\n"
        "\tconst auto t0 = std::chrono::steady_clock::now();\n"
        "\tconst uint64_t seedBefore = RNG::getSeed();\n"
        "\tNode *freeNode = freeChoice();\n",
    ),
    (
        "\treturn HiveCommand::mode() == 2 && chosen != 0 ? chosen : freeNode;\n",
        "\ttally.asked = true;\n"
        "\ttally.tries++;\n"
        "\ttally.freeNone += freeNode == 0 ? 1 : 0;\n"
        "\ttally.free = freeNode;\n"
        "\ttally.offer = HiveCommand::mode() == 2 && chosen != 0 && chosen != freeNode;\n"
        "\ttally.offers += tally.offer ? 1 : 0;\n"
        "\treturn tally.offer ? chosen : freeNode;\n",
    ),
])

sub("Battlescape/HiveCommand.h", [
    (
        "\tconst std::vector<int> *reach = 0;\n"
        "\tmutable int accepted = 0;\n",
        "\tconst std::vector<int> *reach = 0;\n"
        "\tconst std::vector<const Node *> *refused = 0; // HIVE D2: offers this think's own search has refused\n"
        "\tmutable int accepted = 0;\n",
    ),
    (
        "/// The flag: 0 off, 1 shadow, 2 active.\n",
        "/// HIVE D2: what one think's tries came to. tries == freeChecked + freeNone + taken: an offer that did not end the choice is not a try.\n"
        "struct PatrolTally\n"
        "{\n"
        "\tstd::vector<const Node *> refused;\n"
        "\tNode *free = 0;\n"
        "\tbool offer = false, asked = false;\n"
        "\tint tries = 0, freeChecked = 0, freeNone = 0, offers = 0, refusals = 0, taken = 0;\n"
        "};\n\n"
        "/// The flag: 0 off, 1 shadow, 2 active.\n",
    ),
    (
        "void perfPath(long long ns, bool failed);\n",
        "void perfPath(long long ns, bool failed);\n"
        "/// HIVE D2: the soldier's own search has no path to the offered node; the try goes on with the free one.\n"
        "void offerRefused(SavedBattleGame *save, BattleUnit *unit, const Node *offer, PatrolTally &tally, int tryNo, long long ns, int expanded, bool seedMoved);\n"
        "/// HIVE D2: the soldier's own search has a path to the offered node.\n"
        "void offerTaken(PatrolTally &tally, long long ns);\n"
        "/// HIVE D2: a think's choice is over: writes what its tries came to, and whether the fields it took served an offer.\n"
        "void patrolEnded(SavedBattleGame *save, BattleUnit *unit, const PatrolTally &tally, const Node *result);\n",
    ),
])

sub("Battlescape/HiveCommand.cpp", [
    (
        "\tstd::map<int, int> fellBack, dropped; // unit -> the turn\n",
        "\tstd::map<int, int> fellBack, dropped; // unit -> the turn\n"
        "\tstd::map<int, std::map<uint64_t, int> > fieldStates; // HIVE D2, only written: unit -> the state a field was made for -> the turn\n",
    ),
    (
        "\tint intentFloods = 0, searches = 0, paths = 0, pathFails = 0;\n",
        "\tint intentFloods = 0, searches = 0, paths = 0, pathFails = 0;\n"
        "\t// HIVE D2: offers, and the fields that repeat one or served no offer; only written\n"
        "\tlong long offerRefusedNs = 0, maxOfferRefusedNs = 0, offerTakenNs = 0, repeatFloodNs = 0, repeatTurnFloodNs = 0, unusedFloodNs = 0, pendingFloodNs = 0, sigNs = 0;\n"
        "\tint offersMade = 0, offersRefused = 0, offersTaken = 0, seedMoved = 0, repeatFloods = 0, repeatTurnFloods = 0, unusedFloods = 0, pendingFloods = 0;\n",
    ),
    (
        "/// The unit's field: once a turn from where it stands, or anew when something said the old one was wrong.\n",
        "/// HIVE D2, only written: all a field can depend on: the unit, where everyone is and who has been seen, the map with its fire and smoke.\n"
        "uint64_t fieldState(SavedBattleGame *save, const BattleUnit *u)\n"
        "{\n"
        "\tuint64_t h = 1469598103934665603ULL;\n"
        "\tconst auto mix = [&h](uint64_t v) { h = (h ^ v) * 1099511628211ULL; };\n"
        "\tmix(u->getId());\n"
        "\tmix(u->getUnitsSpottedThisTurn().size());\n"
        "\tfor (auto *o : *save->getUnits())\n"
        "\t{\n"
        "\t\tconst Position p = o->getPosition();\n"
        "\t\tmix(o->getId());\n"
        "\t\tmix(o->isOut() ? 1 : 0);\n"
        "\t\tmix(p.x + p.y * 1000 + p.z * 1000000);\n"
        "\t\tmix(o->getTurnsSinceSpottedByFaction(FACTION_HOSTILE) == 0 ? 1 : 0);\n"
        "\t}\n"
        "\tfor (int i = 0; i < save->getMapSizeXYZ(); ++i)\n"
        "\t{\n"
        "\t\tTile *t = save->getTile(i);\n"
        "\t\tfor (int part = 0; part < O_MAX; ++part)\n"
        "\t\t{\n"
        "\t\t\tmix((uint64_t)(uintptr_t)t->getMapData((TilePart)part));\n"
        "\t\t}\n"
        "\t\tmix(t->getFire() * 100 + t->getSmoke());\n"
        "\t}\n"
        "\treturn h;\n"
        "}\n\n"
        "/// The unit's field: once a turn from where it stands, or anew when something said the old one was wrong.\n",
    ),
    (
        "\thq.maxFloodNs = std::max(hq.maxFloodNs, floodNs);\n",
        "\thq.maxFloodNs = std::max(hq.maxFloodNs, floodNs);\n"
        "\t{\n"
        "\t\tconst auto s0 = std::chrono::steady_clock::now();\n"
        "\t\tauto &states = hq.fieldStates[u->getId()];\n"
        "\t\tconst uint64_t state = fieldState(save, u);\n"
        "\t\tconst auto was = states.find(state);\n"
        "\t\tif (was != states.end())\n"
        "\t\t{\n"
        "\t\t\thq.repeatFloods++;\n"
        "\t\t\thq.repeatFloodNs += floodNs;\n"
        "\t\t\tif (was->second == save->getTurn())\n"
        "\t\t\t{\n"
        "\t\t\t\thq.repeatTurnFloods++;\n"
        "\t\t\t\thq.repeatTurnFloodNs += floodNs;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tstates[state] = save->getTurn();\n"
        "\t\thq.sigNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - s0).count();\n"
        "\t}\n",
    ),
    (
        "<< \" paths=\" << hq.paths << \" pathFails=\" << hq.pathFails << \" pathUs=\" << hq.pathNs / 1000 << \" thinks=\" << hq.thinks << \" thinkUs=\" << hq.thinkNs / 1000;\n",
        "<< \" paths=\" << hq.paths << \" pathFails=\" << hq.pathFails << \" pathUs=\" << hq.pathNs / 1000 << \" thinks=\" << hq.thinks << \" thinkUs=\" << hq.thinkNs / 1000\n"
        "\t\t<< \" offers=\" << hq.offersMade << \" offersRefused=\" << hq.offersRefused << \" offersTaken=\" << hq.offersTaken << \" refusedUs=\" << hq.offerRefusedNs / 1000 << \" maxRefusedUs=\" << hq.maxOfferRefusedNs / 1000 << \" takenUs=\" << hq.offerTakenNs / 1000 << \" seedMoved=\" << hq.seedMoved\n"
        "\t\t<< \" repeatFloods=\" << hq.repeatFloods << \" repeatUs=\" << hq.repeatFloodNs / 1000 << \" repeatTurnFloods=\" << hq.repeatTurnFloods << \" repeatTurnUs=\" << hq.repeatTurnFloodNs / 1000 << \" unusedFloods=\" << hq.unusedFloods << \" unusedUs=\" << hq.unusedFloodNs / 1000 << \" sigUs=\" << hq.sigNs / 1000;\n",
    ),
    (
        "\thq.intentFloods = hq.searches = hq.paths = hq.pathFails = 0;\n",
        "\thq.intentFloods = hq.searches = hq.paths = hq.pathFails = 0;\n"
        "\thq.offerRefusedNs = hq.maxOfferRefusedNs = hq.offerTakenNs = hq.repeatFloodNs = hq.repeatTurnFloodNs = hq.unusedFloodNs = hq.pendingFloodNs = hq.sigNs = 0;\n"
        "\thq.offersMade = hq.offersRefused = hq.offersTaken = hq.seedMoved = hq.repeatFloods = hq.repeatTurnFloods = hq.unusedFloods = hq.pendingFloods = 0;\n",
    ),
    (
        "bool NodeFit::accepts(const Node *n) const\n"
        "{\n",
        "bool NodeFit::accepts(const Node *n) const\n"
        "{\n"
        "\tif (refused && std::find(refused->begin(), refused->end(), n) != refused->end()) return false;\n",
    ),
    (
        "\t\thq.intentFloodNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();\n",
        "\t\tconst long long ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();\n"
        "\t\thq.intentFloodNs += ns;\n"
        "\t\thq.pendingFloods += hq.floods - before;\n"
        "\t\thq.pendingFloodNs += ns;\n",
    ),
    (
        "bool dropKept(SavedBattleGame *save, BattleUnit *unit, Node *kept)\n",
        "void offerRefused(SavedBattleGame *save, BattleUnit *unit, const Node *offer, PatrolTally &tally, int tryNo, long long ns, int expanded, bool seedMoved)\n"
        "{\n"
        "\tconst int turn = save->getTurn(), id = unit->getId();\n"
        "\ttally.refused.push_back(offer);\n"
        "\ttally.refusals++;\n"
        "\thq.offersMade++;\n"
        "\thq.offersRefused++;\n"
        "\thq.offerRefusedNs += ns;\n"
        "\thq.maxOfferRefusedNs = std::max(hq.maxOfferRefusedNs, ns);\n"
        "\thq.seedMoved += seedMoved ? 1 : 0;\n"
        "\tLog(LOG_INFO) << \"[HIVEUA] event=OFFER_REFUSED turn=\" << turn << \" unit=\" << id << \" try=\" << tryNo << \" at=\" << pos(unit->getPosition()) << \" offer=\" << pos(const_cast<Node *>(offer)->getPosition())\n"
        "\t\t<< \" free=\" << (tally.free ? pos(tally.free->getPosition()) : std::string(\"(-1,-1,-1)\")) << \" expanded=\" << expanded << \" us=\" << ns / 1000 << \" seed_moved=\" << (seedMoved ? 1 : 0);\n"
        "\thq.fellBack[id] = turn;\n"
        "\tif (tally.free)\n"
        "\t{\n"
        "\t\tChoice &c = hq.choices[id];\n"
        "\t\tc.node = tally.free->getPosition();\n"
        "\t\tc.changed = false;\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\thq.choices.erase(id);\n"
        "\t}\n"
        "}\n\n"
        "void offerTaken(PatrolTally &tally, long long ns)\n"
        "{\n"
        "\ttally.taken++;\n"
        "\thq.offersMade++;\n"
        "\thq.offersTaken++;\n"
        "\thq.offerTakenNs += ns;\n"
        "}\n\n"
        "void patrolEnded(SavedBattleGame *save, BattleUnit *unit, const PatrolTally &tally, const Node *result)\n"
        "{\n"
        "\tif (tally.taken == 0)\n"
        "\t{\n"
        "\t\thq.unusedFloods += hq.pendingFloods;\n"
        "\t\thq.unusedFloodNs += hq.pendingFloodNs;\n"
        "\t}\n"
        "\thq.pendingFloods = 0;\n"
        "\thq.pendingFloodNs = 0;\n"
        "\tLog(LOG_INFO) << \"[HIVEUA] event=PATROLEND turn=\" << save->getTurn() << \" unit=\" << unit->getId() << \" at=\" << pos(unit->getPosition()) << \" tries=\" << tally.tries << \" free_checked=\" << tally.freeChecked << \" free_none=\" << tally.freeNone\n"
        "\t\t<< \" offers=\" << tally.offers << \" refused=\" << tally.refusals << \" taken=\" << tally.taken << \" end=\" << (result ? pos(const_cast<Node *>(result)->getPosition()) : std::string(\"none\")) << \" tu=\" << unit->getTimeUnits();\n"
        "}\n\n"
        "bool dropKept(SavedBattleGame *save, BattleUnit *unit, Node *kept)\n",
    ),
])
print("patched")
