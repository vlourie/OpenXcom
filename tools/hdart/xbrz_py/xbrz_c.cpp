// Тонкая обёртка xBRZ движка (src/Engine/Scalers/xbrz.cpp) для ctypes: тот же фильтр, что игра
// применяет к классическим спрайтам, превращает пиксельные лесенки в ровные диагонали перед SDXL.
// Сборка: tools/hdart/xbrz_py/build.cmd
#include <cstdint>
#include "../../../src/Engine/Scalers/xbrz.h"

extern "C" __declspec(dllexport) void xbrz_scale(int factor, const uint32_t* src, uint32_t* dst, int w, int h)
{
	xbrz::scale((size_t)factor, src, dst, w, h, xbrz::ARGB);
}
