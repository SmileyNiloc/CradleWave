import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter, find_peaks
from pathlib import Path

# ==============================
# CONFIG
# ==============================
FRAME_RATE = 15     # frames per second
TIME = 90           # Length of record
NUM_CHIRPS = 32     # Number of chirps
NUM_SAMPLES = 64    # Number of samples
NUM_FRAMES = 1348   # Number of frames ~ TIME * FRAME_RATE - 1 (for long streams we subtract >1 )

INPUT_CSV_FILE = "raw_data_8.csv"
#raw_data_8     - target 70-80bpm, last 20 seconds out of frame
#raw_data_9     - target 60-70bpm
#raw_data_10    - target 100bpm, decrease over time

# ==============================
# SignalProcessor
# ==============================
class SignalProcessor:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate  # 15 frames per second
        nyq = sample_rate / 2           # Nyquist rate

        # Heart Filters
        # MTI Highpass Filter
        self.hp_b_heart, self.hp_a_heart = butter(3, 0.3 / nyq, "highpass")
        # Bandpass Filter: 48-150bpm range
        self.bp_b_heart, self.bp_a_heart = butter(6, [0.8 / nyq, 2.5 / nyq], "band")

        # Breathing filters
        # MTI Highpass filter
        self.hp_b_breath, self.hp_a_breath = butter(3, 0.07 / nyq, "highpass")
        # Bandpass Filter: 4-24bpm range
        self.bp_b_breath, self.bp_a_breath = butter(3, [0.07 / nyq, 0.4 / nyq], "band")

        # Smoothing Window Kernels
        self.kernel_heart = np.ones(3) / 3      # Window Size = 3
        self.kernel_breath = np.ones(10) / 10   # Window Size = 10

    def process_signal_pipeline(self, raw_signal):
        # MTI (highpass)
        heart = lfilter(self.hp_b_heart, self.hp_a_heart, raw_signal - np.mean(raw_signal))
        breath = lfilter(self.hp_b_breath, self.hp_a_breath, raw_signal - np.mean(raw_signal))

        # Bandpass Filters
        heart = lfilter(self.bp_b_heart, self.bp_a_heart, heart)
        breath = lfilter(self.bp_b_breath, self.bp_a_breath, breath)
        
        # Window Smoothing
        heart = np.convolve(heart, self.kernel_heart, mode="same")
        breath = np.convolve(breath, self.kernel_breath, mode="same")

        return heart, breath

# ==============================
# Doppler processing
# ==============================

# Input Raw Data Frame -> Output Doppler Map
def doppler_map(frame):
    # 2D Fast Fourier Transform
    rd = np.fft.fft2(frame)
    # Shift FFT to order negative -> positive frquencies, zero frequency centered
    rd = np.fft.fftshift(rd, axes=0)
    # Convert to dB
    return 20 * np.log10(np.abs(rd) + 1e-10)

# Input Doppler Raw Data Frame -> Output Scalar (Integration)
def frame_to_scalar(frame):
    # Compute Doppler Map of Raw Data Frame
    rd_map = doppler_map(frame)
    # Flatten 2D Doppler Map to 1D
    frame1D = rd_map.flatten()

    # Should always be true (len = 2048), but prevents error
    if len(frame1D) >= 15:
        # Integration:
        # Select 7 higest energy samples from frame
        integratedFrame = np.partition(frame1D, -7)[-7:]
        # Average 7 highest energy samples to 1 scalar
        scalar = np.mean(integratedFrame)
    else:
        # Extract highest sample
        scalar = np.max(integratedFrame)

    return -scalar  # Invert sign - doppler values record negative


# ==============================
# LOAD DATA
# ==============================
script_dir = Path(__file__).resolve().parent
# .CSV File Read
raw = pd.read_csv(script_dir / INPUT_CSV_FILE, header=None).values

# Reshape each frame to 3D: Frames x Chirps x Samples
frames = raw.reshape(NUM_FRAMES, NUM_CHIRPS, NUM_SAMPLES)


# ==============================
# MAIN SIGNAL PROCESSING
# ==============================

# Instantiate signal processor with frame rate
processor = SignalProcessor(FRAME_RATE)

# Create arrays for recording
buffer = []
heart_log = []
breath_log = []
time_log = []

# MAIN PROCESSING LOOP
for i, frame in enumerate(frames):
    # Convert raw data frame to integrated scalar value
    scalar = frame_to_scalar(frame)
    # Add scalar to buffer
    buffer.append(scalar)

    # Rolling buffer length (10 seconds)
    if len(buffer) > FRAME_RATE * 10:
        buffer.pop(0)

    # For heart rate and breathing rate:
    # Perform Signal Processing (MTI -> Bandpass -> Smoothing)
    heart, breath = processor.process_signal_pipeline(np.array(buffer))

    # Log heart rate, breathing rate, and time
    heart_log.append(heart[-1])
    breath_log.append(breath[-1])
    time_log.append(i / FRAME_RATE)


