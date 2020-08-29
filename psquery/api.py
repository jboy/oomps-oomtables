# Copyright (c) 2020 James Boyden <jboy@jboy.me>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Functions to query processes according to requested fields."""

from abc import ABCMeta, abstractmethod  # Python3 only, sorry  :'(
from collections import namedtuple
from operator import attrgetter
from time import localtime, strftime
from time import time as utc_time_now

# Use `_procio` to augment the capabilities of `psutil`.
from ._procio import read_int_from_proc_pid, read_overcommit_settings

# https://pypi.org/project/psutil/
# https://psutil.readthedocs.io/en/latest/
from psutil import process_iter as psutil_process_iter
from psutil import virtual_memory as psutil_virtual_memory
from psutil import swap_memory as psutil_swap_memory


# TODO: Move these into a new module `fieldefs.py`?

## Field-accessor functions: func(Process) -> value

def _read_int_from_proc(fname, default_int=None):
    assert (default_int is None) or isinstance(default_int, int)
    return read_int_from_proc_pid(fname, default_int)


## Post-processing functions: func(value, post_proc_settings) -> value

# Note:  We store `utc_now` (obtained from `time.time()`, as `utc_time_now()`)
# because method `Process.create_time()` returns "The process creation time
# as a floating point number expressed in seconds since the epoch, in UTC."
#  -- https://psutil.readthedocs.io/en/latest/#psutil.Process.create_time
#
# Note #2:  In contrast, we expect `this_yday` & `this_year` to be *localtime*
# (as if converted from a UTC time returned by `Process.create_time()` or
# the Python `time.time()` function, using the `time.localtime()` function).
# We require `this_yday` & `this_year` to be localtime *not* UTC, because we
# are checking the boundaries of days (at midnight, localtime).
PostProcSettings = namedtuple("PostProcSettings", (
        "cmdline_sep",
        "human_scale", "human_denom", "human_units", "human_final",
        "this_yday", "this_year",
        "utc_now"))


def _get_human_size_units(use_base10_human_size=False):
    """Let the caller choose whether they want base-10 or base-2 size units."""
    if use_base10_human_size:
        scale = 1000.0  # The scale between successive size-units.
        units = ("B", "K", "M", "G")  # All units except the highest.
        final = "T"  # The highest unit we support.
    else:
        scale = 1024.0
        units = ("B ", "Ki", "Mi", "Gi")
        final = "Ti"

    denom = 1.0 / scale  # Pre-calculate the denominator of division-by-scale.
    return (scale, denom, units, final)


def get_post_proc_settings(
        cmdline_sep=" ",
        use_base10_human_size=False):
    """Get the post-processing settings based upon the caller's preferences."""
    (human_scale, human_denom, human_units, human_final) = \
            _get_human_size_units(use_base10_human_size)

    # The date/time right now, in both Localtime & UTC.
    # https://docs.python.org/3/library/time.html#time.localtime
    curr_date = localtime()  # Localtime
    # https://docs.python.org/3/library/time.html#time.time
    utc_now = utc_time_now()  # UTC

    return PostProcSettings(
            cmdline_sep,
            human_scale, human_denom, human_units, human_final,
            curr_date.tm_yday, curr_date.tm_year,
            utc_now)


def _bytes_to_kiB(num_bytes, post_proc_settings):
    """Convert a number of bytes to the corresp number of "kibibytes" (kiB).

    This function is needed because method `Process.memory_info()` states
    "All numbers are expressed in bytes."
     -- https://psutil.readthedocs.io/en/latest/#psutil.Process.memory_info
    """
    return (num_bytes >> 10)


def _calc_desk_time(float_creation_time, post_proc_settings):
    return (post_proc_settings.utc_now - float_creation_time)


def _float_to_int(float_val, post_proc_settings):
    # In Python2, built-in `round` returns a `float`; in Python3, an `int`.
    return int(round(float_val))


def _format_date_time(float_date_time, post_proc_settings):
    """Format the date/time into a human-readable representation string.

    This human-readable format was designed to make it easy to differentiate
    the "orders of magnitude" of date/time on a quick scan down a left-aligned
    column.

    Here are some examples:
     - "2018-Jan-26 "
     - "Aug-16 20:12"
     - "  07:20:13"
    """
    # https://docs.python.org/3/library/time.html#time.localtime
    full_date = localtime(float_date_time)

    is_same_year = (full_date.tm_year == post_proc_settings.this_year)
    is_same_day = (full_date.tm_yday == post_proc_settings.this_yday) and is_same_year
    if is_same_day:
        return strftime("  %H:%M:%S", full_date)
    elif is_same_year:
        return strftime("%b-%d %H:%M", full_date)
    else:
        return strftime("%Y-b-%d ", full_date)


def _format_human_size(num_bytes, post_proc_settings):
    # Based upon https://stackoverflow.com/a/1094933
    scale = post_proc_settings.human_scale
    denom = post_proc_settings.human_denom
    units = post_proc_settings.human_units
    final = post_proc_settings.human_final

    num = float(num_bytes)
    for u in units:
        if num < scale:
            return "%3.1f %s" % (num, u)
        num *= denom
    return "%.1f %s" % (num, final)


