import inspect
import logging
import weakref
from types import MethodType

logger = logging.getLogger(__name__)


class StorableObject(object):
    """Mixin that allows objects of the class to to be stored using netCDF+

    """

    _weak_cache = weakref.WeakKeyDictionary()
    _weak_index = 0L

    _base = None
    _args = None

    observe_objects = False

    @staticmethod
    def set_observer(active):
        """
        (De-)Activate observing creation of storable objects

        This can be used to track which storable objects are still alive and hence look for memory leaks
        and inspect caching. Use :meth:`openpathsampling.netcdfplus.base.StorableObject.count_weaks` to get
        the current summary of created objects

        Parameters
        ----------
        active : bool
            if `True` then observing is enabled. `False` disables observing. Per default observing is
            disabled.


        See Also
        --------
        :meth:`openpathsampling.netcdfplus.base.StorableObject.count_weaks`

        """
        if StorableObject.observe_objects is not active:
            return

        if active:
            # activate and add __init__

            def _init(self):
                StorableObject._weak_cache[self] = StorableObject._weak_index
                StorableObject._weak_index += 1

            StorableObject.__init__ = MethodType(_init, None, StorableObject)
            StorableObject.observe_objects = True

        if not active:
            del StorableObject.__init__


    @staticmethod
    def count_weaks():
        """
        Return the counts of how many objects of storable type are still in memory

        This includes objects not yet recycled by the garbage collector.

        Returns
        -------
        dict of str : int
            the dictionary which assigns the base class name of each references objects the
            integer number of objects still present

        """
        summary = dict()
        complete = list(StorableObject._weak_cache)
        for obj in complete:
            name = obj.base_cls_name
            summary[name] = summary.get(name, 0) + 1

        return summary

    def idx(self, store):
        """
        Return the index which is used for the object in the given store.

        Once you store a storable object in a store it gets assigned a unique number
        that can be used to retrieve the object back from the store. This
        function will ask the given store if the object is stored if so what the used
        index is.

        Parameters
        ----------
        store : :class:`openpathsampling.netcdfplus.objects.ObjectStore`
            the store in which to ask for the index

        Returns
        -------
        int or None
            the integer index for the object of it exists or `None` else

        """
        if hasattr(store, 'index'):
            return store.index.get(self, None)
        else:
            return store.idx(self)

    @property
    def cls(self):
        """
        Return the class name as a string

        Returns
        -------
        str
            the class name

        """
        return self.__class__.__name__

    def save(self, store):
        """
        Save the object in the given store (or storage)

        Parameters
        ----------
        store : :class:`openpathsampling.netcdfplus.objects.ObjectStore` or :class:`openpathsampling.netcdfplus.netcdfplus.NetCDFStorage`
            the store or storage to be saved in. if a storage is given then the default store for
            the given object base type is determined and the appropriate store is used.

        Returns
        -------
        int or None
            the integer index used to save the object or `None` if the object has already been saved.
        """
        store.save(self)

    @classmethod
    def base(cls):
        """
        Return the most parent class that is actually derived from Storable(Named)Object

        Important to determine which store should be used for storage

        Returns
        -------
        type
            the base class
        """
        if cls._base is None:
            if cls is not StorableObject and cls is not StorableNamedObject:
                if StorableObject in cls.__bases__ or StorableNamedObject in cls.__bases__:
                    cls._base = cls
                else:
                    if hasattr(cls.__base__, 'base'):
                        cls._base = cls.__base__.base()
                    else:
                        cls._base = cls

        return cls._base

    @property
    def base_cls_name(self):
        """
        Return the name of the base class

        Returns
        -------
        str
            the string representation of the base class

        """
        return self.base().__name__

    @property
    def base_cls(self):
        """
        Return the base class

        Returns
        -------
        type
            the base class

        See Also
        --------
        :func:`base()`

        """
        return self.base()

    @classmethod
    def descendants(cls):
        """
        Return a list of all subclassed objects

        Returns
        -------
        list of type
            list of subclasses of a storable object
        """
        return cls.__subclasses__() + \
               [g for s in cls.__subclasses__() for g in s.descendants()]

    @staticmethod
    def objects():
        """
        Returns a dictionary of all storable objects

        Returns
        -------
        dict of str : type
            a dictionary of all subclassed objects from StorableObject. The name points to the class.
        """
        subclasses = StorableObject.descendants()

        return {subclass.__name__: subclass for subclass in subclasses}

    @classmethod
    def args(cls):
        """
        Return a list of args of the __init__ function of a class

        Returns
        -------
        list of str
            the list of argument names. No information about defaults is included.

        """
        try:
            args = inspect.getargspec(cls.__init__)
        except TypeError:
            return []
        return args[0]

    _excluded_attr = []
    _exclude_private_attr = True
    _restore_non_initial_attr = True
    _restore_name = True

    def to_dict(self):
        """
        Convert object into a dictionary representation

        Used to convert the dictionary into JSON string for serialization

        Returns
        -------
        dict
            the dictionary representing the (immutable) state of the object

        """
        excluded_keys = ['idx', 'json', 'identifier']
        keys_to_store = {
            key for key in self.__dict__
            if key not in excluded_keys and
            key not in self._excluded_attr and
            not (key.startswith('_') and self._exclude_private_attr)
        }
        return {
            key: self.__dict__[key] for key in keys_to_store
        }

    @classmethod
    def from_dict(cls, dct):
        """
        Reconstruct an object from a dictionary representaiton

        Parameters
        ----------
        dct : dict
            the dictionary containing a state representaion of the class.

        Returns
        -------
        :class:`openpathsampling.netcdfplus.StorableObject`
            the reconstructed storable object
        """
        if dct is None:
            dct = {}
        try:
            init_dct = dct
            non_init_dct = {}
            if hasattr(cls, 'args'):
                args = cls.args()
                init_dct = {key: dct[key] for key in dct if key in args}
                non_init_dct = {key: dct[key] for key in dct if key not in args}

            obj = cls(**init_dct)

            if cls._restore_non_initial_attr:
                if len(non_init_dct) > 0:
                    for key, value in non_init_dct.iteritems():
                        setattr(obj, key, value)
            else:
                if cls._restore_name:
                    if 'name' in dct:
                        obj.name = dct['name']

            return obj

        except TypeError as e:
            #TODO: Better exception
            print dct
            print cls.__name__
            print e
            print args
            print init_dct
            print non_init_dct


