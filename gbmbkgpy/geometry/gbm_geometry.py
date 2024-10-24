import numpy as np
from scipy.interpolate import interp1d
import scipy.interpolate as interpolate
import astropy.time as astro_time
import astropy.io.fits as fits
import astropy.units as u

from gbmgeometry import PositionInterpolator, gbm_detector_list, GBMTime

from gbmbkgpy.geometry.geometry import Geometry
from gbmbkgpy.utils.progress_bar import progress_bar
from gbmbkgpy.io.downloading import (download_gbm_file,
                                     download_trigdata_file,
                                     download_lat_spacecraft)
from gbmbkgpy.utils.binner import Rebinner


def ang2cart(ra, dec):
    """
    transform ra, dec to a unit vector
    taken from gbm_drm_gen
    :param ra:
    :param dec:
    :return: vector
    """
    ra = np.atleast_1d(np.deg2rad(ra))
    dec = np.atleast_1d(np.deg2rad(dec))

    pos = np.zeros((len(ra), 3))
    pos[:, 0] = np.cos(dec) * np.cos(ra)
    pos[:, 1] = np.cos(dec) * np.sin(ra)
    pos[:, 2] = np.sin(dec)

    return pos


def get_ang(X1, X2):
    """
    taken from gbm_drm_gen
    :param X1: vector can be an array of vectors
    :param X2: vector
    :return:
    """
    if X1.shape == 1:
        norm1 = np.linalg.norm(X1)
        norm2 = np.linalg.norm(X2)
        tmp = np.clip(np.dot(X1 / norm1, X2 / norm2), -1, 1)

    else:
        norm1 = np.linalg.norm(X1, axis=1)
        norm2 = np.linalg.norm(X2)
        tmp = np.clip(np.dot((X1.T / norm1).T, X2 / norm2), -1, 1)

    return np.arccos(tmp)


