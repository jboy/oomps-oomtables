# Copyright (c) 2020 James Boyden <jboy@jboy.me>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Like `ps` or `top`, but for per-process memory usage & Linux OOM Score."""

import os
import shutil

# https://pypi.org/project/click/
# https://palletsprojects.com/p/click/
import click
import psquery


class ParsedSelectionCriteria(object):
    def __init__(self, default=None):
        self.selection_criteria = set()
        self.really_all_procs = False
        self._default = default

    def deliver(self):
        """Deliver a possibly-empty tuple of parsed selection criteria."""
        if self.really_all_procs:
            # Select ALL processes, even processes NOT associated with a TTY.
            # After this option or arg, all other args are redundant.
            return ()
        elif len(self.selection_criteria) > 0:
            # Convert the `set` to a `tuple` for consistency with the other two
            # return values.
            return tuple(self.selection_criteria)
        else:
            return (self._default,)


_DEFAULT_FIELDS = "user pid ppid start dtime vszh adj ooms cmds"


@click.command()
@click.option('-a', '--all-procs', is_flag=True,
        help="Select all processes that have a TTY.")

@click.option('-A', '--really-all-procs', is_flag=True,
        help="Select ALL processes, even without a TTY.")

@click.option('-o', '--sort-by-oom', 'sort_by_field_options', multiple=True, flag_value="ooms",
        help="Sort by (ascending) OOM Score.")

@click.option('-O', '--rev-sort-by-oom', 'sort_by_field_options', multiple=True, flag_value="-ooms",
        help="Sort by descending OOM Score.")

@click.option('-r', '--sort-by-rss', 'sort_by_field_options', multiple=True, flag_value="rssk",
        help="Sort by (ascending) Resident Set Size.")

@click.option('-R', '--rev-sort-by-rss', 'sort_by_field_options', multiple=True, flag_value="-rssk",
        help="Sort by descending Resident Set Size.")

@click.option('-s', '--sort-by-start', 'sort_by_field_options', multiple=True, flag_value="starts",
        help="Sort by (ascending) start time.")

@click.option('-S', '--rev-sort-by-start', 'sort_by_field_options', multiple=True, flag_value="-starts",
        help="Sort by descending start time.")

@click.option('-v', '--sort-by-vsz', 'sort_by_field_options', multiple=True, flag_value="vszk",
        help="Sort by (ascending) Virtual Memory Size.")

@click.option('-V', '--rev-sort-by-vsz', 'sort_by_field_options', multiple=True, flag_value="-vszk",
        help="Sort by descending Virtual Memory Size.")

