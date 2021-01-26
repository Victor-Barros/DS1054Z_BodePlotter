# bode.py

import fygen
import numpy as np
import time
from ds1054z import DS1054Z
import argparse
import dft
import matplotlib.pyplot as plt
from mcursor import MultiCursor
from prefixed import Float
import scipy.signal


parser = argparse.ArgumentParser(description="This program plots Bode Diagrams of a DUT using an FY6900 and Rigol DS1054Z")

parser.add_argument('MIN_FREQ', metavar='min', type=float, help="The minimum frequency for which should be tested")
parser.add_argument('MAX_FREQ', metavar='max', type=float, help="The maximum frequency for which should be tested")
parser.add_argument('COUNT', metavar='N', nargs="?", default=50, type=int, help='The number of frequencies for which should be probed')
parser.add_argument("--awg_port", dest="AWG_PORT", default="/dev/ttyUSB0", help="The serial port where the AWG is connected to")
parser.add_argument("--ds_ip", default="auto", dest="OSC_IP", help="The IP address of the DS1054Z. Set to auto, to auto discover the oscilloscope via Zeroconf")
parser.add_argument("--awg_voltage", dest="VOLTAGE", default=5, type=float, help="The amplitude of the signal used for the generator")
parser.add_argument("--step_time", dest="TIMEOUT", default=0.00, type=float, help="The pause between to measurements in ms.")
parser.add_argument("--no_smoothing", dest="SMOOTH", action="store_false", help="Set this to disable the smoothing of the data with a Savitzky–Golay filter")
parser.add_argument("--use_manual_settings", dest="MANUAL_SETTINGS", action="store_true", help="When this option is set, the options on the oscilloscope for voltage and time base are not changed by this program.")
parser.add_argument("--output", dest="file", type=argparse.FileType("w"), help="Write the measured data to the given CSV file.")
parser.add_argument("--no_plots", dest="PLOTS", action="store_false", help="When this option is set no plots are shown. Useful in combination with --output")
parser.add_argument("--use_dft", dest="DFT", action="store_true", help="Use Discrete Fourier Transform on raw data; more accurate but slower.")

args = parser.parse_args()

if args.OSC_IP == "auto":
    import ds1054z.discovery
    results = ds1054z.discovery.discover_devices()
    if not results:
        print("No Devices found! Try specifying the IP Address manually.")
        exit()
    OSC_IP = results[0].ip
    print("Found Oscilloscope! Using IP Address " + OSC_IP)
else:
    OSC_IP = args.OSC_IP

DEFAULT_PORT = args.AWG_PORT
MIN_FREQ = args.MIN_FREQ
MAX_FREQ = args.MAX_FREQ
STEP_COUNT = args.COUNT

# Do some validity checs
if MIN_FREQ < 0 or MAX_FREQ < 0:
    exit("Frequencies has to be greater 0!")

if MIN_FREQ >= MAX_FREQ:
    exit("MAX_FREQ has to be greater then min frequency")

if STEP_COUNT <= 0:
    exit("The step count has to be positive")

TIMEOUT = args.TIMEOUT

AWG_CHANNEL = 0          # //channel 1
AWG_VOLT = args.VOLTAGE

print("Init AWG")

#  awg = jds6600(DEFAULT_PORT)
awg = fygen.FYGen(DEFAULT_PORT)


# AWG_MAX_FREQ = awg.getinfo_devicetype()
AWG_MODEL = awg.get_model()
AWG_MAX_FREQ = float(AWG_MODEL[7:9])

print("Maximum Generator Frequency: %d MHz"% AWG_MAX_FREQ)
if MAX_FREQ > AWG_MAX_FREQ * 1e6:
    exit("Your MAX_FREQ is higher than your AWG can achieve!")

# We use sine for sweep
# awg.setwaveform(AWG_CHANNEL, "sine")
awg.set(AWG_CHANNEL, enable=True, wave='sin')

# Init scope
scope = DS1054Z(OSC_IP)
#scope = DS1054Z('USB0::6833::1230::DS1ZA224411463::0::INSTR')


# Set some options for the oscilloscope

if not args.MANUAL_SETTINGS:
    # Center vertically
    scope.set_channel_offset(1, 0)
    scope.set_channel_offset(2, 0)
    
    # Display one period in 2 divs
    period = (1/MIN_FREQ) / 2
    scope.timebase_scale = period
    scope.run()

    # Set the sensitivity according to the selected voltage
    scope.set_channel_scale(1, args.VOLTAGE / 4, use_closest_match=True)
    # Be a bit more pessimistic for the default voltage, because we run into problems if it is too confident
    scope.set_channel_scale(2, args.VOLTAGE / 4, use_closest_match=True) 

freqs = np.logspace(np.log10(MIN_FREQ), np.log10(MAX_FREQ), num=STEP_COUNT)

# Set amplitude
awg.set(AWG_CHANNEL, volts=AWG_VOLT, enable=True)

volts = list()
phases = list()

# We have to wait a bit before we measure the first value
awg.set(AWG_CHANNEL, freq_hz=float(freqs[0]), enable=True)
time.sleep(0.05)
 
