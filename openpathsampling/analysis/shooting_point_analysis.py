import openpathsampling as paths
import collections
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# based on http://stackoverflow.com/a/3387975
class TransformedDict(collections.MutableMapping):
    """A dictionary that applies an arbitrary key-altering function before
    accessing the keys

    This implementation involves a particular hashing function. It is
    assumed that any two input objects which give the same hash are
    effectively identical, allowing later rehashing based on the same.
    """

    def __init__(self, hash_function, *args, **kwargs):
        self.store = dict()
        self.hash_representatives = dict()
        self.hash_function = hash_function
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        return self.store[self.hash_function(key)]

    def __setitem__(self, key, value):
        hashed = self.hash_function(key)
        if hashed not in self.hash_representatives:
            self.hash_representatives[hashed] = key
        self.store[hashed] = value

    def __delitem__(self, key):
        hashed = self.hash_function(key)
        del self.store[hashed]
        del self.hash_representatives[hashed]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def rehash(self, new_hash):
        """Create a new TransformedDict with this data and new hash.

        It is up to the user to ensure that the mapping from the old hash to
        the new is a function (i.e., each entry from the old hash can be
        mapped directly onto the new hash).

        For example, this is used to map from a snapshot's coordinates to
        a collective variable based on the coordinates. However, if the
        orignal hash was based on coordinates, but the new hash included
        velocities, the resulting mapping would be invalid. It is up to the
        user to avoid such invalid remappings.
        """
        return TransformedDict(new_hash, 
                               {self.hash_representatives[k]: self.store[k] 
                                for k in self.store})


class SnapshotByCoordinateDict(TransformedDict):
    """TransformedDict that uses snapshot coordinates as keys.

    This is primarily used to have a unique key for shooting point analysis
    (e.g., committor analysis).
    """
    def __init__(self, *args, **kwargs):
        hash_fcn = lambda x : x.coordinates.tostring()
        super(SnapshotByCoordinateDict, self).__init__(hash_fcn, 
                                                       *args, **kwargs)


class ShootingPointAnalysis(SnapshotByCoordinateDict):
    """
    Container and methods for shooting point analysis.

    This is especially useful for analyzing committors, which is
    automatically done on a per-configuration basis, and can also be done
    as a histogram.

    Parameters
    ----------
    steps : iterable of :class:`.MCStep`
        input MC steps to analysis
    states : list of :class:`.Volume`
        volumes to consider as states for the analysis. For pandas output,
        these volumes must be named.
    """
    def __init__(self, steps, states):
        super(ShootingPointAnalysis, self).__init__()
        for step in steps:
            try:
                # TODO: this should in step.change.canonical.details
                details = step.change.canonical.trials[0].details
                shooting_snap = details.shooting_snapshot
            except AttributeError:
                # wrong kind of move (no shooting_snapshot)
                pass
            except IndexError:
                # very wrong kind of move (no trials!)
                pass
            else:
                # easy to change how we define the key
                key = shooting_snap
                trial_traj = step.change.canonical.trials[0].trajectory
                init_traj = details.initial_trajectory
                test_points = [s for s in [trial_traj[0], trial_traj[-1]]
                               if s not in [init_traj[0], init_traj[-1]]]

                total = collections.Counter(
                    {state: sum([int(state(pt)) for pt in test_points])
                                for state in states}
                )
                total_count = sum(total.values())
                assert total_count == 1 or total_count == 2
                try:
                    self[key] += total
                except KeyError:
                    self[key] = total

    def committor(self, state, label_function=None):
        """Calculate the (point-by-point) committor.

        This is for the point-by-point (per-configuration) committor, not
        for histograms. See `committor_histogram` for the histogram version.

        Parameters
        ----------
        state : :class:`.Volume`
            the committor is 1.0 if 100% of shots enter this state
        label_function : callable
            the keys for the dictionary that is returned are
            `label_function(snapshot)`; default `None` gives the snapshot as
            key.

        Returns
        -------
        dict :
            mapping labels given by label_function to the committor value
        """
        if label_function is None:
            label_function = lambda s : s
        results = {}
        for k in self:
            out_key = label_function(self.hash_representatives[k])
            counter_k = self.store[k]
            committor = float(counter_k[state]) / sum(counter_k.values())
            results[out_key] = committor
        return results

    @staticmethod
    def _get_key_dim(key):
        try:
            ndim = len(key)
        except TypeError:
            ndim = 1
        if ndim > 2 or ndim < 1:
            raise RuntimeError("Histogram key dimension {0} > 2 or {0} < 1 " 
                               + "(key: {1})".format(ndim, key))
        return ndim

    def committor_histogram(self, new_hash, state, bins):
        """Calculate the histogrammed version of the committor.

        Parameters
        ----------
        new_hash : callable
            values are histogrammed in bins based on new_hash(snapshot)
        state : :class:`.Volume`
            the committor is 1.0 if 100% of shots enter this state
        bins : see numpy.histogram
            bins input to numpy.histogram

        Returns
        -------
        tuple :
            (hist, bins) like numpy.histogram, where hist is the histogram
            count and bins is the bins output from numpy.histogram 
        """
        rehashed = self.rehash(new_hash)
        r_store = rehashed.store
        count_all = {k : sum(r_store[k].values()) for k in r_store}
        count_state = {k : r_store[k][state] for k in r_store}
        ndim = self._get_key_dim(r_store.keys()[0])
        if ndim == 1:
            all_hist = np.histogram(count_all.keys(),
                                    weights=count_all.values(), 
                                    bins=bins)[0]
            state_hist = np.histogram(count_state.keys(),
                                      weights=count_state.values(),
                                      bins=bins)[0]
        elif ndim == 2:
            all_hist = np.histogram2d(x=[k[0] for k in count_all],
                                      y=[k[1] for k in count_all],
                                      weights=count_all.values(),
                                      bins=bins)[0]
            state_hist = np.histogram2d(x=[k[0] for k in count_state],
                                        y=[k[1] for k in count_state],
                                        weights=count_state.values(),
                                        bins=bins)[0]
        state_frac = np.true_divide(state_hist, all_hist)
        return state_frac, bins

    def to_pandas(self, label_function=None):
        """
        Pandas dataframe. Row for each configuration, column for each state.

        Parameters
        ----------
        label_function : callable
            takes snapshot, returns index to use for pandas.DataFrame
        """
        transposed = pd.DataFrame(self.store).transpose().to_dict()
        df = pd.DataFrame(transposed)
        df.columns = [s.name for s in transposed.keys()]
        if label_function is None:
            df.index = range(len(df.index))
        else:
            # TODO: is ordering guaranteed here?
            df.index = [label_function(self.hash_representatives[k])
                        for k in self.store]
        return df
