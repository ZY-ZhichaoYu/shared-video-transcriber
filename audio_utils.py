"""Keep a compact, seekable voice track without requiring external ffmpeg."""
from pathlib import Path
import av
import time


def prepare_audio(source, target, check=lambda: None, on_progress=None):
    target = Path(target)
    temporary = target.with_suffix('.partial.flac')
    with av.open(str(source)) as incoming:
        duration=float(incoming.duration or 0)/av.time_base
        last_report=0
        if not incoming.streams.audio:
            return None
        with av.open(str(temporary), 'w') as outgoing:
            output = outgoing.add_stream('flac', rate=16000)
            output.layout = 'mono'
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for decoded in incoming.decode(audio=0):
                check()
                now=time.monotonic()
                if on_progress and duration and now-last_report>.5:
                    on_progress(min(.999,float(decoded.time or 0)/duration))
                    last_report=now
                for frame in resampler.resample(decoded):
                    frame.pts = None
                    for packet in output.encode(frame):
                        outgoing.mux(packet)
            for frame in resampler.resample(None):
                frame.pts = None
                for packet in output.encode(frame):
                    outgoing.mux(packet)
            for packet in output.encode(None):
                outgoing.mux(packet)
    check()
    temporary.replace(target)
    return str(target)
