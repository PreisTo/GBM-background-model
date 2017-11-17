#!/usr/bin python2.7

import math

import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize as optimization
from numpy import linalg as LA

from gbmbkgpy.utils.external_prop import ExternalProps, writefile
from gbmbkgpy.work_module_refactor import calculate
from gbmbkgpy.work_module_refactor import detector

calc = calculate()
det = detector()
rf = ExternalProps()
wf = writefile()

#docstrings of the different self-made classes within the self-made module
#cdoc = calc.__doc__
#ddoc = det.__doc__
#rdoc = rf.__doc__



day = 150926
detector = det.n5

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


sat_data = rf.poshist_bin(day, bin_time_mid)
sat_time_bin = sat_data[0]
sat_pos_bin = sat_data[1]
sat_lat_bin = sat_data[2]
sat_lon_bin = sat_data[3]
sat_q_bin = sat_data[4]

sun_data = calc.sun_ang_bin(detector, day, bin_time_mid)
sun_ang_bin = sun_data[0]
sun_ang_bin = calc.ang_eff(sun_ang_bin, detector)

earth_data = calc.earth_ang_bin(detector, day, bin_time_mid)
earth_ang_bin = earth_data[0]
earth_ang_bin = calc.ang_eff(earth_ang_bin, detector)


#periodical function corresponding to the orbital behaviour -> reference day is 150926, periodical shift per day is approximately 0.199*math.pi
sat_time = rf.poshist(day)[0]

#J2000-position oriented orbit
distance = (LA.norm(sat_pos_bin, axis=0) - 6371000.785)/1000
#ysin0 = np.sin((2*math.pi*np.arange(len(sat_time)))/5715 + (0.7 + (day - 150926)*0.199)*math.pi)
#ysin = calc.intpol(ysin0, day, 0, sat_time, bin_time_mid, detector)[0]

#LON-oriented orbit (earth rotation considered -> orbit within the magnetic field of the earth)
ysin0 = np.sin((2*math.pi*np.arange(len(sat_time)))/6120.85)
ysin = calc.intpol(ysin0, day, 0, sat_time, bin_time_mid, detector)[0]


#constant function corresponding to the diffuse y-ray background
ycon = np.ones(len(sat_time_bin))


bin_time_mid_norm = bin_time_mid - bin_time_mid[0]

ycon[np.where(echan_counts[0] == 0)] = 0
ysin[np.where(echan_counts[0] == 0)] = 0
distance[np.where(echan_counts[0] == 0)] = 0
earth_ang_bin[np.where(echan_counts[0] == 0)] = 0
sun_ang_bin[np.where(echan_counts[0] == 0)] = 0


def fit_function(x, a, b, c, d, e, f, g):
    return a*ycon + b*(calc.intpol(np.sin((2*math.pi*np.arange(len(sat_time)))/6120.85 + c), day, 0, sat_time, bin_time_mid, detector)[0]) - d*earth_ang_bin - e*sun_ang_bin + f*np.sin(distance + g)# + f*x

x0 = np.array([25., 10., -0.3, 0.01, 0.05, 4., 0.5])
sigma = np.array((echan_counts[0] + 1)**(0.5))

fit_results = optimization.curve_fit(fit_function, bin_time_mid_norm, echan_counts[0], x0, sigma)

print fit_results[0]
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

fit_curve = a*ycon + b*(calc.intpol(np.sin((2*math.pi*np.arange(len(sat_time)))/6120.85 + c), day, 0, sat_time, bin_time_mid, detector)[0]) - d*earth_ang_bin - e*sun_ang_bin + f*np.sin(distance + g)# + f*bin_time_mid_norm

orbit = f*np.sin(distance + g)


#plot-algorhythm
fig, ax1 = plt.subplots()

#add two independent y-axes
ax2 = ax1.twinx()
ax3 = ax1.twinx()
ax4 = ax1.twinx()
axes = [ax1, ax2, ax3, ax4]

#Make some space on the right side for the extra y-axis
fig.subplots_adjust(right=0.75)

# Move the last y-axis spine over to the right by 20% of the width of the axes
axes[-1].spines['right'].set_position(('axes', 1.2))

# To make the border of the right-most axis visible, we need to turn the frame on. This hides the other plots, however, so we need to turn its fill off.
axes[-1].set_frame_on(True)
axes[-1].patch.set_visible(False)

plot1 = ax1.plot(bin_time_mid, echan_counts[0], 'b-', label = 'Counts')
plot2 = ax1.plot(bin_time_mid, fit_curve, 'r-', label = 'Fit')
plot3 = ax2.plot(sat_time_bin, sun_ang_bin, 'y-', label = 'Sun angle')
plot4 = ax2.plot(sat_time_bin, earth_ang_bin, 'c-', label = 'Earth angle')
plot5 = ax3.plot(sat_time_bin, ysin, 'g--', label = 'Orbital period')
plot6 = ax3.plot(sat_time_bin, ycon, 'b--', label = 'Constant background')
plot7 = ax4.plot(sat_time_bin, orbit, 'y--', label = 'Distance')

plots = plot1 + plot2 + plot3 + plot4 + plot5 + plot6 + plot7
labels = [l.get_label() for l in plots]
ax4.legend(plots, labels, loc=1)

ax1.grid()

ax1.set_xlabel('Time of day in 24h')
ax1.set_ylabel('Number of counts')
ax2.set_ylabel('Effective area (cm^2)')
ax3.set_ylabel('Number')
ax4.set_ylabel('Distance')

#ax1.set_xlim([0, 24.1])
ax1.set_ylim([-50, 100])
#ax2.set_xlim([0, 24.1])
ax2.set_ylim([0, 360])
#ax3.set_xlim([0, 24.1])
ax3.set_ylim([-1.5, 1.5])
#ax4.set_xlim([0, 24.1])
#ax4.set_ylim([-1.5, 1.5])

plt.title('Counts and angles of the ' + detector.__name__ + '-detector on the 26th Sept 2015')

#plt.axis([0, 24.1, 0, 500])

#plt.legend()

plt.show()

'''
plt.plot(bin_time_mid, echan_counts[0] - fit_curve, 'b-')

plt.xlabel('time')
plt.ylabel('background-subtracted noise')

plt.title('Count-diagramme after background subtraction')

plt.ylim([-200, 200])

plt.show()
'''
