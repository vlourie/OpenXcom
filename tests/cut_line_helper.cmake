# cut_line_helper.cmake: cuts calculateLineHelper() out of the game's src/Battlescape/TileEngine.cpp into a file the
# vertical trace test includes - the test runs the game's own text, not a copy that could drift from it.
#   cmake -DIN=<TileEngine.cpp> -DOUT=<calc_line_helper.inc> -P cut_line_helper.cmake
file ( READ "${IN}" text )
string ( FIND "${text}" "template<typename FuncNewPosition, typename FuncDrift>" from )
string ( FIND "${text}" "bool calculateParabolaHelper" next )
if ( from EQUAL -1 OR next EQUAL -1 OR NOT next GREATER from )
  message ( FATAL_ERROR "calculateLineHelper() was not found in ${IN} where the test expects it: look at tests/cut_line_helper.cmake" )
endif ()
math ( EXPR length "${next} - ${from}" )
string ( SUBSTRING "${text}" ${from} ${length} cut )
# the cut ends with the "template<...>" line of the next function: drop it
string ( FIND "${cut}" "template<typename FuncNewPosition>" tail REVERSE )
if ( tail EQUAL -1 )
  message ( FATAL_ERROR "the end of calculateLineHelper() was not found in ${IN}" )
endif ()
string ( SUBSTRING "${cut}" 0 ${tail} cut )
string ( FIND "${cut}" "bool calculateLineHelper(" named )
if ( named EQUAL -1 )
  message ( FATAL_ERROR "the text cut out of ${IN} is not calculateLineHelper()" )
endif ()
file ( WRITE "${OUT}" "${cut}" )
