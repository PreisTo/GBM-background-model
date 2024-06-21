import numpy as np
import pandas as pd
from gbm_drm_gen.drmgen import DRMGen
from gbmgeometry import PositionInterpolator
from gbmbkgpy.io.package_data import get_path_of_data_file
from gbmbkgpy.utils.progress_bar import progress_bar
from gbmbkgpy.utils.spectrum import (
    _spec_integral_bb,
    _spec_integral_pl,
    _spectrum_cpl,
    _spec_integral_cpl,
)
from scipy.interpolate import interpolate

try:
    # see if we have mpi and/or are upalsing parallel

    from mpi4py import MPI

    if MPI.COMM_WORLD.Get_size() > 1:  # need parallel capabilities
        using_mpi = True

        comm = MPI.COMM_WORLD
        rank = comm.Get_rank()
        size = comm.Get_size()
        if rank == 0:
            pr = True
        else:
            pr = False
    else:
        pr = True
        using_mpi = False
except:
    using_mpi = False
    pr = True


class PointSrc_free(object):
    def __init__(self, name, ra, dec, det_responses, geometry, echans):
        """
        Initialize a PS and precalculates the response for all the times for which the geomerty was
        calculated. Needed for a spectral fit of the point source.

        :params name: Name of PS
        :params ra: ra position of PS (J2000)
        :params dec: dec position of PS (J2000)
        :params response_object: response_precalculation object
        :params geometry_object: geomerty precalculatation object
        :params index: Powerlaw index of PS spectrum
        """
        self._name = name

        self._ra = float(ra)
        self._dec = float(dec)

        self._detectors = list(det_responses.responses.keys())

        self._rsp = det_responses.responses
        self._geom = geometry

        self._data_type = self._rsp[self._detectors[0]].data_type

        self._echans = echans

        if self._data_type == "ctime" or self._data_type == "trigdat":
            echans_mask = []

            for e in echans:
                bounds = e.split("-")
                mask = np.zeros(8, dtype=bool)
                if len(bounds) == 1:
                    # Only one echan given
                    index = int(bounds[0])
                    mask[index] = True
                else:
                    # Echan start and stop given
                    index_start = int(bounds[0])
                    index_stop = int(bounds[1])
                    mask[index_start : index_stop + 1] = np.ones(
                        1 + index_stop - index_start, dtype=bool
                    )
                echans_mask.append(mask)

        elif self._data_type == "cspec":
            echans_mask = []

            for e in echans:
                bounds = e.split("-")
                mask = np.zeros(128, dtype=bool)
                if len(bounds) == 1:
                    # Only one echan given
                    index = int(bounds[0])
                    mask[index] = True
                else:
                    # Echan start and stop given
                    index_start = int(bounds[0])
                    index_stop = int(bounds[1])
                    mask[index_start : index_stop + 1] = np.ones(
                        1 + index_stop - index_start, dtype=bool
                    )
                echans_mask.append(mask)

        self._echans_mask = echans_mask

        Eout_edges = list(self._rsp.values())[0].Ebin_out_edge
        Ebins = np.zeros((len(Eout_edges) - 1, 2))
        Ebins[:, 0] = Eout_edges[:-1]
        Ebins[:, 1] = Eout_edges[1:]
        mi = np.zeros(len(self._echans_mask))
        ma = np.zeros(len(self._echans_mask))
        for i, mask in enumerate(self._echans_mask):
            mi[i] = np.min(np.argwhere(mask))
            ma[i] = np.max(np.argwhere(mask))
        minindex = int(np.min(mi))
        maxindex = int(np.max(ma))
        self._piv = np.sqrt(Ebins[minindex, 0] * Ebins[maxindex, 1])

        self._time_variation_interp = None

        self._calc_det_responses()

    @property
    def responses(self):
        return self._rsp

    @property
    def ps_effective_response(self):
        """
        Returns an array with the poit source response for the times for which the geometry
        was calculated.
        """

        return self._ps_response

    def set_time_variation_interp(self, interp):
        """
        Set an interpolator defining the time variation of the point source
        """
        self._time_variation_interp = interp

    def _calc_det_responses(self):
        ps_response = {}

        for det_idx, det in enumerate(self._detectors):
            ps_response[det] = self._response_one_det(det_response=self._rsp[det])

        self._ps_response = ps_response

    def _response_one_det(self, det_response):
        response_matrix = []

        pos_inter = PositionInterpolator(
            quats=np.array([self._geom.quaternion[0], self._geom.quaternion[0]]),
            sc_pos=np.array([self._geom.sc_pos[0], self._geom.sc_pos[0]]),
            time=np.array([-1, 1]),
            trigtime=0,
        )
        print("###############################")
        print(self.name, self._ra, self._dec)
        d = DRMGen(
            pos_inter,
            det_response.det,
            det_response.Ebin_in_edge,
            mat_type=2,
            ebin_edge_out=det_response.Ebin_out_edge,
        )
        for j in range(len(self._geom.quaternion)):
            d._quaternions = self._geom.quaternion[j]
            d._sc_pos = self._geom.sc_pos[j]
            d._compute_spacecraft_coordinates()

            all_response_step = d.to_3ML_response(self._ra, self._dec).matrix

            # sum the responses needed
            response_step = np.zeros(
                (len(self._echans_mask), len(all_response_step[0]))
            )
            for i, echan_mask in enumerate(self._echans_mask):
                for j, entry in enumerate(echan_mask):
                    if entry:
                        response_step[i] += all_response_step[j]

            response_matrix.append(response_step.T)

        response_matrix = np.array(response_matrix)

        return response_matrix

    @property
    def name(self):
        return self._name


