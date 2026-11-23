"""UNIFIED ARMY SAFETY: to a clean copy of hive/ua/tree. The patrol's task searches only by the kind of search the unit's own rules give it (no map-wide step over scout=false), a condition never opens the engine's big-unit fallback, and the time of each part is written. No behaviour besides the node. Run once on a fresh copy."""
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "hive" / "us" / "tree" / "src"


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


sub("Savegame/SavedBattleGame.cpp", [(
    "\t\t\treturn getPatrolNode(true, unit, fromNode, fit); // move dammit\n",
    "\t\t\t// UNIFIED ARMY SAFETY (bench): a task's condition emptying the list is not a big unit with nowhere to go; what the rule opens here, it opens for the unit's own free choice only\n"
    "\t\t\tif (fit) return 0;\n"
    "\t\t\treturn getPatrolNode(true, unit, fromNode); // move dammit\n",
)])

sub("Battlescape/AIModule.cpp", [
    (
        "\t\t\t_save->getPathfinding()->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);\n"
        "\t\t\tif (_save->getPathfinding()->getStartDirection() == -1)\n"
        "\t\t\t{\n"
        "\t\t\t\tif (oxceFixes && !_toNode->isAllocated())\n",
        "\t\t\tconst auto hiveT0 = std::chrono::steady_clock::now();\n"
        "\t\t\t_save->getPathfinding()->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);\n"
        "\t\t\tHiveCommand::perfPath(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - hiveT0).count(), _save->getPathfinding()->getStartDirection() == -1);\n"
        "\t\t\tif (_save->getPathfinding()->getStartDirection() == -1)\n"
        "\t\t\t{\n"
        "\t\t\t\tif (oxceFixes && !_toNode->isAllocated())\n",
    ),
    (
        " * only thing the task changes is the node, and the log can say what the soldier would have done without it. The last two tries of the five carry no condition.\n",
        " * only thing the task changes is the node, and the log can say what the soldier would have done without it. The last two tries of the five carry no condition.\n"
        " * UNIFIED ARMY SAFETY: the condition only narrows the very search the engine gives this unit: scout=false stays among the node's links, and the engine's own fallback to the other kind of search is the free choice's alone.\n",
    ),
    (
        "\tconst uint64_t seedBefore = RNG::getSeed();\n"
        "\tNode *freeNode = freeChoice();\n"
        "\tconst uint64_t seedAfter = RNG::getSeed();\n",
        "\tconst auto t0 = std::chrono::steady_clock::now();\n"
        "\tconst uint64_t seedBefore = RNG::getSeed();\n"
        "\tNode *freeNode = freeChoice();\n"
        "\tconst uint64_t seedAfter = RNG::getSeed();\n"
        "\tconst auto t1 = std::chrono::steady_clock::now();\n",
    ),
    (
        "\t\t\tbool mapWide = false;\n"
        "\t\t\tif (HiveCommand::fitRung(fit, r, mapWide))\n"
        "\t\t\t{\n"
        "\t\t\t\tchosen = _save->getPatrolNode(mapWide || scout, _unit, _fromNode, &fit);\n",
        "\t\t\tif (HiveCommand::fitRung(fit, r))\n"
        "\t\t\t{\n"
        "\t\t\t\tchosen = _save->getPatrolNode(scout, _unit, _fromNode, &fit);\n",
    ),
    (
        "\tHiveCommand::patrolChosen(_save, _unit, fit, rung, 5 - triesLeft, freeNode, chosen);\n",
        "\tHiveCommand::perfSearch(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count(), std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t1).count());\n"
        "\tHiveCommand::patrolChosen(_save, _unit, fit, rung, 5 - triesLeft, freeNode, chosen, scout, _fromNode);\n",
    ),
])

