#!/usr/bin python2.7

import subprocess
from subprocess import Popen, PIPE
import os
import matplotlib.pyplot as plt
import numpy as np
import math
import pyfits
from numpy import linalg as LA
import ephem
from scipy import interpolate
import scipy.optimize as optimization
from astropy.time import Time
from astropy.table import Table
from astropy.io import fits
import fileinput
from datetime import datetime
from work_module import calculate
from work_module import detector
from work_module import readfile
from work_module import writefile
calc = calculate()
det = detector()
rf = readfile()
wf = writefile()

#docstrings of the different self-made classes within the self-made module
#cdoc = calc.__doc__
#ddoc = det.__doc__
#rdoc = rf.__doc__



day = 150926
detector = det.n5
data_type = 'ctime'
year = int('20' + str(day)[0:2])

#get the iso-date-format from the day
date = datetime(year, int(str(day)[2:4]), int(str(day)[4:6]))

#get the ordinal indicator for the date
ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n/10%10!=1)*(n%10<4)*n%10::4])

#read the measurement data
ctime_data = rf.ctime(detector, day)
echan = ctime_data[0]
total_counts = ctime_data[1]
echan_counts = ctime_data[2]
total_rate = ctime_data[3]
echan_rate = ctime_data[4]
bin_time = ctime_data[5]
good_time = ctime_data[6]
exptime = ctime_data[7]
bin_time_mid = np.array((bin_time[:,0]+bin_time[:,1])/2)

echan = 6
counts = echan_counts[echan]#define which energy-channels one wants to look at

#read the satellite data
sat_data = rf.poshist_bin(day, bin_time_mid, detector, data_type)
sat_time_bin = sat_data[0]
sat_pos_bin = sat_data[1]
sat_lat_bin = sat_data[2]
sat_lon_bin = sat_data[3]
sat_q_bin = sat_data[4]

#calculate the sun data
sun_data = calc.sun_ang_bin(detector, day, bin_time_mid, data_type)
sun_ang_bin = sun_data[0]
sun_ang_bin = calc.ang_eff(sun_ang_bin, echan)[0]


#calculate the earth data
earth_data = calc.earth_ang_bin(detector, day, bin_time_mid, data_type)
earth_ang_bin = earth_data[0]
earth_ang_bin = calc.ang_eff(earth_ang_bin, echan)[0]

'''#get the fits data from the effective area plots
fitsname = 'peak_eff_area_angle_calib_GBM_all.fits'
__dir__ = os.path.dirname(os.path.abspath(__file__))
directory = 'calibration'
path = os.path.join(os.path.dirname(__dir__), directory)
fitsfilepath = os.path.join(path, fitsname)
fits = fits.open(fitsfilepath, mode='update')
data = fits[1].data
fits.close()
x = data.field(0)
y1 = data.field(1)#for NaI echan[0:2]
y2 = data.field(2)#for NaI echan[4]
y3 = data.field(3)#for NaI echan[6]
y4 = data.field(4)#for BGO (898 keV)
y5 = data.field(5)#for BGO (1836 keV)
#normalize the factor to 0 degrees
y1 = y1/y1[90]
y2 = y2/y2[90]
y3 = y3/y3[90]
y4 = y4/y4[90]
y5 = y5/y5[90]
#calculate the angle factors
tck = interpolate.splrep(x, y3)
sun_angle_factor = interpolate.splev(sun_ang_bin, tck, der=0)
earth_angle_factor = interpolate.splev(earth_ang_bin, tck, der=0)
#convert the angle according to their factors
sun_ang_bin = sun_angle_factor*sun_ang_bin
earth_ang_bin = earth_angle_factor*earth_ang_bin'''


#read the SFL data
flares = rf.flares(year)
flares_day = flares[0]
flares_time = flares[1]
if np.any(flares_day == day) == True:
    flares_today = flares_time[:,np.where(flares_day == day)]
    flares_today = np.squeeze(flares_today, axis=(1,))/3600.
else:
    flares_today = np.array(-5)