def _format_time_delta(float_time_delta, post_proc_settings):
    """Format the time-delta into a human-readable representation string.

    This representation "floats" (in the same sense as floating-point numbers):
    it offers 5 different "orders of magnitude" of time-delta:
     - years (y)
     - weeks (w)
     - days (d)
     - hours (:)
     - minutes & seconds
    and it will display only the 2 most-significant "orders of magnitude",
    such that the most-significant "order of magnitude" is non-zero.
    For time-deltas < 1000 years, the string-length will be <= 10 characters.

    Here are some examples:
     - "+y001 +w42"
     - "+w09 +d01"
     - "+w01 +d03"
     - "+d6 +h18"
     - "+22:28:15"

    This human-readable format was designed (using a "prefix unit"; eg, "+w")
    to make it easy to differentiate the "orders of magnitude" on a quick scan
    down a left-aligned column; and also to distinguish times (eg, "07:20:13")
    from time-deltas (eg, "+22:28:15"").

    As an added bonus:  Sorting these human-readable strings lexicographically
    (ie, according to their ASCII character codes) will order by time-delta.
    """
    num_secs_per_min = 60.0
    num_secs_per_hour = 3600.0  # == 60 * 60.0
    num_secs_per_24_hours = 86400.0  # == 24 * 60 * 60.0
    num_secs_per_7_days = 604800  # == 7 * 24 * 60 * 60.0
    num_secs_per_365_days = 31536000.0  # 365 * 24 * 60 * 60.0

    if float_time_delta >= num_secs_per_365_days:
        # It's a year or more.  Use the "+y003 +w07" time-delta format.
        num_years = int(float_time_delta / num_secs_per_365_days)
        time_remaining = float_time_delta - (num_years * num_secs_per_365_days)
        num_weeks = int(time_remaining / num_secs_per_7)
        return "+y%03d +w%02d" % (num_years, num_weeks)
    elif float_time_delta >= num_secs_per_7_days:
        # It's a week or more, but less than a year.
        # Use the "+w07 +d03" time-delta format.
        num_weeks = int(float_time_delta / num_secs_per_7_days)
        time_remaining = float_time_delta - (num_weeks * num_secs_per_7_days)
        num_days = int(time_remaining / num_secs_per_24_hours)
        return "+w%02d +d%02d" % (num_weeks, num_days)
    elif float_time_delta >= num_secs_per_24_hours:
        # It's a day or more, but less than a week.
        # Use the "+d3 +h17" time-delta format.
        num_days = int(float_time_delta / num_secs_per_24_hours)
        time_remaining = float_time_delta - (num_days * num_secs_per_24_hours)
        num_hours = int(time_remaining / num_secs_per_hour)
        return "+d%d +h%02d" % (num_days, num_hours)
    else:
        # It's less than a day.  Use the "+hh:mm:ss" time-delta format.
        num_hours = int(float_time_delta / num_secs_per_hour)
        time_remaining = float_time_delta - (num_hours * num_secs_per_hour)
        num_mins = int(time_remaining / num_secs_per_min)
        time_remaining = time_remaining - (num_mins * num_secs_per_min)
        num_secs = int(time_remaining)
        return "+%02d:%02d:%02d" % (num_hours, num_mins, num_secs)


def _get_rss(memory_info_tuple, post_proc_settings):
    return memory_info_tuple.rss


def _get_uid(uids_tuple, post_proc_settings):
    # "The real, effective and saved user ids of this process as a named tuple.
    # This is the same as os.getresuid but can be used for any process PID."
    #  -- https://psutil.readthedocs.io/en/latest/#psutil.Process.uids
    #
    # "Return a tuple (ruid, euid, suid) denoting the current process's
    # real, effective, and saved user ids."
    #  -- https://docs.python.org/3/library/os.html#os.getresuid
    (ruid, euid, suid) = uids_tuple
    return ruid


def _get_vsz(memory_info_tuple, post_proc_settings):
    return memory_info_tuple.vms


def _join_cmdline(cmdline_array, post_proc_settings):
    return post_proc_settings.cmdline_sep.join(cmdline_array)


def _sum_cpu_times(cpu_times_tuple, post_proc_settings):
    """Sum the `user` & `system` times in the `psutil.pcputimes` named-tuple.

    To quote the docstring for method `psutil.Process.cpu_times()`:
        Return a named tuple representing the accumulated process times,
        in seconds (see explanation). This is similar to `os.times`
        but can be used for any process PID.
         - user: time spent in user mode.
         - system: time spent in kernel mode.
     -- https://psutil.readthedocs.io/en/latest/#psutil.Process.cpu_times
    """
    return cpu_times_tuple.user + cpu_times_tuple.system


