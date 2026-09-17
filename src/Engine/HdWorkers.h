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
	int _running = 0;
	unsigned _generation = 0;
	bool _quit = false;

	HdWorkers();
	~HdWorkers();
	void workerLoop();
	void takeJobs(const std::function<void(int)> &fn, int jobs);
public:
	/// The process-wide pool (started on first use with the configured number of threads).
	static HdWorkers &instance();
	/// Number of threads that run jobs, the caller included (>= 1).
	int threads() const { return (int)_threads.size() + 1; }
	/// Runs fn(0) .. fn(jobs - 1) across the pool and returns when all have finished.
	void run(int jobs, const std::function<void(int)> &fn);
};

}
