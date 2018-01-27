import time
import sys
import logging
import numpy as np
import pandas as pd

from openpathsampling.netcdfplus import StorableNamedObject, StorableObject

import openpathsampling as paths
import openpathsampling.tools

import collections

from openpathsampling.pathmover import SubPathMover
from .ops_logging import initialization_logging
import abc

from future.utils import with_metaclass

logger = logging.getLogger(__name__)
init_log = logging.getLogger('openpathsampling.initialization')

# python 3 support
try:
    xrange
except NameError:
    xrange = range

class ShootFromSnapshotsSimulation(PathSimulator):
    """
    Generic class for shooting from a set of snapshots.

    This mainly serves as a base class for other simulation types
    (committor, reactive flux, etc.) All of these take initial snapshots
    from within some defined volume, modify the velocities in some way, and
    run the dynamics until some ensemble tells them to stop.

    While this is usually subclassed, it isn't technically abstract, so a
    user can create a simulation of this sort on-the-fly for some weird
    ensembles.

    Parameters
    ----------
    storage : :class:`.Storage`
        the file to store simulations in
    engine : :class:`.DynamicsEngine`
        the dynamics engine to use to run the simulation
    starting_volume : :class:`.Volume`
        volume initial frames must be inside of
    forward_ensemble : :class:`.Ensemble`
        ensemble for shots in the forward direction
    backward_ensemble : :class:`.Ensemble`
        ensemble for shots in the backward direction
    randomizer : :class:`.SnapshotModifier`
        the method used to modify the input snapshot before each shot
    initial_snapshots : list of :class:`.Snapshot`
        initial snapshots to use
    """
    def __init__(self, storage, engine, starting_volume, forward_ensemble,
                 backward_ensemble, randomizer, initial_snapshots):
        super(ShootFromSnapshotsSimulation, self).__init__(storage)
        self.engine = engine
        # FIXME: this next line seems weird; but tests fail without it
        paths.EngineMover.default_engine = engine
        try:
            initial_snapshots = list(initial_snapshots)
        except TypeError:
            initial_snapshots = [initial_snapshots]
        self.initial_snapshots = initial_snapshots
        self.randomizer = randomizer

        self.starting_ensemble = (
            paths.AllInXEnsemble(starting_volume) & paths.LengthEnsemble(1)
        )

        self.forward_ensemble = forward_ensemble
        self.backward_ensemble = backward_ensemble

        self.forward_mover = paths.ForwardExtendMover(
            ensemble=self.starting_ensemble,
            target_ensemble=self.forward_ensemble
        )
        self.backward_mover = paths.BackwardExtendMover(
            ensemble=self.starting_ensemble,
            target_ensemble=self.backward_ensemble
        )

        # subclasses will often override this
        self.mover = paths.RandomChoiceMover([self.forward_mover,
                                              self.backward_mover])

    def to_dict(self):
        dct = {
            'engine': self.engine,
            'initial_snapshots': self.initial_snapshots,
            'randomizer': self.randomizer,
            'starting_ensemble': self.starting_ensemble,
            'forward_ensemble': self.forward_ensemble,
            'backward_ensemble': self.backward_ensemble,
            'mover': self.mover
        }
        return dct

    @classmethod
    def from_dict(cls, dct):
        obj = cls.__new__(cls)
        # user must manually set a storage!
        super(ShootFromSnapshotsSimulation, obj).__init__(storage=None)
        obj.engine = dct['engine']
        obj.initial_snapshots = dct['initial_snapshots']
        obj.randomizer = dct['randomizer']
        obj.starting_ensemble = dct['starting_ensemble']
        obj.forward_ensemble = dct['forward_ensemble']
        obj.backward_ensemble = dct['backward_ensemble']
        obj.mover = dct['mover']
        return obj


    def run(self, n_per_snapshot, as_chain=False):
        """Run the simulation.

        Parameters
        ----------
        n_per_snapshot : int
            number of shots per snapshot
        as_chain : bool
            if as_chain is False (default), then the input to the modifier
            is always the original snapshot. If as_chain is True, then the
            input to the modifier is the previous (modified) snapshot.
            Useful for modifications that can't cover the whole range from a
            given snapshot.
        """
        self.step = 0
        snap_num = 0
        for snapshot in self.initial_snapshots:
            start_snap = snapshot
            # do what we need to get the snapshot set up
            for step in range(n_per_snapshot):
                paths.tools.refresh_output(
                    "Working on snapshot %d / %d; shot %d / %d" % (
                        snap_num+1, len(self.initial_snapshots),
                        step+1, n_per_snapshot
                    ),
                    output_stream=self.output_stream,
                    refresh=self.allow_refresh
                )

                if as_chain:
                    start_snap = self.randomizer(start_snap)
                else:
                    start_snap = self.randomizer(snapshot)

                sample_set = paths.SampleSet([
                    paths.Sample(replica=0,
                                 trajectory=paths.Trajectory([start_snap]),
                                 ensemble=self.starting_ensemble)
                ])
                sample_set.sanity_check()
                new_pmc = self.mover.move(sample_set)
                samples = new_pmc.results
                new_sample_set = sample_set.apply_samples(samples)

                mcstep = MCStep(
                    simulation=self,
                    mccycle=self.step,
                    previous=sample_set,
                    active=new_sample_set,
                    change=new_pmc
                )

                if self.storage is not None:
                    self.storage.steps.save(mcstep)
                    if self.step % self.save_frequency == 0:
                        self.sync_storage()

                self.step += 1
            snap_num += 1