## Field types
FieldType = namedtuple("FieldType", (
        # The FieldType name as a string.
        "name",

        # The Python type that will be returned.
        "py_type",

        # The maximum length (in characters) for values of this FieldType when
        # they are rendered as a string.  This is provided as a convenience to
        # users of this module, worked out once and stored here for repeat use.
        #
        #  - `rec_max_len`: a recommended maximum length (good for most cases)
        #  - `likely_max_len`: a very-probable maximum reasonable length
        #  - `def_max_len`: a maximum length (by definition), might be `None`
        #
        # The `rec_max_len` is a length estimate that will probably work well
        # in most cases; it won't waste much space with padding in general,
        # at the risk of occasionally being broken (causing some columns to be
        # mis-aligned in a tabular format).
        #
        # The `likely_max_len` is a safe length estimate that's very likely to
        # be correct for almost all cases (under some reasonable assumptions);
        # but it can still be incorrect under unreasonable circunstances.
        #
        # In contrast, `def_max_len` is a by-definition upper-limit on possible
        # lengths for that FieldType, which is guaranteed always to be correct
        # (no buffer overruns!), but might be encountered only rarely (if ever)
        # in practice.
        #
        # If there is no length estimate or defined upper-limit, a value of 0
        # will be specified.
        #
        # For example:
        #
        #  * Usernames & group-names:
        #    On Linux, usernames can *technically* be up to 32 characters long:
        #     https://serverfault.com/questions/294121/what-is-the-maximum-username-length-on-current-gnu-linux-systems
        #     https://unix.stackexchange.com/questions/157426/what-is-the-regex-to-validate-linux-users
        #    But most usernames on my Linux system (for both humans & services)
        #    are <= 8 characters long, matching the traditional UNIX practice;
        #    the longest usernames are for obscure daemons that will rarely if
        #    ever be of interest in a process query:
        #     - `speech-dispatcher`: 17
        #     - `systemd-coredump`: 16
        #     - `systemd-network`: 15
        #     - `systemd-resolve`: 15
        #     - `cups-pk-helper`: 14
        #
        #  * UIDs & GIDs:
        #    On Linux (>= 2.4 in 2001) & Solaris (>= 2.0 in 1990),
        #    UIDs are 32 bits (allowing 2**32 == 4,294,967,296 IDs) (10 chars):
        #     https://en.wikipedia.org/wiki/User_identifier#Type
        #     https://serverfault.com/questions/105260/how-big-in-bits-is-a-unix-uid
        #    But the historical UID size of 16 bits (2**16 == 65536 unique IDs)
        #    is rarely exceeded in practice, with a length of just 5 characters.
        #
        #  * PIDs:
        #    On Linux, the default highest PID is 32768 (5 string characters)
        #    before wrap-around, but it can be configured as high as 4,194,304
        #    (7 string characters) on 64-bit systems:
        #     https://serverfault.com/questions/279178/what-is-the-range-of-a-pid-on-linux-and-solaris
        #     https://unix.stackexchange.com/questions/16883/what-is-the-maximum-value-of-the-process-id
        #     https://stackoverflow.com/questions/6294133/maximum-pid-in-linux
        "rec_max_len", "likely_max_len", "def_max_len",

        # Whether the string-rendered field should be left-aligned ("L") or
        # right-aligned ("R").  For example, numeric values (whether literal
        # integers or pre-rendered human-readable strings) should generally be
        # right-aligned.
        "alignment",

        # A human-readable description of the FieldType (like help).
        "descr"))


# These recommended & likely max-lengths are complete guesses,
# because I'm trying to provide ANY useful guidance here.
# These are double the corresponding exe-name-with-path numbers.
CmdlineArrayType = FieldType("CmdlineArray",    list,   100,    160,    None,   'L',
        "Command-line (invoked command & args) as an array of strings")

# These recommended & likely max-lengths are complete guesses,
# because I'm trying to provide ANY useful guidance here.
# These are double the corresponding exe-name-with-path numbers.
CmdlineStringType = FieldType("CmdlineString",  str,    100,    160,    None,   'L',
        "Command-line (invoked command & args) joined as a single string")

# On my system, with 3466 installed executables, there are only 14 executables
# (0.4%) with names longer than 30 characters.  (The longest is 47 characters.)
ExeNameType = FieldType("ExeName",              str,    20,     30,     None,   'L',
        "Executable name (without path)")

# On my system, the longest exe-name-with-path I can find is 81 characters.
# The longest for a currently-running process is 42 characters.
ExePathNameType = FieldType("ExePathName",      str,    50,     80,     None,   'L',
        "Executable name (with absolute path)")

# eg, "123.9 Mi" or "5.4 G" or even "1021.4 Mi" (because 1021.4 < 1024.0).
MemSizeHumanType = FieldType("MemSizeHuman",    str,    9,      9,      None,   'R',
        "Human-readable memory size")

# Assume that no single process will use 1 TB of memory or more
# (under reasonable circumstances -- sorry, Google & Facebook).
#
# To refresh *your* memory:
#  1 KB == 10 **  3 == 1000 B
#  1 MB == 10 **  6 == 1000000 B
#  1 GB == 10 **  9 == 1000000000 B
#  1 TB == 10 ** 12 == 1000000000000 B
# while:
#  1 KiB == 1 << 10 == 1024 B
#  1 MiB == 1 << 20 == 1048576 B
#  1 GiB == 1 << 30 == 1073741824 B
#  1 TiB == 1 << 40 == 1099511627776 B
#
# So 1 TB is the lowest amount of memory that requires 10 decimal digits to
# represent the number of KB.  I'm saying we won't need >= 10 decimal digits.
MemSizeKType = FieldType("MemSizeK",            int,    9,      9,      None,   'R',
        "Memory size in KB or KiB")

