/*
 * Copyright 2010-2026 OpenXcom Developers.
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */
#include "HdGpu.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include "Logger.h"
#include "Options.h"

#ifdef _WIN32
// laptops with two video cards give a process the built-in one unless the exe asks for the discrete one
// (NVIDIA Optimus, AMD PowerXpress); read by the drivers at start, only matters once a GL context is made
extern "C"
{
__declspec(dllexport) unsigned long NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;
}
#endif

#include "HdGpuGl.h"
#include "HdGpuCanvas.h"

namespace OpenXcom
{

HdGpu &HdGpu::instance()
{
	static HdGpu gpu;
	return gpu;
}

#ifdef __NO_OPENGL

bool HdGpu::load() { return false; }
bool HdGpu::build() { return false; }
bool HdGpu::setup(int, int) { Log(LOG_ERROR) << "HD GPU: built without OpenGL"; return false; }
void HdGpu::release() {}
void HdGpu::upload(const SDL_Surface *) {}
void HdGpu::present(int, int, int, int, int, int, bool) {}
bool HdGpu::readBack(SDL_Surface *) { return false; }

#else

namespace hdgl
{
Functions gl;
}

namespace
{

using hdgl::gl;

template <typename F>
bool find(F &fn, const char *name)
{
	void *p = SDL_GL_GetProcAddress(name);
	std::memcpy(&fn, &p, sizeof(p));
	return p != nullptr;
}

const char *glText(GLenum what)
{
	const GLubyte *s = glGetString(what);
	return s ? (const char *)s : "?";
}

// one quad over the viewport out of four vertex numbers (no vertex buffer); texture row 0 is the world's top row
const char *const VERTEX_SHADER =
	"#version 330\n"
	"out vec2 uv;\n"
	"void main()\n"
	"{\n"
	"	vec2 p = vec2(gl_VertexID & 1, gl_VertexID >> 1);\n"
	"	uv = vec2(p.x, 1.0 - p.y);\n"
	"	gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);\n"
	"}\n";
// the world is opaque RGB: its alpha byte is not kept by the drawing code
const char *const FRAGMENT_SHADER =
	"#version 330\n"
	"uniform sampler2D world;\n"
	"in vec2 uv;\n"
	"out vec4 color;\n"
	"void main()\n"
	"{\n"
	"	color = vec4(texture(world, uv).rgb, 1.0);\n"
	"}\n";

GLuint compile(GLenum type, const char *source)
{
	GLuint shader = gl.CreateShader(type);
	gl.ShaderSource(shader, 1, &source, nullptr);
	gl.CompileShader(shader);
	GLint ok = 0;
	gl.GetShaderiv(shader, GL_COMPILE_STATUS, &ok);
	if (!ok)
	{
		char log[1024] = {};
		gl.GetShaderInfoLog(shader, sizeof(log) - 1, nullptr, log);
		Log(LOG_ERROR) << "HD GPU: shader does not compile: " << log;
		gl.DeleteShader(shader);
		return 0;
	}
	return shader;
}

}

GLuint hdgl::program(const char *vertexSource, const char *fragmentSource, const char *what)
{
	GLuint vertex = compile(GL_VERTEX_SHADER, vertexSource);
	GLuint fragment = compile(GL_FRAGMENT_SHADER, fragmentSource);
	if (!vertex || !fragment)
	{
		if (vertex) gl.DeleteShader(vertex);
		if (fragment) gl.DeleteShader(fragment);
		Log(LOG_ERROR) << "HD GPU: no program for " << what;
		return 0;
	}
	GLuint prog = gl.CreateProgram();
	gl.AttachShader(prog, vertex);
	gl.AttachShader(prog, fragment);
	gl.LinkProgram(prog);
	gl.DeleteShader(vertex);
	gl.DeleteShader(fragment);
	GLint ok = 0;
	gl.GetProgramiv(prog, GL_LINK_STATUS, &ok);
	if (!ok)
	{
		char log[1024] = {};
		gl.GetProgramInfoLog(prog, sizeof(log) - 1, nullptr, log);
		Log(LOG_ERROR) << "HD GPU: the program for " << what << " does not link: " << log;
		gl.DeleteProgram(prog);
		return 0;
	}
	return prog;
}

bool HdGpu::load()
{
	bool ok = true;
#define HD_GL_LOAD(ret, name, args) \
	if (!find(gl.name, "gl" #name)) \
	{ \
		Log(LOG_ERROR) << "HD GPU: the driver has no gl" #name; \
		ok = false; \
	}
	HD_GL_FUNCTIONS(HD_GL_LOAD)
#undef HD_GL_LOAD
	find(gl.SwapInterval, "wglSwapIntervalEXT");
	return ok;
}

bool HdGpu::build()
{
	GLuint vertex = compile(GL_VERTEX_SHADER, VERTEX_SHADER);
	GLuint fragment = compile(GL_FRAGMENT_SHADER, FRAGMENT_SHADER);
	if (!vertex || !fragment)
	{
		if (vertex) gl.DeleteShader(vertex);
		if (fragment) gl.DeleteShader(fragment);
		return false;
	}
	_program = gl.CreateProgram();
	gl.AttachShader(_program, vertex);
	gl.AttachShader(_program, fragment);
	gl.LinkProgram(_program);
	gl.DeleteShader(vertex);
	gl.DeleteShader(fragment);
	GLint ok = 0;
	gl.GetProgramiv(_program, GL_LINK_STATUS, &ok);
	if (!ok)
	{
		char log[1024] = {};
		gl.GetProgramInfoLog(_program, sizeof(log) - 1, nullptr, log);
		Log(LOG_ERROR) << "HD GPU: shader program does not link: " << log;
		return false;
	}
	gl.UseProgram(_program);
	gl.Uniform1i(gl.GetUniformLocation(_program, "world"), 0);
	gl.UseProgram(0);
	return true;
}

bool HdGpu::setup(int w, int h)
{
	if (!_fbo)
	{
		const char *version = glText(GL_VERSION);
		int major = 0, minor = 0;
		std::sscanf(version, "%d.%d", &major, &minor);
		Log(LOG_INFO) << "HD GPU: OpenGL " << version << ", " << glText(GL_RENDERER) << " (" << glText(GL_VENDOR) << ")";
		if (major * 10 + minor < 33)
		{
			Log(LOG_ERROR) << "HD GPU: OpenGL 3.3 or newer is needed";
			return false;
		}
		if (!load() || !build())
		{
			release();
			return false;
		}
		gl.GenFramebuffers(1, &_fbo);
		glGenTextures(1, &_texture);
		gl.GenVertexArrays(1, &_vao);
		_w = _h = 0;
		_thread = SDL_ThreadID();
	}
	if (w != _w || h != _h)
	{
		while (glGetError() != GL_NO_ERROR); // whatever was left by the code before
		glBindTexture(GL_TEXTURE_2D, _texture);
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
		_linear = false;
		gl.BindFramebuffer(GL_FRAMEBUFFER, _fbo);
		gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, _texture, 0);
		const GLenum status = gl.CheckFramebufferStatus(GL_FRAMEBUFFER);
		gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
		const GLenum error = glGetError();
		if (status != GL_FRAMEBUFFER_COMPLETE || error != GL_NO_ERROR)
		{
			Log(LOG_ERROR) << "HD GPU: no framebuffer of " << w << "x" << h << " (status 0x" << std::hex << status
				<< ", error 0x" << error << std::dec << ")";
			release();
			return false;
		}
		_w = w;
		_h = h;
		// self test: two pixels up into the texture and back out of the framebuffer, byte for byte
		// (the HD test dump reads the frame this way)
		const Uint32 probe[2] = { 0x80FF4020u, 0x0001FE7Fu };
		Uint32 back[2] = { 0, 0 };
		glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 2, 1, GL_BGRA, GL_UNSIGNED_BYTE, probe);
		gl.BindFramebuffer(GL_READ_FRAMEBUFFER, _fbo);
		glReadPixels(0, 0, 2, 1, GL_BGRA, GL_UNSIGNED_BYTE, back);
		gl.BindFramebuffer(GL_READ_FRAMEBUFFER, 0);
		if (std::memcmp(probe, back, sizeof(probe)) != 0)
		{
			Log(LOG_ERROR) << "HD GPU: the framebuffer does not give back what was put in (" << std::hex
				<< back[0] << " " << back[1] << std::dec << ")";
			release();
			return false;
		}
		Log(LOG_INFO) << "HD GPU: world framebuffer " << w << "x" << h;
	}
	if (gl.SwapInterval)
	{
		gl.SwapInterval(Options::vSyncForOpenGL ? 1 : 0);
	}
	return true;
}

void HdGpu::release()
{
	// the battle canvas's textures and buffers live in the same context
	HdGpuCanvas::instance().release();
	if (_program)
	{
		gl.DeleteProgram(_program);
	}
	if (_vao)
	{
		gl.DeleteVertexArrays(1, &_vao);
	}
	if (_fbo)
	{
		gl.DeleteFramebuffers(1, &_fbo);
	}
	if (_texture)
	{
		glDeleteTextures(1, &_texture);
	}
	_program = _vao = _fbo = _texture = 0;
	_w = _h = 0;
}

void HdGpu::upload(const SDL_Surface *world)
{
	if (!_fbo || world->w != _w || world->h != _h || world->format->BytesPerPixel != 4)
	{
		return;
	}
	glBindTexture(GL_TEXTURE_2D, _texture);
	glPixelStorei(GL_UNPACK_ROW_LENGTH, world->pitch / 4);
	glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, _w, _h, GL_BGRA, GL_UNSIGNED_BYTE, world->pixels);
	glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
}

