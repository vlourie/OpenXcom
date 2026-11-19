// clang on Windows only (tests/CMakeLists.txt): the YAML library of the game asks for <alloca.h> there
// (its C4_MINGW is for GCC alone), and MinGW keeps alloca in <malloc.h>
#include <malloc.h>