# OOM Adjustment values in range [-17, +15] (3 chars).
OomAdjType = FieldType("OomAdj",            int,    3,  3,  3,  'R',
        "OOM Adjustment (pre-Linux 2.6.36; now deprecated): [-17, +15]")

# OOM Score values in range [0, 1000] (4 chars).
OomScoreType = FieldType("OomScore",        int,    4,  4,  4,  'R',
        "OOM Score: [0, 1000]")

# OOM Score Adjustment values in range [-1000, 1000] (5 chars).
OomScoreAdjType = FieldType("OomScoreAdj",  int,    5,  5,  5,  'R',
        "OOM Score Adjustment (Linux 2.6.36 and later): [-1000, 1000]")

PIDType = FieldType("PID",  int,    5,  7,  7,  'R',
        "Process ID (integer)")

# This start-time limit of 12 characters will be valid until 10000 AD.
#
# *Technically* (sigh), the world could last forever, so there's no definite
# upper limit on the year AD.
#
# (The start-time is returned to us as a Python `float`, so there's not even
# really a convenient upper limit due to integer size.)
StartTimeHumanType = FieldType("StartTimeHuman",    str,    12, 12, None,   'L',
        "Human-readable start-time")

# A start-time, in seconds since the UNIX epoch (Jan 1, 1970, 00:00:00 (UTC)),
# as returned by `time.time()` or `time.localtime()`, will be <10000000000 secs
# (ie, <=10 chars) until Nov 21, 2286 AD.
#
# It will be <100000000000 secs (ie, <= 11 chars) until Nov 16, 5138 AD.
# That's more than 3.1 Futuramas away!
#
# For sanity, because we're returning the start-time in seconds in an integer,
# let's assume the start-time must fit within a 64-bit integer (20 chars).
StartTimeSecsType = FieldType("StartTimeSecs",      int,    10, 11, 20, 'R',
        "Start-time in seconds since UNIX epoch")

# Human-readable time-delta will be <=10 chars for a time-delta of <1000 years.
# 999 years is not bad for the real-world lifetime of a single process...
#
# But again, *technically* (sigh), ...
#
# (The start-time & CPU-time are each returned to us as a Python `float`,
# so there's not even really a convenient upper limit due to integer size.)
TimeDeltaHumanType = FieldType("TimeDeltaHuman",    str,    10, 10, None,   'L',
        "Human-readable time-delta")

# Assume a time-delta in seconds will fit within a 64-bit integer (20 chars).
# But in 300 years, there are (300 * 365 * 24 * 60 * 60) seconds (10 chars).
# 300 years is not bad for the real-world lifetime of a single process...
TimeDeltaSecsType = FieldType("TimeDeltaSecs",      int,    10, 10, 20, 'R',
        "Time-delta in integer seconds")

# eg, "/dev/pts/18" or `None`
TtyType = FieldType("Tty",  (str, type(None)),    12, 16, None,   'L',
        "Terminal associated with the process")

UIDType = FieldType("UID",  int,    5,  10, 10, 'R',
        "User ID or Group ID (integer)")

UsernameType = FieldType("Username",    str,    10, 20, 32, 'L',
        "Username (string)")

# These recommended & likely max-lengths are complete guesses,
# because I'm trying to provide ANY useful guidance here.
WorkingDirType = FieldType("WorkingDir",    str,    30, 60, None,   'L',
        "Current Working Directory (absolute path) of process")


_ALL_FIELDS = dict(
        # NAME  (CODE   FIELD_TYPE          ATTR_NAME or FUNC(Process)                  POST_PROCESSING)
        adj=    ('a',   OomScoreAdjType,    _read_int_from_proc("oom_score_adj", 0),    None),
        adjd=   ('A',   OomAdjType,         _read_int_from_proc("oom_adj", 0),          None),
        cmda=   ('C',   CmdlineArrayType,   "cmdline",                                  None),
        cmds=   ('c',   CmdlineStringType,  "cmdline",                                  (_join_cmdline,)),
        ctime=  ('t',   TimeDeltaHumanType, "cpu_times",                                (_sum_cpu_times, _format_time_delta)),
        ctimes= ('T',   TimeDeltaSecsType,  "cpu_times",                                (_sum_cpu_times, _float_to_int)),
        dtime=  ('d',   TimeDeltaHumanType, "create_time",                              (_calc_desk_time, _format_time_delta)),
        dtimes= ('D',   TimeDeltaSecsType,  "create_time",                              (_calc_desk_time, _float_to_int)),
        #euid=   ('E', "proc.uids()"
        #euser=  ('e', ???
        exe=    ('x',   ExeNameType,        "name",                                     None),
        exep=   ('X',   ExePathNameType,    "exe",                                      None),
        #gid=    ('g', "proc.gids()"
        #npgv=   ('n', ???
        #npgr=   ('n', ???
        ooms=   ('o',   OomScoreType,       _read_int_from_proc("oom_score", 0),        None),
        pid=    ('p',   PIDType,            "pid",                                      None),
        ppid=   ('P',   PIDType,            "ppid",                                     None),
        rssh=   ('r',   MemSizeHumanType,   "memory_info",                              (_get_rss, _format_human_size)),
        rssk=   ('R',   MemSizeKType,       "memory_info",                              (_get_rss, _bytes_to_kiB)),
        start=  ('s',   StartTimeHumanType, "create_time",                              (_format_date_time,)),
        starts= ('S',   StartTimeSecsType,  "create_time",                              (_float_to_int,)),
        tty=    ('y',   TtyType,            "terminal",                                 None),
        uid=    ('U',   UIDType,            "uids",                                     (_get_uid,)),
        user=   ('u',   UsernameType,       "username",                                 None),
        vszh=   ('v',   MemSizeHumanType,   "memory_info",                              (_get_vsz, _format_human_size)),
        vszk=   ('V',   MemSizeKType,       "memory_info",                              (_get_vsz, _bytes_to_kiB)),
        wd=     ('w',   WorkingDirType,     "cwd",                                      None),
)


