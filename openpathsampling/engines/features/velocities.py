"""
Attributes
----------
velocities : numpy.ndarray, shape=(atoms, 3), dtype=numpy.float32
    atomic velocities
"""

variables = ['velocities']
minus = ['velocities']
numpy = ['velocities']

dimensions = ['n_atom', 'n_spatial']


def netcdfplus_init(store):

    store.create_variable(
        'velocities', 'numpy.float32',
        dimensions=('n_atom', 'n_spatial'),
        description="the velocity of atom 'atom' in dimension " +
                    "'coordinate' of momentum 'momentum'.",
        chunksizes=(1, 'n_atom', 'n_spatial'))
