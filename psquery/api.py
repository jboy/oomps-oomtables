# Copyright (c) 2020 James Boyden <jboy@jboy.me>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Select, filter, sort, and query processes according to requested fields."""

from abc import ABCMeta, abstractmethod  # Python3 only, sorry  :'(
from collections import namedtuple
from operator import attrgetter

# Module `_fields` contains the field definitions.
from ._fields import get_field_info, get_post_proc_settings
# Use `_procio` to augment the capabilities of `psutil`.
from ._procio import read_overcommit_settings

# https://github.com/giampaolo/psutil
# https://pypi.org/project/psutil/
# https://psutil.readthedocs.io/en/latest/
from psutil import process_iter as psutil_process_iter
from psutil import virtual_memory as psutil_virtual_memory
from psutil import swap_memory as psutil_swap_memory


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


def _get_field_accessors(field_names, psutil_attr_names=None):
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
        # If the field name is not valid, `ValueError` will be raised.
        (field_code, field_type, attr_name_or_func, post_processing) = get_field_info(field_name)

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
            _get_field_accessors(all_field_names_in_list)
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