# TODO: To get number of pages (virtual or RSS), check out:
#   $ cat /proc/$pid/statm
#   1461407 22849 13530 39075 0 69932 0
#
#   $ cat /proc/$pid/status
#   <snip long>
#   VmSize:	 5845628 kB
#   <snip>
#   VmRSS:	   91648 kB
#
#   $ man 5 proc  # then search for "measured in pages"
#        /proc/[pid]/statm
#               Provides information about memory usage, measured in pages.  The columns are:
# 
#                   size       (1) total program size
#                              (same as VmSize in /proc/[pid]/status)
#                   resident   (2) resident set size
#                              (same as VmRSS in /proc/[pid]/status)
#                   shared     (3) number of resident shared pages (i.e., backed by a file)
#                              (same as RssFile+RssShmem in /proc/[pid]/status)
#                   text       (4) text (code)
#                   lib        (5) library (unused since Linux 2.6; always 0)
#                   data       (6) data + stack
#                   dt         (7) dirty pages (unused since Linux 2.6; always 0)
#
# This functionality is not supported by `psutil`, so it should go into `_procio`.


MemoryInfo = namedtuple("MemoryInfo", (
        "mem_total_KiB", "mem_free_KiB", "mem_used_KiB",
        "mem_avail_KiB", "mem_avail_perc", "mem_buff_cache_KiB",
        "swap_total_KiB", "swap_free_KiB", "swap_used_KiB"))

def _collect_memory_info():
    # https://psutil.readthedocs.io/en/latest/#psutil.virtual_memory
    virt_mem_info = psutil_virtual_memory()
    # https://psutil.readthedocs.io/en/latest/#psutil.swap_memory
    swap_mem_info = psutil_swap_memory()

    # "total physical memory (excluding swap)"
    mem_total = virt_mem_info.total
    # instantly available, "without the system going into swap"
    mem_avail = virt_mem_info.available
    # "percentage usage calculated as `(total - available) / total * 100`"
    mem_avail_perc = 100.0 - virt_mem_info.percent
    # "memory not being used at all (zeroed) that is readily available"
    # "this doesn't reflect the actual memory available (use available instead)"
    mem_free  = virt_mem_info.free
    # "designed for informational purposes only"
    mem_used = virt_mem_info.used
    # "(Linux, BSD)"
    mem_buffer_cached = virt_mem_info.buffers + virt_mem_info.cached

    # "total swap memory in bytes"
    swap_total = swap_mem_info.total
    swap_free = swap_mem_info.free
    swap_used = swap_mem_info.used

    return MemoryInfo(
            mem_total >> 10,
            mem_free >> 10,
            mem_used >> 10,
            mem_avail >> 10,
            mem_avail_perc,
            mem_buffer_cached >> 10,
            swap_total >> 10,
            swap_free >> 10,
            swap_used >> 10)


def _collect_header_info():
    memory_info = _collect_memory_info()
    overcommit_settings = read_overcommit_settings()

    return (memory_info, overcommit_settings)


def _get_field_info(field_names, psutil_attr_names=None):
    field_accessors = []
    field_types = []
    # The caller can supply `psutil_attr_names`, so we can add more values
    # into an existing set rather than creating a new set.
    if psutil_attr_names is None:
        psutil_attr_names = set()
    else:
        assert isinstance(psutil_attr_names, set)

    # Construct the list of attributes names to query.  Avoid duplicates.
    #  https://psutil.readthedocs.io/en/latest/#psutil.process_iter
    #  https://psutil.readthedocs.io/en/latest/#psutil.Process.as_dict
    # While we're iterating, check the validity of each supplied field name.
    for field_name in field_names:
        try:
            (field_code, field_type, attr_name_or_func, post_processing) = _ALL_FIELDS[field_name]
        except KeyError as e:
            # Invalid field name
            raise ValueError("invalid field name: %s" % field_name)

        is_attr_name = isinstance(attr_name_or_func, str)
        field_accessors.append((field_name, is_attr_name, attr_name_or_func, post_processing))
        field_types.append(field_type)
        if is_attr_name:
            psutil_attr_names.add(attr_name_or_func)

    return (tuple(field_accessors), tuple(field_types), psutil_attr_names)


