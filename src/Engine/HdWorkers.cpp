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
#include <chrono>
#include <cstdlib>
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
	// a wake costs the woken thread some microseconds of processor time to go to sleep again, and 22 of them
	// for every slice of a frame cost more than the whole battle canvas (docs/research/gpu-render-plan-2026-10-27.md, 2.2)
	// 400 us: on the 285K the geoscape 0.67 -> 0.45 cores, the base 0.66 -> 0.52, a battle 0.32 -> 0.25, the frame
	// longer by under half a millisecond (200 us saved less, docs/research/gpu-render-plan-2026-10-27.md, 2.3)
	long long grainUs = 400;
	if (const char *env = getenv("OXCE_HD_POOL_GRAIN_US"))
	{
		grainUs = std::max(0LL, atoll(env));
		Log(LOG_INFO) << "HD render: pool grain " << grainUs << " us";
	}
	_grainNs = grainUs * 1000;
	_stats = getenv("OXCE_HD_POOL_STATS") != nullptr;
	for (int i = 1; i < n; ++i)
	{
		_threads.emplace_back(&HdWorkers::workerLoop, this);
	}
	Log(LOG_INFO) << "HD render: " << n << " render thread(s)";
	// the settings that decide how heavy a frame is: without them a log from another machine
	// cannot be read at all (see docs/PERF.md)
	Log(LOG_INFO) << "HD setup: " << Options::displayWidth << "x" << Options::displayHeight
		<< " scale=" << Options::oxceHdScale << " mode=" << Options::oxceHdMode
		<< " ui=" << Options::oxceHdUi << " frameSkip=" << Options::oxceHdFrameSkip
		<< " openGL=" << (Options::useOpenGL ? "on" : "off")
		<< " shader=" << (Options::useOpenGL ? Options::useOpenGLShader : std::string("-"))
		<< " gpu=" << (Options::oxceHdGpu ? "on" : "off")
		<< " cores=" << (int)std::thread::hardware_concurrency();
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

int HdWorkers::takeJobs(const std::function<void(int)> &fn, int jobs, long long &ns)
{
	const auto start = std::chrono::steady_clock::now();
	int taken = 0;
	for (int i = _next.fetch_add(1); i < jobs; i = _next.fetch_add(1))
	{
		fn(i);
		++taken;
	}
	ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count();
	_workNs += ns;
	return taken;
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
			_wake.wait(lock, [&] { return _quit || (_generation != seen && _slots > 0); });
			if (_quit)
			{
				return;
			}
			seen = _generation;
			--_slots;
			++_running;
			job = _job;
			jobs = _jobs;
		}
		long long ns;
		takeJobs(*job, jobs, ns);
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
	// the pool runs one batch at a time: a call from a job, or from another thread while a batch runs
	// (the data loading thread of the start screen), runs its jobs itself
	bool idle = false;
	if (_threads.empty() || jobs == 1 || !_busy.compare_exchange_strong(idle, true))
	{
		for (int i = 0; i < jobs; ++i)
		{
			fn(i);
		}
		return;
	}
	struct Release { std::atomic<bool> &busy; ~Release() { busy = false; } } release{ _busy };
	// only as many workers are woken as there are jobs besides the caller's: waking the whole pool for the
	// frame clear's 8 slices cost the main thread a fifth of its work on the base (profile 27.10);
	// and only as many as the work this call site gave last time pays for, one grain each besides the caller's
	// (a call site seen for the first time gets the whole pool, as before)
	Cost &cost = _costs[&fn.target_type()];
	int want = std::min(jobs - 1, (int)_threads.size());
	if (cost.known && _grainNs > 0)
	{
		const double work = cost.jobNs * jobs;
		want = std::min(want, std::max(0, (int)(work / _grainNs) - 1));
	}
	{
		std::lock_guard<std::mutex> lock(_mutex);
		_job = &fn;
		_jobs = jobs;
		_next = 0;
		_slots = want;
		_workNs = 0;
		++_generation;
	}
	if (want == (int)_threads.size())
	{
		_wake.notify_all();
	}
	else
	{
		for (int i = 0; i < want; ++i)
		{
			_wake.notify_one();
		}
	}
	long long ownNs;
	const int own = takeJobs(fn, jobs, ownNs);
	{
		std::unique_lock<std::mutex> lock(_mutex);
		// the batch is closed: a worker woken late does not take fn, which is gone once run returns
		_slots = 0;
		_done.wait(lock, [&] { return _running == 0; });
	}
	// the work is judged by the caller's own jobs: the workers' are dearer the more of them run (each pulls the
	// sprites into its own cache: the battle canvas costs 1.2 ms on one thread and 10 ms summed over 22);
	// a dearer batch is believed at once (the next one gets threads enough), a cheaper one slowly:
	// one light frame must not leave a heavy scroll to the caller alone
	if (own > 0)
	{
		const double jobNs = (double)ownNs / own;
		cost.jobNs = (!cost.known || jobNs > cost.jobNs) ? jobNs : cost.jobNs * 0.9 + jobNs * 0.1;
		cost.known = true;
	}
	if (_stats)
	{
		++cost.batches;
		cost.woken += want;
		cost.workNs += _workNs;
		reportStats();
	}
}

void HdWorkers::reportStats()
{
	const long long now = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
	if (_statsAt == 0)
	{
		_statsAt = now;
	}
	if (now - _statsAt < 5000)
	{
		return;
	}
	const double s = (now - _statsAt) / 1000.0;
	_statsAt = now;
	std::vector<std::pair<const std::type_info*, Cost*>> sites;
	for (auto &i : _costs)
	{
		if (i.second.batches > 0)
		{
			sites.emplace_back(i.first, &i.second);
		}
	}
	std::sort(sites.begin(), sites.end(), [](const auto &a, const auto &b) { return a.second->workNs > b.second->workNs; });
	for (auto &i : sites)
	{
		Cost &c = *i.second;
		Log(LOG_INFO) << "HD pool: " << (int)(c.batches / s) << " batch/s woken/batch " << (double)c.woken / c.batches
			<< " work us/batch " << c.workNs / c.batches / 1000 << " job us " << (int)(c.jobNs / 1000) << " " << i.first->name();
		c.batches = c.woken = c.workNs = 0;
	}
}

}
