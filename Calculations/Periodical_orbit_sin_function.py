#!/usr/bin python2.7

import os
import matplotlib.pyplot as plt
import numpy as np
import math
import pyfits
from numpy import linalg as LA
import ephem
from work_module import calculate
from work_module import detector
from work_module import readfile
calc = calculate()
det = detector()
rf = readfile()

#docstrings of the different self-made classes within the self-made module
#cdoc = calc.__doc__
#ddoc = det.__doc__
#rdoc = rf.__doc__

day = 150926

sat_data = rf.poshist(150926)
sat_time = sat_data[0]
sat_pos = sat_data[1]

#print np.where(np.fabs(sat_pos[0] - sat_pos[0,0]) < 3000)
#print np.where(np.fabs(sat_pos[1] - sat_pos[1,0]) < 2000)
#print np.where(np.fabs(sat_pos[2] - sat_pos[2,0]) < 2000)

#periodical function corresponding to the orbital behaviour -> reference day is 150926, periodical shift per day is approximately 0.199*math.pi
ysin = np.sin((2*math.pi*np.arange(len(sat_time)))/5715 + (0.7 + (day - 150926)*0.199)*math.pi)*20 + 300

daytime = (sat_time - sat_time[0] + 5)/3600.

plt.plot(daytime, ysin, 'g-')

plt.show()
