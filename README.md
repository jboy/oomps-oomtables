# oomps/oomtables

Command-line Python programs to configure/control the Linux Out-Of-Memory (OOM) Killer:

* **oomps:** Like `ps` or `top`, but for per-process memory usage & Linux OOM Score.
* **oomtables:** Rules-based control of the Linux Out-Of-Memory (OOM) Killer
  (inspired by ye olde Linux `iptables`, but with syntax more like `if`-statements in C
  or functions in Shell).

These programs are command-line-processing, configuration-parsing front-ends to this Python library:

* **psquery:** A Python library for selecting, filtering, sorting & querying processes.

## Development status

* **oomps:** Early-stage development
* **oomtables:** Planning
* **psquery:** Early-stage development

## Dependencies

* [Python3](https://www.python.org/downloads/)
* [`click`](https://pypi.org/project/click/) for command-line interface parsing
  ([`click` homepage](https://palletsprojects.com/p/click/),
  [`click` on Github](https://github.com/pallets/click),
  [`click` documentation](https://click.palletsprojects.com/))
* [`psutil`](https://pypi.org/project/psutil/) for cross-platform process-querying
  ([`psutil` on Github](https://github.com/giampaolo/psutil),
  [`psutil` documentation](https://psutil.readthedocs.io/en/latest/))
