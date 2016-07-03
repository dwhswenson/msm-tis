import numpy as np
import pandas as pd
import scipy
import matplotlib.pyplot as plt
import math
from lookup_function import LookupFunction, VoxelLookupFunction
import collections

class SparseHistogram(object):
    """
    Base class for sparse-based histograms.

    Parameters
    ----------
    bin_widths : array-like
        bin (voxel) size
    left_bin_edges : array-like
        lesser side of the bin (for each direction)
    """
    def __init__(self, bin_widths, left_bin_edges):
        self.bin_widths = np.array(bin_widths)
        if left_bin_edges is None:
            self.left_bin_edges = None
        else:
            self.left_bin_edges = np.array(left_bin_edges)
        self.count = 0
        self.name = None
        self._histogram = None

    def empty_copy(self):
        """Returns a new histogram with the same bin shape, but empty"""
        return type(self)(self.bin_widths, self.left_bin_edges)

    def histogram(self, data=None, weights=None):
        """Build the histogram.

        Parameters
        ----------
        data : list of list of floats
            input data
        weights : list of floats
            weight for each input data point

        Returns
        -------
        collection.Counter :
            copy of the current counter
        """
        if data is None and self._histogram is None:
            raise RuntimeError("histogram() called without data!")
        elif data is not None:
            self._histogram = collections.Counter({})
            return self.add_data_to_histogram(data, weights)
        else:
            return self._histogram.copy()

    @staticmethod
    def sum_histograms(hists):
        # (w, r) = (hists[0].bin_width, hists[0].bin_range)
        # newhist = Histogram(bin_width=w, bin_range=r)
        newhist = hists[0].empty_copy()
        newhist._histogram = collections.Counter({})

        for hist in hists:
            if not newhist.compare_parameters(hist):
                raise RuntimeError
            newhist.count += hist.count
            newhist._histogram += hist._histogram

        return newhist

    def map_to_float_bins(self, trajectory):
        return (np.asarray(trajectory) - self.left_bin_edges) / self.bin_widths

    def map_to_bins(self, data):
        """
        Parameters
        ----------
        data : np.array
            input data

        Returns
        -------
        tuple:
            the bin that the data represents
        """
        return tuple(np.floor((data - self.left_bin_edges) / self.bin_widths))

    def add_data_to_histogram(self, data, weights=None):
        """Adds data to the internal histogram counter.

        Parameters
        ----------
        data : list or list of list
            input data
        weights : list or None
            weight associated with each datapoint. Default `None` is same
            weights for all

        Returns
        -------
        collections.Counter :
            copy of the current histogram counter
        """
        if self._histogram is None:
            return self.histogram(data, weights)
        if weights is None:
            weights = [1.0]*len(data)

        part_hist = sum((collections.Counter({self.map_to_bins(d) : w})
                         for (d, w) in zip (data, weights)),
                        collections.Counter({}))

        self._histogram += part_hist
        self.count += len(data) if weights is None else sum(weights)
        return self._histogram.copy()

    @staticmethod
    def _left_edge_to_bin_edge_type(left_bins, widths, bin_edge_type):
        if bin_edge_type == "l":
            return left_bins
        elif bin_edge_type == "m":
            return left_bins + 0.5 * widths
        elif bin_edge_type == "r":
            return left_bins + widths
        elif bin_edge_type == "p":
            pass # TODO: patches; give the range
        else:
            raise RuntimeError("Unknown bin edge type: " + str(bin_edge_type))


    def xvals(self, bin_edge_type):
        """Position values for the bin

        Parameters
        ----------
        bin_edge_type : 'l' 'm', 'r', 'p'
            type of values to return; 'l' gives left bin edges, 'r' gives
            right bin edges, 'm' gives midpoint of the bin, and 'p' is not
            implemented, but will give vertices of the patch for the bin

        Returns
        -------
        np.array :
            The values of the bin edges
        """
        int_bins = np.array(self._histogram.keys())
        left_bins = int_bins * self.bin_widths + self.left_bin_edges
        return self._left_edge_to_bin_edge_type(left_bins, self.bin_widths,
                                                bin_edge_type)

    def __call__(self, bin_edge_type="m"):
        return VoxelLookupFunction(left_bin_edges=self.left_bin_edges,
                                   bin_widths=self.bin_widths,
                                   counter=self._histogram)

    def normalized(self, raw_probability=False, bin_edge="m"):
        """
        Callable normalized version of the sparse histogram.

        Parameters
        ----------
        raw_probability : bool
            if True, the voxel size is ignored and the sum of the counts
            adds to one. If False (default), the sum of the counts times the
            voxel volume adds to one.
        bin_edge : string
            not used; here for compatibility with 1D versions

        Returns
        -------
        :class:`.VoxelLookupFunction`
            callable version of the normalized histogram
        """
        voxel_vol = reduce(lambda x, y: x.__mul__(y), self.bin_widths)
        scale = voxel_vol if not raw_probability else 1.0
        norm = 1.0 / (self.count * scale)
        counter = collections.Counter({k : self._histogram[k] * norm
                                       for k in self._histogram.keys()})
        return VoxelLookupFunction(left_bin_edges=self.left_bin_edges,
                                   bin_widths=self.bin_widths,
                                   counter=counter)

    def compare_parameters(self, other):
        """Test whether the other histogram has the same parameters.

        Used to check whether we can simply combine these histograms.

        Parameters
        ----------
        other : :class:`.SparseHistogram`
            histogram to compare with

        Returns
        -------
        bool :
            True if these were set up with equivalent parameters, False
            otherwise
        """
        # None returns false: use that as a quick test
        if other == None:
            return False
        if self.left_bin_edges is None or other.left_bin_edges is None:
            # this is to avoid a numpy warning on the next
            return self.left_bin_edges is other.left_bin_edges
        if self.left_bin_edges != other.left_bin_edges:
            return False
        if self.bin_widths != other.bin_widths:
            return False
        return True


