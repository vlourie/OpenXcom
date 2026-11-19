# Included from src/CMakeLists.txt when OXCE_PARSERS_TEST names this folder: the game's executable gets the tests of the
# data parsers (parsers_test.cpp) in front of its main(). Without "--parsers-test" as the first argument it is the game
# as it is. A build of its own (see README.md here), never the player's.
# not to be taken for the game: the file is named after what it is (run.py starts it with SDL's dummy drivers, no window)
set_target_properties ( openxcom PROPERTIES OUTPUT_NAME oxce_parsers_test )
target_sources ( openxcom PRIVATE "${CMAKE_CURRENT_LIST_DIR}/parsers_test.cpp" )
# SDL renames main() to SDL_main(); the game's one becomes oxce_game_main(), the test's one takes its place
set_property ( SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp" APPEND PROPERTY COMPILE_DEFINITIONS SDL_main=oxce_game_main )
set_property ( SOURCE "${CMAKE_CURRENT_LIST_DIR}/parsers_test.cpp" APPEND PROPERTY INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}" )
