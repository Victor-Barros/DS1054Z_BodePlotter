
# This module implements DFT-based measurement of sine wave amplitude and phase.
# By averaging over all the samples, it is more precise than just using
# the scope's built-in Vpp and phase measurements.

import time
import numpy
import math
import cmath

def measure_with_dft(scope, frequency):
    scope.single()
    waittime = 0
    while scope.running:
        time.sleep(0.01)
        waittime += 1
        if waittime % 10 == 0: scope.tforce()
    
    ch1 = scope.get_waveform_samples(1, 'NORM')
    ch2 = scope.get_waveform_samples(2, 'NORM')
    samplerate = 1.0 / scope.waveform_preamble_dict['xinc']
    
    # Trim the data to full number of periods
    samples_per_period = samplerate / frequency
    periods = int(len(ch1) / samples_per_period)
    samples = round(periods * samples_per_period)
    ch1 = ch1[:int(samples)]
    ch2 = ch2[:int(samples)]
    
    if periods <= 0:
        return 0, 0, 0
    
    # Perform DFT at a single frequency
    exp = numpy.exp(math.tau * 1j * numpy.linspace(0, periods, samples, endpoint = False))
    dft1 = numpy.sum(numpy.multiply(exp, ch1)) / samples
    dft2 = numpy.sum(numpy.multiply(exp, ch2)) / samples
    
    amplitude1 = 4 * abs(dft1) # Convert to Vpp reading
    amplitude2 = 4 * abs(dft2)
    phase = cmath.phase(dft1) - cmath.phase(dft2)
    deg_phase = (numpy.degrees(phase) + 180.0) % 360.0 - 180.0
    
    return amplitude1, amplitude2, deg_phase

if __name__ == '__main__':
    # Test this module with "python dft.py 192.168.100.10 10000"
    import ds1054z
    import sys
    scope = ds1054z.DS1054Z(sys.argv[1])
    freq = float(sys.argv[2])
    print(measure_with_dft(scope, freq))