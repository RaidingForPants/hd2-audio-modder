import numpy
import os
import pyaudio
import subprocess
import wave

from const_global import CACHE, VGMSTREAM
from log import logger

class SoundHandler:
    
    def __init__(self):
        self.audio_process = None
        self.wave_object = None
        self.audio_id = -1
        self.audio = pyaudio.PyAudio()
        
    def kill_sound(self):
        if self.audio_process is not None:
            if self.callback is not None:
                self.callback()
                self.callback = None
            self.audio_process.close()
            self.wave_file.close()
            try:
                os.remove(self.audio_file)
            except:
                pass
            self.audio_process = None
        
    def play_audio(self, sound_id, sound_data, callback=None):
        if not os.path.exists(VGMSTREAM):
            return
        self.kill_sound()
        self.callback = callback
        if self.audio_id == sound_id:
            self.audio_id = -1
            return
        filename = f"temp{sound_id}"
        if not os.path.isfile(f"{filename}.wav"):
            with open(f'{os.path.join(CACHE, filename)}.wem', 'wb') as f:
                f.write(sound_data)
            process = subprocess.run([VGMSTREAM, "-o", f"{os.path.join(CACHE, filename)}.wav", f"{os.path.join(CACHE, filename)}.wem"], stdout=subprocess.DEVNULL)
            os.remove(f"{os.path.join(CACHE, filename)}.wem")
            if process.returncode != 0:
                logger.error(f"Encountered error when converting {sound_id}.wem for playback")
                self.callback = None
                return
            
        self.audio_id = sound_id
        self.wave_file = wave.open(f"{os.path.join(CACHE, filename)}.wav")
        self.audio_file = f"{os.path.join(CACHE, filename)}.wav"
        self.frame_count = 0
        self.max_frames = self.wave_file.getnframes()
        
        def read_stream(input_data, frame_count, time_info, status):
            self.frame_count += frame_count
            if self.frame_count > self.max_frames:
                if self.callback is not None:
                    self.callback()
                    self.callback = None
                self.audio_id = -1
                self.wave_file.close()
                try:
                    os.remove(self.audio_file)
                except:
                    pass
                return (None, pyaudio.paComplete)
            data = self.wave_file.readframes(frame_count)
            if self.wave_file.getnchannels() > 2:
                data = self.downmix_to_stereo(data, self.wave_file.getnchannels(), self.wave_file.getsampwidth(), frame_count)
            return (data, pyaudio.paContinue)

        self.audio_process = self.audio.open(format=self.audio.get_format_from_width(self.wave_file.getsampwidth()),
                channels = min(self.wave_file.getnchannels(), 2),
                rate=self.wave_file.getframerate(),
                output=True,
                stream_callback=read_stream)
        self.audio_file = f"{os.path.join(CACHE, filename)}.wav"
        
    def downmix_to_stereo(self, data, channels, channel_width, frame_count):
        arr = numpy.frombuffer(data, dtype=numpy.int16)
        stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int16)
        if channel_width == 2:
            arr = numpy.frombuffer(data, dtype=numpy.int16)
            stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int16)
        elif channel_width == 1:
            arr = numpy.frombuffer(data, dtype=numpy.int8)
            stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int8)
        elif channel_width == 4:
            arr = numpy.frombuffer(data, dtype=numpy.int32)
            stereo_array = numpy.zeros(shape=(frame_count, 2), dtype=numpy.int32)
        arr = arr.reshape((frame_count, channels))

        if channels == 4:
            for index, frame in enumerate(arr):
                stereo_array[index][0] = int(0.42265 * frame[0] + 0.366025 * frame[2] + 0.211325 * frame[3])
                stereo_array[index][1] = int(0.42265 * frame[1] + 0.366025 * frame[3] + 0.211325 * frame[2])
        
            return stereo_array.tobytes()
                
        if channels == 6:
            for index, frame in enumerate(arr):
                stereo_array[index][0] = int(0.374107*frame[1] + 0.529067*frame[0] + 0.458186*frame[3] + 0.264534*frame[4] + 0.374107*frame[5])
                stereo_array[index][1] = int(0.374107*frame[1] + 0.529067*frame[2] + 0.458186*frame[4] + 0.264534*frame[3] + 0.374107*frame[5])
        
            return stereo_array.tobytes()
        
        #if not 4 or 6 channel, default to taking the L and R channels rather than mixing
        for index, frame in enumerate(arr):
            stereo_array[index][0] = frame[0]
            stereo_array[index][1] = frame[1]
        
        return stereo_array.tobytes()