sub("Battlescape/HiveCommand.h", [
    (
        "/// The steps of the choice, in their order: not yet visited inside the place, by the unit's own kind of search and then all over the map; the same with visited ones; nearer the place than the unit stands, for one outside it.\n"
        "const int FIT_RUNGS = 5;\n",
        "/// The steps of the choice, in their order, all by the unit's own kind of search: not yet visited inside the place; visited ones too; nearer the place than the unit stands, for one outside it.\n"
        "const int FIT_RUNGS = 3;\n",
    ),
    (
        "/// Sets the fit for one step of the choice; false, the step does not apply. mapWide: the search of this step goes over the whole map.\n"
        "bool fitRung(NodeFit &fit, int rung, bool &mapWide);\n",
        "/// Sets the fit for one step of the choice; false, the step does not apply.\n"
        "bool fitRung(NodeFit &fit, int rung);\n",
    ),
    (
        "/// What came of the choice, for the log and the feedback: free is what the unit would have taken with no task, chosen what the task allowed (0: nothing, the free one stands).\n"
        "void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen);\n",
        "/// What came of the choice, for the log and the feedback: free is what the unit would have taken with no task, chosen what the task allowed (0: nothing, the free one stands). scout: the unit's own kind of search.\n"
        "void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen, bool scout, const Node *fromNode);\n"
        "/// The time of one choice: the free search and the steps of the condition. Written, nothing more.\n"
        "void perfSearch(long long freeNs, long long stepsNs);\n"
        "/// The time of one path check of a patrol's node and whether it failed. Written, nothing more.\n"
        "void perfPath(long long ns, bool failed);\n",
    ),
])