class Histogram(SparseHistogram):
    """Wrapper for numpy.histogram with additional conveniences.

    In addition to the behavior in numpy.histogram, this provides a few
    additional calculations, as well as behavior that allows for better
    interactive use (tricks to assist caching by libraries using it, etc.)
    """
    def __init__(self, n_bins=None, bin_width=None, bin_range=None):
        """Creates the parameters for the histogram.

        Either `n_bins` or `bin_width` must be given. If `bin_width` is
        used, then `bin_range` is required. If `n_bins` is used, then
        `bin_range` is optional. `n_bins` overrides `bin_width`.

        If no options are given, the default is to use 40 bins and the
        range generated by np.histogram.
        """
        # this is to compare whether another histogram had the same setup,
        # and is useful for other programs that want to cache a histogram
        self._inputs = [n_bins, bin_width, bin_range]

        # regularize options
        self.bin_width = None # if not set elsewhere
        self.bin_range = None # if not set elsewhere
        if bin_range is not None:
            max_bin = max(bin_range)
            min_bin = min(bin_range)
            if bin_width is not None:
                self.bin_width = bin_width
                self.n_bins = int(math.ceil((max_bin-min_bin)/self.bin_width))
                # if this isn't actually divisible, you'll get one extra bin
            if n_bins is not None:
                self.n_bins = n_bins
                self.bin_width = (max_bin-min_bin)/(self.n_bins)
            self.bins = [min_bin + self.bin_width*i
                         for i in range(self.n_bins+1)]
        else:
            if n_bins is not None:
                self.n_bins = n_bins
            else:
                self.n_bins = 20 # default
            self.bins = self.n_bins

        try:
            left_bin_edges = (self.bins[0],)
        except TypeError:
            left_bin_edges = None

        super(Histogram, self).__init__(bin_widths=(self.bin_width,),
                                        left_bin_edges=left_bin_edges)

    def empty_copy(self):
        return type(self)(bin_width=self.bin_width, bin_range=self.bin_range)

    def histogram(self, data=None, weights=None):
        """Build the histogram based on `data`.

        Note
        ----
        Calling this with new data overwrites the previous histogram. This
        is the expected behavior; in using this, you should check if the
        histogram parameters have changed from a previous run (using
        `compare_parameters`) and you should be aware whether your data has
        changed. If you want to add data to the histogram, you should use
        `add_data_to_histogram`.
        """
        if self.left_bin_edges is not None:
            return super(Histogram, self).histogram(data, weights)
        if data is not None:
            max_val = max(data)
            min_val = min(data)
            self.bin_width = (max_val-min_val)/self.bins
            self.left_bin_edges = np.array((min_val,))
            self.bin_widths = np.array((self.bin_width,))
        return super(Histogram, self).histogram(data, weights)

    def xvals(self, bin_edge_type="l"):
        int_bins = np.array(self._histogram.keys())[:,0]
        # always include left_edge_bin as 0 point; always include 0 and
        # greater bin values (but allow negative)
        min_bin = min(min(int_bins), 0)
        n_bins = max(int_bins) - min_bin + 1
        width = self.bin_widths[0]
        left_bins = (self.left_bin_edges[0] + np.arange(n_bins) * width)
        return self._left_edge_to_bin_edge_type(left_bins, width,
                                                bin_edge_type)

    def __call__(self, bin_edge="m"):
        """Return copy of histogram if it has already been built"""
        vals = self.xvals(bin_edge)
        hist = self.histogram()
        bins = sorted(hist.keys())
        min_bin = min(bins[0][0], self.left_bin_edges[0])
        max_bin = bins[-1][0]
        bin_range = range(int(min_bin), int(max_bin)+1)
        hist_list = [hist[(b,)] for b in bin_range]
        return LookupFunction(vals, hist_list)

    def compare_parameters(self, other):
        """Return true if `other` has the same bin parameters as `self`.

        Useful for checking whether a histogram needs to be rebuilt.
        """
        if not super(Histogram, self).compare_parameters(other):
            return False
        if type(other.bins) is not int:
            if type(self.bins) is int:
                return False
            for (t, b) in zip(self.bins, other.bins):
                if t != b:
                    return False
        else:
            return self._inputs == other._inputs
        return True

    def _normalization(self):
        """Return normalization constant (integral over this histogram)."""
        hist = self('l')
        bin_edges = self.xvals('l')
        dx = [bin_edges[i+1] - bin_edges[i] for i in range(len(bin_edges)-1)]
        dx += [dx[-1]]  # assume the "forever" bin is same as last limited
        norm = np.dot(hist.values(), dx)
        return norm

    # Yes, the following could be cached. No, I don't think it is worth it.
    # Keep in mind that we need a separate cache for each one that we build,
    # and that typically it will take almost no time to build one of these
    # (runtime in linear in number of histogram bins). Adding caching
    # complicates the code for no real benefit (you're more likely to suffer
    # from L2 cache misses than to get a speedup).

    def normalized(self, raw_probability=False, bin_edge="m"):
        """Return normalized version of histogram.

        By default (`raw_probability` false), this returns the histogram
        normalized by its integral (according to rectangle-rule
        integration). If `raw_probability` is true, this returns the
        histogram normalized by the sum of the bin counts, with no
        consideration of the bin widths.
        """
        normed_hist = self() # returns a copy
        nnorm = self._normalization() if not raw_probability else self.count
        norm = 1.0/nnorm
        normed_hist_list = [normed_hist(k) * norm for k in normed_hist.keys()]
        xvals = self.xvals(bin_edge)
        return LookupFunction(xvals, normed_hist_list)

    def cumulative(self, maximum=1.0, bin_edge="r"):
        """Cumulative from the left: number of values less than bin value.

        Use `maximum=None` to get the raw counts.
        """
        cumul_hist = []
        total = 0.0
        hist = self(bin_edge)
        for k in sorted(hist.keys()):
            total += hist(k)
            cumul_hist.append(total)

        cumul_hist = np.array(cumul_hist)
        if total == 0:
            return 0
        if maximum is not None:
            cumul_hist *= maximum / total

        xvals = self.xvals(bin_edge)
        return LookupFunction(xvals, cumul_hist)

    def reverse_cumulative(self, maximum=1.0, bin_edge="l"):
        """Cumulative from the right: number of values greater than bin value.

        Use `maximum=None` to get the raw counts.
        """
        cumul_hist = []
        total = 0.0
        hist = self(bin_edge)
        for k in reversed(sorted(hist.keys())):
            total += hist(k)
            cumul_hist.insert(0, total)

        cumul_hist = np.array(cumul_hist)
        if total == 0:
            return 0
        if maximum is not None:
            cumul_hist *= maximum / total

        xvals = self.xvals(bin_edge)
        return LookupFunction(xvals, cumul_hist)

    def rebinned(self, scaling):
        """Redistributes histogram bins of width binwidth*scaling

        Exact if scaling is an integer; otherwise uses the assumption that
        original bins were uniformly distributed. Note that the original
        data is not destroyed.
        """
        #TODO
        pass

    def plot_bins(self, scaling=1.0):
        """Bins used in plotting. Scaling useful when plotting `rebinned`"""
        # TODO: add scaling support
        return self.bins[1:]