class GBMGeometry(Geometry):

    def __init__(self, date, cr_tracer_type="MCL", bgo_side=None):
        self._date = date

        assert cr_tracer_type in ["MCL", "BGO"], "Invalid tracer type"


        if cr_tracer_type=="MCL":
            self._create_mcl_cr_tracer_interp(date)
        else:
            assert bgo_side is not None, "Please enter the needed BGO side"
            self._create_bgo_cr_tracer_interp(date, bgo_side)

    def _compute_sc_coords(self, quaternions):
        """
        Calc. spacecraft coordiates axis in icrs frame
        Taken from: gbm_drm_gen
        :param quaternions: Quaternions of sat rotation
        :returns: x,y anz axis in icrs frame
        """

        scx = np.zeros(3)
        scy = np.zeros(3)
        scz = np.zeros(3)

        scx[0] = (
            quaternions[0] ** 2
            - quaternions[1] ** 2
            - quaternions[2] ** 2
            + quaternions[3] ** 2
        )
        scx[1] = 2.0 * (
            quaternions[0] * quaternions[1]
            + quaternions[3] * quaternions[2]
        )
        scx[2] = 2.0 * (
            quaternions[0] * quaternions[2]
            - quaternions[3] * quaternions[1]
        )
        scy[0] = 2.0 * (
            quaternions[0] * quaternions[1]
            - quaternions[3] * quaternions[2]
        )
        scy[1] = (
            - quaternions[0] ** 2
            + quaternions[1] ** 2
            - quaternions[2] ** 2
            + quaternions[3] ** 2
        )
        scy[2] = 2.0 * (
            quaternions[1] * quaternions[2]
            + quaternions[3] * quaternions[0]
        )
        scz[0] = 2.0 * (
            quaternions[0] * quaternions[2]
            + quaternions[3] * quaternions[1]
        )
        scz[1] = 2.0 * (
            quaternions[1] * quaternions[2]
            - quaternions[3] * quaternions[0]
        )
        scz[2] = (
            -quaternions[0] ** 2
            - quaternions[1] ** 2
            + quaternions[2] ** 2
            + quaternions[3] ** 2
        )
        return scx, scy, scz

    def icrs_to_satellite(self, time, ra, dec):
        """
        Transform icrs coords to satellite coords
        Taken from: gbm_drm_gen
        :param time: time of interest
        :param ra: ra in icrs (degree) (array or float)
        :param dec: dec in icrs (degree) (array or float)
        :returns: az, el in sat frame (degree)
        """
        quaternions = self._position_interpolator.quaternion(time)

        scx, scy, scz = self._compute_sc_coords(quaternions)

        ra = np.atleast_1d(ra)
        dec = np.atleast_1d(dec)
        num_ra = len(ra)

        source_pos_sc = np.zeros((num_ra, 3))
        source_pos = ang2cart(ra, dec)

        source_pos_sc[:, 0] = np.dot(source_pos, scx) #scx.dot(source_pos)
        source_pos_sc[:, 1] = np.dot(source_pos, scy) #scy.dot(source_pos)
        source_pos_sc[:, 2] = np.dot(source_pos, scz) #scz.dot(source_pos)

        el = np.arccos(source_pos_sc[:, 2])
        az = np.arctan2(source_pos_sc[:, 1], source_pos_sc[:, 0])

        az_mask = az < 0

        az[az_mask] += 2 * np.pi

        el = 90 - np.rad2deg(el)

        az = np.rad2deg(az)

        return az, el

    def satellite_to_icrs(self, time, az, el):
        """
        Transform satellite coords to icrs coords
        Taken from: gbm_drm_gen
        :param time: time of interest
        :param az: ra in icrs (degree) (array or float)
        :param el: dec in icrs (degree) (array or float)
        :returns: az, el in sat frame (degree)
        """
        quaternions = self._position_interpolator.quaternion(time)

        scx, scy, scz = self._compute_sc_coords(quaternions)

        az = np.atleast_1d(az)
        el = np.atleast_1d(el)
        num_az = len(az)

        # inverse matrix

        sc_tot = np.array([scx, scy, scz])

        scx, scy, scz = np.linalg.inv(sc_tot)

        source_pos_sc = np.zeros((num_az, 3))
        source_pos = ang2cart(az, el)

        source_pos_sc[:, 0] = np.dot(source_pos, scx)
        source_pos_sc[:, 1] = np.dot(source_pos, scy)
        source_pos_sc[:, 2] = np.dot(source_pos, scz)

        dec = np.arccos(np.clip(source_pos_sc[:, 2], -1, 1))
        ra = np.arctan2(np.clip(source_pos_sc[:, 1], -1, 1),
                        np.clip(source_pos_sc[:, 0], -1, 1))

        ra_mask = ra < 0

        ra[ra_mask] += 2 * np.pi

        dec = 90 - np.rad2deg(dec)

        ra = np.rad2deg(ra)

        return ra, dec

    def is_occulted(self, time, ra, dec):
        """
        Check if a position defined by ra and dec (in ICRS) is occulted at
        the given time
        :param time: time of interest (float)
        :param ra: ra of source (array or float)
        :param dec: dec of source (array or float)
        :returns: bool
        """

        # get sc pos at this time
        sc_pos = self._position_interpolator.sc_pos(time)

        # earth opening angle seen from sat
        earth_radius = 6371.0
        fermi_radius = np.sqrt((sc_pos ** 2).sum())
        horizon_angle = 90 - np.rad2deg(np.arccos(earth_radius / fermi_radius))
        min_vis = np.deg2rad(horizon_angle)

        # vector defined by ra and dec
        cart_position = ang2cart(ra, dec)

        # angle between the two vectors
        ang_sep = get_ang(cart_position, -sc_pos)

        # check if occulted
        return ang_sep < min_vis

    def sc_pos(self, time):
        """
        Returns the spacecraft position, in ECI coordinates,
        for given time. Unit: km (!)
        """
        return self._position_interpolator.sc_pos(time)

    def _get_gbm_geom_det(self, time, det_name="n0"):

        sc_pos = self._position_interpolator.sc_pos(time)
        quaternions = self._position_interpolator.quaternion(time)

        det = gbm_detector_list[det_name](
            quaternion=quaternions,
            sc_pos=sc_pos,
            time=astro_time.Time(
                self._position_interpolator.utc(time)
            ),
        )

        return det

    def earth_pos_cart(self, time):
        """
        Earth position in sat frame for a given time as 3D-vector
        """

        # get gbm_geometry object at given time
        det_geom = self._get_gbm_geom_det(time)

        # get earth position in sat frame
        earth_az_zen = det_geom.earth_az_zen_sat

        # calc vector
        earth_cart = ang2cart(*earth_az_zen)

        return earth_cart

    def sun_pos_cart(self, time):
        """
        Sun position in sat frame for a given time as 3D-vector
        """
        # get gbm_geometry object at given time
        det_geom = self._get_gbm_geom_det(time)

        # get earth position in sat frame
        sun_az_zen = [det_geom.sun_position.lon.deg,
                      det_geom.sun_position.lat.deg]

        # calc vector
        sun_cart = ang2cart(*sun_az_zen)

        return sun_cart

    def _create_bgo_cr_tracer_interp(self, date, side, echans=np.arange(85,105,1)):


        # download bgo data
        datafile_path = download_gbm_file(date, "cspec", f"b{side}")

        # read in data
        with fits.open(datafile_path) as f:
            counts = f["SPECTRUM"].data["COUNTS"][:, echans[0]]
            for echan in echans[1:]:
                counts += f["SPECTRUM"].data["COUNTS"][:, echan]
            bin_start = f["SPECTRUM"].data["TIME"]
            bin_stop = f["SPECTRUM"].data["ENDTIME"]

        # bin in 100 second bins
        total_time_bins = np.vstack((bin_start, bin_stop)).T
        min_bin_width = 100

        this_rebinner = Rebinner(total_time_bins, min_bin_width)
        rebinned_time_bins = this_rebinner.time_rebinned
        (rebinned_counts,) = this_rebinner.rebin(counts)

        rates = rebinned_counts / (rebinned_time_bins[:, 1] - rebinned_time_bins[:, 0])

        # Add first time and last time with corresponding rate to rate_list
        rates = np.concatenate((rates[:1], rates, rates[-1:]))

        times = np.concatenate(
            (bin_start[:1], np.mean(rebinned_time_bins, axis=1), bin_stop[-1:])
        )
        interp_tracer = interpolate.UnivariateSpline(
                times, rates, s=1000, k=3
            )

        def final_tracer(x):
            return interp_tracer(x)-interp_tracer(x).min()

        self._interp_tracer = final_tracer
    
    def _create_mcl_cr_tracer_interp(self, date):
        """
        create mcl interpolation function
        """

        # read the file
        year = "20%s" % date[:2]
        month = date[2:-2]
        dd = date[-2:]

        day = astro_time.Time("%s-%s-%s" % (year, month, dd))

        min_met = GBMTime(day).met

        max_met = GBMTime(day + u.Quantity(1, u.day)).met

        gbm_time = GBMTime(day)

        mission_week = np.floor(gbm_time.mission_week.value)

        filepath = download_lat_spacecraft(mission_week)

        # Init all arrays as empty arrays
        lat_time = np.array([])
        mc_l = np.array([])

        # lets check that this file has the right info

        week_before = False
        week_after = False

        with fits.open(filepath) as fits_file:

            # do we need the week before?
            if fits_file["PRIMARY"].header["TSTART"] >= min_met:
                # we need to get week before
                week_before = True

                before_filepath = download_lat_spacecraft(mission_week-1)

            # do we need the next week?
            if fits_file["PRIMARY"].header["TSTOP"] <= max_met:

                # we need to get week after

                week_after = True

                after_filepath = download_lat_spacecraft(mission_week+1)

            # first lets get the primary file

            lat_time = np.mean(
                np.vstack((fits_file["SC_DATA"].data["START"],
                           fits_file["SC_DATA"].data["STOP"])),
                axis=0,
            )
            mc_l = fits_file["SC_DATA"].data["L_MCILWAIN"]

        # if we need to append anything to make up for the
        # dates not being included in the files
        # do it here...
        if week_before:
            with fits.open(before_filepath) as fits_file:
                lat_time_before = np.mean(
                    np.vstack((fits_file["SC_DATA"].data["START"],
                               fits_file["SC_DATA"].data["STOP"])),
                    axis=0,
                )
                mc_l_before = fits_file["SC_DATA"].data["L_MCILWAIN"]

            mc_l = np.append(mc_l_before, mc_l)
            lat_time = np.append(lat_time_before, lat_time)

        if week_after:
            with fits.open(after_filepath) as fits_file:
                lat_time_after = np.mean(
                    np.vstack((fits_file["SC_DATA"].data["START"],
                               fits_file["SC_DATA"].data["STOP"])),
                    axis=0,
                )
                mc_l_after = fits_file["SC_DATA"].data["L_MCILWAIN"]

            mc_l = np.append(mc_l, mc_l_after)
            lat_time = np.append(lat_time, lat_time_after)

        # get mc_l diff
        mc_l -= np.min(mc_l)

        self._interp_tracer = interp1d(lat_time, mc_l)

    def cr_tracer(self, time):
        """
        Returns the McIlwain L-parameter difference for the satellite position
        for a given time and the minumum mcl value
        :param time: times of interest (array or float)
        """
        return self._interp_tracer(time)


class GBMGeometryPosHist(GBMGeometry):

    def __init__(self, date,cr_tracer_type="MCL", bgo_side=None):

        # download data file and get file location
        poshist_path = download_gbm_file(date, "poshist")

        # construct position interpolator object
        self._position_interpolator = PositionInterpolator.from_poshist(
            poshist_file=poshist_path
        )

        super().__init__(date,cr_tracer_type=cr_tracer_type,bgo_side=bgo_side)


class GBMGeometryTrigdat(GBMGeometry):

    def __init__(self, trigger,cr_tracer_type="MCL", bgo_side=None):

        # download trigdat file
        trigger_path = download_trigdata_file(trigger)

        # construct position interpolator object
        self._position_interpolator = PositionInterpolator.from_trigdat(
            trigdat_file=trigger_path
        )

        raise NotImplementedError("Not implemented yet. Need to get date from trigger object.")
        super().__init__(date)
