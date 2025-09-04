#
# Author:: Joshua J. Berry <des@condordes.net>
# Copyright:: Copyright (c) 2013, Joshua J. Berry
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from datetime import timedelta
import fnmatch
from typing import Generator, Optional, TypedDict, cast
import yaml
import os
import re

__all__ = ['CronitorConfig']

ServerYAML = TypedDict('ServerYAML', {
    'job_dir': str,
    'template_dir': str,
    'asset_dir': str,
    'rules_file': str,
    'listen_on': list[str],
})

RuleYAML = TypedDict('RuleYAML', {
    'match': str,
    'keep': Optional[str],
    'due_every': Optional[str],
    'ignores': Optional[list[str]],
    'errors': Optional[list[str]],
})

SERVER_DEFAULTS = cast(ServerYAML, {
    # These must be specified:
    #"job_dir": None,
    #"template_dir": None,
    #"rules_file": None,
    "listen_on": ['*:8434'], # 8 for port 80, 434 == sum(bytes of "cron") :)
})

RULE_DEFAULTS = cast(RuleYAML, {
    #"matches": glob,
    "keep": "30d",
    "due_every": "1000y",
    # "errors": [regexp, regexp, ...]
    # "ignores": [regexp, regexp, ...]
})



class CronitorConfig(object):
    def __init__(self, server_file: str) -> None:
        self.__server_path = server_file

        with open(server_file, 'r') as f:
            self.__server = cast(ServerYAML, yaml.safe_load(f))

    def _server_get(self, key: str) -> str | list[str]:
        try:
            return self.__server[key] # type: ignore
        except KeyError:
            return SERVER_DEFAULTS[key] # type: ignore

    def _path(self, key: str) -> str:
        # This path is relative to the configuration file
        path = cast(str, self._server_get(key))
        return os.path.abspath(os.path.join(os.path.dirname(self.__server_path),
                                            path))

    def rules_for(self, job_name: str) -> 'RuleSet':
        with open(self._path('rules_file'), 'r') as f:
            return RuleSet(yaml.safe_load(f), job_name)

    @property
    def rules_file(self) -> str:
        return self._path('rules_file')

    @property
    def job_dir(self) -> str:
        return self._path('job_dir')

    @property
    def template_dir(self) -> str:
        return self._path('template_dir')

    @property
    def asset_dir(self) -> str:
        return self._path('asset_dir')

    @property
    def listen_on(self) -> Generator[tuple[str, int], None, None]:
        vals = self._server_get('listen_on')
        for v in vals:
            addr, port = v.split(":")
            if addr == "*":
                addr = ''
            yield addr, int(port)



class RuleSet(object):
    def __init__(self, rules_data: list[RuleYAML], job_name: str) -> None:
        rules = [Rule(**r) for r in rules_data]
        self.__rules = [r for r in rules if r.matches(job_name)]

    @property
    def keep(self) -> timedelta:
        for r in self.__rules:
            if r.keep is not None:
                return r.keep
        return parse_duration(cast(str, RULE_DEFAULTS['keep']))

    @property
    def due_every(self) -> timedelta:
        for r in self.__rules:
            if r.due_every is not None:
                return r.due_every
        return parse_duration(cast(str, RULE_DEFAULTS['due_every']))

    def is_error_line(self, line: str) -> bool:
        # To get rid of newlines and trailing whitepsace that will confound
        # regexes using '$'
        line = line.rstrip()
        for r in self.__rules:
            for i in r.ignores:
                if i.search(line):
                    return False

        for r in self.__rules:
            for e in r.errors:
                if e.search(line):
                    return True

        return False



class Rule(object):
    def __init__(self, match: str,
                 keep: Optional[str] = None, due_every: Optional[str] = None,
                 ignores: Optional[list[str]] = None,
                 errors: Optional[list[str]] = None,
                 ignores_i: Optional[list[str]] = None,
                 errors_i: Optional[list[str]] = None) -> None:
        self.pattern = match
        self.keep = parse_duration(keep) if keep else None
        self.due_every = parse_duration(due_every) if due_every else None
        self.ignores = self._to_relist(ignores, ignores_i)
        self.errors = self._to_relist(errors, errors_i)

    def _to_relist(self, case: Optional[list[str]], nocase: Optional[list[str]]) -> list[re.Pattern[str]]:
        l: list[re.Pattern[str]] = []
        if case:
            l += [re.compile(r) for r in case]
        if nocase:
            l += [re.compile(r, re.IGNORECASE) for r in nocase]
        return l

    def matches(self, job_name: str) -> bool:
        return fnmatch.fnmatch(job_name, self.pattern)


#
# Utility function for parsing durations
#

MIN = 60
HOURS = 60*60
DAYS = 24*HOURS
WEEKS = 7*DAYS
MONTHS = 30*DAYS
YEARS = 365*DAYS
DURATIONS = {
    '': 1, 's': 1, 'sec': 1,
    'min': MIN,
    'h': HOURS, 'hr': HOURS, 'hrs': HOURS,
    'd': DAYS, 'day': DAYS, 'days': DAYS,
    'w': WEEKS, 'wk': WEEKS, 'wks': WEEKS,
    'm': MONTHS, 'mo': MONTHS, 'mos': MONTHS,
    'y': YEARS, 'yr': YEARS, 'yrs': YEARS
    }

def parse_duration(dur: str) -> timedelta:
    secs = 0

    for e in re.split(' +', dur):
        m = re.match('([0-9]+)([a-zA-Z]*)', e)
        if not m: raise ValueError(dur)
        secs += int(m.group(1)) * DURATIONS[m.group(2).lower()]

    return timedelta(seconds=secs)