if not args.MANUAL_SETTINGS:# initialize voltage reading to see if scope is set in correct vertical scale, in case vout is bigger than vin
    scope.display_channel(1, enable=True)
    scope.display_channel(2, enable=True)
    volt = scope.get_channel_measurement(2, 'vpp')

    vscalelist = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
    scopevscale = scope.get_channel_scale(2)
    index = vscalelist.index(scopevscale)

    while volt is None: # increase voltage scale until vpp is read
        #print("vscale ",  vscalelist[index])
        scope.set_channel_scale(2, vscalelist[index] , use_closest_match=True)
        time.sleep(1)
        volt = scope.get_channel_measurement(2, 'vpp')
        print("vpp: ", volt)
        if index < 9:
            index = index + 3
        else:
            index = 12 

count=1

for freq in freqs:
    awg.set(AWG_CHANNEL, freq_hz=float(freq), enable=True)
    time.sleep(TIMEOUT)
    
    if args.DFT:
        volt0, volt, phase = dft.measure_with_dft(scope, freq)
        
    else:
        volt0 = scope.get_channel_measurement(1, 'vpp')
        volt = scope.get_channel_measurement(2, 'vpp')
        phase = scope.get_channel_measurement('CHAN1, CHAN2', 'rphase')

        if phase:
            phase = -1*phase
        else:
            phase = 0

        phases.append(phase)

        if volt0 < 0.01:
            print("Input voltage is very low, check your connections and retry")
            exit()

        volts.append(volt/volt0)
         
         
    # Use a better timebase
    if not args.MANUAL_SETTINGS:
        # Display one period in 2 divs
        period = (1/freq) / 2
        scope.timebase_scale = period

        # Use better voltage scale for next time
        if volt:
            scope.set_channel_scale(2, volt / 4, use_closest_match=True)
        else:
            scope.set_channel_scale(2, AWG_VOLT / 4, use_closest_match=True)

    print(count," - ","freq: ",'{:.2h}Hz'.format(Float(freq)), " volt0: ", '{:.3f}'.format(volt0), " volt: ", '{:.3f}'.format(volt), " phase: ", '{:.3f}'.format(phase))
    count+=1

# Write data to file if needed
if args.file:
    args.file.write("Frequency in Hz; Gain in dB; Phase in Degree\n")

    for n in range(0, len(freqs)):
        if volts[n]:
            volt = volts[n]
        else:
            volt = float("nan")
        
        if phases[n]:
            phase = phases[n]
        else:
            phase = phases[n]
        
        args.file.write("%f;%f;%f \n"%(freqs[n], 20*np.log10(volt), phase))
      
    args.file.close()

# Plot graphics

if not args.PLOTS:
    exit()

fig, axs = plt.subplots(2,sharex = True)
fig.suptitle('Bode Diagram')

volts = 20*np.log10(volts)

axs[0].plot(freqs, volts, label="Measured data")

if args.SMOOTH:
    try:
        y1hat = scipy.signal.savgol_filter(volts, 9, 3) # window size 51, polynomial order 3
        axs[0].plot(freqs, y1hat, "--", color="red", label="Smoothed data")
    except:
        print("Error during smoothing amplitude data")

axs[0].set_title("Gain(N=%d)"%STEP_COUNT)
axs[0].set_ylabel("Gain [dB]")
axs[0].legend()
axs[0].set_xscale("log")
axs[0].grid(True, which="both")

try:
    axs[1].plot(freqs, phases)
    axs[1].set_title("Phase (N=%d)"%STEP_COUNT)
    axs[1].set_ylabel("Phase [°]")
    axs[1].set_xlabel("Frequency [Hz]")
except:
    print("Phase was not correctly measured, check your connections")

if args.SMOOTH:
    try:
        y2hat = scipy.signal.savgol_filter(phases, 9, 3) # window size 51, polynomial order 3
        axs[1].plot(freqs, y2hat, "--", color="red", label="Smoothed data")
    except:
        print("Error during smoothing phase data")

axs[1].set_xscale("log")

axs[1].grid(True, which="both")

xvals = np.logspace(np.log10(min(freqs)),np.log10(max(freqs)),100*len(freqs))

if args.SMOOTH:
    y1interp = np.interp(np.log10(xvals),np.log10(freqs),y1hat)
    y2interp = np.interp(np.log10(xvals),np.log10(freqs),y2hat)
else:
    y1interp = np.interp(np.log10(xvals),np.log10(freqs),volts)
    y2interp = np.interp(np.log10(xvals),np.log10(freqs),phases)

def format_x(value):
    return '{:.2h}Hz'.format(Float(value))
def format_y1(value):
    return '{:.3f}dB'.format(value)
def format_y2(value):
    return '{:.3f}°'.format(value)
    
cursor = MultiCursor(fig.canvas,(axs[0],axs[1]), x_data=xvals,x_label='Freq',x_format_func=format_x,y_data=[y1interp,y2interp], y_labels=['Gain','Phase'],y_format_funcs=[format_y1,format_y2], color='r', lw=1, horizOn=True)

plt.show()
