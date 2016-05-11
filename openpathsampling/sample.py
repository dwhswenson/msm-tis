import random
import logging

import openpathsampling as paths
from openpathsampling.netcdfplus import StorableObject, lazy_loading_attributes

logger = logging.getLogger(__name__)

class SampleKeyError(Exception):
    def __init__(self, key, sample, sample_key):
        self.key = key
        self.sample = sample
        self.sample_key = sample_key
        self.msg = (str(self.key) + " does not match " + str(self.sample_key)
                    + " from " + str(self.sample))

@lazy_loading_attributes('movepath')
class SampleSet(StorableObject):
    '''
    SampleSet is essentially a list of samples, with a few conveniences.  It
    can be treated as a list of samples (using, e.g., .append), or as a
    dictionary of ensembles mapping to a list of samples, or as a dictionary
    of replica IDs to samples. Replica ID has to an integer but it can be
    negative or zero.

    The dictionaries ensemble_dict and replica_dict are conveniences which
    should be kept consistent by any method which modifies the container.
    They do not need to be stored.

    Note
    ----
        Current implementation is as an unordered set. Therefore we don't
        have some of the convenient tools in Python sequences (e.g.,
        slices). On the other hand, I'm not sure whether that is meaningful
        here.
        Since replicas are integers we add slicing/ranges for replicas. In
        addition we support any iterable as input in __getitem__ an it will
        return an iterable over the results. This makes it possible to write
        `sset[0:5]` to get a list of of ordered samples by replica_id, or
        sset[list_of_ensembles].  replica_ids can be any number do not have
        to be subsequent to slicing does not make sense and we ignore it. We
        will also ignore missing replica_ids. A slice `1:5` will return all
        existing replica ids >=1 and <5. If you want exactly all replicas
        from 1 to 4 use `sset[xrange(1,5)]`


    Attributes
    ----------
    samples : list of Sample
        The samples included in this set.
    ensemble_dict : dict
        A dictionary with Ensemble objects as keys and lists of Samples as
        values.
    replica_dict : dict
        A dictionary with replica IDs as keys and lists of Samples as values
    '''

    def __init__(self, samples, movepath=None):
        super(SampleSet, self).__init__()

        self.samples = []
        self.ensemble_dict = {}
        self.replica_dict = {}
        self.extend(samples)
        self.movepath = movepath

    @property
    def ensembles(self):
        return self.ensemble_dict.keys()

    @property
    def replicas(self):
        return self.replica_dict.keys()

    def __getitem__(self, key):
        if isinstance(key, paths.Ensemble):
            return random.choice(self.ensemble_dict[key])
        elif type(key) is int:
            return random.choice(self.replica_dict[key])
        elif hasattr(key, '__iter__'):
            return (self[element] for element in key)
        elif type(key) is slice:
            rep_idxs = filter(
                lambda x :
                    (key.start is None or x >= key.start) and
                    (key.stop is None or x < key.stop),
                sorted(self.replica_dict.keys())

            )

            return (self[element] for element in rep_idxs)

    def __setitem__(self, key, value):
        # first, we check whether the key matches the sample: if no, KeyError
        if isinstance(key, paths.Ensemble):
            if key != value.ensemble:
                raise SampleKeyError(key, value, value.ensemble)
        else:
            if key != value.replica:
                raise SampleKeyError(key, value, value.replica)

        if value in self.samples:
            # if value is already in this, we don't need to do anything
            return
        # Setting works by replacing one with the same key. We pick one with
        # this key at random (using __getitem__), delete it, and then append
        # the new guy. If nothing exists with the desired key, this is the
        # same as append.
        try:
            dead_to_me = self[key]
        except KeyError:
            dead_to_me = None
        if dead_to_me is not None:
            del self[dead_to_me]
        self.append(value)

    def __eq__(self, other):
        if len(self.samples) == len(other.samples):
            return True
            for samp1, samp2 in zip(self.samples,other.samples):
                if samp1 is not samp2:
                    return False

            return True
        else:
            return False

    def __delitem__(self, sample):
        self.ensemble_dict[sample.ensemble].remove(sample)
        self.replica_dict[sample.replica].remove(sample)
        if len(self.ensemble_dict[sample.ensemble]) == 0:
            del self.ensemble_dict[sample.ensemble]
        if len(self.replica_dict[sample.replica]) == 0:
            del self.replica_dict[sample.replica]
        self.samples.remove(sample)

    # TODO: add support for remove and pop

    def __iter__(self):
        for sample in self.samples:
            yield sample

    def __len__(self):
        return len(self.samples)

    def __contains__(self, item):
        return item in self.samples

    def all_from_ensemble(self, ensemble):
        try:
            return self.ensemble_dict[ensemble]
        except KeyError:
            return []

    def all_from_replica(self, replica):
        try:
            return self.replica_dict[replica]
        except KeyError:
            return []

    def append(self, sample):
        if sample in self.samples:
            # question: would it make sense to raise an error here? can't
            # have more than one copy of the same sample, but should we
            # ignore it silently or complain?
            return

        self.samples.append(sample)
        try:
            self.ensemble_dict[sample.ensemble].append(sample)
        except KeyError:
            self.ensemble_dict[sample.ensemble] = [sample]
        try:
            self.replica_dict[sample.replica].append(sample)
        except KeyError:
            self.replica_dict[sample.replica] = [sample]

    def extend(self, samples):
        # note that this works whether the parameter samples is a list of
        # samples or a SampleSet!
        if type(samples) is not paths.Sample and hasattr(samples, '__iter__'):
            for sample in samples:
                self.append(sample)
        else:
            # also acts as .append() if given a single sample
            self.append(samples)

    def apply_samples(self, samples, copy=True):
        '''Updates the SampleSet based on a list of samples, by setting them
        by replica in the order given in the argument list.'''
        if type(samples) is Sample:
            samples = [samples]
        if copy==True:
            newset = SampleSet(self)
        else:
            newset = self
        for sample in samples:
            if type(sample) is not paths.Sample:
                raise ValueError('No SAMPLE!')
            # TODO: should time be a property of Sample or SampleSet?
            newset[sample.replica] = sample
        return newset

    def replica_list(self):
        '''Returns the list of replicas IDs in this SampleSet'''
        return self.replica_dict.keys()

    def ensemble_list(self):
        '''Returns the list of ensembles in this SampleSet'''
        return self.ensemble_dict.keys()

    def sanity_check(self):
        '''Checks that the sample trajectories satisfy their ensembles
        '''
        logger.info("Starting sanity check")
        for sample in self:
            # TODO: Replace by using .valid which means that it is in the ensemble
            # and does the same testing but with caching so the .valid might
            # fail in case of some bad hacks. Since we check anyway, let's just

            #assert(sample.valid)
            logger.info("Checking sanity of "+repr(sample.ensemble)+
                        " with "+str(sample.trajectory))
            try:
                assert(sample.ensemble(sample.trajectory))
            except AssertionError as e:
                failmsg = ("Trajectory does not match ensemble for replica "
                           + str(sample.replica))
                if not e.args:
                    e.args = [failmsg]
                else:
                    arg0 = failmsg + e.args[0]
                    e.args = tuple([arg0] + list(e.args[1:]))
                raise # reraises last exception

    def consistency_check(self):
        '''Check that all internal dictionaries are consistent

        This is mainly a sanity check for use in testing, but might be
        good to run (rarely) in the code until we're sure the tests cover
        all use cases.
        '''

        # check that we have the same number of samples in everything
        nsamps_ens = 0
        for ens in self.ensemble_dict.keys():
            nsamps_ens += len(self.ensemble_dict[ens])
        nsamps_rep = 0
        for rep in self.replica_dict.keys():
            nsamps_rep += len(self.replica_dict[rep])
        nsamps = len(self.samples)
        assert nsamps==nsamps_ens, \
                "nsamps != nsamps_ens : %d != %d" % (nsamps, nsamps_ens)
        assert nsamps==nsamps_rep, \
                "nsamps != nsamps_rep : %d != %d" % (nsamps, nsamps_rep)

        # if we have the same number of samples, then we check that each
        # sample in samples is in each of the dictionaries
        for samp in self.samples:
            assert samp in self.ensemble_dict[samp.ensemble], \
                    "Sample not in ensemble_dict! %r %r" % (samp, self.ensemble_dict)
            assert samp in self.replica_dict[samp.replica], \
                    "Sample not in replica_dict! %r %r" % (samp, self.replica_dict)

        # finally, check to be sure that thre are no duplicates in
        # self.samples; this completes the consistency check
        for samp in self.samples:
            assert self.samples.count(samp) == 1, \
                    "More than one instance of %r!" % samp

    def __add__(self, other):
        """
        Add the move path to the Sample and return the new sample set
        """
        if isinstance(other, paths.PathMoveChange):
            return self.apply_samples(other.results)
        elif type(other) is list:
            okay = True
            for samp in other:
                if not isinstance(samp, paths.Sample):
                    okay = False

            return self.apply_samples(other)
        else:
            raise ValueError('Only lists of Sample or PathMoveChanges allowed.')

    def append_as_new_replica(self, sample):
        """
        Adds the given sample to this SampleSet, with a new replica ID.

        The new replica ID is taken to be one greater than the highest
        previous replica ID.
        """
        if len(self) == 0:
            max_repID = -1
        else:
            max_repID = max([s.replica for s in self.samples])
        self.append(Sample(
            replica=max_repID + 1,
            trajectory=sample.trajectory,
            ensemble=sample.ensemble,
            bias=sample.bias,
            details=sample.details,
            parent=sample.parent,
            mover=sample.mover
        ))

    @staticmethod
    def map_trajectory_to_ensembles(trajectory, ensembles):
        """Return SampleSet mapping one trajectory to all ensembles.

        One common approach to starting a simulation is to take a single
        transition trajectory (which satisfies all ensembles) and use it as
        the starting point for all ensembles.
        """
        return SampleSet([
            Sample.initial_sample(
                replica=ensembles.index(e),
                trajectory=paths.Trajectory(trajectory.as_proxies()), # copy
                ensemble = e)
            for e in ensembles
        ])

    @staticmethod
    def translate_ensembles(sset, new_ensembles):
        """Return SampleSet using `new_ensembles` as ensembles.

        This creates a SampleSet which replaces the ensembles in the old
        sample set with equivalent ensembles from a given list. The string
        description of the ensemble is used as a test.

        Note that this assumes that there are no one-to-many or many-to-one
        relations in the ensembles. If there are, then there is no unique
        way to translate.

        The approach used here will return the SampleSet with the maximum
        number of ensembles that overlap between the two groups.
        """
        translation = {}
        for ens1 in sset.ensemble_list():
            for ens2 in new_ensembles:
                if ens1.__str__() == ens2.__str__():
                    translation[ens1] = ens2

        new_samples = []
        for ens in translation:
            old_samples = sset.all_from_ensemble(ens)
            for s in old_samples:
                new_samples.append(Sample(
                    replica=s.replica,
                    ensemble=translation[s.ensemble],
                    trajectory=s.trajectory
                ))
        res = SampleSet.relabel_replicas_per_ensemble(SampleSet(new_samples))
        return res

    @staticmethod
    def relabel_replicas_per_ensemble(ssets):
        """
        Return a SampleSet with one trajectory ID per ensemble in the given ssets.

        This is used if you create several sample sets (e.g., from
        bootstrapping different transitions) which have the same trajectory
        ID associated with different ensembles.
        """
        if type(ssets) is SampleSet:
            ssets = [ssets]
        samples = []
        repid = 0
        for sset in ssets:
            for s in sset:
                samples.append(Sample(
                    replica=repid,
                    trajectory=s.trajectory,
                    ensemble=s.ensemble
                ))
                repid += 1
        return SampleSet(samples)
        



    # @property
    # def ensemble_dict(self):
    #     if self._ensemble_dict is None:
    #         self._ensemble_dict = self._get_ensemble_dict()
    #
    #     return self._ensemble_dict
    #
    # def _get_ensemble_dict(self):
    #     """
    #     Returns the dictionary of ensembles and their samples but not cached
    #     :return:
    #     """
    #     ensembles = set([sample.ensemble for sample in self.samples])
    #     print ensembles
    #     return { sample.ensemble : [sample for sample in self.samples if sample.ensemble is ensemble] for ensemble in ensembles}
    #
    #
    # @property
    # def replica_dict(self):
    #     if self._replica_dict is None:
    #         self._replica_dict = self._get_replica_dict()
    #
    #     return self._replica_dict
    #
    # def _get_replica_dict(self):
    #     """
    #     Returns the dictionary of replica and their samples but not cached
    #     :return:
    #     """
    #     replicas = set([sample.replica for sample in self.samples])
    #     return { sample.replica : [sample for sample in self.samples if sample.replica is replica] for replica in replicas}
    #
    # def __plus__(self, other):
    #     if other.predecessor is self:
    #         newset = self.copy()
    #         for sample in other._samples:
    #             if sample not in self._samples:
    #                 self._append(sample)
    #
    #         return newset
    #     else:
    #         raise ValueError('Incompatible MovePaths')


