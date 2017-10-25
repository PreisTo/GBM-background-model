#!/usr/bin python2.7

import os
import matplotlib.pyplot as plt
import numpy as np
import math

def cps( SED, E1, E2, A = 5 ):
    "This function converts an input SED in the corresponding countrate dN/dt within the given energy interval E2 - E1. Insert the parameters in the following order: SED, E1, E2, A (= 5 set as default)"
    dNdt = SED*4*math.fabs(E2 - E1)*A/(E2 + E1)**2
    return dNdt

flux = float(raw_input("What was the observed SED? "))
E1 = float(raw_input("Set your energy interval.\nE1 "))
E2 = float(raw_input("E2 "))
dNdt = cps( flux, E1, E2 )
print 'The resulting countrate is %.2f counts/s.' % dNdt
