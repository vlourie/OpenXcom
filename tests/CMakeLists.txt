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

# the world on the card after the driver's errors: made anew, rests, off (a header only, no video card needed)
add_executable ( hdgputrust_test hdgputrust_test.cpp )
target_compile_options ( hdgputrust_test PRIVATE -Wall -Wextra )
if ( HD_TEST_SANITIZE )
  target_compile_options ( hdgputrust_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} -fno-omit-frame-pointer -g )
  target_link_options ( hdgputrust_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} )
endif ()
add_test ( NAME hdgputrust COMMAND hdgputrust_test )

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
# the side rays (target + INT_MIN): they were abs(INT_MIN) and a signed overflow - undefined, and clang -O2 sent the
# ray along the floor instead of up. The arithmetic of the trace wraps now as x86 gcc always made it, so the rays
# recorded with the game's compiler on 18.11.2026 (before the fix) must come out under every compiler, and the
# undefined-behaviour sanitizer must have nothing to say (it stops the run if it has)
add_test ( NAME vertical_trace_intmin COMMAND vertical_trace_test intmin )
set_tests_properties ( vertical_trace_intmin PROPERTIES ENVIRONMENT "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1" )

# the Adlib player of the game on damaged tracks made in the test itself (AUDIT-05 G): must end without a report of
# the sanitizers. The music of the original game against another tree, and random damage: tests/adlib/run.py
add_executable ( adlib_test adlib/adlib_test.cpp ../src/Engine/Adlib/adlplayer.cpp ../src/Engine/Adlib/fmopl.cpp )
target_include_directories ( adlib_test PRIVATE ../src/Engine/Adlib )
if ( HD_TEST_SANITIZE )
  target_compile_options ( adlib_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} -fno-omit-frame-pointer -g )
  target_link_options ( adlib_test PRIVATE -fsanitize=${HD_TEST_SANITIZE} )
endif ()
add_test ( NAME adlib_damaged COMMAND adlib_test bad )
set_tests_properties ( adlib_damaged PROPERTIES ENVIRONMENT "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1" )

# the crash record and the trace of an exception (Windows, 64 bit): every mode is a process that crashes on purpose,
# tests/crashtrace/run.py checks what it leaves. Never built with the sanitizers: they take the crash for themselves
if ( WIN32 AND CMAKE_SIZEOF_VOID_P EQUAL 8 )
  find_package ( Python3 COMPONENTS Interpreter )
  add_executable ( crashtrace_test crashtrace/crashtrace_test.cpp ../src/Engine/CrashTrace.cpp )
  target_link_libraries ( crashtrace_test PRIVATE dbghelp Threads::Threads )
  # as the game is linked: the names of the frames come from the table of exports
  target_link_options ( crashtrace_test PRIVATE -Wl,--export-all-symbols -s )
  if ( Python3_FOUND AND NOT HD_TEST_SANITIZE )
    add_test ( NAME crashtrace COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/crashtrace/run.py
      --exe $<TARGET_FILE:crashtrace_test> --work ${CMAKE_CURRENT_BINARY_DIR}/crashtrace_work )
  endif ()
endif ()
