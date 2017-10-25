#!/usr/bin python2.7

import os
import matplotlib.pyplot as plt
import numpy as np

#Read the data file
__dir__ = os.path.dirname(os.path.abspath(__file__))
filepath = os.path.join(__dir__, 'glg_trigdat_all_bn150627183_v01_ascii.dat')
f2 = open(filepath)
#store the file contents in a list of every row
lines = f2.readlines()[23:]
f2.close()

#here you see what the functions do
#print type(lines)
#print len(lines)
#print(lines[2])
#print(type(lines[2]))
#print(lines[2].split())
#print(float(lines[2].split()[0]))

#just some variables going to be arrays of our data
x1 = []
y1 = []

#scan each line in the list, split the string into two and add them to the arrays
for line in lines:
    p = line.split()
    x1.append(float(p[0]))
    y1.append(float(p[2]))

#check the number of x entries
#print len(x1)

#make numpy arrays for more flexibility
xv = np.array(x1)
yv = np.array(y1)


#plot the data and set the styles
#r-- is a red ------ line (just one - would be a regular line)
#bs are blue squares
#g^ are green triangles
#yo are yellow circles
plt.plot(xv,yv, 'r-')

#labeling the axes
plt.ylabel('counts/s')
plt.xlabel('time in s')

#plot-title
plt.title('GRB 150627.183')

#the range of the axes: [xmin, xmax, ymin, ymax]
#plt.axis([-10, 100, 100, 600])

#anzeigen lassen
plt.show()