def histograms_to_pandas_dataframe(hists, fcn="histogram", fcn_args={}):
    """Converts histograms in hists to a pandas data frame"""
    keys = None
    hist_dict = {}
    frames = []
    for hist in hists:
        # check that the keys match
        if keys is None:
            keys = hist.xvals()
        for (t,b) in zip(keys, hist.xvals()):
            if t != b:
                raise Warning("Bins don't match up")
        if hist.name is None:
            hist.name = str(hists.index(hist))

        hist_data = {
            "histogram" : hist,
            "normalized" : hist.normalized,
            "reverse_cumulative" : hist.reverse_cumulative,
            "cumulative" : hist.cumulative,
            "rebinned" : hist.rebinned
        }[fcn](**fcn_args).values()

        bin_edge = {
            "histogram" : "m",
            "normalized" : "m",
            "reverse_cumulative" : "l",
            "cumulative" : "r"
        }[fcn]
        xvals = hist.xvals(bin_edge)

        frames.append(pd.DataFrame({hist.name : hist_data}, index=xvals))
    all_frames = pd.concat(frames, axis=1)
    return all_frames.fillna(0.0)


def write_histograms(fname, hists):
    """Writes all histograms in list `hists` to file named `fname`

    If the filename is the empty string, then output is to stdout.
    Assumes that all files should have the same bins.
    """
    pass

