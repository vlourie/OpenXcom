"""SCD first compile fixes. arg: cpp"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
s = s.replace("m.noLos = r->getNoLOSAccuracyPenalty(bs->save->getMod());", "m.noLos = r->getNoLOSAccuracyPenalty(const_cast<Mod*>(bs->save->getMod()));")
s = s.replace("std::set<Position> claimed;", "std::set<int> claimed;")
s = s.replace("claimed.count(c)", "claimed.count(ActionGenerator::pack(c))")
s = s.replace("!claimed.count(memo.plan.cell)", "!claimed.count(ActionGenerator::pack(memo.plan.cell))")
s = s.replace("planner.claimed.insert(plan.cell);", "planner.claimed.insert(ActionGenerator::pack(plan.cell));")
p.write_text(s, encoding="utf-8")