#periodical function corresponding to the orbital behaviour -> reference day is 150926, periodical shift per day is approximately 0.199*math.pi
sat_time = rf.poshist(day)[0]
def j2000_orb(f, g, counts):#J2000-position oriented orbit
    j2000_orb = f*(calc.intpol(np.sin((2*math.pi*np.arange(len(sat_time)))/5531 + g), day, 0, sat_time, bin_time_mid, detector)[0])
    j2000_orb[np.where(counts == 0)] = 0
    return j2000_orb

def geo_orb(b, c, counts):#LON-oriented orbit (earth rotation considered -> orbit within the magnetic field of the earth)
    geo_orb = b*(calc.intpol(np.sin((2*math.pi*np.arange(len(sat_time)))/6120.85 + c), day, 0, sat_time, bin_time_mid, detector)[0])
    geo_orb[np.where(counts == 0)] = 0
    return geo_orb


#constant function corresponding to the diffuse y-ray background
cgb = np.ones(len(counts))


cgb[np.where(counts == 0)] = 0
earth_ang_bin[np.where(counts == 0)] = 0
sun_ang_bin[np.where(counts == 0)] = 0


def fit_function(x, a, b, c, d, e, f, g):
    return a*cgb + geo_orb(b, c, counts) + d*earth_ang_bin + e*sun_ang_bin + j2000_orb(f, g, counts)

x0 = np.array([26., 0.2, -1.3, -0.2, -0.004, -1., 1.5])
sigma = np.array((counts + 1)**(0.5))

fit_results = optimization.curve_fit(fit_function, bin_time_mid, counts, x0, sigma)
coeff = fit_results[0]

print 'CGB coefficient:',coeff[0]
print 'Geographical orbit coefficient & phase:',coeff[1],'&',coeff[2]
print 'Earth angle coefficient:',coeff[3]
print 'Sun angle coefficient:',coeff[4]
print 'J2000 orbit coefficient & phase:',coeff[5],'&',coeff[6]
#print np.where(total_counts == 0)
#print bin_time_mid[np.where(total_counts == 0)]
#print sat_time_bin[np.where(total_counts == 0)]
#print bin_time_mid[0]
#print sat_time_bin[0]

a = fit_results[0][0]
b = fit_results[0][1]
c = fit_results[0][2]
d = fit_results[0][3]
e = fit_results[0][4]
f = fit_results[0][5]
g = fit_results[0][6]

geo_orb = geo_orb(b, c, counts)
j2000_orb = j2000_orb(f, g, counts)

fit_curve = a*cgb + geo_orb + d*earth_ang_bin + e*sun_ang_bin + j2000_orb


#plot-algorhythm
plot_time_bin_date = calc.met_to_date(bin_time_mid)[0]
plot_time_bin = (plot_time_bin_date - calc.day_to_met(day)[1])*24#Time of day in hours
plot_time_sat_date = calc.met_to_date(sat_time_bin)[0]
plot_time_sat = (plot_time_sat_date - calc.day_to_met(day)[1])*24#Time of day in hours
#plot each on its own axis (source)
'''fig, ax1 = plt.subplots()

#add two independent y-axes
ax2 = ax1.twinx()
ax3 = ax1.twinx()
#ax4 = ax1.twinx()
axes = [ax1, ax2, ax3]#, ax4]

#Make some space on the right side for the extra y-axis
fig.subplots_adjust(right=0.75)

# Move the last y-axis spine over to the right by 20% of the width of the axes
axes[-1].spines['right'].set_position(('axes', 1.2))

# To make the border of the right-most axis visible, we need to turn the frame on. This hides the other plots, however, so we need to turn its fill off.
axes[-1].set_frame_on(True)
axes[-1].patch.set_visible(False)

plot1 = ax1.plot(plot_time_bin, counts, 'b-', label = 'Counts')
plot2 = ax1.plot(plot_time_bin, fit_curve, 'r-', label = 'Fit')
plot3 = ax2.plot(plot_time_sat, sun_ang_bin, 'y-', label = 'Sun angle')
plot4 = ax2.plot(plot_time_sat, earth_ang_bin, 'c-', label = 'Earth angle')
plot5 = ax3.plot(plot_time_sat, geo_orb, 'g--', label = 'Geographical orbit')
plot6 = ax3.plot(plot_time_sat, cgb, 'b--', label = 'Cosmic y-ray background')
plot7 = ax3.plot(plot_time_sat, j2000_orb, 'y--', label = 'J2000 orbit')

plots = plot1 + plot2 + plot3 + plot4 + plot5 + plot6 + plot7
labels = [l.get_label() for l in plots]
ax3.legend(plots, labels, loc=1)

ax1.grid()

ax1.set_xlabel('Time of day in 24h')
ax1.set_ylabel('Number of counts')
ax2.set_ylabel('Effective area (cm^2)')
ax3.set_ylabel('Number')
#ax4.set_ylabel('Distance')

#ax1.set_xlim([0, 24.1])
ax1.set_ylim([-50, 100])
#ax2.set_xlim([0, 24.1])
ax2.set_ylim([0, 300])
#ax3.set_xlim([0, 24.1])
ax3.set_ylim([-5.5, 1.5])
#ax4.set_xlim([0, 24.1])
#ax4.set_ylim([-1.5, 1.5])

plt.title(data_type + '-counts-fit of the ' + detector.__name__ + '-detector on the ' + ordinal(int(str(day)[4:6])) + ' ' + date.strftime('%B')[0:3] + ' ' + str(year))

plt.show()'''