class PointSrc_fixed(PointSrc_free):
    def __init__(
        self,
        name,
        ra,
        dec,
        det_responses,
        geometry,
        echans,
        spec,  # spectral_index=2.114
    ):
        super(PointSrc_fixed, self).__init__(
            name, ra, dec, det_responses, geometry, echans
        )
        """
        Initialize a PS and precalculates the rates for all the times for which the geomerty was
        calculated.

        :params name: Name of PS
        :params ra: ra position of PS (J2000)
        :params dec: dec position of PS (J2000)
        :params response_object: response_precalculation object
        :params geometry_object: geomerty precalculatation object
        :params spec: Which spectrum type? pl or bb? And spectral params.
        #:params index: Powerlaw index of PS spectrum
        """
        # Read the spec dict to figure out which spec and the spectral params
        self._read_spec(spec)

        # Calculate the rates for the ps with the normalization set to 1
        self._calc_ps_rates()

        # Interpolate between the times, for which the geometry was calculated
        self._interpolate_ps_rates()

    def _read_spec(self, spec):
        """
        Read the spec dict to figure out which spectral type and which params should be used
        :param spec: Dict with spectral type and parameters
        """

        # Read spectral type
        self._spec_type = spec["spectrum_type"]

        # Check if spectral type is valid
        assert (
            self._spec_type == "bb"
            or self._spec_type == "pl"
            or self._spec_type == "cpl"
        ), "Spectral Type must be bb (Blackbody) or pl (Powerlaw) or cpl (Cutoff Powerlaw)"

        self._norm = spec["norm"]
        # Read spectral params
        if self._spec_type == "bb":
            self._bb_temp = spec["blackbody_temp"]
        if self._spec_type == "pl":
            if spec["powerlaw_index"] == "swift":
                self._pl_index = self._get_swift_pl_index()
            else:
                self._pl_index = spec["powerlaw_index"]
        if self._spec_type == "cpl":
            self._cpl_index = spec["cpl_index"]
            self._xc = spec["xc"]

    def get_ps_rates(self, met):
        """
        Returns an array with the predicted count rates for the times for which the geometry
        was calculated for all energy channels. Assumed an normalization=1 (will be fitted later)
        and the fixed spectral index defined in the init of the object.
        :param met:
        """

        # Get the rates for all times
        ps_rates = self._interp_rate_ps(met)

        # The interpolated flux has the dimensions (len(time_bins), 2, len(detectors), len(echans))
        # We want (len(time_bins), len(detectors), len(echans), 2) so we net to swap axes
        # The 2 is the start stop in the time_bins

        ps_rates = np.swapaxes(ps_rates, 1, 2)
        ps_rates = np.swapaxes(ps_rates, 2, 3)

        if self._time_variation_interp is not None:
            time_variation = np.tile(
                self._time_variation_interp(met),
                (len(self._echans), len(self._detectors), 1, 1),
            )

            time_variation = np.swapaxes(time_variation, 0, 2)

            ps_rates = ps_rates * np.clip(time_variation, a_min=0, a_max=None)

        return ps_rates

    def _calc_ps_rates(self):
        """
        Calaculates the rate in all energy channels for all times for which the geometry was calculated.
        Uses the responses calculated in _response_array.
        :param pl_index: Index of powerlaw
        """

        folded_flux_ps = np.zeros(
            (
                len(self._geom.geometry_times),
                len(self._detectors),
                len(self._echans),
            )
        )

        for det_idx, det in enumerate(self._detectors):
            true_flux_ps = self._integral_ps(
                e1=self._rsp[det].Ebin_in_edge[:-1], e2=self._rsp[det].Ebin_in_edge[1:]
            )

            ps_response_det = self._ps_response[det]

            folded_flux_ps[:, det_idx, :] = np.dot(true_flux_ps, ps_response_det)

        self._folded_flux_ps = self._norm * folded_flux_ps

    def _interpolate_ps_rates(self):
        self._interp_rate_ps = interpolate.interp1d(
            self._geom.geometry_times, self._folded_flux_ps, axis=0
        )

    def _integral_ps(self, e1, e2):
        """
        Method to integrate the diff. flux over the Ebins of the incoming photons
        :params e1: lower bound of Ebin_in
        :params e2: upper bound of Ebin_in
        :params index: Index of spectrum
        :return: flux in the Ebin_in
        """
        if self._spec_type == "bb":
            return _spec_integral_bb(e1, e2, 1, self._bb_temp)

        if self._spec_type == "pl":
            return _spec_integral_pl(e1, e2, 1, self._piv, self._pl_index)
        if self._spec_type == "cpl":
            return _spec_integral_cpl(e1, e2, 1, self._xc, self._piv, self._cpl_index)

    def _get_swift_pl_index(self):
        """
        Get the index of this point source from the pl fit to the 105 month survey of Swift
        :return: pl index
        """
        bat = pd.read_table(
            get_path_of_data_file("background_point_sources/", "BAT_catalog_clean.dat"),
            names=["name1", "name2", "pl_index"],
        )

        res = bat.pl_index[bat[bat.name2.str.upper() == self.name.upper()].index].values
        if len(res) == 0:
            pl_index = 3
            if pr:
                print(
                    f"No index found for {self.name} in the swift 105 month survey."
                    f" We will set the index to -{pl_index}"
                )

        else:
            pl_index = float(res[0])
            if pr:
                print(
                    f"Index for {self.name} is set to {-1*pl_index}"
                    " according to the Swift 105 month survey"
                )

        return pl_index

    @property
    def spec_type(self):
        return self._spec_type
