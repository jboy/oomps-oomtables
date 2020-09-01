# Copyright (c) 2020 James Boyden <jboy@jboy.me>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Definitions of the per-process fields that may be requested & queried."""

from collections import namedtuple
from time import localtime, strftime
from time import time as utc_time_now

# Use `_procio` to augment the capabilities of `psutil`.
from ._procio import read_int_from_proc_pid


## Settings for the post-processing functions: named-tuple `PostProcSettings`

# These settings are calculated, and a `PostProcSettings` instance is created,
# when function `get_post_proc_settings` is called.
#
# Note:  We store `utc_now` (obtained from `time.time()`, as `utc_time_now()`)
# because method `Process.create_time()` returns "The process creation time
# as a floating point number expressed in seconds since the epoch, in UTC."
#  -- https://psutil.readthedocs.io/en/latest/#psutil.Process.create_time
#
# Note #2:  In contrast, we expect `this_yday` & `this_year` to be *localtime*
# (as if converted from a UTC time returned by `Process.create_time()` or
# the Python `time.time()` function, using the `time.localtime()` function).
# We require `this_yday` & `this_year` to be localtime, *NOT* UTC, because we
# are checking the boundaries of days (at midnight, localtime).
PostProcSettings = namedtuple("PostProcSettings", (
        # Caller-specified string (defaults to a space character " ") that will
        # separate the command & each argument in a joined command-line string
        # (field-type "cmds") returned by post-processing func `_join_cmdline`.
        "cmdline_sep",
        # Caller's choice of "human-readable" size units: base-10 or base-2.
        # They are provided by function `_get_human_size_units`.
        "human_scale", "human_denom", "human_units", "human_final",
        # Today's date (localtime), integer values `yday` & `year`.
        # Calculated and stored, when func `get_post_proc_settings` is called.
        "this_yday", "this_year",
        # Floating-point seconds since the epoch, in UTC, of right now.
        # Calculated and stored, when func `get_post_proc_settings` is called.
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


## Field-accessor functions & post-processing functions:
##  func(value, pid, post_proc_settings) -> value

def _read_int_from_proc(fname, default_int=None):
    assert (default_int is None) or isinstance(default_int, int)
    return read_int_from_proc_pid(fname, default_int)


def _bytes_to_kiB(num_bytes, pid, post_proc_settings):
    """Convert a number of bytes to the corresp number of "kibibytes" (kiB).

    This function is needed because method `Process.memory_info()` states
    "All numbers are expressed in bytes."
     -- https://psutil.readthedocs.io/en/latest/#psutil.Process.memory_info
    """
    # TODO: Make this support base-10 (ie, `num_bytes // 1000`) if `post_proc_settings` says so?
    return (num_bytes >> 10)


def _calc_desk_time(float_creation_time, pid, post_proc_settings):
    return (post_proc_settings.utc_now - float_creation_time)


def _float_to_int(float_val, pid, post_proc_settings):
    # In Python2, built-in `round` returns a `float`; in Python3, an `int`.
    return int(round(float_val))


def _format_date_time(float_date_time, pid, post_proc_settings):
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


def _format_human_size(num_bytes, pid, post_proc_settings):
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


def _format_time_delta(float_time_delta, pid, post_proc_settings):
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


def _get_rsz(memory_info_tuple, pid, post_proc_settings):
    return memory_info_tuple.rss


def _get_uid(uids_tuple, pid, post_proc_settings):
    # "The real, effective and saved user ids of this process as a named tuple.
    # This is the same as os.getresuid but can be used for any process PID."
    #  -- https://psutil.readthedocs.io/en/latest/#psutil.Process.uids
    #
    # "Return a tuple (ruid, euid, suid) denoting the current process's
    # real, effective, and saved user ids."
    #  -- https://docs.python.org/3/library/os.html#os.getresuid
    (ruid, euid, suid) = uids_tuple
    return ruid


def _get_vsz(memory_info_tuple, pid, post_proc_settings):
    return memory_info_tuple.vms


def _join_cmdline(cmdline_array, pid, post_proc_settings):
    return post_proc_settings.cmdline_sep.join(cmdline_array)


def _list_to_tuple(list_val, pid, post_proc_settings):
    return tuple(list_val)


def _sum_cpu_times(cpu_times_tuple, pid, post_proc_settings):
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
CmdlineArrayType = FieldType("CmdlineArray",    tuple,  100,    160,    None,   'L',
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
        "Current working directory (absolute path) of process")


## Field infos
Fi = namedtuple("FieldInfo", (
        # The field key as a 1-character string, or `None` if 1-character key.
        # This is called "key" after the terminology used in `man ps`, when it
        # talks about "sort keys" & "short keys".
        "key",

        # The FieldType
        "field_type",

        # A tuple of `psutil` attribute names that must be queried for this field.
        # May be the empty tuple if this field value is not available from `psutil`.
        # To increase readability and decrease boilerplate, if there's just
        # a single tuple element, the surrounding tuple can be elided.
        "attr_names",

        # A tuple of field-accessor / post-processing functions, or empty tuple.
        # Each function must take parameters `(value, pid, post_proc_settings)`
        # and will return a new value.
        # To increase readability & decrease boilerplate, if there's just
        # a single tuple element, the surrounding tuple can be elided.
        "acc_funcs",

        # A human-readable description of the FieldInfo (like help).
        "descr"))


# The master-list of field definitions.
_ALL_FIELD_DEFS = dict(
        # NAME  Fi( CODE    FIELD_TYPE
        adj=    Fi( 'a',    OomScoreAdjType,
                        # ATTR_NAMES
                        (),
                        # ACCESSOR / POST-PROCESSING FUNCS
                        _read_int_from_proc("oom_score_adj", 0),
                        "OOM Score Adjustment (Linux 2.6.36 and later): [-1000, 1000]"
                ),

        adjd=   Fi( 'A',    OomAdjType,
                        (),
                        _read_int_from_proc("oom_adj", 0),
                        "OOM Adjustment (pre-Linux 2.6.36; now deprecated): [-17, +15]"
                ),

        cmda=   Fi( 'C',    CmdlineArrayType,
                        "cmdline",
                        # Return the "command-line as an array" as a `tuple`
                        # rather than a `list`, so it's immutable.
                        _list_to_tuple,
                        "Command-line (invoked command & args) as an array of strings"
                ),

        cmds=   Fi( 'c',    CmdlineStringType,
                        "cmdline",
                        _join_cmdline,
                        "Command-line (invoked command & args) joined as a single string"
                ),

        ctime=  Fi( 't',    TimeDeltaHumanType,
                        "cpu_times",
                        (_sum_cpu_times, _format_time_delta),
                        "Accumulated CPU time, user + system, in human-readable format"
                ),

        ctimes= Fi( 'T',    TimeDeltaSecsType,
                        "cpu_times",
                        (_sum_cpu_times, _float_to_int),
                        "Accumulated CPU time, user + system, in integer seconds"
                ),

        dtime=  Fi( 'd',    TimeDeltaHumanType,
                        "create_time",
                        (_calc_desk_time, _format_time_delta),
                        "\"Desk\" time since the process started, in human-readable format"
                ),

        dtimes= Fi( 'D',    TimeDeltaSecsType,
                        "create_time",
                        (_calc_desk_time, _float_to_int),
                        "\"Desk\" time since the process started, in integer seconds"
                ),

        #euid=   Fi( 'E',  "proc.uids()"
        #euser=  Fi( 'e',  ???

        exe=    Fi( 'x',    ExeNameType,
                        "name",
                        (),
                        "Executable name (without path)"
                ),

        exep=   Fi( 'X',    ExePathNameType,
                        "exe",
                        (),
                        "Executable name (with absolute path)"
                ),

        #gid=    Fi( 'g',  "proc.gids()"
        #npgv=   Fi( 'n',  ???
        #npgr=   Fi( 'n',  ???

        ooms=   Fi( 'o',    OomScoreType,
                        (),
                        _read_int_from_proc("oom_score", 0),
                        "Linux OOM Score: [0, 1000]"
                ),

        pid=    Fi( 'p',    PIDType,
                        "pid",
                        (),
                        "Process ID (integer)"
                ),

        ppid=   Fi( 'P',    PIDType,
                        "ppid",
                        (),
                        "Parent process ID (integer)"
                ),

        rszh=   Fi( 'r',    MemSizeHumanType,
                        "memory_info",
                        (_get_rsz, _format_human_size),
                        "Resident set size in memory, in human-readable format"
                ),

        rszk=   Fi( 'R',    MemSizeKType,
                        "memory_info",
                        (_get_rsz, _bytes_to_kiB),
                        "Resident set size in memory, in KB or KiB"
                ),

        start=  Fi( 's',    StartTimeHumanType,
                        "create_time",
                        _format_date_time,
                        "Start-time of process (UTC), in human-readable format"
                ),

        starts= Fi( 'S',    StartTimeSecsType,
                        "create_time",
                        _float_to_int,
                        "Start-time of process (UTC), in seconds since UNIX epoch"
                ),

        tty=    Fi( 'y',    TtyType,
                        "terminal",
                        (),
                        "Terminal associated with the process"
                ),

        uid=    Fi( 'U',    UIDType,
                        "uids",
                        _get_uid,
                        "User ID (integer)"
                ),

        user=   Fi( 'u',    UsernameType,
                        "username",
                        (),
                        "Username (string)"
                ),

        vszh=   Fi( 'v',    MemSizeHumanType,
                        "memory_info",
                        (_get_vsz, _format_human_size),
                        "Virtual memory size, in human-readable format"
                ),

        vszk=   Fi( 'V',    MemSizeKType,
                        "memory_info",
                        (_get_vsz, _bytes_to_kiB),
                        "Virtual memory size, in KB or KiB"
                ),

        wd=     Fi( 'w',    WorkingDirType,
                        "cwd",
                        (),
                        "Current working directory (absolute path) of process"
                ),
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


def get_field_info(field_name):
    """Access the FieldInfo for supplied `field_name`.

    If `field_name` is not valid, raise `ValueError`.
    """
    try:
        return _ALL_FIELD_DEFS[field_name]
    except KeyError as e:
        # Invalid field name.
        raise ValueError("invalid field name: %s" % field_name)


def list_all_fields():
    headers = ("NAME", "KEY", "DESCR")
    all_fields = []
    for field_name, field_info in _ALL_FIELD_DEFS.items():
        key = field_info.key
        all_fields.append((field_name, key if key is not None else "", field_info.descr))
    return (headers, all_fields)
