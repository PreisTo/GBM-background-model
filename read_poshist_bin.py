#!/usr/bin python2.7

import os
import matplotlib.pyplot as plt
import numpy as np
import math
import pyfits
from numpy import linalg as LA
import ephem

class n0:
    azimuth = 45.8899994*2*math.pi/360.
    zenith = 20.5799999*2*math.pi/360.
    azimuthg = 45.8899994
    zenithg = 20.5799999

class n1:
    azimuth = 45.1100006*2*math.pi/360.
    zenith = 45.3100014*2*math.pi/360.
    azimuthg = 45.1100006
    zenithg = 45.3100014

class n2:
    azimuth = 58.4399986*2*math.pi/360.
    zenith = 90.2099991*2*math.pi/360.
    azimuthg = 58.4399986
    zenithg = 90.2099991

class n3:
    azimuth = 314.869995*2*math.pi/360.
    zenith = 45.2400017*2*math.pi/360.
    azimuthg = 314.869995
    zenithg = 45.2400017

class n4:
    azimuth = 303.149994*2*math.pi/360.
    zenith = 90.2699966*2*math.pi/360.
    azimuthg = 303.149994
    zenithg = 90.2699966

class n5:
    azimuth = 3.34999990*2*math.pi/360.
    zenith = 89.7900009*2*math.pi/360.
    azimuthg = 3.34999990
    zenithg = 89.7900009

class n6:
    azimuth = 224.929993*2*math.pi/360.
    zenith = 20.4300003*2*math.pi/360.
    azimuthg = 224.929993
    zenithg = 20.4300003

class n7:
    azimuth = 224.619995*2*math.pi/360.
    zenith = 46.1800003*2*math.pi/360.
    azimuthg = 224.619995
    zenithg = 46.1800003

class n8:
    azimuth = 236.610001*2*math.pi/360.
    zenith = 89.9700012*2*math.pi/360.
    azimuthg = 236.610001
    zenithg = 89.9700012

class n9:
    azimuth = 135.190002*2*math.pi/360.
    zenith = 45.5499992*2*math.pi/360.
    azimuthg = 135.190002
    zenithg = 45.5499992

class na:
    azimuth = 123.730003*2*math.pi/360.
    zenith = 90.4199982*2*math.pi/360.
    azimuthg = 123.730003
    zenithg = 90.4199982

class nb:
    azimuth = 183.740005*2*math.pi/360.
    zenith = 90.3199997*2*math.pi/360.
    azimuthg = 183.740005
    zenithg = 90.3199997

class b0:
    azimuth = math.acos(1)
    zenith = math.asin(1)
    azimuthg = 0.0
    zenithg = 90.0

class b1:
    azimuth = math.pi
    zenith = math.asin(1)
    azimuthg = 180.0
    zenithg = 90.0

def read_ctime(detector, day, seconds = 0):
    """This function reads a cspec file and stores the data in arrays of the form: echan[emin, emax], total_counts, echan_counts[echan], exptime, total_rate, echan_rate, cstart, cstop, gtstart, gtstop\n
    Input:\n
    read_ctime ( detector, day = YYMMDD, seconds = SSS )\n
    0 = energy channel interval\n
    1 = total number of counts\n
    2 = number of counts per energy channel\n
    3 = total count rate\n
    4 = count rate per energy channel\n
    5 = bin time interval[start, end]\n
    6 = good time interval[start, end]\n
    7 = time of exposure\n"""
    
    #read the file. Check if one wants to read a specific trigger file or a daily file
    if seconds == 0:
        filename = 'glg_ctime_' + str(detector) + '_' + str(day) + '_v00.pha'
    else:
        filename = 'glg_ctime_' + str(detector) + '_bn' + str(day) + str(seconds) + '_v00.pha'
    __dir__ = os.path.dirname(os.path.abspath(__file__))
    fits_path = os.path.join(os.path.dirname(__dir__), 'ctime')
    filepath = os.path.join(fits_path, str(filename))
    fits = pyfits.open(filepath)
    energy = fits[1].data
    spectrum = fits[2].data
    goodtime = fits[3].data
    fits.close()
    
    #extract the data
    emin = energy['E_MIN'] #lower limit of the energy channels
    emax = energy['E_MAX'] #upper limit of the energy channels
    echan = np.zeros((len(emin),2), float) #combine the energy limits of the energy channels in one matrix
    echan[:,0] = emin
    echan[:,1] = emax
    counts = spectrum['COUNTS']
    total_counts = np.sum(counts, axis=1) #total number of counts for each time intervall
    echan_counts = np.vstack(([counts[:,0].T], [counts[:,1].T], [counts[:,2].T], [counts[:,3].T], [counts[:,4].T], [counts[:,5].T], [counts[:,6].T], [counts[:,7].T])) #number of counts as a table with respect to the energy channel -> echan_counts[0] are the counts for the first energy channel
    exptime = spectrum['EXPOSURE'] #length of the time intervall
    total_rate = np.divide(total_counts, exptime) #total count rate for each time intervall
    echan_rate = np.divide(echan_counts, exptime) #count rate per time intervall for each energy channel
    cstart = spectrum['TIME'] #start time of the time intervall
    cstop = spectrum['ENDTIME'] #end time of the time intervall
    #bin_time = np.zeros((len(cstart),2), float) #combine the time limits of the counting intervals in one matrix
    #bin_time[:,0] = cstart
    #bin_time[:,1] = cstop
    gtstart = goodtime['START'] #start time of data collecting times (exiting SAA)
    gtstop = goodtime['STOP'] #end time of data collecting times (entering SAA)
    #times are in Mission Elapsed Time (MET) seconds. See Fermi webside or read_poshist for more information.
    good_time = np.zeros((len(gtstart),2), float) #combine the time limits of the goodtime intervals in one matrix
    good_time[:,0] = gtstart
    good_time[:,1] = gtstop
    return echan, total_counts, echan_counts, total_rate, echan_rate, cstart, cstop, good_time, exptime