class CommittorSimulation(ShootFromSnapshotsSimulation):
    """Committor simulations. What state do you hit from a given snapshot?

    Parameters
    ----------
    storage : :class:`.Storage`
        the file to store simulations in
    engine : :class:`.DynamicsEngine`
        the dynamics engine to use to run the simulation
    states : list of :class:`.Volume`
        the volumes representing the stable states
    randomizer : :class:`.SnapshotModifier`
        the method used to modify the input snapshot before each shot
    initial_snapshots : list of :class:`.Snapshot`
        initial snapshots to use
    direction : int or None
        if direction > 0, only forward shooting is used, if direction < 0,
        only backward, and if direction is None, mix of forward and
        backward. Useful if using no modification on the randomizer.
    """
    def __init__(self, storage, engine=None, states=None, randomizer=None,
                 initial_snapshots=None, direction=None):
        all_state_volume = paths.join_volumes(states)
        no_state_volume = ~all_state_volume
        # shoot forward until we hit a state
        forward_ensemble = paths.SequentialEnsemble([
            paths.AllOutXEnsemble(all_state_volume),
            paths.AllInXEnsemble(all_state_volume) & paths.LengthEnsemble(1)
        ])
        # or shoot backward until we hit a state
        backward_ensemble = paths.SequentialEnsemble([
            paths.AllInXEnsemble(all_state_volume) & paths.LengthEnsemble(1),
            paths.AllOutXEnsemble(all_state_volume)
        ])
        super(CommittorSimulation, self).__init__(
            storage=storage,
            engine=engine,
            starting_volume=no_state_volume,
            forward_ensemble=forward_ensemble,
            backward_ensemble=backward_ensemble,
            randomizer=randomizer,
            initial_snapshots=initial_snapshots
        )
        self.states = states
        self.direction = direction

        # override the default self.mover given by the superclass
        if self.direction is None:
            self.mover = paths.RandomChoiceMover([self.forward_mover,
                                                  self.backward_mover])
        elif self.direction > 0:
            self.mover = self.forward_mover
        elif self.direction < 0:
            self.mover = self.backward_mover

    def to_dict(self):
        dct = super(CommittorSimulation, self).to_dict()
        dct['states'] = self.states
        dct['direction'] = self.direction
        return dct

    @classmethod
    def from_dict(cls, dct):
        obj = super(CommittorSimulation, cls).from_dict(dct)
        obj.states = dct['states']
        obj.direction = dct['direction']
        return obj