# ===============================================
# PEAKS DETECTION ALGORITHM (HEART AND BREATHING)
# ===============================================
def breathing_peak_detect(breath_filtered, fs_breath, window_sec=20):
    """
    Divide breath_filtered into 20 second windows and count peaks in each.
    
    breath_filtered: 1D filtered breathing signal
    fs_breath:       sample rate of breath signal (default 15 same as FRAME_RATE)
    window_sec:      window size in seconds (default 20)
    
    returns: list of (time_sec, breaths_per_min) tuples
    """
    # Calculate total number of samples per window
    samples_per_window = int(window_sec * fs_breath)  # Default 300 samples at 15 Hz
    # Total number of windows in recorded sample 
    # >>>Sometimes total samples is slightly less than TIME * FRAME_RATE, check exact dimmensions for creating windows<<<
    num_windows = (len(breath_filtered)+1) // samples_per_window
    results = []
    prev_val = 0
    # Peaks Detection Per Window
    for i in range(num_windows):
        # Extract Window
        current_window = breath_filtered[i * samples_per_window : (i + 1) * samples_per_window]
        # Peaks Detection
        # distance: minimum distance between peaks 2 * fs_breath = 2 * frames/second = 2 seconds
        # This corresponds to max 30 breaths/min
        # prominence = 0.15 = minimum amplitude for peak detection = 0.15
        peaks, _ = find_peaks(current_window, distance=int(2 * fs_breath), prominence = 0.15)
        # Mumber of peaks
        num_breaths = len(peaks)
        # Inter-window smoothing (weighted avg previous value with current value for new window)
        # First run (no smoothing)
        if prev_val == 0:
            breaths_per_min = (num_breaths / window_sec) * 60
            prev_val = breaths_per_min
        # Subsequent runs (2/3 * current_value + 1/3 * previous_value = new)
        else:
            breaths_per_min = (((num_breaths / window_sec) * 60)*2 + prev_val) / 3
            prev_val = breaths_per_min

        # Timestamp = center of window
        center_time = (i * samples_per_window + samples_per_window / 2) / fs_breath
        # Log results
        results.append((int(center_time), int(breaths_per_min)))
    return results

def heart_peak_detect(heart_filtered, fs_heart, window_sec=20):
    """
    Divide heart_filtered into 20 second windows and count peaks in each.
    
    heart_filtered:  1D filtered breathing signal
    fs_breath:       sample rate of breath signal (default 15 same as FRAME_RATE)
    window_sec:      window size in seconds (default 20)
    
    returns: list of (time_sec, bpm) tuples
    """
    # Extract Window
    samples_per_window = int(window_sec * fs_heart) # Default 300 samples at 15 Hz
    # Total number of windows in recorded sample 
    # >>>Sometimes total samples is slightly less than TIME * FRAME_RATE, check exact dimmensions for creating windows<<<
    num_windows = (len(heart_filtered)+1) // samples_per_window

    results = []
    prev_val = 0
    for i in range(num_windows):
        chunk = heart_filtered[i * samples_per_window : (i + 1) * samples_per_window]

        # Minimum distance between peaks = 0.4s = 1 sample at 2.5 Hz
        # This corresponds to max 150 bpm
        peaks, _ = find_peaks(chunk, distance=int(0.2 * fs_heart), prominence = 0.15)

        num_beats = int(len(peaks))
        
        # Inter-window smoothing (avg prev value with current for new window)
        # First run (no smoothing)
        if prev_val == 0:
            bpm = (num_beats / window_sec) * 60
            prev_val = bpm
        # Subsequent runs (2/3 * current_value + 1/3 * previous_value = new)
        else:
            bpm = (((num_beats / window_sec) * 60)*2 + prev_val) / 3
            prev_val = bpm

        # Timestamp = center of window
        center_time = (i * samples_per_window + samples_per_window / 2) / fs_heart
        # Log results
        results.append((int(center_time), int(bpm)))
    return results

# set breathing and heart frame rates to FRAME_RATE (could be used to downsample/integrate along slow time)
fs_breath = FRAME_RATE
fs_heart = FRAME_RATE
breathing_results = breathing_peak_detect(breath_log, fs_breath, window_sec=20)
heart_results = heart_peak_detect(heart_log, fs_heart, window_sec=20)
print("Breathing Results: (center time (s), bpm)")
print(breathing_results)
print("Heart Rate Results: (center time (s), bpm)")
print(heart_results)

# ==============================
# SAVE CSV
# ==============================
out = np.column_stack((time_log, heart_log, breath_log))
np.savetxt(
    "replayed_filtered_signals.csv",
    out,
    delimiter=",",
    header="time_sec,heart_filtered,breath_filtered",
    comments="",
)

# ==============================
# PLOT
# ==============================
time_arr = np.array(time_log)
heart_arr = np.array(heart_log)
breath_arr = np.array(breath_log)

# How many seconds to plot?
mask = time_arr <= 90

plt.figure(figsize=(12,6))
plt.plot(time_arr[mask], heart_arr[mask], label="Filtered Heart Signal")
plt.plot(time_arr[mask], breath_arr[mask], label="Filtered Breathing Signal")

plt.xlabel("Time (s)")
plt.ylabel("Amplitude")
plt.title("Filtered Vitals Signals 90 Seconds")
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.show()