# ===========================================================================
# Enhanced FMCW Radar Signal Monitoring (Simplified)
# Displays only filtered signal without heart rate estimation
# ===========================================================================

import argparse
import matplotlib.pyplot as plt
import numpy as np
import time
from scipy.signal import butter, filtfilt, find_peaks, welch, windows, lfilter
from scipy import signal

from ifxradarsdk import get_version_full
from ifxradarsdk.fmcw import DeviceFmcw
from ifxradarsdk.fmcw.types import FmcwSimpleSequenceConfig, FmcwMetrics
from helpers.DopplerAlgo import *


#Definitions for websocket client
from helpers.websockets import WebSocketClient
import asyncio

# WebSocket URL (use wss:// for secure WebSocket, not https://)
WEBSOCKET_URL = "wss://cradlewave-351958736605.us-central1.run.app/ws/heart_rate"

# -------------------------------------------------
# Signal Processing Methods
# -------------------------------------------------

class SignalProcessor:
    """Implements signal processing pipeline"""
    
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.nyquist = sample_rate / 2
        self.hp_b, self.hp_a = butter(3, 0.3 / self.nyquist, 'highpass')
        self.bp_b, self.bp_a = butter(6, [0.8 / self.nyquist, 2.5 / self.nyquist], 'band')
        # self.window_size = max(3, int(0.5 * self.sample_rate))
        
    # 1
    def moving_target_indicator(self, signal_data):
        """MTI filter to remove static clutter"""
        # Remove the DC component
        signal_data = signal_data - np.mean(signal_data)
        
        # 3rd order butterworth high-pass filter
        # sample rate = 15 Hz, nyquist = 7.5 Hz
        # 0.3 / 7.5 = 0.4
        return lfilter(self.hp_b, self.hp_a, signal_data)
    
    # 2
    def sliding_average_filter(self, signal_data, window_size = 5):
        """Sliding average filter to remove impulse noise"""
        if len(signal_data) < window_size:
            return signal_data
        
        kernel = np.ones(window_size) / window_size
        filtered = np.convolve(signal_data, kernel, mode='same')
        return filtered
    
    # 3
    def bandpass_filter(self, signal_data, lowcut=0.8, highcut=2.5):
        """Bandpass filter for heartbeat frequency range (48-150 bpm)"""
        if len(signal_data) < 20:
            return signal_data
            
        return lfilter(self.bp_b, self.bp_a, signal_data)
    
    # 
    def estimate_heart_rate_fft(self, signal_data):

        # f, pxx = welch(signal_data, fs=self.sample_rate, nperseg=len(signal_data)//2)

        """Estimate heart rate using FFT peak search"""
        if len(signal_data) < 60:
            return 0
            
        """
        # Detrend and normalize
        signal_data = signal_data - np.mean(signal_data)
        if np.std(signal_data) > 0:
            signal_data = signal_data / np.std(signal_data)
        
        # Apply window to reduce spectral leakage
        window = signal.windows.hann(len(signal_data))
        windowed_signal = signal_data * window
        
        # Compute FFT with zero padding for better frequency resolution
        # n_fft = max(512, len(windowed_signal) * 4)
        # fft_vals = np.fft.rfft(windowed_signal, n=n_fft)
        # freqs = np.fft.rfftfreq(n_fft, 1/self.sample_rate)
        freqs = welch(signal_data, fs=self.sample_rate, nperseg=len(signal_data)//2)
        
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
        signal_data = signal_data - np.mean(signal_data)
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
    
    def process_signal_pipeline(self, raw_signal):
        """Complete processing pipeline"""
        # Step 1: Remove static interference
        mti_filtered = self.moving_target_indicator(raw_signal)
        
        # Step 2: Sliding average filter
        filtered = mti_filtered
        # for _ in range(4):
        filtered = self.sliding_average_filter(filtered, window_size = 3)
        
        # Step 3: Bandpass filtering
        bp_filtered = self.bandpass_filter(filtered)
        
        # Step 4: Estimate heart rate
        bpm = self.estimate_heart_rate_fft(bp_filtered)
        
        return {
            'mti_filtered': mti_filtered,
            'smoothed': filtered,
            'bp_filtered': bp_filtered,
            'heart_rate_bpm': bpm
        }


# -------------------------------------------------
# Real-time Plot (Simplified)
# -------------------------------------------------
class RealTimePlot:
    def __init__(self, frate, window_duration=10.0):
        self._frate = frate
        self._window_duration = window_duration
        self._max_points = int(window_duration * frate)
        
        self._filtered_values = []
        self._absolute_frame_count = 0
        
        plt.ion()
        self._fig, self._ax = plt.subplots(1, 1, figsize=(12, 6))
        self._fig.canvas.manager.set_window_title("Filtered Signal Monitoring")
        
        # Filtered signal plot
        self._filtered_line, = self._ax.plot([], [], 'b-', linewidth=2, 
                                              label='Filtered Signal')
        self._ax.set_xlabel('Time (seconds)')
        self._ax.set_ylabel('Signal Strength (dB)')
        self._ax.set_title('Filtered Signal')
        self._ax.grid(True, alpha=0.3)
        self._ax.legend()
        
        plt.tight_layout()
        
        self._fig.canvas.mpl_connect('close_event', self.close)
        self._is_window_open = True
        
    def add_data(self, filtered_value):
        """Add new data point and update plot"""
        self._filtered_values.append(filtered_value)
        self._absolute_frame_count += 1
        
        # Keep only recent data
        if len(self._filtered_values) > self._max_points:
            self._filtered_values.pop(0)
        
        # Update time axis
        current_time = self._absolute_frame_count / self._frate
        start_time = max(0, current_time - self._window_duration)
        
        time_axis = np.linspace(start_time, current_time, len(self._filtered_values))
        
        # Update filtered signal plot
        self._filtered_line.set_data(time_axis, self._filtered_values)
        self._ax.set_xlim(start_time, current_time)
        
        if len(self._filtered_values) > 0:
            y_min = min(self._filtered_values)
            y_max = max(self._filtered_values)
            y_margin = (y_max - y_min) * 0.1
            self._ax.set_ylim(y_min - y_margin, y_max + y_margin)
        
        self._fig.canvas.draw_idle()
        self._fig.canvas.flush_events()
    
    def close(self, event=None):
        if self._is_window_open:
            self._is_window_open = False
            plt.close(self._fig)
            print('Plot window closed!')
    
    def is_open(self):
        return self._is_window_open


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def parse_program_arguments(description, def_nframes, def_frate):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-n', '--nframes', type=int, default=def_nframes,
                        help="number of frames, default " + str(def_nframes))
    parser.add_argument('-f', '--frate', type=int, default=def_frate,
                        help="frame rate in Hz, default " + str(def_frate))
    parser.add_argument('-c', '--collect', type=float, default=10.0,
                        help="initial data collection time in seconds, default 10.0")
    return parser.parse_args()


def linear_to_dB(x):
    return 20 * np.log10(abs(x) + 1e-10) # avoids log(0)


# -------------------------------------------------
# Main logic
# -------------------------------------------------
async def main():
    client = WebSocketClient(WEBSOCKET_URL)
    # asyncio.create_task(client.connect())
    await client.connect()
    await asyncio.sleep(0.1)  # Let the event loop start async tasks

    args = parse_program_arguments(
        '''FMCW Radar Signal Monitoring (Filtered Only)''',
        def_nframes=150,
        def_frate=15)

    with DeviceFmcw() as device:
        print(f"Radar SDK Version: {get_version_full()}")
        print("Sensor: " + str(device.get_sensor_type()))

        num_rx_antennas = 1

        metrics = FmcwMetrics(
            range_resolution_m=0.05,
            max_range_m=1.0,
            max_speed_m_s=0.75,
            speed_resolution_m_s=0.05,
            center_frequency_Hz=60_750_000_000,
        )

        # Create and configure sequence
        sequence = device.create_simple_sequence(FmcwSimpleSequenceConfig())
        sequence.loop.repetition_time_s = 1 / args.frate
        chirp_loop = sequence.loop.sub_sequence.contents
        device.sequence_from_metrics(metrics, chirp_loop)

        chirp = chirp_loop.loop.sub_sequence.contents.chirp
        chirp.sample_rate_Hz = 1_000_000
        chirp.rx_mask = 1
        chirp.tx_mask = 1
        chirp.tx_power_level = 31
        chirp.if_gain_dB = 20
        chirp.lp_cutoff_Hz = 500000
        chirp.hp_cutoff_Hz = 80000

        device.set_acquisition_sequence(sequence)

        # Initialize signal processor and doppler algorithm
        processor = SignalProcessor(sample_rate=args.frate)
        doppler = DopplerAlgo(chirp.num_samples, chirp_loop.loop.num_repetitions, 
                             num_rx_antennas)
        
        collect_frames = int(args.collect * args.frate)
        rt_plot = RealTimePlot(args.frate)
        
        print(f"\n{'='*60}")
        print(f"Phase 1: Collecting initial data for {args.collect} seconds")
        print(f"         ({collect_frames} frames)")
        print(f"{'='*60}\n")
        
        raw_signal_buffer = []
        
        # Phase 1: Collect initial data
        for frame_number in range(collect_frames):
            if frame_number % 30 == 0:
                print(f"Collection: {frame_number}/{collect_frames} frames "
                      f"({frame_number/args.frate:.1f}s)")
            
            frame_contents = device.get_next_frame()
            frame_data = frame_contents[0]
            # print(f"frame contents {frame_data} \n")
            
            all_frame_dB_values = []
            for i_ant in range(num_rx_antennas):
                mat = frame_data[i_ant, :, :]
                dfft_dbfs = linear_to_dB(doppler.compute_doppler_map(mat, i_ant))
                all_frame_dB_values.extend(dfft_dbfs.flatten())
            
            if len(all_frame_dB_values) >= 10:
                top_10_values = np.partition(all_frame_dB_values, -10)[-10:]
                frame_peak_dB = np.mean(top_10_values)
            else:
                frame_peak_dB = np.max(all_frame_dB_values)
            
            raw_signal_buffer.append(frame_peak_dB * (-1))
        
        print(f"\n{'='*60}")
        print("Phase 2: Real-time signal monitoring")
        print("Close the plot window to stop.")
        print(f"{'='*60}\n")

        # Process initial buffer
        initial_result = processor.process_signal_pipeline(
            np.array(raw_signal_buffer))
        
        # Initialize plot with processed data
        for filt in initial_result['smoothed']: # smoothed
            rt_plot.add_data(filt)
            #test websocket by sending initial data (not 100% realistic, but will test queueing)
            # for key, item in initial_result.items():
        
        # await client.send_data(initial_result)


        frame_counter = collect_frames
        dropped_frames = 0
        last_time = time.time()
        last_hr_time = time.time()
        hr_interval = 10.0  # Print heart rate every 10 seconds
        

        #clear queue before starting real-time loop
        await client.wait_until_done()


        while rt_plot.is_open():
            try:
                frame_start = time.time()
                frame_contents = device.get_next_frame()
                frame_data = frame_contents[0]
                
                all_frame_dB_values = []
                for i_ant in range(num_rx_antennas):
                    mat = frame_data[i_ant, :, :]
                    dfft_dbfs = linear_to_dB(doppler.compute_doppler_map(mat, i_ant))
                    all_frame_dB_values.extend(dfft_dbfs.flatten())
                
                if len(all_frame_dB_values) >= 10:
                    top_10_values = np.partition(all_frame_dB_values, -10)[-10:]
                    frame_peak_dB = np.mean(top_10_values)
                else:
                    frame_peak_dB = np.max(all_frame_dB_values)
                
                raw_signal_buffer.append(frame_peak_dB * (-1))
                if len(raw_signal_buffer) > rt_plot._max_points:
                    raw_signal_buffer.pop(0)
                
                # Process signal
                result = processor.process_signal_pipeline(
                    np.array(raw_signal_buffer))
                rt_plot.add_data(result['smoothed'][-1]) # smoothed
                # print(f"Debug: Frame {frame_counter}, Filtered Value: {result['mti_filtered'][-1]:.3f}")
                # Send the frame_countner and the result(and array with a couple different values) to backedn via websocket

                frame_counter += 1
                
                # Heart rate estimation every 10 seconds
                if time.time() - last_hr_time >= hr_interval:
                    hr_bpm = result['heart_rate_bpm']
                    print(f"\n{'='*60}")
                    print(f"*** Heart Rate Estimate: {hr_bpm:.1f} BPM ***")
                    print(f"{'='*60}\n")
                    last_hr_time = time.time()
                    await client.send_data({"time":last_hr_time,
                                            "heart_rate":hr_bpm})                  
                # Timing management
                frame_time = time.time() - frame_start
                expected_time = 1.0 / args.frate
                if frame_time < expected_time:
                    await asyncio.sleep(expected_time - frame_time)
                
                # Status update
                if frame_counter % 30 == 0:
                    elapsed = time.time() - last_time
                    actual_fps = 30 / elapsed if elapsed > 0 else 0
                    
                    signal_std = np.std(result['bp_filtered'])
                    signal_range = np.max(result['bp_filtered']) - np.min(result['bp_filtered'])
                    
                    print(f"Frames: {frame_counter} ({frame_counter/args.frate:.1f}s) | "
                          f"FPS: {actual_fps:.1f} | Dropped: {dropped_frames} | "
                          f"Signal Quality: STD={signal_std:.3f}, Range={signal_range:.3f}")
                    last_time = time.time()
                
            except KeyboardInterrupt:
                print("\nStopped by user.")
                break
            except Exception as e:
                error_msg = str(e)
                if "FRAME_ACQUISITION_FAILED" in error_msg or "frame was dropped" in error_msg:
                    dropped_frames += 1
                    if dropped_frames % 10 == 1:
                        print(f"Warning: Frame dropped (total: {dropped_frames})")
                    await asyncio.sleep(0.01)
                    continue
                else:
                    print(f"Error: {e}")
                    import traceback
                    traceback.print_exc()
                    break

        rt_plot.close()
        print(f"\n{'='*60}")
        print(f"Application finished")
        print(f"Total frames: {frame_counter}, Dropped: {dropped_frames}")
        print(f"{'='*60}")
        await client.wait_until_done()

if __name__ == '__main__':
    asyncio.run(main())
