import random
from opentis.ensemble import Ensemble
from opentis.wrapper import storable

class SampleKeyError(Exception):
    def __init__(self, key, sample, sample_key):
        self.key = key
        self.sample = sample
        self.sample_key = sample_key
        self.msg = (str(self.key) + " does not match " + str(self.sample_key)
                    + " from " + str(self.sample))

class SampleSet(object):
    ''' SampleSet is essentially a list of samples, with a few conveniences.
    It can be treated as a list of samples (using, e.g., .append), or as a
    dictionary of ensembles mapping to a list of samples, or as a dictionary
    of replica IDs to samples. Any type is allowed as a replica ID except
    Sample or Ensemble.

    The dictionaries ensemble_dict and replica_dict are conveniences which
    should be kept consistent by any method which modifies the container.
    They do not need to be stored.

    Note
    ----
        Current implementation is as an unordered set. Therefore we don't
        have some of the convenient tools in Python sequences (e.g.,
        slices). On the other hand, I'm not sure whether that is meaningful
        here.

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

    def __init__(self, samples):
        self.samples = []
        self.ensemble_dict = {}
        self.replica_dict = {}
        for sample in samples:
            self.append(sample)

    def __getitem__(self, key):
        if isinstance(key, Ensemble):
            return random.choice(self.ensemble_dict[key])
        else:
            return random.choice(self.replica_dict[key])

    def __setitem__(self, key, value):
        # first, we check whether the key matches the sample: if no, KeyError
        if isinstance(key, Ensemble):
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
        return (item in self.samples)

    def all_from_ensemble(self, ensemble):
        return self.ensemble_dict[ensemble]

    def all_from_replica(self, replica):
        return self.replica_dict[replica]

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

    def apply_samples(self, samples):
        '''Updates the SampleSet based on a list of samples, by setting them
        by replica in the order given in the argument list.'''
        for sample in samples:
            self[sample.replica] = sample

    def replica_list(self):
        return self.replica_dict.keys()

    def ensemble_list(self):
        return self.ensemble_dict.keys()
            
    def consistency_check(self):
        '''This is mainly a sanity check for use in testing, but might be
        good to run (rarely) in the code until we're sure the tests cover
        all use cases.'''
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


@storable
class Sample(object):
    """
    A Sample is the return object from a PathMover and contains all information about the move, initial trajectories,
    new trajectories (both as references). IF a Mover does several moves at a time (e.g. a swap) then
    a separate move object for each resulting trajectory is returned
    """

    def __init__(self, replica=None, trajectory=None, ensemble=None, details=None, step=-1):
        self.idx = dict()

        self.replica = replica
        self.ensemble = ensemble
        self.trajectory = trajectory
        self.details = details
        self.step=step

    def __call__(self):
        return self.trajectory

    @staticmethod
    def set_time(step, samples):
        for sample in samples:
            sample.step = step