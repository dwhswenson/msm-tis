import numpy as np
from shared import StaticContainerStore
import mdtraj
from openpathsampling.netcdfplus import WeakLRUCache

variables = ['statics']
lazy = ['statics']

storables = ['statics']

dimensions = ['n_atom', 'n_spatial']


def netcdfplus_init(store):
    static_store = StaticContainerStore()
    static_store.set_caching(WeakLRUCache(10000))

    name = store.prefix + 'statics'

    static_store.set_dimension_prefix_store(store)

    store.storage.create_store(name, static_store, False)

    store.create_variable(
        'statics',
        'lazyobj.' + name,
        description="the snapshot index (0..n_configuration-1) of "
                    "snapshot '{idx}'.",
        chunksizes=(1,))


@property
def coordinates(snapshot):
    """
    Returns
    -------
    coordinates: numpy.ndarray, shape=(atoms, 3), dtype=numpy.float32
        the atomic coordinates of the configuration. The coordinates are
        wrapped in a `simtk.unit.Unit`.
    """

    if snapshot.statics is not None:
        return snapshot.statics.coordinates

    return None


@property
def box_vectors(snapshot):
    """
    Returns
    -------
    box_vectors: numpy.ndarray, shape=(3, 3), dtype=numpy.float32
        the box_vectors of the configuration. The coordinates are wrapped in a
        simtk.unit.Unit.
    """
    if snapshot.statics is not None:
        return snapshot.statics.box_vectors

    return None


@property
def md(snapshot):
    """
    Returns
    -------
    md : mdtraj.Trajectory
        the actual trajectory object. Can be used with all functions from mdtraj

    Notes
    -----
    Rather slow since the topology has to be made each time. Try to avoid it
    """

    if snapshot.statics is not None:
        n_atoms = snapshot.coordinates.shape[0]

        output = np.zeros([1, n_atoms, 3], np.float32)
        output[0, :, :] = snapshot.coordinates

        return mdtraj.Trajectory(output, snapshot.topology.md)


@property
def xyz(snapshot):
    """
    Returns
    -------
    xyz : numpy.ndarray, shape=(atoms, 3), dtype=numpy.float32
        atomic coordinates without dimensions. Be careful.

    """
    import simtk.unit as u

    coord = snapshot.coordinates
    if type(coord) is u.Quantity:
        return coord._value
    else:
        return coord
