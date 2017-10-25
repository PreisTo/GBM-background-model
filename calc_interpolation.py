#!/usr/bin python2.7

import os
import matplotlib.pyplot as plt
import numpy as np
import math
import pyfits
from numpy import linalg as LA
import ephem
from scipy import interpolate

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


def read_poshist(day):
    """This function reads a posthist file and stores the data in arrays of the form: sat_time, sat_pos, sat_lat, sat_lon, sat_q.\n
    Input:\n
    read_poshist ( day = YYMMDD )\n
    Output:\n
    0 = time\n
    1 = position (x, y, z)\n
    2 = latitude\n
    3 = longitude\n
    4 = quaternion matrix (q1, q2, q3, q4)"""
    
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
    return sat_time, sat_pos, sat_lat, sat_lon, sat_q


def calc_intpol(vector, day, direction = 0, sat_time = 0, bin_time_mid = 0, detector = 0, data_type = 'ctime'):
    """This function interpolates a vector (from poshist- or count-files) and adjusts the length to the arrays of the other source-file and stores the data in an array of the form: vector\n
    Input:\n
    calc_intpol ( vector, \n
    day = JJMMDD, \n
    direction = 0(from poshist- to count-file(0) or the other way(1); default: 0), \n
    sat_time = 0(input sat_time if available; default: 0), \n
    bin_time = 0(input bin_time if available; default: 0), \n
    detector = 0(input the detector in the form det.n0; default: 0), \n
    data_type = 'ctime'(input ctime or cspec as string; default: 'ctime') )\n
    Output:\n
    0 = vector\n
    1 = sat_time\n
    2 = bin_time"""
    
    #get the missing satellite and measurement data, if needed
    if sat_time == 0:
        sat_data = read_poshist(day)
        sat_time = np.array(sat_data[0]) #time (MET) in seconds

    if bin_time_mid == 0:
        if detector != 0:
            if data_type == 'ctime':
                bin_data = read_ctime(detector, day)
                bin_time = np.array(bin_data[5]) #time (MET) in seconds
                bin_time_mid = np.array((bin_time[:,0]+bin_time[:,1])/2)#convert bin_time into 1-D array. Take the medium of start and stop time of the bin.
            elif data_type == 'cspec':
                bin_data = read_cspec(detector, day)
                bin_time = np.array(bin_data[5]) #time (MET) in seconds
                bin_time_mid = np.array((bin_time[:,0]+bin_time[:,1])/2)#convert bin_time into 1-D array. Take the medium of start and stop time of the bin.
            else:
                print "Invalid data_type input. Please insert 'ctime' or 'cspec' for the data_type. See .__doc__ for further information."
                return vector, sat_time, bin_time
        else:
            print "Missing or false detector input. Please insert the chosen detector (f. e. det.n0). See .__doc__ for further information."
            return vector, sat_time, bin_time
    
    #define x-values depending on the direction of the interpolation
    if direction == 0:
        x1 = np.array(sat_time)
        x2 = np.array(bin_time_mid)
    elif direction == 1:
        x1 = np.array(bin_time_mid)
        x2 = np.array(sat_time)
    else:
        print 'Invalid direction input. Please insert 0 or 1 for the direction. See .__doc__ for further information.'
        return vector, sat_time, bin_time_mid
    
    vector_shape = np.shape(vector)
    vector_dim = vector_shape[0]
    
    #interpolate all subvectors of the input vector with splines and evaluate the splines at the new x-values
    if len(vector_shape) == 1:
        tck = interpolate.splrep(x1, vector, s=0)
        new_vector = interpolate.splev(x2, tck, der=0)
    else:
        new_vector = np.zeros((vector_dim, len(x2)), float)
        for i in range(0, vector_dim):
            tck = interpolate.splrep(x1, vector[i], s=0)
            new_vector[i] = interpolate.splev(x2, tck, der=0)
    
    return new_vector, sat_time, bin_time_mid

day = 150926
x0 = [1, 3, 5]
interp = calc_intpol(x0, day, 0, 0, 0, 0, 'whatever')
x1 = interp[0]
print x1


#n0_occ = calc_earth_ang(n0, day)
#earth_ang = n0_occ[0]
#sat_time = n0_occ[1]
#daytime = (sat_time - sat_time[0] + 5)/3600.

#plt.plot(daytime, earth_ang, 'b-')

#plt.xlabel('time of day')
#plt.ylabel('occultation angle')

#plt.title('Earth-occultation of the n0-detector on the 26th Sept 2015')

#plt.show()