sub("Battlescape/HiveCommand.cpp", [
    (
        "\tlong long thinkNs = 0, floodNs = 0;\n",
        "\tlong long thinkNs = 0, floodNs = 0;\n"
        "\t// UNIFIED ARMY SAFETY: where the turn's time goes; only written\n"
        "\tlong long intentFloodNs = 0, maxFloodNs = 0, freeNs = 0, stepsNs = 0, pathNs = 0, maxChoiceNs = 0;\n"
        "\tint intentFloods = 0, searches = 0, paths = 0, pathFails = 0;\n",
    ),
    (
        "\thq.floods++;\n"
        "\thq.floodNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();\n",
        "\thq.floods++;\n"
        "\tconst long long floodNs = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();\n"
        "\thq.floodNs += floodNs;\n"
        "\thq.maxFloodNs = std::max(hq.maxFloodNs, floodNs);\n",
    ),
    (
        "\tLog(LOG_INFO) << \"[HIVEPERF] turn=\" << turn << \" phase=turn floods=\" << hq.floods << \" floodUs=\" << hq.floodNs / 1000;\n",
        "\tLog(LOG_INFO) << \"[HIVEPERF] turn=\" << turn << \" phase=turn floods=\" << hq.floods << \" floodUs=\" << hq.floodNs / 1000 << \" maxFloodUs=\" << hq.maxFloodNs / 1000\n"
        "\t\t<< \" intentFloods=\" << hq.intentFloods << \" intentFloodUs=\" << hq.intentFloodNs / 1000 << \" searches=\" << hq.searches << \" freeUs=\" << hq.freeNs / 1000 << \" stepsUs=\" << hq.stepsNs / 1000 << \" maxChoiceUs=\" << hq.maxChoiceNs / 1000\n"
        "\t\t<< \" paths=\" << hq.paths << \" pathFails=\" << hq.pathFails << \" pathUs=\" << hq.pathNs / 1000 << \" thinks=\" << hq.thinks << \" thinkUs=\" << hq.thinkNs / 1000;\n",
    ),
    (
        "\thq.floods = 0;\n"
        "\thq.floodNs = 0;\n",
        "\thq.floods = 0;\n"
        "\thq.floodNs = 0;\n"
        "\thq.intentFloodNs = hq.maxFloodNs = hq.freeNs = hq.stepsNs = hq.pathNs = hq.maxChoiceNs = 0;\n"
        "\thq.intentFloods = hq.searches = hq.paths = hq.pathFails = 0;\n",
    ),
    (
        "\tif (!taskOf(save, unit, fit)) return false;\n"
        "\tfit.reach = &fieldOf(save, unit).node;\n"
        "\treturn true;\n",
        "\tif (!taskOf(save, unit, fit)) return false;\n"
        "\tconst auto t0 = std::chrono::steady_clock::now();\n"
        "\tconst int before = hq.floods;\n"
        "\tfit.reach = &fieldOf(save, unit).node;\n"
        "\tif (hq.floods != before)\n"
        "\t{\n"
        "\t\thq.intentFloods += hq.floods - before;\n"
        "\t\thq.intentFloodNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();\n"
        "\t}\n"
        "\treturn true;\n",
    ),
    (
        "bool fitRung(NodeFit &fit, int rung, bool &mapWide)\n"
        "{\n"
        "\tfit.accepted = 0;\n"
        "\tfit.closer = rung == 4;\n"
        "\tfit.skipVisited = rung <= 1;\n"
        "\tmapWide = rung == 1 || rung >= 3;\n"
        "\treturn rung == 4 ? fit.here > fit.radius : rung <= 1 ? fit.hasVisited : true;\n"
        "}\n",
        "bool fitRung(NodeFit &fit, int rung)\n"
        "{\n"
        "\tfit.accepted = 0;\n"
        "\tfit.closer = rung == 2;\n"
        "\tfit.skipVisited = rung == 0;\n"
        "\treturn rung == 2 ? fit.here > fit.radius : rung == 0 ? fit.hasVisited : true;\n"
        "}\n"
        "\n"
        "void perfSearch(long long freeNs, long long stepsNs)\n"
        "{\n"
        "\thq.searches++;\n"
        "\thq.freeNs += freeNs;\n"
        "\thq.stepsNs += stepsNs;\n"
        "\thq.maxChoiceNs = std::max(hq.maxChoiceNs, freeNs + stepsNs);\n"
        "}\n"
        "\n"
        "void perfPath(long long ns, bool failed)\n"
        "{\n"
        "\tif (mode() == 0) return;\n"
        "\thq.paths++;\n"
        "\thq.pathFails += failed ? 1 : 0;\n"
        "\thq.pathNs += ns;\n"
        "}\n",
    ),
    (
        "void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen)\n"
        "{\n",
        "void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen, bool scout, const Node *fromNode)\n"
        "{\n"
        "\tconst auto linked = [save, fromNode](const Node *n)\n"
        "\t{\n"
        "\t\tif (!n || !fromNode) return false;\n"
        "\t\tfor (int l : *const_cast<Node *>(fromNode)->getNodeLinks())\n"
        "\t\t{\n"
        "\t\t\tif (l >= 1 && l < (int)save->getNodes()->size() && save->getNodes()->at(l) == n) return true;\n"
        "\t\t}\n"
        "\t\treturn false;\n"
        "\t};\n",
    ),
    (
        "\t\t<< \" free_inside=\" << (inside(free) ? 1 : 0) << \" free_closer=\" << (closer(free) ? 1 : 0) << \" fallback=\" << (chosen ? 0 : 1) << \" tu=\" << unit->getTimeUnits();\n",
        "\t\t<< \" free_inside=\" << (inside(free) ? 1 : 0) << \" free_closer=\" << (closer(free) ? 1 : 0) << \" fallback=\" << (chosen ? 0 : 1) << \" tu=\" << unit->getTimeUnits()\n"
        "\t\t<< \" scout=\" << (scout ? 1 : 0) << \" chosen_linked=\" << (linked(chosen) ? 1 : 0) << \" free_linked=\" << (linked(free) ? 1 : 0) << \" from=\" << (fromNode ? pos(const_cast<Node *>(fromNode)->getPosition()) : std::string(\"-\")) << \" from_rank=\" << (fromNode ? const_cast<Node *>(fromNode)->getRank() : -1);\n",
    ),
])
print("patched")