def _select_processes(AllFields, field_accessors, psutil_attr_names, selection_funcs, post_proc_settings):
    selected_processes = []

    # Pre-initialise re-usable list `field_values` to the appropriate length,
    # so we can update a pre-allocated list in-place.
    field_values = [None for field in field_accessors]

    # Function `psutil.process_iter` yields a `psutil.Process` for each process
    # running on the system.  Processes are yielded in ascending order of PID
    # (ie, successive PIDs increase).
    #
    # Other benefits of using `psutil.process_iter` (according to the docs):
    #  1. It's "safe from race condition[s]" [1].
    #  2. If a list of attr-names is supplied, it will have the "same meaning"
    #    as in `psutil.Process.as_dict` [1] (and will yield the same speed-up,
    #    because only those specific attributes will be retrieved, rather than
    #    "all process info" being retrieved, which is apparently "slow") [1].
    #  3. This `psutil.Process.as_dict` "uses `oneshot()` context manager" [2],
    #    "which considerably speeds up the retrieval of multiple process
    #    information at the same time" [3], because "different process info
    #    <snip> may be fetched by using the same routine, but only one value
    #    is returned and the others are discarded" [3].
    #
    # [1] https://psutil.readthedocs.io/en/latest/#psutil.process_iter
    # [2] https://psutil.readthedocs.io/en/latest/#psutil.Process.as_dict
    # [3] https://psutil.readthedocs.io/en/latest/#psutil.Process.oneshot
    psutil_attr_names = tuple(psutil_attr_names)  # for speed
    for proc in psutil_process_iter(psutil_attr_names):
        attr_dict = proc.info
        for field_idx, (field_name, is_attr_name, accessor, post_processing) in enumerate(field_accessors):
            # Note:  There might be more fields requested than psutil attributes
            # returned, because not all the fields that can be requested, can be
            # obtained directly from psutil Process results.  Also, some fields
            # use the same psutil attribute, which would also cause a disparity.
            #
            # Furthermore, some psutil attributes might be used for sorting,
            # not for requested fields, so that's another reason for a mismatch.
            #
            # So there's no point in trying to "zip" the list of fields directly
            # with the iterable `attr_dict.items()`.
            field_value = attr_dict[accessor] if is_attr_name else accessor(proc)

            # `post_processing` will be `None` or a sequence of functions.
            if post_processing is not None:
                for pp_func in post_processing:
                    field_value = pp_func(field_value, post_proc_settings)

            # Update the elements of the pre-allocated list in-place.
            field_values[field_idx] = field_value

        all_fields = AllFields(*field_values)
        is_selected_process = False
        if not selection_funcs:
            # No `selection_funcs` were supplied, so we default to selecting
            # ALL processes.
            is_selected_process = True
        else:
            for f in selection_funcs:
                if f(all_fields):
                    is_selected_process = True
                    break

        if is_selected_process:
            selected_processes.append(all_fields)

    return selected_processes


## These process selection criteria match the processes using field values
## just like the ones that are returned to the caller.

