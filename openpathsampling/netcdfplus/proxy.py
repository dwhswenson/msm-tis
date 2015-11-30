"""

@author: JH Prinz
"""
import functools

import weakref

# =============================================================================
# Loader Proxy
# =============================================================================

class LoaderProxy(object):
    """
    A proxy that loads an underlying object if attributes are accessed
    """
    __slots__ = ['_subject', '_idx', '_store', '__weakref__']

    def __init__(self, store, idx):
        self._idx = idx
        self._store = store
        self._subject = None

    @property
    def __subject__(self):
        if self._subject is not None:
            obj = self._subject()
            if obj is not None:
                return obj

        ref = self._load_()

        if ref is None:
            return None

        self._subject = weakref.ref(ref)
        return ref

    def __eq__(self, other):
        if self is other:
            return True
        elif type(other) is LoaderProxy:
            if self._idx == other._idx and self._store is other._store:
                return True
        elif self.__subject__ is other:
            return True

        return False

    @property
    def __class__(self):
        return self._store.content_class

    def __getattr__(self, item):
        return getattr(self.__subject__, item)

    def _load_(self):
        """
        Call the loader and get the referenced object
        """
        return self._store[self._idx]


class DelayedLoader(object):
    """
    Descriptor class to handle proxy objects in attributes

    If a proxy is stored in an attribute then the full object will be returned
    """
    def __get__(self, instance, owner):
        if instance is not None:
            obj = instance._lazy[self]
            if type(obj) is tuple:
                (store, idx) = obj
                return store[idx]
            elif hasattr(obj, '_idx'):
                return obj.__subject__
            else:
                return obj
        else:
            return self

    def __set__(self, instance, value):
        if type(value) is tuple:
            instance._lazy[self] = value
        else:
            instance._lazy[self] = value


def lazy_loading_attributes(*attributes):
    """
    Set attributes in the decorated class to be handled as lazy loaded objects.

    An attribute that is added here will be turned into a special descriptor that
    will dynamically load an objects if it is represented internally as a LoaderProxy
    object and will return the real object, not the proxy!

    The second thing you can do is that saving using the `.write()` command will
    automatically remove the real object and turn the stored object into a proxy.

    Examples
    --------
    Set an attribute to a LoaderProxy

    >>> my_obj.lazy_attribute = LoaderProxy(snapshot_store, 13)

    >>> print my_obj.lazy_attribute
    openpathsampling.Snapshot object

    It will not return the proxy. This is completely hidden.

    If you want to use the intelligent saving that will remove the reference to the
    object you can do
    >>> sample_store.write('parent', index, my_sample)

    After this call the attribute `my_sample.parent` will be turned into a proxy.

    """
    def _decorator(cls):
        for attr in attributes:
            setattr(cls, attr, DelayedLoader())

        _super_init = cls.__init__

        @functools.wraps(cls.__init__)
        def _init(self, *args, **kwargs):
            self._lazy = dict()
            _super_init(self, *args, **kwargs)

        cls.__init__ = _init
        return cls

    return _decorator