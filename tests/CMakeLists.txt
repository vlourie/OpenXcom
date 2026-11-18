# The tests of OXCE-HD that need no data of the game: a project of its own, the game's build does not know it.
#   cmake -S tests -B build-tests -G Ninja && ninja -C build-tests && ctest --test-dir build-tests --output-on-failure
# With sanitizers: -DHD_TEST_SANITIZE=address,undefined (anywhere clang or gcc has them) or =thread (Linux).
cmake_minimum_required ( VERSION 3.10 )
project ( OxceHdTests CXX )

set ( CMAKE_CXX_STANDARD 17 )
set ( CMAKE_CXX_STANDARD_REQUIRED ON )
if ( NOT CMAKE_BUILD_TYPE )
  set ( CMAKE_BUILD_TYPE RelWithDebInfo )
endif ()
set ( HD_TEST_SANITIZE "" CACHE STRING "Sanitizers for the tests: address,undefined or thread" )

find_package ( SDL REQUIRED )
find_package ( Threads REQUIRED )
enable_testing ()

add_executable ( hdworkers_test hdworkers_test.cpp stubs.cpp ../src/Engine/HdWorkers.cpp )
# (the options' header takes the YAML library of the game: headers only, nothing of it is linked)
target_include_directories ( hdworkers_test PRIVATE ${SDL_INCLUDE_DIR} ../libs/rapidyaml )
if ( WIN32 AND CMAKE_CXX_COMPILER_ID MATCHES "Clang" )
  target_include_directories ( hdworkers_test SYSTEM PRIVATE shim )
endif ()
target_link_libraries ( hdworkers_test PRIVATE Threads::Threads )
if ( WIN32 )
  target_link_libraries ( hdworkers_test PRIVATE psapi )
endif ()
# the answer of HdWorkers::run() left unlooked at is an error here as it is in the game (src/CMakeLists.txt)
target_compile_options ( hdworkers_test PRIVATE -Wall -Wextra -Wno-unused-parameter -Werror=unused-result )
if ( HD_TEST_SANITIZE )
  target_compile_options ( hdworkers_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} -fno-omit-frame-pointer -g )
  target_link_options ( hdworkers_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} )
endif ()
add_test ( NAME hdworkers COMMAND hdworkers_test )
set_tests_properties ( hdworkers PROPERTIES TIMEOUT 300 )

# what the video driver tells of its errors from threads of its own (a header only, no video card needed)
add_executable ( hdgputold_test hdgputold_test.cpp )
target_link_libraries ( hdgputold_test PRIVATE Threads::Threads )
target_compile_options ( hdgputold_test PRIVATE -Wall -Wextra )
if ( HD_TEST_SANITIZE )
  target_compile_options ( hdgputold_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} -fno-omit-frame-pointer -g )
  target_link_options ( hdgputold_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} )
endif ()
add_test ( NAME hdgputold COMMAND hdgputold_test )
set_tests_properties ( hdgputold PROPERTIES TIMEOUT 300 )

# the rays of the line of fire with the target straight above or below the shooter (audit AUDIT-04 9): the game's own
# calculateLineHelper(), cut out of TileEngine.cpp when the test is built. A test only - the game is not changed
add_custom_command ( OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/calc_line_helper.inc
  COMMAND ${CMAKE_COMMAND} -DIN=${CMAKE_CURRENT_SOURCE_DIR}/../src/Battlescape/TileEngine.cpp
    -DOUT=${CMAKE_CURRENT_BINARY_DIR}/calc_line_helper.inc -P ${CMAKE_CURRENT_SOURCE_DIR}/cut_line_helper.cmake
  DEPENDS ../src/Battlescape/TileEngine.cpp cut_line_helper.cmake )
add_executable ( vertical_trace_test vertical_trace_test.cpp ${CMAKE_CURRENT_BINARY_DIR}/calc_line_helper.inc )
target_include_directories ( vertical_trace_test PRIVATE ${CMAKE_CURRENT_BINARY_DIR} )
if ( HD_TEST_SANITIZE )
  target_compile_options ( vertical_trace_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} -fno-omit-frame-pointer -g )
  target_link_options ( vertical_trace_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} )
endif ()
# the rays that have no undefined behaviour: the same answer everywhere
add_test ( NAME vertical_trace_plain COMMAND vertical_trace_test plain )
# the side rays (target + INT_MIN): abs(INT_MIN) and a signed overflow, undefined behaviour that is OPEN (the fix
# touches the battle's mechanics and waits for a word).
#   - under the undefined-behaviour sanitizer the run must be stopped by it: WILL_FAIL. The day the trace is made
#     defined this test turns red - take WILL_FAIL away then;
#   - with the game's compiler (gcc) the rays must be the ones recorded on 18.11.2026: a fix must not move them;
#   - with clang and no sanitizer the test is not played: there the answer depends on the optimization (-O2 sends
#     the ray along the floor instead of up - measured, docs/QA/audit4-check-2026-11-18.md), there is nothing to hold.
if ( HD_TEST_SANITIZE MATCHES "undefined" )
  add_test ( NAME vertical_trace_intmin COMMAND vertical_trace_test intmin )
  set_tests_properties ( vertical_trace_intmin PROPERTIES WILL_FAIL TRUE
    ENVIRONMENT "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1" )
elseif ( CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND NOT HD_TEST_SANITIZE )
  add_test ( NAME vertical_trace_intmin COMMAND vertical_trace_test intmin )
endif ()