# TODO: might as well add a main fucntion to this; read data / weight from
# stdin and output an appropriate histogram depending on some options. Then
# it is both a useful script and a library class!

def labels_for_bins(histogram, dof, bin_numbers, label_format="{:}"):
    """Generate tick labels given bin numbers.

    Axes for a plot based on a pandas dataframe use bin numbers. This
    converts a list of such bin numbers to the float values for the bins, as
    formatted strings.
    """
    bin_width = histogram.bin_widths[dof]
    left_bin_edge = histogram.left_bin_edges[dof]
    bin_to_val = lambda n : n * bin_width + left_bin_edge
    return [label_format.format(bin_to_val(n)) for n in bin_numbers]

def ticks_for_labels(histogram, dof, ticklabels):
    bin_width = histogram.bin_widths[dof]
    left_bin_edge = histogram.left_bin_edges[dof]
    val_to_bin = lambda x : (x - left_bin_edge) / bin_width
    return [val_to_bin(float(label)) for label in ticklabels]

def plot_limits(histogram, dof, minimum, maximum):
    bin_width = histogram.bin_widths[dof]
    left_bin_edge = histogram.left_bin_edges[dof]
    val_to_bin = lambda x : (x - left_bin_edge) / bin_width
    return (val_to_bin(minimum), val_to_bin(maximum))