void HdGpu::present(int displayW, int displayH, int top, int bottom, int left, int right, bool linear)
{
	if (!_fbo)
	{
		return;
	}
	top = std::max(0, top);
	bottom = std::max(0, bottom);
	left = std::max(0, left);
	right = std::max(0, right);
	gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
	glDisable(GL_BLEND);
	glDisable(GL_SCISSOR_TEST);
	glDisable(GL_DEPTH_TEST);
	glViewport(0, 0, displayW, displayH);
	glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT);
	// GL counts rows from the bottom: the bottom band is the viewport's y
	glViewport(left, bottom, std::max(1, displayW - left - right), std::max(1, displayH - top - bottom));
	gl.UseProgram(_program);
	gl.ActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D, _texture);
	if (linear != _linear)
	{
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, linear ? GL_LINEAR : GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, linear ? GL_LINEAR : GL_NEAREST);
		_linear = linear;
	}
	gl.BindVertexArray(_vao);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	gl.BindVertexArray(0);
	gl.UseProgram(0);
	SDL_GL_SwapBuffers();
}

bool HdGpu::readBack(SDL_Surface *out)
{
	if (!_fbo || out->w != _w || out->h != _h || out->format->BytesPerPixel != 4)
	{
		return false;
	}
	gl.BindFramebuffer(GL_READ_FRAMEBUFFER, _fbo);
	glPixelStorei(GL_PACK_ROW_LENGTH, out->pitch / 4);
	glReadPixels(0, 0, _w, _h, GL_BGRA, GL_UNSIGNED_BYTE, out->pixels);
	glPixelStorei(GL_PACK_ROW_LENGTH, 0);
	gl.BindFramebuffer(GL_READ_FRAMEBUFFER, 0);
	return glGetError() == GL_NO_ERROR;
}

#endif

}
