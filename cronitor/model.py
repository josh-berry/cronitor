#
# Author:: Joshua J. Berry <des@condordes.net>
# Copyright:: Copyright (c) 2013, Joshua J. Berry
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
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

from datetime import datetime, timedelta
import os
import re

TS_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'



class JobSet(object):
    def __init__(self, config):
        self.__config = config

    def _config(self):
        return self.__config

    def _job_dir(self, name):
        return os.path.join(self.__config.job_dir, name)

    def __getitem__(self, name):
        return Job(self, name)

    @property
    def jobs(self):
        names = safe_listdir(self.__config.job_dir)
        names.sort()
        for name in names:
            if os.path.isdir(self._job_dir(name)):
                j = Job(self, name)
                try:
                    j.latest_entry
                    yield j
                except IndexError:
                    os.rmdir(self._job_dir(name))



class Job(object):
    def __init__(self, jobset, name):
        # because files with extensions (including ".") are private
        assert re.match('[0-9A-Za-z_-]*', name)

        self.__name = name
        self.__log_path = jobset._job_dir(name)
        self.__rules = jobset._config().rules_for(name)

    @property
    def name(self):
        return self.__name

    @property
    def path(self):
        return self.__log_path

    @property
    def rules(self):
        return self.__rules

    def record_log_entry(self, ts, logdata):
        if not os.path.isdir(self.__log_path):
            os.makedirs(self.__log_path)

        log_path = os.path.join(self.__log_path, ts.strftime(TS_FORMAT))
        with open(log_path, 'w') as f:
            f.write(logdata)

        self.rotate()

        return LogEntry(self, ts.strftime(TS_FORMAT))

    def rotate(self):
        oldest_age = datetime.now() - self.__rules.keep

        entries = safe_listdir(self.__log_path)
        for e in entries:
            try:
                ts = datetime.strptime(e, TS_FORMAT)
            except ValueError:
                # Ignore things we don't recognize.
                continue

            if ts < oldest_age:
                os.unlink(os.path.join(self.__log_path, e))

    def __getitem__(self, entry):
        if isinstance(entry, datetime):
            entry = datetime.strftime(entry, TS_FORMAT)

        if not os.path.isfile(os.path.join(self.__log_path, entry)):
            raise KeyError(entry)

        return LogEntry(self, entry)

    @property
    def log_entries(self):
        entries = safe_listdir(self.__log_path)
        entries.sort()
        entries.reverse()
        for e in entries:
            try:
                yield LogEntry(self, e)
            except ValueError:
                # Skip things we don't recognize.
                pass

    def has_entries(self):
        ents = self.log_entries
        try:
            ents.next()
            return True
        except StopIteration:
            return False

    @property
    def latest_entry(self):
        entries = safe_listdir(self.__log_path)
        entries.sort()
        return LogEntry(self, entries[-1])

    @property
    def is_overdue(self):
        late_before = datetime.now() - self.__rules.due_every
        late_by = self.latest_entry.timestamp - late_before
        if late_by < timedelta(0):
            return abs(late_by)
        return False

    @property
    def status(self):
        if self.is_overdue:
            return 'overdue'
        else:
            return self.latest_entry.status



class LogEntry(object):
    def __init__(self, job, timestamp):
        self.job = job
        self.path = os.path.join(self.job.path, timestamp)
        self.timestamp = datetime.strptime(timestamp, TS_FORMAT)

        self.__header = None
        self.__lines = None

    def _read(self):
        if self.__header: return

        header = {}
        with open(self.path, 'r') as f:
            # Read the header, up to the first blank line
            line = f.readline().strip()
            while line:
                m = re.match('([a-zA-Z0-9_.-]*):\s*(.*)', line)
                if not m:
                    # This shouldn't happen unless the log file is
                    # poorly-formatted for some reason.  If this happens, just
                    # assume the rest of the file is the log itself -- this is
                    # probably the least-bad failure case since it gives the
                    # user the contents of the file and lets them see what might
                    # have happened.
                    break

                header[m.group(1)] = m.group(2)
                line = f.readline().strip()

            # Everything after the blank line is the log text
            lines = f.readlines()

            self.__header = header
            self.__lines = lines

    @property
    def status(self):
        if self.rc != 0:
            return 'failed'

        # Make sure nothing weird or nasty appears in the log
        for line, is_err in self.scan_text():
            if is_err:
                return 'error'

        return 'ok'

    @property
    def metadata(self):
        self._read()
        return self.__header

    @property
    def command(self):
        self._read()
        return self.__header.get('Command', '')

    @property
    def rc(self):
        self._read()
        return self.__header.get('Return-Code', -1)

    @property
    def pwd(self):
        self._read()
        return self.__header.get('Directory', '')

    @property
    def env(self):
        self._read()
        env = {}
        for k, v in self.__header.iteritems():
            if k.startswith("ENV."):
                env[k[4:]] = v
        return env

    @property
    def text(self):
        self._read()
        return ''.join(self.__lines)

    def scan_text(self):
        self._read()
        rules = self.job.rules
        for line in self.__lines:
            is_err = rules.is_error_line(line)
            yield line, is_err



def safe_listdir(path):
    if os.path.isdir(path):
        return os.listdir(path)
    else:
        return []