def histogram_ticks(histogram, dof, ticklabels=None, intticks=None,
                    domain=None, label_format="{:4.2f}"):
    """Generate information about axis labeling.

    Parameters
    ----------
    histogram : :class:`.SparseHistogram`
        histogram to label
    dof : int
        the degree of freedom (zero-indexed)
    ticklabels : list of float-castable
        the labels for the axis ticks
    intticks : list of int
        locations according to a pandas dataframe for the ticks; to be
        converted from pandas row/column number to value
    domain : 2-tuple of float-castable
        the limits (lower, upper) for the domain

    Returns
    -------
    dict : 
        entry 'values' goes into plt.set_xticks(values); entry 'labels' goes
        into plt.set_xticklabels(label); and entries 'min_val' and 'max_val'
        go into plt.xlim(min_val, max_val)
    """
    if ticklabels is None and intticks is None:
        pass # TODO: can we even run this?
    if ticklabels is not None and intticks is not None:
        pass # TODO: does this make any sense?
    bin_width = histogram.bin_widths[dof]
    left_bin_edge = histogram.left_bin_edges[dof]
    val_to_bin = lambda x : (x - left_bin_edge) / bin_width
    bin_to_val = lambda n : n * bin_width + left_bin_edge

    if ticklabels is not None:
        float_ticks = [float(tic) for tic in ticklabels]
        bin_ticks = [val_to_bin(tic) for tic in float_ticks]

    max_tick = max(float_ticks) if ticklabels is not None else float("-inf")

    vals = zip(*counter.keys())[dof]
    min_bin = min(min(vals), left_bin_edge / bin_width)
    max_min = max(max(vals), val_to_bin(max_tick))

    bin_range = np.arange(min_bin - left_bin_edge/bin_width, max_bin+1)

    if intticks is not None:
        bin_ticks = intticks

class HistogramPlotter2D(object):
    def __init__(self, histogram, label_format="{:}"):
        self.histogram = histogram
        self.label_format = label_format
        pass

    @staticmethod
    def df_range_1d(hist, tics=None, lims=None):
	if tics is None:
	    tics = []
	if lims is None:
	    lims = []
	hist = list(hist)
	tics = list(tics)
	lims = list(lims)
	return (int(min(hist + tics + lims)), int(max(hist + tics + lims)))

    @staticmethod
    def limits(df_range, lims=None):
        if lims is None:
            lims = (0, df_range[1]-df_range[0])
        return lims

    def to_bins(self, alist, dof):
        left_edge = self.histogram.left_bin_edges[dof]
        bin_width = self.histogram.bin_widths[dof]
        result = None
        if alist is not None:
            result = (np.asarray(alist) - left_edge) / bin_width
        return result

    def plot(self, normed=True, xticklabels=None, yticklabels=None,
             xlim=None, ylim=None, **kwargs):
        hist_fcn = self.histogram.normalized(raw_probability=True)
        left_bin_edges = self.histogram.left_bin_edges
        bin_widths = self.histogram.bin_widths

        # convert to bin-based units

        x, y = zip(*self.histogram._histogram.keys())

        xticks = self.to_bins(xticklabels, 0)
        xlim = self.to_bins(xlim, 0)
        x_range = self.df_range_1d(x, xticks, xlim)
        xlim = self.limits(x_range, xlim)

        yticks = self.to_bins(yticklabels, 1)
        ylim = self.to_bins(ylim, 1)
        y_range = self.df_range_1d(y, yticks, ylim)
        ylim = self.limits(y_range, ylim)

        df = hist_fcn.df_2d(x_range=x_range, y_range=y_range)

        self.df = df
        self.x_range = x_range
        self.y_range = y_range
        self.xlim = xlim
        self.ylim = ylim

	df_index_to_val = lambda n : (
            (n + x_range[0]) * bin_widths[0] + left_bin_edges[0]
        )
	df_column_to_val = lambda n : (
            (n + y_range[0]) * bin_widths[1] + left_bin_edges[1] 
        )

	mesh = plt.pcolormesh(df.fillna(0.0).transpose(), cmap="Blues")
	mesh.axes.set_xticklabels(
            [self.label_format.format(df_index_to_val(n)) 
             for n in mesh.axes.get_xticks()]
        )
	mesh.axes.set_yticklabels(
            [self.label_format.format(df_column_to_val(n)) 
             for n in mesh.axes.get_yticks()]
        )
	plt.xlim(xlim[0], xlim[1])
	plt.ylim(ylim[0], ylim[1])
	plt.colorbar()
        return mesh

    def plot_trajectory(self, trajectory):
        pass


