from openpathsampling.engines import Topology, SnapshotDescriptor
from snapshot import ToySnapshot


class ToyTopology(Topology):
    """
    Attributes
    ----------
    masses : numpy.ndarray (n_atoms, dtype=float)
        The masses associated with each atom
    """

    def __init__(self, n_spatial, masses, pes, n_atoms=1):
        super(ToyTopology, self).__init__(n_atoms=n_atoms, n_spatial=n_spatial)
        self.masses = masses
        self.pes = pes

    def to_descriptor(self):
        """
        Helper function to fast create a descriptor

        Returns
        -------
        :obj:`SnapshotDescriptor`

        """
        return SnapshotDescriptor.construct(
            ToySnapshot,
            {
                'n_atom': self.n_atoms,
                'n_spatial': self.n_spatial
            }
        )
