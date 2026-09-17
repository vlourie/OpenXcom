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
#include "HdWorkers.h"
#include <algorithm>
#include "Logger.h"
#include "Options.h"

namespace OpenXcom
{

HdWorkers &HdWorkers::instance()
{
	static HdWorkers pool;
	return pool;
}

HdWorkers::HdWorkers()
{
	int n = Options::oxceHdThreads;
	if (n <= 0)
	{
		// not every thread of the machine: the sound mixer's callback and the system need a core
		// too, and when they do not get one in time short sounds (a unit's footsteps) are dropped
		const int cores = (int)std::thread::hardware_concurrency();
		n = cores > 4 ? cores - 2 : cores;
	}
	n = std::max(1, std::min(32, n));
	for (int i = 1; i < n; ++i)
	{
		_threads.emplace_back(&HdWorkers::workerLoop, this);
	}
	Log(LOG_INFO) << "HD render: " << n << " render thread(s)";
}

HdWorkers::~HdWorkers()
{
	{
		std::lock_guard<std::mutex> lock(_mutex);
		_quit = true;
	}
	_wake.notify_all();
	for (auto &thread : _threads)
	{
		thread.join();
	}
}

void HdWorkers::takeJobs(const std::function<void(int)> &fn, int jobs)
{
	for (int i = _next.fetch_add(1); i < jobs; i = _next.fetch_add(1))
	{
		fn(i);
	}
}

void HdWorkers::workerLoop()
{
	unsigned seen = 0;
	for (;;)
	{
		const std::function<void(int)> *job;
		int jobs;
		{
			std::unique_lock<std::mutex> lock(_mutex);
			_wake.wait(lock, [&] { return _quit || _generation != seen; });
			if (_quit)
			{
				return;
			}
			seen = _generation;
			job = _job;
			jobs = _jobs;
		}
		takeJobs(*job, jobs);
		{
			std::lock_guard<std::mutex> lock(_mutex);
			if (--_running == 0)
			{
				_done.notify_all();
			}
		}
	}
}

void HdWorkers::run(int jobs, const std::function<void(int)> &fn)
{
	if (jobs <= 0)
	{
		return;
	}
	if (_threads.empty() || jobs == 1)
	{
		for (int i = 0; i < jobs; ++i)
		{
			fn(i);
		}
		return;
	}
	{
		std::lock_guard<std::mutex> lock(_mutex);
		_job = &fn;
		_jobs = jobs;
		_next = 0;
		_running = (int)_threads.size();
		++_generation;
	}
	_wake.notify_all();
	takeJobs(fn, jobs);
	std::unique_lock<std::mutex> lock(_mutex);
	_done.wait(lock, [&] { return _running == 0; });
}

}
