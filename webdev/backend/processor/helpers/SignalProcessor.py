from scipy.signal import butter, lfilter, find_peaks
import numpy as np


class SignalProcessor:
    # Implements signal processing pipeline

    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.nyquist = sample_rate / 2
        self.hp_b_heart, self.hp_a_heart = butter(3, 0.3 / self.nyquist, "highpass")
        self.bp_b_heart, self.bp_a_heart = butter(
            6, [0.8 / self.nyquist, 2.5 / self.nyquist], "band"
        )
        self.hp_b_breath, self.hp_a_breath = butter(3, 0.07 / self.nyquist, "highpass")
        self.bp_b_breath, self.bp_a_breath = butter(
            3, [0.07 / self.nyquist, 0.4 / self.nyquist], "band"
        )
        self.kernel_heart = np.ones(5) / 5
        self.kernel_breath = np.ones(3) / 3
        # self.window_size = max(3, int(0.5 * self.sample_rate))

    # 1
    def moving_target_indicator_heart(self, signal_data):
        # MTI filter to remove static clutter
        # Remove the DC component
        signal_data = signal_data - np.mean(signal_data)

        # 3rd order butterworth high-pass filter
        # sample rate = 15 Hz, nyquist = 7.5 Hz
        # 0.3 / 7.5 = 0.4
        return lfilter(self.hp_b_heart, self.hp_a_heart, signal_data)

    def moving_target_indicator_breath(self, data):
        data = data - np.mean(data)
        return lfilter(self.hp_b_breath, self.hp_a_breath, data)

    # 2
    def sliding_average_filter_heart(self, signal_data, window_size=5):
        # Sliding average filter to remove impulse noise
        if len(signal_data) < window_size:
            return signal_data

        # kernel = np.ones(window_size) / window_size
        return np.convolve(signal_data, self.kernel_heart, mode="same")

    def sliding_average_filter_breath(self, data, window=3):
        if len(data) < window:
            return data
        # kernel = np.ones(window) / window
        return np.convolve(data, self.kernel_breath, mode="same")

    # 3
    def bandpass_filter_heart(self, signal_data):
        # Bandpass filter for heartbeat frequency range (48-150 bpm)
        if len(signal_data) < 20:
            return signal_data

        return lfilter(self.bp_b_heart, self.bp_a_heart, signal_data)

    def bandpass_filter_breath(self, data):
        if len(data) < 20:
            return data
        return lfilter(self.bp_b_breath, self.bp_a_breath, data)

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

        """
        # Remove DC and normalize
        # signal_data = signal_data - np.mean(signal_data)
        std = np.std(signal_data)
        if std > 0:
            signal_data /= std
        
        nperseg = max(128, len(signal_data)//4)
        nfft = max(512, len(signal_data)*2)
        window = windows.hann(nperseg)
        noverlap = int(0.5 * nperseg)

        # Apply Welch PSD estimation
        freqs, pxx = welch(
            signal_data,
            fs=self.sample_rate,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            nfft=nfft
        )
        
        # Focus on heart rate band (0.8–2.5 Hz)
        mask = (freqs >= 0.8) & (freqs <= 2.5)
        freqs_band = freqs[mask]
        pxx_band = pxx[mask]
        
        if len(freqs_band) == 0:
            return 0, 0
        
        # Find dominant frequency
        peak_idx = np.argmax(pxx_band)
        dominant_freq = freqs_band[peak_idx]
        bpm = dominant_freq * 60
        
        # Confidence metric (power ratio)
        mean_power = np.mean(pxx_band)
        peak_power = pxx_band[peak_idx]
        confidence = (peak_power / (mean_power + 1e-10))
        
        # Apply simple threshold to reject weak signals
        if confidence < 2.0:
            bpm = 0
        
        return bpm
        """

    def estimate_breathing_rate_fft(self, data):
        if len(data) < 60:
            return 0

        peaks, _ = find_peaks(data, height=1.5)
        if len(peaks) == 0:
            return 0

        time_window = len(data) / self.sample_rate
        bpm = (len(peaks) / time_window) * 60
        return bpm

    def process_signal_pipeline(self, raw_signal):
        # Complete processing pipeline
        # Step 1: Remove static interference
        mti_filtered_heart = self.moving_target_indicator_heart(raw_signal)
        mti_filtered_breath = self.moving_target_indicator_breath(raw_signal)

        # Step 2: Sliding average filter
        filtered_heart = mti_filtered_heart
        filtered_breath = mti_filtered_breath
        # for _ in range(4):
        filtered_heart = self.sliding_average_filter_heart(
            filtered_heart, window_size=5
        )
        filtered_breath = self.sliding_average_filter_breath(filtered_breath, window=3)

        # Step 3: Bandpass filtering
        bp_filtered_heart = self.bandpass_filter_heart(filtered_heart)
        bp_filtered_breath = self.bandpass_filter_breath(filtered_breath)

        # Step 4: Estimate heart rate
        bpm = self.estimate_heart_rate_fft(bp_filtered_heart)
        breath = self.estimate_breathing_rate_fft(bp_filtered_breath)

        return {
            "mti_filtered_heart": mti_filtered_heart,
            "smoothed_heart": filtered_heart,
            "bp_filtered_heart": bp_filtered_heart,
            "bp_filtered_breath": bp_filtered_breath,
            "heart_rate_bpm": bpm,
            "breathing_rate": breath,
        }
