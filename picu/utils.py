import collections.abc
import functools


class memoized(object):
    """
    Decorator. Caches a function's return value each time it is called.
    If called later with the same arguments, the cached value is returned
    (not reevaluated).
    """
    def __init__(self, func):
        self.func = func
        self.cache = {}

    def __call__(self, *args, **kwargs):
        all_args = (args, tuple(sorted(kwargs)))
        if not isinstance(all_args, collections.abc.Hashable):
            # uncacheable. a list, for instance.
            # better to not cache than blow up.
            return self.func(*args, **kwargs)

        if all_args in self.cache:
            return self.cache[all_args]
        else:
            value = self.func(*args, **kwargs)
            self.cache[all_args] = value
            return value

    def __repr__(self):
        '''Return the function's docstring.'''
        return self.func.__doc__

    def __get__(self, obj, objtype):
        '''Support instance methods.'''
        return functools.partial(self.__call__, obj)


memoized_property = lambda f: property(memoized(f))