class ProcessSelectionCriterion(metaclass=ABCMeta):
    """Match processes using field values like the ones returned to the caller."""
    # Attribute `_repr` will be a pre-calculated, cached "representation"
    # for each distinct derived class of this abstract base class.
    #
    # This representation will ensure that derived classes can be hashed, and
    # compared for equality & inequality, based on class-type & member-values,
    # not on the default of instance memory-address.  The equality/inequality
    # comparison will work correctly for derived classes of the same type, but
    # ALSO between derived classes of different types.
    #
    # The comparison & hashing calculations will be as efficient as possible.
    # We store instances of the derived classes in a `set` for uniqueness, so
    # we want hashing & equality comparisons to be correct, but as efficient
    # as possible.
    #
    # The representation will also be used to provide a consistent, useful
    # `__repr__` string-representation for all derived types.
    #
    # If a derived class contains no instance-specific attributes, its repr
    # will simply be the `id()` (memory-address) of its class type instance.
    # This will effectively distinguish, with a single integer comparison,
    # between derived classes of different types.  For example:
    #
    # If a derived class *does* possess some instance-specific attributes, its
    # repr will be a tuple of the `id()` of its class type instance, followed
    # by all of its instance-specific attributes.
    __slots__ = ("_repr",)

    def __init__(self, *derived_args):
        """Derived classes MUST call this super-class `__init__` method.

        Calling this `super().__init__` method will set the `_repr` attribute,
        mixing-in any extra parameters that are specific to that derived class.
        """
        if derived_args:
            # Parameter `derived_args` will be a tuple of any extra arguments
            # passed from the `__init__` method of the derived class.
            #
            # We'll mix these extra attributes into `_repr`.
            self._repr = (id(self.__class__),) + derived_args
        else:
            self._repr = id(self.__class__)

    @abstractmethod
    def field_names(self):
        """Return a tuple of the field names required for this criterion.

        This method must be overridden in derived classes.
        """
        pass

    @abstractmethod
    def get_func(self):
        """Return a function closure that tests the field values of a process.

        The function closure will expect a single argument that has attributes
        that include the field names required for this criterion.

        The function will return a boolean result: whether the process matches.

        This method must be overridden in derived classes.
        """
        pass

    def __repr__(self):
        """Return an unambiguous string representation of an instance.

        This method does NOT need to be overridden; it will work as-is in all
        derived classes.  But it requires that the `_repr` attribute was set
        correctly by the `super().__init__` method of this super-class.
        """
        if isinstance(self._repr, int):
            # The representation is just the memory address of the class type.
            # There were no extra arguments; just use the derived class name.
            return "%s()" % self.__class__.__name__
        else:
            # There *were* extra arguments; use them too, after the class name.
            args_fmt = ", ".join("%r" for arg in self._repr[1:])
            args = args_fmt % self._repr[1:]
            return "%s(%s)" % (self.__class__.__name__, args)

    def __eq__(self, other):
        """Return equality based on type & member-values, not on memory-address.

        This method does NOT need to be overridden; it will work as-is in all
        derived classes.  But it requires that the `_repr` attribute was set
        correctly by the `super().__init__` method of this super-class.
        """
        return getattr(other, "_repr", None) == self._repr

    def __ne__(self, other):
        """Return in-equality based on type & member-values, not on memory-address.

        This method does NOT need to be overridden; it will work as-is in all
        derived classes.  But it requires that the `_repr` attribute was set
        correctly by the `super().__init__` method of this super-class.
        """
        return getattr(other, "_repr", None) != self._repr

    def __hash__(self):
        """Return a hash-value based on type & member-values, not on memory-address.

        This method does NOT need to be overridden; it will work as-is in all
        derived classes.  But it requires that the `_repr` attribute was set
        correctly by the `super().__init__` method of this super-class.
        """
        return hash(self._repr)


class ProcessHasTty(ProcessSelectionCriterion):
    """Match processes that are associated with a TTY (terminal)."""
    __slots__ = ()
    _field_names = ("tty",)

    def __init__(self):
        super().__init__()

    def field_names(self):
        return self._field_names

    def get_func(self):
        return (lambda process: process.tty is not None)


class ProcessUidEquals(ProcessSelectionCriterion):
    """Match processes owned by a user whose UID equals supplied `uid`."""
    __slots__ = ("_uid_to_equal")
    _field_names = ("uid",)

    def __init__(self, uid):
        super().__init__(uid)
        self._uid_to_equal = uid

    def field_names(self):
        return self._field_names

    def get_func(self):
        return (lambda process: process.uid == self._uid_to_equal)


class SortByField(object):
    """Sort by a single specified field."""
    __slots__ = ("field_name", "reverse")

    def __init__(self, field_name, reverse=False):
        self.field_name = field_name
        self.reverse = reverse

    def __repr__(self):
        return "%s(%r, reverse=%r)" % (__class__.__name__, self.field_name, self.reverse)