@click.argument('args', nargs=-1)
def oomps(
        all_procs,
        really_all_procs,
        sort_by_field_options,
        args):
    """Like `ps` or `top`, but for per-process memory usage & Linux OOM Score.

    \b
    ARGS might be any of:
      ~ : Select only processes owned by the caller's UID.
      / : Select all processes that have a TTY.
      // : Select ALL processes, even without a TTY.
    """
    (parsed_selection_criteria, fields_to_query) = \
            _parse_args(all_procs, really_all_procs, args)

    # Parse the sorting options.
    sort_by_fields = []
    # If none of the `sort_by_field_options` flags are specified, the default
    # of `sort_by_field_options` will be `None`, not an empty collection.
    # You can't iterate over `None`!
    if sort_by_field_options:
        for flag_value in sort_by_field_options:
            if flag_value.startswith('-'):
                # It's a reverse sort, eg "-vszk".
                sort_by_fields.append(psquery.SortByField(flag_value[1:], reverse=True))
            else:
                sort_by_fields.append(psquery.SortByField(flag_value))
    # The first sort field should be the highest priority; the second should
    # be the second-highest priority; etc.  So we'll maintain this ordering,
    # but put them all into a tuple.
    sort_by_fields = tuple(sort_by_fields)

    # Long lines will be automatically truncated if this script's output is
    # connected to a terminal.  Otherwise, if this script's output is connected
    # to a pipeline (such as `less` or even just `cat`), long lines will NOT be
    # truncated.
    #
    # Helpful Tip: If you're using `less`, use `less -S` to truncate long lines
    # of output at the terminal width (rather than the default of wrapping).
    terminal_width = _get_terminal_width()

    # Note:  We only pass the *ordered* collection `fields_to_query` into
    # `psquery.query_fields`, to ensure that we receive a `QueriedProcess`
    # named-tuple result that has fields in a predictable & useful order.
    (queried_procs, field_types, memory_info, overcommit_settings) = \
            psquery.query_fields(fields_to_query,
                    selection_criteria=parsed_selection_criteria.deliver(),
                    sort_by_fields=sort_by_fields,
                    return_field_types=True, return_header_info=True)

    click.echo(_format_memory_info(memory_info))
    click.echo(_format_overcommit_settings(overcommit_settings))

    #field_formats = [("{:%s}" % ft.rec_max_len) for ft in field_types]
    # Make use of the tuple-nature of namedtuple `QueriedProcess`:
    # Use old-style `("%s %s %s" % tup)` string-formatting.
    field_formats = [
            ("%%%s%ds" % ("-" if ft.alignment == 'L' else "", ft.rec_max_len))
            for ft in field_types]
    # But don't pad the last field with trailing whitespace.
    # That is, if the last field is left-aligned, don't pad it.
    if field_types[-1].alignment == 'L':
        # The last field *is* left-aligned, so it *has* been padded
        # with trailing whitespace.  Change the last format string
        # so the last field will *not* be padded.
        field_formats[-1] = "%-s"
    proc_format = " ".join(field_formats)
    click.echo((proc_format % tuple(fields_to_query)).upper()[:terminal_width])
    for qp in queried_procs:
        # Make use of the tuple-nature of namedtuple `QueriedProcess`.
        # Use old-style `("%s %s %s" % tup)` string-formatting.
        click.echo((proc_format % qp)[:terminal_width])


def _parse_args(all_procs, really_all_procs, args):
    """Parse the non-option command-line args, and the few "widening" options.

    These parsed args will yield:
     - the initial process selection criteria (before any filtering options)
     - the fields to query
    """
    this_process_ruid = os.getuid()
    this_process_home = os.path.expanduser("~")
    default_criterion = psquery.ProcessUidEquals(this_process_ruid)
    parsed_selection_criteria = ParsedSelectionCriteria(default_criterion)

    fields_to_query = _DEFAULT_FIELDS.split()

    if really_all_procs:
        # Select ALL processes, even processes NOT associated with a TTY.
        # After this option or arg, all other args are redundant.
        parsed_selection_criteria.really_all_procs = True
    elif all_procs:
        parsed_selection_criteria.selection_criteria.add(psquery.ProcessHasTty())

    # Input:    Bash & Python `os.path.expanduser()`:
    # ~         /home/jboy
    # ~alt      /home/alt
    # ~,        ~,
    # ~,alt     ~,alt
    # ~,~alt    ~,~alt
    # ~alt,     ~alt,
    for arg in args:
        if arg == "//":
            # Select ALL processes, even processes NOT associated with a TTY.
            # After this option or arg, all other args are redundant.
            parsed_selection_criteria.really_all_procs = True
        elif arg == "/":
            parsed_selection_criteria.selection_criteria.add(psquery.ProcessHasTty())
        elif arg == "~" or arg == this_process_home:
            parsed_selection_criteria.selection_criteria.add(default_criterion)

    return (parsed_selection_criteria, fields_to_query)