@lazy_loading_attributes('parent', 'details', 'mover')
class Sample(StorableObject):
    """
    A Sample represents a given "draw" from its ensemble, and is the return
    object from a PathMover. It and contains all information about the move,
    initial trajectories, new trajectories (both as references). 
    
    Since each Sample is a single representative of a single ensemble, each
    Sample consists of one replica ID, one trajectory, and one ensemble.
    This means that movers which generate more than one "draw" (often from
    different ensembles, e.g. replica exchange) will generate more than one
    Sample object.

    Attributes
    ----------
    replica : int
        The replica ID to which this Sample applies. The replica ID can also be negative.
    trajectory : openpathsampling.Trajectory
        The trajectory (path) for this sample
    ensemble : openpathsampling.Ensemble
        The Ensemble this sample is drawn from
    details : openpathsampling.MoveDetails
        Object 
    step : int
        the Monte Carlo step number associated with this Sample
    """

    def __init__(self,
                 replica=None,
                 trajectory=None,
                 ensemble=None,
                 bias=1.0,
                 details=None,
                 parent=None,
                 mover=None
                 ):

        super(Sample, self).__init__()
        self.bias = bias
        self.replica = replica
        self.ensemble = ensemble
        self.trajectory = trajectory
        self.parent = parent
        self.details = details
        self.mover = mover

    def __call__(self):
        return self.trajectory

    #=============================================================================================
    # LIST INHERITANCE FUNCTIONS
    #=============================================================================================

    def __len__(self):
        return len(self.trajectory)

    def __getslice__(self, *args, **kwargs):
        return self.trajectory.__getslice__(*args, **kwargs)

    def __getitem__(self, *args, **kwargs):
        return self.trajectory.__getitem__(*args, **kwargs)

    def __reversed__(self):
        """
        Return a reversed iterator over all snapshots in the samples trajectory

        Returns
        -------
        Iterator()
            The iterator that iterates the snapshots in reversed order

        Notes
        -----
        A reversed trajectory also has reversed snapshots! This means
        that Trajectory(list(reversed(traj))) will lead to a time-reversed
        trajectory not just frames in reversed order but also reversed momenta.

        """
        if self.trajectory is not None:
            return reversed(self.trajectory)
        else:
            return [] # empty iterator

    def __iter__(self):
        """
        Return an iterator over all snapshots in the samples trajectory

        Returns
        -------
        Iterator()
            The iterator that iterates the snapshots

        """
        if self.trajectory is not None:
            return iter(self.trajectory)
        else:
            return [] # empty iterator

    def __str__(self):
        mystr  = "Replica: "+str(self.replica)+"\n"
        mystr += "Trajectory: "+str(self.trajectory)+"\n"
        mystr += "Ensemble: "+repr(self.ensemble)+"\n"
        return mystr

    @property
    def valid(self):
        """Returns true if a sample is in its ensemble

        Returns
        -------
        bool
            `True` if the trajectory is in the ensemble `False` otherwise
        """
        if self._valid is None:
            if self.trajectory is None:
                self._valid = True
            else:
                if self.ensemble is not None:
                    self._valid = self.ensemble(self.trajectory)
                else:
                    # no ensemble means ALL ???
                    self._valid = True

        return self._valid

    def __repr__(self):
        return '<Sample @ ' + str(hex(id(self))) + '>'

    def copy_reset(self):
        '''
        Copy of Sample with initialization move details.
        '''
        result = Sample(
            replica=self.replica,
            trajectory=self.trajectory,
            ensemble=self.ensemble
        )
        return result

    @staticmethod
    def initial_sample(replica, trajectory, ensemble):
        """
        Initial sample from scratch.

        Used to create sample in a given ensemble when generating initial
        conditions from trajectories.
        """
        result = Sample(
            replica=replica,
            trajectory=trajectory,
            ensemble=ensemble
        )
        return result


    @property
    def acceptance(self):
        if not self.valid:
            return 0.0

        return self.bias