def query_fields(fields_to_query,
        selection_criteria=(),
        filtering_criteria=(),  # TODO: Implement
        sort_by_fields=(),  # TODO: Document
        return_field_types=False,
        return_header_info=False,
        use_base10_human_size=False):
    """Select processes; query the fields requested in `fields_to_query`.

    Results will be returned as a list of instances of type `QueriedProcess`,
    one `QueriedProcess` instance for each process selected.  The list will be
    sorted by process ID (PID) by default.

    Type `QueriedProcess` will be a new `namedtuple` type defined on-the-fly to
    contain the results of this specific query; there will be one named-tuple
    field in `QueriedProcess` for each field specified in `fields_to_query`.
    A different field-request will result in a different `QueriedProcess` type.

    Even the order of the named-tuple fields in `QueriedProcess` depends upon
    the iteration-order of the fields in `fields_to_query`; so it's recommended
    that `fields_to_query` is an ordered collection type (eg, `list`, `tuple`),
    to ensure that the tuple fields in `QueriedProcess` are defined in an order
    that is predictable & useful to you.

    It's an error if `fields_to_query` contains:
     - duplicate field names; or
     - no field names (ie, it's an empty container)
    In either of these cases, a `ValueError` will be raised.

    If `selection_criteria` is an empty container (the default), ALL running
    processes will be selected.

    If `selection_criteria` is non-empty, it must contain only instances
    of types that derive from abstract class `ProcessSelectionCriterion`;
    examples include the classes `ProcessHasTty` & `ProcessUidEquals`.

    A running process will be selected if it fulfills *ANY* of the specified
    selection criteria.  Because matching *any* of the criteria will result in
    the selection of a process, the order of criteria-testing does not matter.
    Hence, the supplied container `selection_criteria` does NOT need to be an
    ordered collection type.
    """
    # First, ensure that `fields_to_query` is not empty.
    num_fields_to_query = len(fields_to_query)
    if num_fields_to_query == 0:
        raise ValueError("no field names supplied: %s" % fields_to_query)
    # Second, ensure there are no duplicates in `fields_to_query`.
    all_field_names_in_set = set(fields_to_query)  # A `set` contains no duplicates.
    if num_fields_to_query != len(all_field_names_in_set):
        raise ValueError("duplicate field names supplied: %s" % ",".join(fields_to_query))

    # Now convert `fields_to_query` to a `tuple`, to ensure fastest iteration.
    # [And also to ensure it's immutable, so we can't accidentally mutate it.]
    if not isinstance(fields_to_query, tuple):
        fields_to_query = tuple(fields_to_query)
    QueriedProcess = namedtuple("QueriedProcess", fields_to_query)

    # Now create our own `list` copy of the supplied collection of field names
    # to query, so that we *can* modify our list if necessary (to add fields
    # for process selection, filtering, and sorting) while still maintaining
    # the ordering of the first `fields_to_query`.
    all_field_names_in_list = list(fields_to_query)

    # Add the field names required for process selection.
    # We want to maintain the order of the first `fields_to_query` in this list,
    # so we append to the end of the list.  But we don't want duplicates in this
    # list (because we'll also use it to define field names in a `namedtuple`),
    # so we only append new fields if they're not already in the list (which we
    # check by also maintaining a set of field names).
    selection_funcs = []
    for select_crit in selection_criteria:
        selection_funcs.append(select_crit.get_func())
        selection_fields = select_crit.field_names()
        for f in selection_fields:
            if f not in all_field_names_in_set:
                all_field_names_in_set.add(f)
                all_field_names_in_list.append(f)

    # Add the field names required for process sorting.
    for sbf in sort_by_fields:
        f = sbf.field_name
        # And while we're iterating through a collection of (what we assume are)
        # `SortByField` instances, verify that they actually have the expected
        # `.reverse` attribute (in addition to the `.field_name` attribute).
        r = sbf.reverse
        if f not in all_field_names_in_set:
            all_field_names_in_set.add(f)
            all_field_names_in_list.append(f)

    # TODO: Do the same thing for the filtering fields (if any).

    # Named-tuple `AllFields` enables a "Decorate-Sort-Undecorate"-like idiom
    # that we use for process selection, filtering & sorting:
    #  https://docs.python.org/3/howto/sorting.html#the-old-way-using-decorate-sort-undecorate
    (all_field_accessors, all_field_types, psutil_attr_names) = \
            _get_field_info(all_field_names_in_list)
    AllFields = namedtuple("AllFields", tuple(all_field_names_in_list))

    post_proc_settings = \
            get_post_proc_settings(
                    use_base10_human_size=use_base10_human_size)

    selected_processes = \
            _select_processes(AllFields, all_field_accessors,
                    psutil_attr_names, selection_funcs, post_proc_settings)

    # Now sort the selected processes by the specified sort criteria (if any).
    #
    # If multiple sort criteria were specified, we collect them into a tuple
    # (in the order they were supplied as command-line options, left-to-right
    # on the command-line: first option supplied => first element in tuple;
    # etc.) and then perform a single-pass lexicographical sort of the tuple
    # (in which the first element of the tuple has the highest priority in the
    # sort; etc.).
    #
    # [OK, confession time:  We don't actually do that; we actually *reverse*
    # the list of sort criteria, so that we sort in reverse order of fields,
    # because apparently Python's Timsort "does multiple sorts efficiently" [1].
    # But the result should be the same!]
    #
    # [1] https://docs.python.org/3/howto/sorting.html#sort-stability-and-complex-sorts
    #
    # So the first command-line sort-option supplied, will have the highest
    # priority; and each successive sort-option supplied on the command-line,
    # will be used only for differentiation between tied sorts in the earlier
    # sort-options.
    #
    # [This seems like the most-reasonable, least-surprising way to interpret
    # multiple command-line sort-options.]
    if len(sort_by_fields) == 1:
        # There was just one sort criterion supplied.
        sbf = sort_by_fields[0]
        selected_processes.sort(key=attrgetter(sbf.field_name), reverse=sbf.reverse)
    elif len(sort_by_fields) > 1:
        # Create our own `list` copy of `sort_by_fields` so we can reverse it.
        sort_by_fields = list(sort_by_fields)
        sort_by_fields.reverse()
        for sbf in sort_by_fields:
            selected_processes.sort(key=attrgetter(sbf.field_name), reverse=sbf.reverse)

    # Now "undecorate" the `AllFields`, converting it to `QueriedProcess`
    # by slicing `[:num_fields_to_query]` and `*`-expanding it into the
    # constructor of `QueriedProcess, then replace the `AllFields` instance
    # with the new `QueriedProcess` instance, in-place in the sorted list.
    for idx, fields in enumerate(selected_processes):
        selected_processes[idx] = QueriedProcess(*(fields[:num_fields_to_query]))

    if return_field_types or return_header_info:
        result = (selected_processes,)
        if return_field_types:
            result += (all_field_types[:num_fields_to_query],)
        if return_header_info:
            result += _collect_header_info()
        return result
    else:
        return selected_processes

