import sys
import argparse
import os
import json


import openpathsampling as paths

from openpathsampling.storage import Storage

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Analyze a file.')
    parser.add_argument('file', metavar='file.nc', help='an integer for the accumulator')

    args = parser.parse_args()
    file = args.file

    if not os.path.isfile(file):
        print file, 'does not exist ! ENDING!'
        exit()

    storage = Storage(
        filename = file,
        mode = 'r'
    )

    storage.samples.cache_all()
    storage.samplesets.cache_all()
    storage.pathmovechanges.cache_all()

    class ReadableObjectJSON(paths.storage.todict.ObjectJSON):
        def __init__(self, unit_system = None):
            super(ReadableObjectJSON, self).__init__(unit_system)
            self.excluded_keys = ['name', 'idx', 'json', 'identifier']
            self.storage = storage

        def build(self,obj):
            if type(obj) is dict:
                if '_cls' in obj and '_idx' in obj:
                    return obj['_cls'] + '[#' + str(obj['_idx']) + ']'

                if '_cls' in obj:
                    return { obj['_cls'] : self.build(obj['_dict'])}

                return { key: self.build(value) for key, value in obj.iteritems() }

            return super(ReadableObjectJSON, self).build(obj)

    def indent(s, width=4):
        spl = s.split('\n')
        spl = [' '*width + p for p in spl]
        return '\n'.join(spl)

    def headline(s):
        print
        print "###############################################################################"
        print "##", s.upper()
        print "###############################################################################"
        print

    def line(a, b):
        print '    {:<32} : {:<30}'.format(a,b)

    def nline(n, a, b):
        print '     {:>4}] {:<25} : {:<30}'.format(n,a,b)

    def format_json(json_str):
        obj = json.loads(json_str)
        return json.dumps(obj, sort_keys=True,
                  indent=2, separators=(',', ': '))

    def format_by_json(obj):
        return json.dumps(obj, sort_keys=True,
                  indent=2, separators=(',', ': '))

    simplifier = ReadableObjectJSON()

    headline("General")

    line("Filename", file)
    line("Size", str(os.path.getsize(file) / 1024 / 1024) + " MB")

    headline("Content")

    line("Number of trajectories", storage.trajectories.count())
    line("Number of snapshots", storage.snapshots.count())
    line("Number of configurations", storage.configurations.count())
    line("Number of momenta", storage.momenta.count())

    headline("Topology")

    topology = storage.topology

    line("Number of Atoms", topology.n_atoms)
    line("Number of Dimensions", topology.n_spatial)

    if type(topology) is paths.MDTrajTopology:
        line('MDTraj Topology','')

#    md_topology = topology.md

#    counterion_indices = [ a.index for a in md_topology.atoms if a.residue.name[-1] == '+']
#    solvent_indices = [ a.index for a in md_topology.atoms if a.residue.name == 'HOH']
#    protein_indices = [ a.index for a in md_topology.atoms if a.residue.name[-1] != '+' and a.residue.name != 'HOH']

#    line("Number of waters", len(solvent_indices) / 3)
#    line("Number of protein atoms", len(protein_indices))

    headline("Snapshot Zero")
    # load initial equilibrate snapshot given by ID #0
    snapshot = storage.snapshots.load(0)

    line("Potential Energy",str(snapshot.potential_energy))
    line("Kinetic Energy",str(snapshot.kinetic_energy))

    headline("Ensembles")

    for e_idx in range(0, storage.ensembles.count()):
        ensemble = storage.ensembles.load(e_idx)
        nline(e_idx,ensemble.cls, '')
#        print indent(str(ensemble),16)
        print indent(format_by_json(simplifier.from_json(ensemble.json)), 16)

    headline("PathMovers")

    for p_idx in range(0, storage.pathmovers.count()):
        pathmover = storage.pathmovers.load(p_idx)
        nline(p_idx,pathmover.name, '')
        print indent(format_by_json(simplifier.from_json(pathmover.json)), 16)

    headline("ShootingPointSelector")

    for p_idx in range(0, storage.shootingpointselectors.count()):
        obj = storage.shootingpointselectors.load(p_idx)
        nline(p_idx, obj.cls, '')
#        print indent(format_by_json(simplifier.from_json(obj.json)), 16)

    headline("ShootingPoints (" + str(storage.shootingpoints.count()) + ")")

