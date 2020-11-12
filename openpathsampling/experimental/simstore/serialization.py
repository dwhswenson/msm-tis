import numpy as np
from .my_types import parse_ndarray_type
from . import serialization_helpers as serialization
import json

import logging
logger = logging.getLogger(__name__)


def load_list_uuid(json_str, cache_list):
    uuid_list = json.loads(json_str)
    if uuid_list is None:
        return uuid_list
    uuid_list = [serialization.decode_uuid(u) for u in uuid_list]
    return [serialization.search_caches(uuid, cache_list)
            for uuid in uuid_list]


def make_lazy_class(cls_):
    # this is to mix-in inheritence
    class LazyLoader(GenericLazyLoader, cls_):
        pass
    return LazyLoader


class GenericLazyLoader(object):
    def __init__(self, uuid, class_, storage):
        serialization.set_uuid(self, uuid)
        self.storage = storage
        self.class_ = class_
        self._loaded_object = None

    def load(self):
        if self._loaded_object is None:
            self._loaded_object = \
                    self.storage.load([serialization.get_uuid(self)],
                                      force=True)[0]
        if self._loaded_object is None:
            raise RuntimeError("UUID not found in storage: " +
                               serialization.get_uuid(self))
        return self._loaded_object

    def __getattr__(self, attr):
        # apparently IPython pretty-printing looks for a bunch of
        # attributes; this means we auto-load if we try to autoprint the
        # repr in IPython (TODO)
        return getattr(self.load(), attr)

    def __getitem__(self, item):
        return self.load()[item]

    def __iter__(self):
        return self.load().__iter__()

    def __len__(self):
        return len(self.load())

    def __str__(self):
        if self._loaded_object:
            return str(self._loaded_object)
        else:
            return repr(self)

    def __repr__(self):
        if self._loaded_object:
            return repr(self._loaded_object)
        else:
            return ("<LazyLoader for " + str(self.class_.__name__)
                    + " UUID " + str(self.__uuid__) + ">")


class ProxyObjectFactory(object):
    def __init__(self, storage, serialization_schema):
        self.storage = storage
        self.serialization_schema = serialization_schema
        self.lazy_classes = {}

    def make_lazy(self, cls, uuid):
        if cls not in self.lazy_classes:
            self.lazy_classes[cls] = make_lazy_class(cls)
        return self.lazy_classes[cls](uuid=uuid,
                                      class_=cls,
                                      storage=self.storage)

    def make_all_lazies(self, lazies):
        # lazies is dict of {table_name: list_of_lazy_uuid_rows}
        all_lazies = {}
        for (table, lazy_uuid_rows) in lazies.items():
            logger.debug("Making {} lazy proxies for objects in table '{}'"\
                         .format(len(lazy_uuid_rows), table))
            cls = self.serialization_schema.table_to_info[table].cls
            for row in lazy_uuid_rows:
                all_lazies[row.uuid] = self.make_lazy(cls, row.uuid)
        return all_lazies



class SchemaDeserializer(object):
    default_handlers = {
        'lazy': serialization.search_caches,
        'uuid': serialization.search_caches,
        'list_uuid': load_list_uuid,
    }

    def __init__(self, schema, table, cls):
        self.schema = schema
        self.table = table
        if table is not None:
            self.entries = schema[table]
        else:
            self.entries = []
        self.cls = cls
        self.attribute_handlers = self.init_attribute_handlers()

    # TODO: move this external
    @staticmethod
    def make_numpy_handler(dtype, shape):
        return lambda data, _: np.fromstring(data, dtype=dtype).reshape(shape)

    def init_attribute_handlers(self):
        attribute_handlers = {}
        for (attr, type_name) in self.entries:
            handler = None
            if type_name in self.default_handlers:
                handler = self.default_handlers[type_name]
            else:
                as_ndarray = parse_ndarray_type(type_name)
                if as_ndarray:
                    (dtype, shape) = as_ndarray
                    handler = self.make_numpy_handler(dtype, shape)
            if handler:
                attribute_handlers[attr] = handler
        return attribute_handlers

    def make_dct(self, table_dct, cache_list):
        for attr in self.attribute_handlers:
            table_dct[attr] = self.attribute_handlers[attr](table_dct[attr],
                                                            cache_list)
        return table_dct

    def __call__(self, uuid, table_dct, cache_list):
        dct = self.make_dct(table_dct, cache_list)
        # if 'uuid' in dct:
            # del dct['uuid']
        obj = self.cls.from_dict(dct)
        serialization.set_uuid(obj, uuid)
        return obj


class ToDictSerializer(SchemaDeserializer):
    default_handlers = {
        'uuid': serialization.get_uuid,
        'lazy': serialization.get_uuid,
        'json': serialization.to_bare_json,
        'json_obj': serialization.to_json_obj,
        'list_uuid': serialization.to_bare_json
    }

    # TODO: move this external; that will allow us to remove this class
    # (use it as input to SchemaSerializer or a class factory for that)
    @staticmethod
    def make_numpy_handler(dtype, shape):
        return lambda arr: arr.astype(dtype=dtype, copy=False).tostring()

    def __call__(self, obj):
        dct = obj.to_dict()
        for attr in self.attribute_handlers:
            dct[attr] = self.attribute_handlers[attr](dct[attr])
        dct = serialization.replace_uuid(dct,
                                         uuid_encoding=lambda x: x)
        dct.update({'uuid': serialization.get_uuid(obj)})
        return dct


class SchemaSerializer(ToDictSerializer):
    def __call__(self, obj):
        dct = {attr: getattr(obj, attr)
               for (attr, type_name) in self.entries}
        replace = {attr: handler(dct[attr])
                   for (attr, handler) in self.attribute_handlers.items()}
        replace = serialization.replace_uuid(replace,
                                             uuid_encoding=lambda x: x)
        dct.update(replace)
        dct.update({'uuid': serialization.get_uuid(obj)})
        return dct
