import numpy as np
from gbm_drm_gen.drmgen import DRMGen
import os
from gbmbkgpy.io.package_data import get_path_of_data_dir, get_path_of_data_file, get_path_of_external_data_dir
import astropy.io.fits as fits

try:

    # see if we have mpi and/or are upalsing parallel

    from mpi4py import MPI
    if MPI.COMM_WORLD.Get_size() > 1: # need parallel capabilities
        using_mpi = True

        comm = MPI.COMM_WORLD
        rank = comm.Get_rank()

    else:

        using_mpi = False
except:

    using_mpi = False


class Rate_Generator_DRM(object):
    """
    With this Class one can generate the counts in all Energy bins for given spectra of the earth albeo
    and the CGB for all directions around the detector. It uses the full GBM DRMs which contain scattering
    in the satellite and partial energy loss of the photons.
    The rates are calculated on a spherical grid around the detector.
    """
    def __init__(self, det, day, Ngrid=None, Ebin_edge_incoming=None, data_type='ctime'):
        """
        initialize the grid around the detector and set the values for the Ebins of incoming and detected photons
        :param det: which detector is used
        :param Ngrid: Number of Gridpoints for Grid around the detector
        :param Ebin_edge_incoming: Ebins edges of incomming photons
        :param Ebin_edge_detector: Ebins edges of detector
        """
        self._data_type = data_type

        #if no values for Ngrid, Ebin_incoming and/or Ebin_detector are given we use the standard values
        if Ngrid==None:
            Ngrid=40000
        else:
            assert type(Ngrid) == int, 'Ngrid has to be an integer!'
        if Ebin_edge_incoming==None:
            # incoming spectrum between ~3 and ~5000 keV
            Ebin_edge_incoming=np.array(np.logspace(0.5, 3.7, 301), dtype=np.float32)
        if data_type=='ctime' or data_type=='cspec':
            datafile_name = 'glg_{0}_{1}_{2}_v00.pha'.format(data_type, det, day)
            datafile_path = os.path.join(get_path_of_external_data_dir(), data_type, day, datafile_name)
            with fits.open(datafile_path) as f:
                edge_start = f['EBOUNDS'].data['E_MIN']
                edge_stop = f['EBOUNDS'].data['E_MAX']
            self._Ebin_out_edge = np.append(edge_start, edge_stop[-1])
        else:
            print('Use a valid data_typ. Either ctime or cspec')
        self._points = np.array(self._fibonacci_sphere(samples=Ngrid))
        self._Ngrid = Ngrid
        self._Ebin_in_edge = Ebin_edge_incoming
        if det[0]=='n':
            if det[1]=='a':
                self._det=10
            elif det[1]=='b':
                self._det=11
            else:
                self._det=int(det[1])
        elif det[0]=='b':
            if det[1]=='0':
                self._det=12
            elif det[1]=='1':
                self._det=13
        else:
            print('Please use a valid detector name!')

        # Run a function that precalculates the responses for all points - supports MPI to speed this up
        if using_mpi:
            points_per_rank = float(Ngrid) / float(size)
            points_lower_index = int(np.floor(points_per_rank * rank))
            points_upper_index = int(np.floor(points_per_rank * (rank + 1)))
            Response_array_rank = self._build_response(points_lower_index, points_upper_index)
            # gather in rank 0
            Response_array_all = comm.gather(Response_array_rank, root=0)
            # put them in one list
            if rank == 0:
                Response_array_all = np.concatenate(Response_array_all)
            # broadcast the resulting list to all ranks
            Response_array = comm.bcast(Response_array_all, root=0)
            self._Response_array = Response_array
        else:
            self._Response_array = self._build_response(0, self._Ngrid)

        #Set the initial values for the spectra of earth and CGB. Can be changed with the corresponding methods

        #cgb spectrum
        #self._C_cgb = (10.15) * 10 ** (-2)
        self._index1_cgb = 1.32
        self._index2_cgb = 2.88
        self._break_energy_cgb = 29.99

        #earth spectrum
        #self._C_earth = (1.48) * 10 ** (-2)
        self._index1_earth = -5
        self._index2_earth = 1.72
        self._break_energy_earth = 33.7

        #Points sources spectrum
        self._index_ps = 2
    def _fibonacci_sphere(self, samples=1):
        rnd = 1.

        points = []
        offset = 2. / samples
        increment = np.pi * (3. - np.sqrt(5.));

        for i in range(samples):
            y = ((i * offset) - 1) + (offset / 2);
            r = np.sqrt(1 - pow(y, 2))

            phi = ((i + rnd) % samples) * increment

            x = np.cos(phi) * r
            z = np.sin(phi) * r

            points.append([x, y, z])

        return points

    def _build_response(self, points_lower_index, points_upper_index):
        """
        Function to precalculate the responses for all points on the grid. Parameters important for MPI.
        :param points_lower_index: gives the start index of the points array with which this rank should start
        :param points_upper_index: gives the stop index (-1) of the points array with which this rank should stop
        :return: Response for all points between points_lower_index and points_upper_index
        """
        Response_list=[]
        for point in self._points[points_lower_index:points_upper_index]:
            # Create a DRMGen object to get the Instrumentresponse later. The values for the quaterions and sc_pos are dummy
            # values. Not needed, because we will calculate everything in the sat. frame and do not consider athmospheric
            # scattering
            DRM = DRMGen(np.array([0.0745, -0.105, 0.0939, 0.987]),
                         np.array([-5.88 * 10 ** 6, -2.08 * 10 ** 6, 2.97 * 10 ** 6]), self._det, self.Ebin_in_edge,
                         mat_type=0, ebin_edge_out=self._Ebin_out_edge)
            rsp = self._response(point[0], point[1], point[2], DRM)
            #add to list
            Response_list.append(rsp)
        return np.array(Response_list)
    @property
    def points(self):
        return self._points

    @property
    def Ngrid(self):
        return self._Ngrid

    @property
    def Ebin_in_edge(self):
        return self._Ebin_in_edge

    @property
    def Ebin_out_edge(self):
        return self._Ebin_out_edge

    def set_earth_spectra(self, index1, index2, break_energy):
        """
        Set the constants of the earth spectrum
        :param index1:
        :param index2:
        :param break_energy:
        :return:
        """
        #self._C_earth = C
        self._index1_earth = index1
        self._index2_earth = index2
        self._break_energy_earth = break_energy

    def set_cgb_spectra(self, index1, index2, break_energy):
        """
        Set the constants of the cgb spectrum
        :param index1:
        :param index2:
        :param break_energy:
        :return:
        """
        #self._C_cgb = C
        self._index1_cgb = index1
        self._index2_cgb = index2
        self._break_energy_cgb = break_energy

    def set_Ebin_edge_incoming(self, Ebin_edge_incoming):
        """
        Set new Ebins for the incoming photons
        :param Ebin_edge_incoming:
        :return:
        """
        self._Ebin_in_edge=Ebin_edge_incoming

    def set_Ebin_edge_outcoming(self, Ebin_edge_outcoming):
        """
        set new Ebins for the detector
        :param Ebin_edge_outcoming:
        :return:
        """
        self._Ebin_out_edge=Ebin_edge_outcoming

    def _response(self, x, y, z, DRM):
        """
        gives the Instrumentresponse for a certain point on the unit sphere around the detector

        :param x: x-positon on unit sphere in sat. coord
        :param y: y-positon on unit sphere in sat. coord
        :param z: z-positon on unit sphere in sat. coord
        :param DRM: The DRM object
        :return:
        """
        zen = np.arcsin(z) * 180 / np.pi
        az = np.arctan2(y, x) * 180 / np.pi
        return DRM.to_3ML_response_direct_sat_coord(az, zen)

    def _spectrum(self, energy, C, index1, index2, break_energy):
        """
        define the function of a broken power law. Needed for earth and cgb spectrum
        :param energy:
        :param C:
        :param index1:
        :param index2:
        :param break_energy:
        :return:
        """
        return C / ((energy / break_energy) ** index1 + (energy / break_energy) ** index2)


    """Earth"""

    def _differential_flux_earth(self, e):
        """
        calculate the diff. flux with the constants defined for the earth
        :param e: Energy of incoming photon
        :return: differential flux
        """
        C = 1  # set the constant=1 will be fitted later to fit the data best
        return self._spectrum(e, C, self._index1_earth, self._index2_earth, self._break_energy_earth)

    def _integral_earth(self, e1, e2):
        """
        method to integrate the diff. flux over the Ebins of the incoming photons
        :param e1: lower bound of Ebin_in
        :param e2: upper bound of Ebin_in
        :return: flux in the Ebin_in
        """
        return (e2 - e1) / 6.0 * (
                self._differential_flux_earth(e1) + 4 * self._differential_flux_earth((e1 + e2) / 2.0) +
                self._differential_flux_earth(e2))
    """CGB"""
    def _differential_flux_cgb(self, e):
        """
        same as for Earth, just other constants
        :param e: Energy
        :return: differential flux
        """
        C = 1  # set the constant=1 will be fitted later to fit the data best
        return self._spectrum(e, C, self._index1_cgb, self._index2_cgb, self._break_energy_cgb)

    def _integral_cgb(self, e1, e2):
        """
        same as for earth
        :param e1: lower bound of Ebin_in
        :param e2: upper bound of Ebin_in
        :return: flux in the Ebin_in
        """
        return (e2 - e1) / 6.0 * (
                self._differential_flux_cgb(e1) + 4 * self._differential_flux_cgb((e1 + e2) / 2.0) +
                self._differential_flux_cgb(e2))

    def calculate_earth_rates(self, points_index_start, points_index_stop):
        """
        Function to calculate the expected rates from all the points on the unit sphere for the assumed
        spectra for earth. Parameter important for MPI calculation.
        :param points_index_start:
        :param points_index_stop:
        :return:
        """
        # calculate the sr that one point occults, depends on how many points are used
        sr_points = 4 * np.pi / self._Ngrid
        # loop the points array and calculate the expected rate in every Ebin.
        # This is done by convolving the true flux we get from the spectrum we assume for earth
        # with the response matrix for every point
        folded_rates_earth = []
        for i in range(points_index_start, points_index_stop):
            # get the response of the i'th point of the grid (precalculated above)
            rsp = self._Response_array[i]
            true_flux_earth = self._integral_earth(rsp.monte_carlo_energies[:-1], rsp.monte_carlo_energies[1:])
            folded_rate_earth = np.dot(true_flux_earth, rsp.matrix.T) * sr_points
            folded_rates_earth.append(folded_rate_earth)

        return np.array(folded_rates_earth)

    def calculate_cgb_rates(self, points_index_start, points_index_stop):
        """
        Function to calculate the expected rates from all the points on the unit sphere for the assumed
        spectra for cgb. Parameter important for MPI calculation.
        :param points_index_start:
        :param points_index_stop:
        :return:
        """
        # calculate the sr that one point occults, depends on how many points are used
        sr_points = 4 * np.pi / self._Ngrid
        # loop the points array and calculate the expected rate in every Ebin.
        # This is done by convolving the true flux we get from the spectrum we assume for cgb
        # with the response matrix for every point
        folded_rates_cgb = []
        for i in range(points_index_start, points_index_stop):
            # get the response of the i'th point of the grid (precalculated above)
            rsp = self._Response_array[i]
            true_flux_cgb = self._integral_cgb(rsp.monte_carlo_energies[:-1], rsp.monte_carlo_energies[1:])
            folded_rate_cgb = np.dot(true_flux_cgb, rsp.matrix.T) * sr_points
            folded_rates_cgb.append(folded_rate_cgb)

        return np.array(folded_rates_cgb)

    ###################################################### FOR POINTSOURCES

    def _spectrum_ps(self, energy, C, index):
        """
        define the function of a power law. Needed for PS spectrum
        :param energy:
        :param C:
        :param index:
        :return:
        """
        return C / energy**index

    def _differential_flux_ps(self, e):
        """
        calculate the diff. flux with the constants defined for the earth
        :param e: Energy of incoming photon
        :return: differential flux
        """
        C = 1  # set the constant=1 will be fitted later to fit the data best
        return self._spectrum_ps(e, C, self._index_ps)

    def _integral_ps(self, e1, e2):
        """
        method to integrate the diff. flux over the Ebins of the incoming photons
        :param e1: lower bound of Ebin_in
        :param e2: upper bound of Ebin_in
        :return: flux in the Ebin_in
        """
        return (e2 - e1) / 6.0 * (
                self._differential_flux_ps(e1) + 4 * self._differential_flux_ps((e1 + e2) / 2.0) +
                self._differential_flux_ps(e2))

    def calculate_ps_rates(self, points_index_start, points_index_stop):
        """
        Function to calculate the expected rates from all the points on the unit sphere for the assumed
        spectra for a ps. Parameter important for MPI calculation.
        :param points_index_start:
        :param points_index_stop:
        :return:
        """
        # loop the points array and calculate the expected rate in every Ebin.
        # This is done by convolving the true flux we get from the spectrum we assume for ps
        # with the response matrix for every point
        folded_rates_ps = []
        for i in range(points_index_start, points_index_stop):
            # get the response of the i'th point of the grid (precalculated above)
            rsp = self._Response_array[i]
            true_flux_ps = self._integral_ps(rsp.monte_carlo_energies[:-1], rsp.monte_carlo_energies[1:])
            folded_rate_ps = np.dot(true_flux_ps, rsp.matrix.T)
            folded_rates_ps.append(folded_rate_ps)

        return np.array(folded_rates_ps)