#    for p_idx in range(0, storage.shootingpoints.count()):
#        obj = storage.shootingpoints.load(p_idx)
#        nline(p_idx,obj.json, obj.cls)

    headline("CollectiveVariables (" + str(storage.collectivevariables.count()) + ")")

#    all_snapshot_traj = storage.snapshots.all()

    for p_idx in range(0, storage.collectivevariables.count()):
        obj = storage.collectivevariables.load(p_idx)
        nline(p_idx,obj.name, '')
        add = ''
#        values = obj(all_snapshot_traj)
#        found_values = [ (idx, value) for idx, value in enumerate(values) if value is not None ]
#        if len(found_values) > 0:
#            add = '{ %d : %f, ... } ' % (found_values[0][0], found_values[0][1]._value )

#        nline(p_idx,obj.name, str(len(found_values)) + ' entries ' + add)

    headline("MCSteps")

    for p_idx in range(0, storage.steps.count()):
        obj = storage.steps.load(p_idx)
        nline(p_idx, '', '')
        print indent(str(obj.change),16)

    headline("SampleSets")

    for p_idx in range(0, storage.samplesets.count()):
        obj = storage.samplesets.load(p_idx)
        nline(p_idx, str(len(obj)) + ' sample(s)', [storage.idx(sample) for sample in obj ])
#        print indent(str(obj.movepath),16)


    headline("Samples")

    def shortened_dict(d):
        keys = sorted(d.keys())
        old_idx = -2
        count = 0
        for idx in keys:
            if idx == old_idx + 1 or idx == old_idx - 1:
                count += 1
            else:
                if count > 1:
                    sys.stdout.write(" <" + str(count - 1) + ">")
                if old_idx >= 0 and count > 0:
                    sys.stdout.write(" " + str(old_idx))
                sys.stdout.write(" " + str(idx))
                count = 0
            old_idx = idx

        if count > 1:
            sys.stdout.write(" <" + str(count - 1) + "> ")
        if count > 0:
            sys.stdout.write(" " + str(old_idx))

    def format_traj(traj_obj):
        s = ''
        traj = storage.trajectories.snapshot_indices(traj_obj.idx(storage.trajectories))
        old_idx = -2
        count = 0
        for idx in traj:
            if idx/2 == old_idx/2 + 1 or idx/2 == old_idx/2 - 1:
                count += 1
            else:
                if count > 1:
                    s += " <" + str(count - 1) + ">"
                if old_idx >= 0 and count > 0:
                    s += " " + str(old_idx)
                s += " " + str(idx)
                count = 0
            old_idx = idx

        if count > 1:
            s += " <" + str(count - 1) + "> "
        if count > 0:
            s += " " + str(old_idx/2)+ ('-' if old_idx % 2 == 0 else '+')

        return s

    def print_traj(name, traj_obj):
        traj = storage.trajectories.snapshot_indices(traj_obj.idx[storage.trajectories])
        sys.stdout.write("      {:>10}:  {:>5} frames [".format(name, str(len(traj))) + ' ]')
        print format_traj(traj_obj)


    for o_idx in range(0, storage.samples.count()):

        sample = storage.samples.load(o_idx)
        nline(o_idx, 'trajectory #' + str(storage.idx(sample.trajectory)),'[ ' + str(len(sample.trajectory)) + ' frames ] ' + format_traj(sample.trajectory))

    headline("Trajectories")

    for t_idx in range(0, storage.trajectories.count()):
        traj = storage.trajectories.snapshot_indices(t_idx)
        sys.stdout.write("  {:>4} [{:>5} frames] : ".format(str(t_idx),str(len(traj))))
        old_idx = -2
        count = 0
        for idx in traj:
            if idx == old_idx + 1 or idx == old_idx - 1:
                count += 1
            else:
                if count > 1:
                    sys.stdout.write(" <" + str(count - 1) + ">")
                if old_idx >= 0 and count > 0:
                    sys.stdout.write(" " + str(old_idx))
                sys.stdout.write(" " + str(idx))
                count = 0
            old_idx = idx

        if count > 1:
            sys.stdout.write(" ... <" + str(count - 1) + "> ...")
        if count > 0:
            sys.stdout.write(" " + str(old_idx))


        sys.stdout.write("\n")
