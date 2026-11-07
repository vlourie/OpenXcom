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
#include <atomic>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <typeinfo>
#include <unordered_map>
#include <vector>

namespace OpenXcom
{

/**
 * A small pool of worker threads for the HD renderer: runs a batch of
 * independent jobs (the horizontal strips of a frame, the rows of a copy)
 * across the machine's cores and waits for all of them. The calling thread
 * takes jobs too, so with no workers everything simply runs inline.
 */
class HdWorkers
{
private:
	std::vector<std::thread> _threads;
	std::mutex _mutex;
	std::condition_variable _wake;
	std::condition_variable _done;
	const std::function<void(int)> *_job = nullptr;
	int _jobs = 0;
	std::atomic<int> _next { 0 };
	/// A batch is running (see run).
	std::atomic<bool> _busy { false };
	/// Workers in the running batch, and how many more may join it (only as many are woken as it has jobs).
	int _running = 0, _slots = 0;
	unsigned _generation = 0;
	bool _quit = false;
	/// What the batches of each call site cost (keyed by the type of its job function: one per lambda),
	/// so that a batch wakes only as many workers as its work pays for. Touched only by the batch's caller.
	struct Cost
	{
		/// Time of one job the caller ran itself, nanoseconds: the last batch's when it was dearer, else drifting down to it.
		double jobNs = 0;
		bool known = false;
		/// For OXCE_HD_POOL_STATS: batches, workers woken and work since the last report.
		long long batches = 0, woken = 0, workNs = 0;
	};
	bool _stats = false;
	long long _statsAt = 0;
	void reportStats();
	std::unordered_map<const std::type_info*, Cost> _costs;
	/// Processor time the threads of the running batch spent in its jobs, nanoseconds.
	std::atomic<long long> _workNs { 0 };
	/// The work one woken thread must get for its wake to pay (OXCE_HD_POOL_GRAIN_US for tests), nanoseconds.
	long long _grainNs = 0;

	HdWorkers();
	~HdWorkers();
	void workerLoop();
	/// Takes jobs of the running batch until none are left; returns how many it ran, and in ns the time they took.
	int takeJobs(const std::function<void(int)> &fn, int jobs, long long &ns);
public:
	/// The process-wide pool (started on first use with the configured number of threads).
	static HdWorkers &instance();
	/// Number of threads that run jobs, the caller included (>= 1).
	int threads() const { return (int)_threads.size() + 1; }
	/// Runs fn(0) .. fn(jobs - 1) across the pool and returns when all have finished. The jobs must not
	/// depend on which thread runs them: a batch of little work runs on fewer threads, or on the caller alone.
	void run(int jobs, const std::function<void(int)> &fn);
};

}