class DirectSimulation(PathSimulator):
    """
    Direct simulation to calculate rates and fluxes.

    In practice, this is primarily used to calculate the flux if you want to
    do so without saving the entire trajectory. However, it will also save
    the trajectory, if you want it to.

    Parameters
    ----------
    storage : :class:`.Storage`
        file to store the trajectory in. Default is None, meaning that the
        trajectory isn't stored (also faster)
    engine : :class:`.DynamicsEngine`
        the engine for the molecular dynamics
    states : list of :class:`.Volume`
        states to look for transitions between
    flux_pairs : list of 2-tuples of ``(state, interface)``
        fluxes will calculate the flux out of `state` and through
        `interface` for each pair in this list
    initial_snapshot : :class:`.Snapshot`
        initial snapshot for the MD

    Attributes
    ----------
    transitions : dict with keys 2-tuple of paths.Volume, values list of int
        for each pair of states (from_state, to_state) as a key, gives the
        number of frames for each transition from the entry into from_state
        to entry into to_state
    rate_matrix : pd.DataFrame
        calculates the rate matrix, in units of per-frames
    fluxes : dict with keys 2-tuple of paths.Volume, values float
        flux out of state and through interface for each (state, interface)
        key pair
    n_transitions : dict with keys 2-tuple of paths.Volume, values int
        number of transition events for each pair of states
    n_flux_events : dict with keys 2-tuple of paths.Volume, values int
        number of flux events for each (state, interface) pair
    """
    def __init__(self, storage=None, engine=None, states=None,
                 flux_pairs=None, initial_snapshot=None):
        super(DirectSimulation, self).__init__(storage)
        self.engine = engine
        self.states = states
        self.flux_pairs = flux_pairs
        if flux_pairs is None:
            self.flux_pairs = []
        self.initial_snapshot = initial_snapshot
        self.save_every = 1

        # TODO: might set these elsewhere for reloading purposes?
        self.transition_count = []
        self.flux_events = {pair: [] for pair in self.flux_pairs}

    @property
    def results(self):
        return {'transition_count': self.transition_count,
                'flux_events': self.flux_events}

    def load_results(self, results):
        self.transition_count = results['transition_count']
        self.flux_events = results['flux_events']

    def run(self, n_steps):
        most_recent_state = None
        first_interface_exit = {p: -1 for p in self.flux_pairs}
        last_state_visit = {s: -1 for s in self.states}
        was_in_interface = {p: None for p in self.flux_pairs}
        local_traj = paths.Trajectory([self.initial_snapshot])
        self.engine.current_snapshot = self.initial_snapshot
        for step in xrange(n_steps):
            frame = self.engine.generate_next_frame()

            # update the most recent state if we're in a state
            state = None  # no state at all
            for s in self.states:
                if s(frame):
                    state = s
            if state:
                last_state_visit[state] = step
                if state is not most_recent_state:
                    # we've made a transition: on the first entrance into
                    # this state, we reset the last_interface_exit
                    state_flux_pairs = [p for p in self.flux_pairs
                                        if p[0] == state]
                    for p in state_flux_pairs:
                        first_interface_exit[p] = -1
                    # if this isn't the first change of state, we add the
                    # transition
                    if most_recent_state:
                        self.transition_count.append((state, step))
                    most_recent_state = state

            # update whether we've left any interface
            for p in self.flux_pairs:
                state = p[0]
                interface = p[1]
                is_in_interface = interface(frame)
                # by line: (1) this is a crossing; (2) the most recent state
                # is correct; (3) this is the FIRST crossing
                first_exit_condition = (
                    not is_in_interface and was_in_interface[p]  # crossing
                    and state is most_recent_state  # correct recent state
                    and first_interface_exit[p] < last_state_visit[state]
                )
                if first_exit_condition:
                    first_exit = first_interface_exit[p]
                    # successful exit
                    if 0 < first_exit < last_state_visit[state]:
                        flux_time_range = (step, first_exit)
                        self.flux_events[p].append(flux_time_range)
                    first_interface_exit[p] = step
                was_in_interface[p] = is_in_interface

            if self.storage is not None:
                local_traj += [frame]

        if self.storage is not None:
            self.storage.save(local_traj)

    @property
    def transitions(self):
        prev_state = None
        prev_time = None
        results = {}
        for (new_state, time) in self.transition_count:
            if prev_state is not None and prev_time is not None:
                lag = time - prev_time
                try:
                    results[(prev_state, new_state)] += [lag]
                except KeyError:
                    results[(prev_state, new_state)] = [lag]
            prev_state = new_state
            prev_time = time
        return results

    @property
    def rate_matrix(self):
        transitions = self.transitions
        try:
            time_per_step = self.engine.snapshot_timestep
        except AttributeError:
            time_per_step = 1.0
        total_time = {s: sum(sum((transitions[t] for t in transitions
                                  if t[0] == s), [])) * time_per_step
                      for s in self.states}

        rates = {t : len(transitions[t]) / total_time[t[0]]
                 for t in transitions}
        # rates = {t : 1.0 / np.array(transitions[t]).mean()
                 # for t in transitions}

        state_names = [s.name for s in self.states]
        rate_matrix = pd.DataFrame(columns=state_names, index=state_names)
        for t in rates:
            rate_matrix.at[t[0].name, t[1].name] = rates[t]
        return rate_matrix

    @property
    def fluxes(self):
        results = {}
        try:
            time_per_step = self.engine.snapshot_timestep
        except AttributeError:
            time_per_step = 1.0

        for p in self.flux_events:
            lags = [t[0] - t[1] for t in self.flux_events[p]]
            results[p] = 1.0 / np.mean(lags) / time_per_step
        return results

        # return {p : 1.0 / np.array(self.flux_events[p]).mean()
                # for p in self.flux_events}

    @property
    def n_transitions(self):
        transitions = self.transitions
        return {t : len(transitions[t]) for t in transitions}

    @property
    def n_flux_events(self):
        return {p : len(self.flux_events[p]) for p in self.flux_events}