class StorableNamedObject(StorableObject):
    """Mixin that allows an object to carry a .name property that can be saved

    It is not allowed to rename an object once it has been given a name. Also
    storage usually sets the name to empty if an object has not been named
    before. This means that you cannot name an object, after is has been saved.
    """

    def __init__(self):
        super(StorableNamedObject, self).__init__()
        self._name = ''
        self._name_fixed = False

    @property
    def default_name(self):
        """
        Return the default name.

        Usually derived from the objects class

        Returns
        -------
        str
            the default name

        """
        return '[' + self.__class__.__name__ + ']'

    def fix_name(self):
        """
        Set the objects name to be immutable.

        Usually called after load and save to fix the stored state.
        """
        self._name_fixed = True

    @property
    def name(self):
        """
        Return the current name of the object.

        If no name has been set a default generated name is returned.

        Returns
        -------
        str
            the name of the object
        """
        if self._name == '':
            return self.default_name
        else:
            return self._name

    @name.setter
    def name(self, name):
        if self._name_fixed:
            raise ValueError('Objects cannot be renamed to "%s" after is has been saved, it is already named "%s"' % (
                name, self._name))
        else:
            if name != self._name:
                self._name = name
                logger.debug('Nameable object is renamed from "%s" to "%s"' % (self._name, name))

    @property
    def is_named(self):
        """True if this object has a custom name.

        This distinguishes default algorithmic names from assigned names.
        """
        return self._name != ""

    def named(self, name):
        """Name an unnamed object.

        This only renames the object if it does not yet have a name. It can
        be used to chain the naming onto the object creation. It should also
        be used when naming things algorithmically: directly setting the
        .name attribute could override a user-defined name.

        Examples
        --------
        >>> import openpathsampling as p
        >>> full = p.FullVolume().named('myFullVolume')
        """

        if self._name == "":
            self._name = name

        return self


def create_to_dict(keys_to_store):
    def to_dict(self):
        return {key: getattr(self, key) for key in keys_to_store}

    return to_dict