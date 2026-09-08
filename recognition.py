"""Local ASR with one cached model and timestamped output."""
import os
import threading

_LOCK = threading.Lock()
_MODEL = None
_KEY = None
MODELS = {'tiny', 'base', 'small', 'medium', 'large-v3'}


def transcribe(path, model_size='small', language=None, hotwords='', on_segment=None, on_status=None, cancelled=None):
    global _MODEL, _KEY
    if model_size not in MODELS:
        raise ValueError('不支持的语音模型')
    notify = on_status or (lambda value: None)
    check = cancelled or (lambda: None)
    notify('等待语音引擎')
    while not _LOCK.acquire(timeout=0.25):
        check()
    try:
        check()
        device = os.environ.get('VIDEO_WHISPER_DEVICE', 'cpu')
        compute = os.environ.get('VIDEO_WHISPER_COMPUTE', 'int8' if device == 'cpu' else 'float16')
        key = (model_size, device, compute)
        if key != _KEY:
            notify('加载语音模型（首次使用可能需要下载）')
            from faster_whisper import WhisperModel
            _MODEL = None
            _KEY = None
            _MODEL = WhisperModel(model_size, device=device, compute_type=compute, cpu_threads=min(8, os.cpu_count() or 4))
            _KEY = key
        check()
        notify('识别语音')
        segments, info = _MODEL.transcribe(
            path, beam_size=5, temperature=0.0,
            language=language, hotwords=hotwords or None, vad_filter=True,
            initial_prompt=('以下可能出现的专有名词：' + hotwords) if hotwords else None,
            word_timestamps=True,
            vad_parameters={'min_silence_duration_ms': 500}, condition_on_previous_text=False,
        )
        result = []
        for seg in segments:
            check()
            item = {'start': round(float(seg.start), 3), 'end': round(float(seg.end), 3), 'text': seg.text.strip()}
            reasons = []
            words = getattr(seg, 'words', None) or []
            low_words = [w.word.strip() for w in words if w.probability < .45 and w.word.strip()]
            if getattr(seg, 'avg_logprob', 0) < -.8:
                reasons.append('整段识别把握较低')
            if low_words:
                reasons.append('部分词语把握较低：' + '、'.join(low_words[:8]))
            if getattr(seg, 'compression_ratio', 0) > 2.4:
                reasons.append('可能存在重复内容')
            if getattr(seg, 'no_speech_prob', 0) > .55:
                reasons.append('可能受静音或背景声影响')
            item.update(needs_review=bool(reasons), review_reasons=reasons,
                        avg_logprob=round(float(getattr(seg, 'avg_logprob', 0)), 3),
                        words=[{'start':round(w.start,3), 'end':round(w.end,3), 'text':w.word,
                                'probability':round(w.probability,3)} for w in words])
            if item['text']:
                result.append(item)
            if on_segment:
                on_segment(item, float(info.duration), result)
        return {'transcript': '\n'.join(s['text'] for s in result), 'segments': result,
                'duration': float(info.duration), 'language': info.language, 'model': model_size,
                'review_count': sum(s['needs_review'] for s in result),
                'language_probability': getattr(info, 'language_probability', None),
                'recognition_version': '2.1'}
    finally:
        _LOCK.release()
