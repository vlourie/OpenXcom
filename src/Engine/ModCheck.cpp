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
#include "ModCheck.h"
#include <algorithm>
#include <cctype>
#include <exception>
#include <sstream>
#include <tuple>
#include "CrossPlatform.h"
#include "LuaSandbox.h"
#include "Yaml.h"

namespace OpenXcom
{
namespace ModCheck
{

namespace
{

std::string lower(std::string s)
{
	std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return (char)std::tolower(c); });
	return s;
}

bool endsWith(const std::string &s, const std::string &tail)
{
	return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}

/// One line per file: the report is split by tabs, and an error text may hold anything.
std::string oneLine(std::string s)
{
	std::replace_if(s.begin(), s.end(), [](char c) { return c == '\n' || c == '\r' || c == '\t'; }, ' ');
	return s;
}

void walk(const std::string &root, const std::string &rel, std::vector<std::string> &files)
{
	for (const auto &entry : CrossPlatform::getFolderContents(root + rel))
	{
		const std::string &name = std::get<0>(entry);
		if (std::get<1>(entry))
		{
			walk(root, rel + name + "/", files);
		}
		else
		{
			files.push_back(rel + name);
		}
	}
}

std::string checkLua(const std::string &path)
{
	auto stream = CrossPlatform::readFile(path);
	std::ostringstream code;
	code << stream->rdbuf();
	std::string text = code.str();
	if (text.compare(0, 3, "\xEF\xBB\xBF") == 0)
	{
		text.erase(0, 3); // as LuaHost::reload: Notepad saves with it
	}
	return LuaSandbox::compileOnly(CrossPlatform::baseFilename(path), text);
}

std::string checkYaml(const std::string &path)
{
	try
	{
		YAML::YamlRootNodeReader reader(path);
		return "";
	}
	catch (const std::exception &e)
	{
		return e.what();
	}
}

}

int run(const std::vector<std::string> &args)
{
	if (args.size() != 4 || args[1] != "-modcheck")
	{
		return -1;
	}
	std::string root = args[2];
	if (!root.empty() && root.back() != '/' && root.back() != '\\')
	{
		root += '/';
	}
	std::ostringstream out;
	std::vector<std::string> files;
	walk(root, "", files);
	std::sort(files.begin(), files.end());
	int bad = 0;
	for (const auto &file : files)
	{
		const std::string name = lower(file);
		const bool lua = endsWith(name, ".lua");
		if (!lua && !endsWith(name, ".yml") && !endsWith(name, ".rul"))
		{
			continue;
		}
		const std::string error = lua ? checkLua(root + file) : checkYaml(root + file);
		if (error.empty())
		{
			out << "ok\t" << file << "\n";
		}
		else
		{
			out << "bad\t" << file << "\t" << oneLine(error) << "\n";
			++bad;
		}
	}
	// without this line whoever reads the report knows the parser fell over on the last file
	out << "done\t" << files.size() << "\n";
	if (!CrossPlatform::writeFile(args[3], out.str()))
	{
		return 3;
	}
	return bad > 0 ? 1 : 0;
}

}
}
