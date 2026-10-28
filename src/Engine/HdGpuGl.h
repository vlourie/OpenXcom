#pragma once
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
// The OpenGL functions of the HD layer on the video card (HdGpu, HdGpuCanvas): private to those files.
#ifndef __NO_OPENGL
#include <cstddef>
#include <SDL.h>
#include <SDL_opengl.h>

#ifndef APIENTRY
#define APIENTRY
#endif
#ifndef GL_BGRA
#define GL_BGRA 0x80E1
#endif
#ifndef GL_CLAMP_TO_EDGE
#define GL_CLAMP_TO_EDGE 0x812F
#endif
#ifndef GL_TEXTURE0
#define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_FRAGMENT_SHADER
#define GL_FRAGMENT_SHADER 0x8B30
#endif
#ifndef GL_VERTEX_SHADER
#define GL_VERTEX_SHADER 0x8B31
#endif
#ifndef GL_COMPILE_STATUS
#define GL_COMPILE_STATUS 0x8B81
#endif
#ifndef GL_LINK_STATUS
#define GL_LINK_STATUS 0x8B82
#endif
#ifndef GL_READ_FRAMEBUFFER
#define GL_READ_FRAMEBUFFER 0x8CA8
#endif
#ifndef GL_DRAW_FRAMEBUFFER
#define GL_DRAW_FRAMEBUFFER 0x8CA9
#endif
#ifndef GL_FRAMEBUFFER_COMPLETE
#define GL_FRAMEBUFFER_COMPLETE 0x8CD5
#endif
#ifndef GL_COLOR_ATTACHMENT0
#define GL_COLOR_ATTACHMENT0 0x8CE0
#endif
#ifndef GL_FRAMEBUFFER
#define GL_FRAMEBUFFER 0x8D40
#endif
#ifndef GL_TEXTURE_2D_ARRAY
#define GL_TEXTURE_2D_ARRAY 0x8C1A
#endif
#ifndef GL_MAX_ARRAY_TEXTURE_LAYERS
#define GL_MAX_ARRAY_TEXTURE_LAYERS 0x88FF
#endif
#ifndef GL_TEXTURE_BUFFER
#define GL_TEXTURE_BUFFER 0x8C2A
#endif
#ifndef GL_RGBA32I
#define GL_RGBA32I 0x8D82
#endif
#ifndef GL_R32UI
#define GL_R32UI 0x8236
#endif
#ifndef GL_RED_INTEGER
#define GL_RED_INTEGER 0x8D94
#endif
#ifndef GL_PIXEL_PACK_BUFFER
#define GL_PIXEL_PACK_BUFFER 0x88EB
#endif
#ifndef GL_STREAM_DRAW
#define GL_STREAM_DRAW 0x88E0
#endif
#ifndef GL_STREAM_READ
#define GL_STREAM_READ 0x88E1
#endif
#ifndef GL_READ_ONLY
#define GL_READ_ONLY 0x88B8
#endif
#ifndef GL_SYNC_GPU_COMMANDS_COMPLETE
#define GL_SYNC_GPU_COMMANDS_COMPLETE 0x9117
#endif
#ifndef GL_ALREADY_SIGNALED
#define GL_ALREADY_SIGNALED 0x911A
#endif
#ifndef GL_CONDITION_SATISFIED
#define GL_CONDITION_SATISFIED 0x911C
#endif
#ifndef GL_WAIT_FAILED
#define GL_WAIT_FAILED 0x911D
#endif
#ifndef GL_SYNC_FLUSH_COMMANDS_BIT
#define GL_SYNC_FLUSH_COMMANDS_BIT 0x00000001
#endif
#ifndef GL_MAX_TEXTURE_BUFFER_SIZE
#define GL_MAX_TEXTURE_BUFFER_SIZE 0x8C2B
#endif
#ifndef GL_CURRENT_PROGRAM
#define GL_CURRENT_PROGRAM 0x8B8D
#endif

