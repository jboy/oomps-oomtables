# Copyright (c) 2020 James Boyden <jboy@jboy.me>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Functions to query the Linux proc-filesystem that are missing from `psutil`."""

from collections import namedtuple


def _read_int_from_file(fullpath, default=None):
    """Open the file with path `fullpath` and attempt to read an `int` value.

    If there are any problems or errors, exceptions will be raised; unless the
    value of `default` is not `None`, in which case the value of `default` will
    be returned instead of raising exceptions.
    """
    try:
        val = open(fullpath, 'r').read()
    except Exception as e:  # FileNotFoundError in Python3; IOError in Python2
        if default is not None:
            return default
        else:
            raise

    try:
        return int(val)
    except Exception as e:  # Probably ValueError due to failed `int` conversion
        if default is not None:
            return default
        # Don't raise a new ValueError at this point, or else Python will complain:
        # "During handling of the above exception, another exception occurred:"
        # Instead, quietly complete this block, then raise a new exception.

    # If we got to here, we did not successfully `return int(val)`.
    # Now we can safely raise our exception.
    raise ValueError("did not read int from file `%s`: %s" % (fullpath, repr(val)))


def read_int_from_proc_pid(fname, default_int=None):
    """Return a function that reads an `int` from file "/proc/${pid}/${fname}".

    The `fname` is supplied to *this* function (so that the returned function
    will read the same `fname` per-PID) but the `pid` will be supplied to the
    returned function when it is being called (so the returned function can be
    called per-process).

    To obtain the PID, the returned function will attempt to access attribute
    `process.pid` of its parameter `process`.
    """
    # Verify that `default_int` is either `None` or an `int`, to ensure
    # that this function returns an `int` or raises an exception trying.
    if (default_int is not None) and not isinstance(default_int, int):
        raise ValueError("invalid `default_int`: %s" % default_int)

    fullpath_pid_template = "/proc/%%d/%s" % fname
    def _impl(process):
        fullpath = fullpath_pid_template % process.pid
        return _read_int_from_file(fullpath, default_int)
    return _impl


OvercommitSettings = namedtuple("OvercommitSettings", ("mode", "descr", "ratio"))

_OVERCOMMIT_DESCRS = [
        "heuristic overcommit (default)",
        "always overcommit, never check",
        "always check, never overcommit"
]

def read_overcommit_settings(raise_on_error=True):
    """Return overcommit settings (mode number, mode descr, ratio).

    If any error occurs (eg, expected files not found in the proc-filesystem),
    allow the usual exceptions to be raised; unless `raise_on_error` is `False`,
    in which case, the error will be suppressed and `None` will be returned.
    """
    # https://www.kernel.org/doc/Documentation/vm/overcommit-accounting
    # https://serverfault.com/questions/606185/how-does-vm-overcommit-memory-work
    try:
        mode = _read_int_from_file("/proc/sys/vm/overcommit_memory")
        descr = _OVERCOMMIT_DESCRS[mode]
    except Exception as e:
        if raise_on_error:
            raise
        else:
            # Suppress the error; return `None`.
            mode = None
            descr = None

    # https://engineering.pivotal.io/post/virtual_memory_settings_in_linux_-_the_problem_with_overcommit
    try:
        ratio = _read_int_from_file("/proc/sys/vm/overcommit_ratio")
    except Exception as e:
        if raise_on_error:
            raise
        else:
            # Suppress the error; return `None`.
            ratio = None

    return OvercommitSettings(mode, descr, ratio)