def plot_2d_histogram(histogram, normed=True, xticklabels=None,
                      yticklabels=None, xlim=None, ylim=None,
                      label_format="{:}", **kwargs):
    """Plot a 2D sparse histogram

    Parameters
    ----------
    histogram : SparseHistogram
        the histogram to plot
    normed : bool
        whether to plot the (raw probability) normalized version or the
        unnormalized version

    """
    # get the counter we'll use, set up
    if normed:  # TODO: allow non-raw normalization too
        hist_fcn = histogram.normalized(raw_probability=True)
    else:
        hist_fcn = histogram()
    counter = hist_fcn.counter

    bin_widths = histogram.bin_widths
    left_bin_edges = histogram.left_bin_edges
    if len(bin_widths) != 2:  # pragma: no cover
        raise RuntimeError("This isn't a 2D histogram!")

    # misc things we need for axes
    val_to_bin = lambda x, dof : (x - left_bin_edges[dof]) / bin_widths[dof]
    bin_to_val = lambda n, dof : n * bin_widths[dof] + left_bin_edges[dof]
    max_xtick = max(xticklabels) if xticklabels is not None else float('-inf')
    max_ytick = max(yticklabels) if yticklabels is not None else float('-inf')

    (x, y) = zip(*counter.keys())
    min_xbin = min(min(x), left_bin_edges[0]/bin_widths[0])
    min_ybin = min(min(y), left_bin_edges[1]/bin_widths[1])
    max_xbin = max(max(x), val_to_bin(max_xtick, 0))
    max_ybin = max(max(y), val_to_bin(max_ytick, 1))

    # bin ranges are integers: use to set size of DataFrame, etc
    xbin_range = np.arange(min_xbin-left_bin_edges[0]/bin_widths[0], max_xbin+1)
    ybin_range = np.arange(min_ybin-left_bin_edges[1]/bin_widths[1], max_ybin+1)

    if xticklabels is not None:
        xticks = [val_to_bin(float(tic), 0) for tic in xticklabels]
    if yticklabels is not None:
        yticks = [val_to_bin(float(tic), 1) for tic in yticklabels]

    # dataframe for our data
    df = pd.DataFrame(index=xbin_range, columns=ybin_range)
    for (k, v) in counter.items():
        df.set_value(k[0],k[1], v)
    df = df.fillna(0.0)

    fig, ax = plt.subplots()
    heatmap = ax.pcolormesh(df.transpose(), **kwargs)
    if xticklabels is None:
        xticks = ax.axes.get_xticks()
        xticklabels = ["{:4.2f}".format(tic * bin_widths[0] + left_bin_edges[0]) for tic in xticks]
    if yticklabels is None:
        yticks = ax.axes.get_yticks()
        yticklabels = ["{:4.2f}".format(tic * bin_widths[0] + left_bin_edges[0]) for tic in yticks]

    formatted_xticks = ["{:4.2f}".format(float(x)) for x in xticklabels]
    formatted_yticks = ["{:4.2f}".format(float(y)) for y in yticklabels]
    ax.axes.set_xticks(xticks)
    ax.axes.set_xticklabels(formatted_xticks)
    ax.axes.set_yticks(yticks)
    ax.axes.set_yticklabels(formatted_yticks)
    if xlim is None:
        plt.xlim(0,len(xbin_range))
    else:
        plt.xlim(val_to_bin(xlim[0], 0), val_to_bin(xlim[1], 0))
    if ylim is None:
        plt.ylim(0,len(ybin_range))
    else:
        plt.ylim(val_to_bin(ylim[0], 1), val_to_bin(ylim[1], 1))

    plt.colorbar(heatmap, ax=ax)

    return ax