def read_poshist_bin(day, bin_time_mid = 0, detector = 0, data_type = 'ctime'):
    """This function reads a posthist file, converts the data-arrays into the form of the bin_time-arrays from the 'ctime' or 'cspec' files and stores the data in arrays of the form: sat_time_bin, sat_pos_bin, sat_lat_bin, sat_lon_bin, sat_q_bin, bin_time_mid.\n
    Input:\n
    read_poshist ( day = YYMMDD,\n
    bin_time_mid = 0(input bin_time_mid if available; default: 0), \n
    detector = 0(input the detector in the form det.n0; default: 0), \n
    data_type = 'ctime'(input ctime or cspec as string; default: 'ctime') )\n
    Output:\n
    0 = time\n
    1 = position (x, y, z)\n
    2 = latitude\n
    3 = longitude\n
    4 = quaternion matrix (q1, q2, q3, q4)\n
    5 = bin_time_mid"""
    
    #read the file
    filename = 'glg_poshist_all_' + str(day) + '_v00.fit'
    __dir__ = os.path.dirname(os.path.abspath(__file__))
    fits_path = os.path.join(os.path.dirname(__dir__), 'poshist')
    filepath = os.path.join(fits_path, str(filename))
    fits = pyfits.open(filepath)
    data = fits[1].data
    fits.close()
    
    #extract the data
    sat_time = data.SCLK_UTC #Mission Elapsed Time (MET) seconds. The reference time used for MET is midnight (0h:0m:0s) on January 1, 2001, in Coordinated Universal Time (UTC). The FERMI convention is that MJDREF=51910 (UTC)=51910.0007428703703703703 (TT)
    sat_pos = np.array([data.POS_X, data.POS_Y, data.POS_Z]) #Position in J2000 equatorial coordinates
    sat_lat = data.SC_LAT
    sat_lon = data.SC_LON #Earth-angles -> considers earth rotation (needed for SAA)
    sat_q = np.array([data.QSJ_1, data.QSJ_2, data.QSJ_3, data.QSJ_4]) #Quaternionen -> 4D-space with which one can describe rotations (rocking motion); regarding the satellite system with respect to the J2000 geocentric coordinate system
    
    #convert the data-arrays
    #sat_time
    sat_time_conv = calc_intpol(sat_time, day, 0, sat_time, bin_time_mid, datector, data_type)
    sat_time_bin = sat_time_conv[0]
    bin_time_mid = sat_time_conv[2]
    #sat_pos
    sat_pos_bin = calc_intpol(sat_pos, day, 0, sat_time, bin_time_mid, datector, data_type)
    #sat_lat
    sat_lat_bin = calc_intpol(sat_lat, day, 0, sat_time, bin_time_mid, datector, data_type)
    #sat_lon
    sat_lon_bin = calc_intpol(sat_lon, day, 0, sat_time, bin_time_mid, datector, data_type)
    #sat_q
    sat_q_bin = calc_intpol(sat_q, day, 0, sat_time, bin_time_mid, datector, data_type)
    return sat_time_bin, sat_pos_bin, sat_lat_bin, sat_lon_bin, sat_q_bin, bin_time_mid

day = 150926
detector = n0

ctime_data = read_ctime(detector.__name__, day)
echan = ctime_data[0]
total_counts = ctime_data[1]
echan_counts = ctime_data[2]
total_rate = ctime_data[3]
echan_rate = ctime_data[4]
cstart = ctime_data[5]
cstop = ctime_data[6]
good_time = ctime_data[7]
exptime = ctime_data[8]

sat_data = read_poshist_bin(day)
sat_time_bin = sat_data[0]
sat_pos_bin = sat_data[1]
sat_lat_bin = sat_data[2]
sat_lon_bin = sat_data[3]
sat_q_bin = sat_data[4]
bin_time_mid = sat_data[5]



plt.plot(bin_time_mid, sat_time)

plt.show()