#plot each on the same axis as converted to counts
fig, ax1 = plt.subplots()

plot1 = ax1.plot(plot_time_bin, counts, 'b-', label = 'Counts')
plot2 = ax1.plot(plot_time_bin, fit_curve, 'r-', label = 'Fit')
plot3 = ax1.plot(plot_time_sat, e*sun_ang_bin, 'y-', label = 'Sun angle')
plot4 = ax1.plot(plot_time_sat, d*earth_ang_bin, 'c-', label = 'Earth angle')
plot5 = ax1.plot(plot_time_sat, geo_orb, 'g--', label = 'Geographical orbit')
plot6 = ax1.plot(plot_time_sat, a*cgb, 'b--', label = 'Cosmic y-ray background')
plot7 = ax1.plot(plot_time_sat, j2000_orb, 'y--', label = 'J2000 orbit')

#plot vertical lines for the solar flares of the day
if np.all(flares_today != -5):
    if len(flares_today[0]) > 1:
        for i in range(0, len(flares_today[0])):
            plt.axvline(x = flares_today[0,i], ymin = 0., ymax = 1., linewidth=2, color = 'grey')
            plt.axvline(x = flares_today[1,i], ymin = 0., ymax = 1., color = 'grey', linestyle = '--')
    else:
        plt.axvline(x = flares_today[0], ymin = 0., ymax = 1., linewidth=2, color = 'grey')
        plt.axvline(x = flares_today[1], ymin = 0., ymax = 1., color = 'grey', linestyle = '--')

plots = plot1 + plot2 + plot3 + plot4 + plot5 + plot6 + plot7
labels = [l.get_label() for l in plots]
ax1.legend(plots, labels, loc=1)

ax1.grid()

ax1.set_xlabel('Time of day in 24h')
ax1.set_ylabel('Number of counts')

ax1.set_xlim([-0.5, 24.5])
ax1.set_ylim([-100, 200])

plt.title(data_type + '-counts-fit of the ' + detector.__name__ + '-detector on the ' + ordinal(int(str(day)[4:6])) + ' ' + date.strftime('%B')[0:3] + ' ' + str(year))

plt.show()



'''plt.plot(plot_time_bin, counts - fit_curve, 'b-')

plt.xlabel('Time of day in 24h')
plt.ylabel('Residual noise')

plt.grid()

plt.title(data_type + '-counts-fit residuals of the ' + detector.__name__ + '-detector on the ' + ordinal(int(str(day)[4:6])) + ' ' + date.strftime('%B')[0:3] + ' ' + str(year))

plt.ylim([-200, 200])

plt.show()'''

