from scipy.signal import butter, lfilter, find_peaks
from scipy import signal
import numpy as np


class SignalProcessor:
    # Implements signal processing pipeline

    def __init__(self, sample_rate):
        self.sample_rate = sample_rate  # 15 frames per second default
        self.nyquist = sample_rate / 2  # Nyquist frequency

        # Heart Filters
        # MTI Highpass Filter
        self.hp_b_heart, self.hp_a_heart = butter(3, 0.3 / self.nyquist, "highpass")
        # Bandpass Filter: 48-150bpm range
        self.bp_b_heart, self.bp_a_heart = butter(
            6, [0.8 / self.nyquist, 2.5 / self.nyquist], "band"
        )

        # Breathing filters
        # MTI Highpass filter
        self.hp_b_breath, self.hp_a_breath = butter(3, 0.07 / self.nyquist, "highpass")
        # Bandpass Filter: 4-24bpm range
        self.bp_b_breath, self.bp_a_breath = butter(
            3, [0.07 / self.nyquist, 0.4 / self.nyquist], "band"
        )

        # Smoothing Window Kernels
        self.kernel_heart = np.ones(3) / 3  # Window Size = 3
        self.kernel_breath = np.ones(10) / 10  # Window Size = 10

    # 1
    def moving_target_indicator_heart(self, signal_data):
        # MTI filter to remove static clutter
        # 3rd order butterworth high-pass filter
        return lfilter(
            self.hp_b_heart, self.hp_a_heart, signal_data - np.mean(signal_data)
        )

    def moving_target_indicator_breath(self, signal_data):
        # MTI filter to remove static clutter
        # 3rd order butterworth high-pass filter
        return lfilter(
            self.hp_b_breath, self.hp_a_breath, signal_data - np.mean(signal_data)
        )

    # 2
    def bandpass_filter_heart(self, signal_data):
        # Bandpass filter for heartbeat frequency range (48-150 bpm)
        if len(signal_data) < 20:
            return signal_data

        return lfilter(self.bp_b_heart, self.bp_a_heart, signal_data)

    def bandpass_filter_breath(self, signal_data):
        if len(signal_data) < 20:
            return signal_data
        return lfilter(self.bp_b_breath, self.bp_a_breath, signal_data)

    # 3
    def sliding_average_filter_heart(self, signal_data, window_size=3):
        # Sliding average filter to remove impulse noise
        if len(signal_data) < window_size:
            return signal_data

        # kernel = np.ones(window_size) / window_size
        return np.convolve(signal_data, self.kernel_heart, mode="same")

    def sliding_average_filter_breath(self, signal_data, window_size=10):
        # Sliding average filter to remove impulse noise
        if len(signal_data) < window_size:
            return signal_data
        # kernel = np.ones(window_size) / window_size
        return np.convolve(signal_data, self.kernel_breath, mode="same")

    # 4
    def estimate_heart_rate_fft(self, signal_data):

        # Estimate heart rate using FFT peak search
        if len(signal_data) < 60:
            return 0

        # Detrend and normalize
        signal_data = signal_data - np.mean(signal_data)
        if np.std(signal_data) > 0:
            signal_data = signal_data / np.std(signal_data)

        # Apply window to reduce spectral leakage
        window = signal.windows.hann(len(signal_data))
        windowed_signal = signal_data * window

        # Compute FFT with zero padding for better frequency resolution
        n_fft = max(512, len(windowed_signal) * 4)
        fft_vals = np.fft.rfft(windowed_signal, n=n_fft)
        freqs = np.fft.rfftfreq(n_fft, 1 / self.sample_rate)
        # freqs = welch(signal_data, fs=self.sample_rate, nperseg=len(signal_data)//2)

        # Focus on heartbeat frequency range (0.8-2.5 Hz = 48-150 bpm)
        valid_idx = (freqs >= 0.8) & (freqs <= 2.5)
        valid_freqs = freqs[valid_idx]
        valid_fft = np.abs(fft_vals[valid_idx])

        # Find dominant frequency
        if len(valid_fft) > 0 and np.max(valid_fft) > 0:
            peak_idx = np.argmax(valid_fft)
            dominant_freq = valid_freqs[peak_idx]
            bpm = dominant_freq * 60

        # Confidence check: ensure the peak is significant
        mean_power = np.mean(valid_fft)
        peak_power = valid_fft[peak_idx]

        if peak_power < 2 * mean_power:
            return 0

        return bpm

    def heart_peak_detect(self, signal_data, frame_rate, window, prev_val):
        """
        Divide heart_filtered into 20 second windows and count peaks in each.

        heart_filtered:  1D filtered breathing signal
        fs_breath:       sample rate of breath signal (default 15 same as FRAME_RATE)
        window_sec:      window size in seconds (default 20)

        returns: list of (time_sec, bpm) tuples
        """
        # Extract Window
        samples_per_window = int(window * frame_rate)  # Default 300 samples at 15 Hz
        # Total number of windows in recorded sample
        # >>>Sometimes total samples is slightly less than TIME * FRAME_RATE, check exact dimmensions for creating windows<<<
        num_windows = 1
        results = []
        for i in range(num_windows):
            chunk = signal_data[i * samples_per_window : (i + 1) * samples_per_window]

            # Minimum distance between peaks = 0.4s = 1 sample at 2.5 Hz
            # This corresponds to max 150 bpm
            peaks, _ = find_peaks(
                chunk, distance=int(0.2 * frame_rate), prominence=0.15
            )

            num_beats = int(len(peaks))

            # Inter-window smoothing (avg prev value with current for new window)
            # First run (no smoothing)
            if prev_val == 0:
                bpm = (num_beats / window) * 60
                prev_val = bpm
            # Subsequent runs (2/3 * current_value + 1/3 * previous_value = new)
            else:
                bpm = (((num_beats / window) * 60) * 2 + prev_val) / 3
                prev_val = bpm

            # Timestamp = center of window
            center_time = (i * samples_per_window + samples_per_window / 2) / frame_rate
            # Log results
            results.append((int(center_time), int(bpm)))
        return results

    def breathing_peak_detect(self, signal_data, frame_rate, window, prev_val):
        """
        Divide breath_filtered into 20 second windows and count peaks in each.

        breath_filtered: 1D filtered breathing signal
        fs_breath:       sample rate of breath signal (default 15 same as FRAME_RATE)
        window_sec:      window size in seconds (default 20)

        returns: list of (time_sec, breaths_per_min) tuples
        """
        # Calculate total number of samples per window
        samples_per_window = int(window * frame_rate)  # Default 300 samples at 15 Hz
        # Total number of windows in recorded sample
        # >>>Sometimes total samples is slightly less than TIME * FRAME_RATE, check exact dimmensions for creating windows<<<
        num_windows = 1
        results = []
        # Peaks Detection Per Window
        for i in range(num_windows):
            # Extract Window
            current_window = signal_data[
                i * samples_per_window : (i + 1) * samples_per_window
            ]
            # Peaks Detection
            # distance: minimum distance between peaks 2 * fs_breath = 2 * frames/second = 2 seconds
            # This corresponds to max 30 breaths/min
            # prominence = 0.15 = minimum amplitude for peak detection = 0.15
            peaks, _ = find_peaks(
                current_window, distance=int(2 * frame_rate), prominence=0.15
            )
            # Mumber of peaks
            num_breaths = len(peaks)
            # Inter-window smoothing (weighted avg previous value with current value for new window)
            # First run (no smoothing)
            if prev_val == 0:
                breaths_per_min = (num_breaths / window) * 60
                prev_val = breaths_per_min
            # Subsequent runs (2/3 * current_value + 1/3 * previous_value = new)
            else:
                breaths_per_min = (((num_breaths / window) * 60) * 2 + prev_val) / 3
                prev_val = breaths_per_min

            # Timestamp = center of window
            center_time = (i * samples_per_window + samples_per_window / 2) / frame_rate
            # Log results
            results.append((int(center_time), int(breaths_per_min)))
        return results

    # NEED ATTENTION: Currently bpm and breath return list of (time_sec, bpm) tuples. This requires a window to be defined to partition the signal into chunks.
    # Each chunk is processed with the final bpm coming from a weighted sum of the current chunk and previous chunk bpm for smoothing.
    # This should be changed so the previous value is passed into the original process-signal-pipeline function (starting at 0), and the bpm and breath values are simply a bpm output.
    # Need to determine where this is called.

    def process_signal_pipeline(self, raw_signal, prev_heart_val, prev_breath_val):
        # Complete processing pipeline
        # Step 1: Remove static interference
        mti_filtered_heart = self.moving_target_indicator_heart(raw_signal)
        mti_filtered_breath = self.moving_target_indicator_breath(raw_signal)

        # Step 2: Bandpass filtering
        bp_filtered_heart = self.bandpass_filter_heart(mti_filtered_heart)
        bp_filtered_breath = self.bandpass_filter_breath(mti_filtered_breath)

        # Step 3: Sliding average filter
        filtered_heart = self.sliding_average_filter_heart(
            bp_filtered_heart, window_size=5
        )
        filtered_breath = self.sliding_average_filter_breath(
            bp_filtered_breath, window=3
        )

        # Step 4: Estimate heart rate -ATTENTION: BASED ON 20 SAMPLE PARTITION WITHIN SIGNAL_DATA, SEE ABOVE COMMENT
        bpm = self.heart_peak_detect(
            filtered_heart, self.sample_rate, window=20, prev_val=prev_heart_val
        )
        breath = self.breathing_peak_detect(
            filtered_breath, self.sample_rate, window=20, prev_val=prev_breath_val
        )

        return {
            # "mti_filtered_heart": mti_filtered_heart,
            # "bp_filtered_heart": bp_filtered_heart,
            "filtered_heart": filtered_heart,
            "filtered_breath": filtered_breath,
            "heart_rate_bpm": bpm,
            "breathing_rate": breath,
        }
