# oomps/oomtables

Command-line Python programs to configure/control the Linux Out-Of-Memory (OOM) Killer:

* **oomps:** Like `ps` or `top`, but for per-process memory usage & Linux OOM Score.
* **oomtables:** Rules-based control of the Linux Out-Of-Memory (OOM) Killer
  (inspired by ye olde Linux `iptables`, but with syntax more like `if`-statements in C
  or functions in Shell).

These programs are command-line-processing, configuration-parsing front-ends to this Python library:

* **psquery:** A Python3 library for selecting, filtering, sorting & querying processes.

## Development status

* **oomps:** Early-stage development
* **oomtables:** Planning
* **psquery:** Early-stage development

## oomps

### Help

	Usage: oomps [OPTIONS] [ARGS]...

	  Like `ps` or `top`, but for per-process memory usage & Linux OOM Score.

	  This command runs in 3 stages:
	   1. Select (processes) by specified criteria (default: caller's UID).
	   2. Sort (processes) by specified field criteria (default: PID).
	   3. Print (process field values) to stdout, in column-based format.

	  There may be any number of [ARGS], in any order.  [ARGS] are used for
	  selecting processes and specifying which fields (process attributes)
	  should be included in the print to stdout.

	  [ARGS] for selecting processes may be any of:
	    ~                 Select processes owned by the caller's UID.

	    +                 Select processes owned by the caller's UID.
	    +<uid>            Select processes owned by integer UID <uid>.

	    %                 Select all processes that have a TTY.
	    %<exestart>       Select processes that have a TTY, that also have
				  executable name starting with `<exestart>`.

	    %%                Select ALL processes, even without a TTY.
	    %%<exestart>      Select processes, even without a TTY, that have
				  executable name starting with `<exestart>`.

	    <pid>             Select process with integer PID `<pid>`.
	    <pid>,<pid>       Select processes with PIDs in comma-separated list.

	  A process is selected if ANY of the selection criteria match. (So the
	  selection criteria "OR" together.)

	  If no [ARGS] are specified for process selection, the selection criteria
	  default to `~` (select processes owned by the caller's UID).  This is
	  similar to how the `ps` command behaves without command-line arguments.

	  When an argument accepts a comma-separated list, the list may instead be
	  whitespace-separated if the caller prefers (but a single list may NOT
	  contain both commas and whitespace).

	  [ARGS] for specifying which fields should be shown may be any of:
	    .<field>              Show <field> first in columns.
	    .<new>/<old>          Replace <old> field with <new> in-place.
	    ./<field>             Remove <field> field from columns.
	    ..<field1>,<field2>   Show <field1>,<field2> list first in columns.

	    ==<field1>,<field2>   Specify exactly which fields should be shown
				      (completely overriding the default).

	  To see which fields may be shown, use option `--help-list-fields`. A field
	  may be specified by its field name or its 1-character field key.

	Options:
	  -a, --all-procs          Select: all processes that have a TTY.
	  -A, --really-all-procs   Select: ALL processes, even without a TTY.
	  -o, --sort-by-oom        Sort:   by (ascending) OOM Score.
	  -O, --rev-sort-by-oom    Sort:   by descending OOM Score.
	  -r, --sort-by-rsz        Sort:   by (ascending) resident set size.
	  -R, --rev-sort-by-rsz    Sort:   by descending resident set size.
	  -s, --sort-by-start      Sort:   by (ascending) start time.
	  -S, --rev-sort-by-start  Sort:   by descending start time.
	  -v, --sort-by-vsz        Sort:   by (ascending) virtual memory size.
	  -V, --rev-sort-by-vsz    Sort:   by descending virtual memory size.
	  --help-list-fields       List all fields and exit.
	  --help-list-fields-md    List all fields (in Markdown format) and exit.
	  --help                   Show this message and exit.

### Fields

| NAME | Is Default | KEY | DESCR |
| -- | ---------- | -- | -- |
| `adj` | Y | `a` | OOM Score Adjustment (Linux 2.6.36 and later): [-1000, 1000] |
| `adjd` |   | `A` | OOM Adjustment (pre-Linux 2.6.36; now deprecated): [-17, +15] |
| `cmda` |   | `C` | Command-line (invoked command & args) as an array of strings |
| `cmds` | Y | `c` | Command-line (invoked command & args) joined as a single string |
| `ctime` |   | `t` | Accumulated CPU time, user + system, in human-readable format |
| `ctimes` |   | `T` | Accumulated CPU time, user + system, in integer seconds |
| `dtime` | Y | `d` | "Desk time" since the process started, in human-readable format |
| `dtimes` |   | `D` | "Desk time" since the process started, in integer seconds |
| `exe` |   | `x` | Executable name (without path) |
| `exep` |   | `X` | Executable name (with absolute path) |
| `ooms` | Y | `o` | Linux OOM Score: [0, 1000] |
| `pid` | Y | `p` | Process ID (integer) |
| `ppid` | Y | `P` | Parent process ID (integer) |
| `rszh` |   | `r` | Resident set size in memory, in human-readable format |
| `rszk` |   | `R` | Resident set size in memory, in KB or KiB |
| `start` | Y | `s` | Start-time of process (UTC), in human-readable format |
| `starts` |   | `S` | Start-time of process (UTC), in seconds since UNIX epoch |
| `tty` |   | `y` | Terminal associated with the process |
| `uid` |   | `U` | User ID (integer) |
| `user` | Y | `u` | Username (string) |
| `vszh` | Y | `v` | Virtual memory size, in human-readable format |
| `vszk` |   | `V` | Virtual memory size, in KB or KiB |
| `wd` |   | `w` | Current working directory (absolute path) of process |

## Dependencies

* [Python3](https://www.python.org/downloads/)
* [`click`](https://pypi.org/project/click/) for command-line interface parsing
  ([`click` on Github](https://github.com/pallets/click),
  [`click` documentation](https://click.palletsprojects.com/))
* [`psutil`](https://pypi.org/project/psutil/) for cross-platform process-querying
  ([`psutil` on Github](https://github.com/giampaolo/psutil),
  [`psutil` documentation](https://psutil.readthedocs.io/en/latest/))