def _get_terminal_width():
    """Return the terminal width (number of columns of characters) or `None`.

    If this script's output is connected to a terminal, return the positive
    integer width in characters of the terminal; otherwise, if this script's
    output is connected to a pipeline, return `None`.

    This function uses Python stdlib function `shutil.get_terminal_size()`,
    which first attempts to use the `${COLUMNS}` environment variable.
    """
    (term_width, term_height) = shutil.get_terminal_size(fallback=(0, 0))
    return term_width if term_width > 0 else None

    # Originally I was using Click's function `click.get_terminal_size()` [1].
    # It works correctly when this script's output is connected to a terminal.
    # Unfortunately, if I pipe the output into some other program like `less`
    # or even just `cat`, Click's function always returns that the terminal is
    # 80 characters wide, even when the terminal is wider than 80 characters.
    # Click also does not offer any other way to determine whether the output
    # is connected to some other program.
    #
    # [1] https://click.palletsprojects.com/en/7.x/api/#click.get_terminal_size
    #
    # The Click source file "termui.py" [2] contains the definition of function
    # `click.get_terminal_size()` [3]:
    #
    # [2] /usr/local/lib/python3.6/site-packages/click/termui.py
    # [3] https://github.com/pallets/click/blob/master/src/click/termui.py#L219
    #
    # Reviewing the code of function `click.get_terminal_size()` [3] reveals
    # that it calls Python stdlib function `shutil.get_terminal_size()` [4][5],
    # which in turn calls Python stdlib function `os.get_terminal_size()` [6]
    # (after first attempting to read the `${COLUMNS}` environment variable).
    #
    # [4] https://docs.python.org/3/library/shutil.html#shutil.get_terminal_size
    # [5] https://github.com/python/cpython/blob/master/Lib/shutil.py#L1313
    # [6] https://docs.python.org/3/library/os.html#os.get_terminal_size
    #
    # If function `os.get_terminal_size()` [6] is not connected to a terminal,
    # it raises exception `OSError`:
    #     Traceback (most recent call last):
    #       <snip>
    #         print(os.get_terminal_size())
    #     OSError: [Errno 25] Inappropriate ioctl for device
    #
    # The incorrect (width, height) values come from the default parameter
    # `fallback=(80, 24)` of function `shutil.get_terminal_size()` [4][5],
    # which is returned if both of:
    #  - the `${COLUMNS}` environment variable is not set, or returns 0;
    # and:
    #  - function `os.get_terminal_size()` raises an exception.


def _format_memory_info(memory_info):
    """Format `memory_info` into a 2-line memory-usage header.

    The format of this 2-line memory-usage header is almost identical to the
    corresponding 2-line memory-usage header of the Linux/UNIX `top` program.

    The only intentional difference is that this format replaces the word "Mem"
    on the right-side of the 2nd line of the `top` header, with a percentage
    (in parentheses) of the "avail" memory as a proportion of the "total".

    For comparison, here is an example 2-line header returned by this function:
        KiB Mem :  3840888 total,   996016 free,  1897564 used,   947308 buff/cache
        KiB Swap:  8388604 total,  5490304 free,  2898300 used,  1440104 avail (37.5%)

    And here is the corresponding 2-line header of `top` running on Linux:
        KiB Mem :  3840888 total,  1010144 free,  1887936 used,   942808 buff/cache
        KiB Swap:  8388604 total,  5490304 free,  2898300 used.  1454240 avail Mem
    """
    line_1 = " ".join((
            "KiB Mem :",
            "{mi.mem_total_KiB:8d} total,",
            "{mi.mem_free_KiB:8d} free,",
            "{mi.mem_used_KiB:8d} used,",
            "{mi.mem_buff_cache_KiB:8d} buff/cache\n"))
    line_2 = " ".join((
            "KiB Swap:",
            "{mi.swap_total_KiB:8d} total,",
            "{mi.swap_free_KiB:8d} free,",
            "{mi.swap_used_KiB:8d} used,",
            "{mi.mem_avail_KiB:8d} avail",
            "({mi.mem_avail_perc:4.1f}%)"))

    return (line_1 + line_2).format(mi=memory_info)


def _format_overcommit_settings(overcommit_settings):
    """Format the Linux OOM `overcommit_settings` into a 1-line header.

    Here is an example returned by this function:
        Overcommit: mode = 0 "heuristic overcommit (default)", ratio = 50.0%
    """
    return "Overcommit: mode = {os.mode} \"{os.descr}\", ratio = {os.ratio:4.1f}%\n".format(
            os=overcommit_settings)


if __name__ == "__main__":
    oomps()