namespace OpenXcom
{
namespace hdgl
{

// the OpenGL 2.0-3.3 functions the HD layer calls: opengl32 exports only 1.1, the rest the driver gives by name
// (a loader in the manner of glad, but only for what is used; kept apart from the ones OpenGL.cpp loads for itself);
// a sync object is a pointer the driver gives (GLsync), held as void *
#define HD_GL_FUNCTIONS(X) \
	X(void, GenFramebuffers, (GLsizei, GLuint *)) \
	X(void, DeleteFramebuffers, (GLsizei, const GLuint *)) \
	X(void, BindFramebuffer, (GLenum, GLuint)) \
	X(void, FramebufferTexture2D, (GLenum, GLenum, GLenum, GLuint, GLint)) \
	X(GLenum, CheckFramebufferStatus, (GLenum)) \
	X(void, GenVertexArrays, (GLsizei, GLuint *)) \
	X(void, DeleteVertexArrays, (GLsizei, const GLuint *)) \
	X(void, BindVertexArray, (GLuint)) \
	X(GLuint, CreateShader, (GLenum)) \
	X(void, ShaderSource, (GLuint, GLsizei, const char *const *, const GLint *)) \
	X(void, CompileShader, (GLuint)) \
	X(void, GetShaderiv, (GLuint, GLenum, GLint *)) \
	X(void, GetShaderInfoLog, (GLuint, GLsizei, GLsizei *, char *)) \
	X(void, DeleteShader, (GLuint)) \
	X(GLuint, CreateProgram, ()) \
	X(void, AttachShader, (GLuint, GLuint)) \
	X(void, LinkProgram, (GLuint)) \
	X(void, GetProgramiv, (GLuint, GLenum, GLint *)) \
	X(void, GetProgramInfoLog, (GLuint, GLsizei, GLsizei *, char *)) \
	X(void, DeleteProgram, (GLuint)) \
	X(void, UseProgram, (GLuint)) \
	X(GLint, GetUniformLocation, (GLuint, const char *)) \
	X(void, Uniform1i, (GLint, GLint)) \
	X(void, Uniform2f, (GLint, GLfloat, GLfloat)) \
	X(void, Uniform1ui, (GLint, GLuint)) \
	X(void, ActiveTexture, (GLenum)) \
	X(void, GenBuffers, (GLsizei, GLuint *)) \
	X(void, DeleteBuffers, (GLsizei, const GLuint *)) \
	X(void, BindBuffer, (GLenum, GLuint)) \
	X(void, BufferData, (GLenum, std::ptrdiff_t, const void *, GLenum)) \
	X(void, BufferSubData, (GLenum, std::ptrdiff_t, std::ptrdiff_t, const void *)) \
	X(void *, MapBuffer, (GLenum, GLenum)) \
	X(GLboolean, UnmapBuffer, (GLenum)) \
	X(void, TexBuffer, (GLenum, GLenum, GLuint)) \
	X(void, TexImage3D, (GLenum, GLint, GLint, GLsizei, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *)) \
	X(void, TexSubImage3D, (GLenum, GLint, GLint, GLint, GLint, GLsizei, GLsizei, GLsizei, GLenum, GLenum, const void *)) \
	X(void *, FenceSync, (GLenum, GLbitfield)) \
	X(GLenum, ClientWaitSync, (void *, GLbitfield, unsigned long long)) \
	X(void, DeleteSync, (void *))

struct Functions
{
#define HD_GL_POINTER(ret, name, args) ret (APIENTRY *name) args = nullptr;
	HD_GL_FUNCTIONS(HD_GL_POINTER)
#undef HD_GL_POINTER
	/// WGL_EXT_swap_control (Windows only; elsewhere the driver's default stays).
	int (APIENTRY *SwapInterval)(int) = nullptr;
	/// glCopyImageSubData (OpenGL 4.3, GL_ARB_copy_image): an array of frames grows without its frames going up
	/// again (Atlas::grow); null where the driver has not got it.
	void (APIENTRY *CopyImageSubData)(GLuint, GLenum, GLint, GLint, GLint, GLint, GLuint, GLenum, GLint, GLint, GLint, GLint,
		GLsizei, GLsizei, GLsizei) = nullptr;
};

/// The functions, loaded by HdGpu::setup.
extern Functions gl;

/// A program out of a vertex and a fragment shader (GLSL 330); 0 and a line in the log when they do not build.
GLuint program(const char *vertex, const char *fragment, const char *what);

}
}
#endif
