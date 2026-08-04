# robot/ai_chat/src/bomi_ai_chat/audio_io/wakeword.py
"""웨이크워드('보미야') 감지 — 로봇을 '깨우는' 상시 청취기.

어디에 위치하는가
    대화 루프(pipeline.run)의 맨 앞이다. 로봇은 평소에 이 감지기로 마이크를 상시
    듣기만 하다가, "보미야"를 들으면 그때 비로소 대화 한 턴(빔 고정 → STT → LLM →
    TTS)을 시작한다. 즉 이 파일은 '언제 대화를 시작할지'만 정하고, '무엇을 말할지'는
    전혀 관여하지 않는다.

왜 존재하는가
    상시 STT/LLM 을 돌리면 비용·지연·오작동이 크다. 값싼 로컬 웨이크워드 모델로 먼저
    걸러서, 진짜 부를 때만 무거운 파이프라인을 깨운다. 웨이크워드 대기 중에는 빔을
    고정하지 않는다(사방 어디서 불러도 들어야 하므로). 빔 고정은 감지 후 대화 턴에서만
    한다(pipeline.run_once).

무엇을 쓰는가
    openWakeWord(로컬 .onnx 모델) + onnxruntime. 학습은 training 폴더에서 따로 했고,
    여기서는 결과물 .onnx 만 로드해 추론한다.

캡처 규칙 — 학습 데이터와 동일하게
    학습 클립은 ReSpeaker 왼쪽 채널(처리된 빔)을 네이티브 SR 로 녹음 후 16k 로 리샘플한
    것이다. 여기서도 같은 경로(장치 이름 해석 → 왼쪽 채널 → 16k 리샘플)로 들어야 모델이
    학습 분포와 같은 소리를 받는다. 그래서 sounddevice_backend 의 헬퍼를 재사용한다.

참고
    CLAUDE.md §13(barge-in/echo), §16(로컬 판정은 로컬에서), training/detect_mic.py(원형)
"""

from __future__ import annotations

import logging
import queue

import numpy as np
import sounddevice as sd

from .sounddevice_backend import _resample_int16, _resolve_input_device

LOGGER = logging.getLogger(__name__)


class WakeWordDetector:
    """마이크를 상시 듣다가 '보미야'가 들리면 wait_for_wake()가 반환한다.

    무엇을 하는가
        openWakeWord 모델(.onnx)을 로드하고, 마이크 스트림을 열어 80ms(1280 샘플)
        단위로 점수를 매긴다. '최근 window 프레임 중 min_hits 개 이상'이 임계값을
        넘으면 감지로 보고 반환한다.

    왜 '연속'이 아니라 '창 안 개수'인가
        진짜 발화는 점수가 튀엄튀엄 높게 뜨고(예: 0.7→0.4→0.9), 스치는 오탐은 한
        프레임만 튄다. '연속 N프레임'은 진짜 발화를 자주 놓쳐서, 창 방식이 recall 을
        지키면서 단발 오탐을 걸러낸다(training/detect_mic.py 에서 검증한 규칙).

    무거운 로드는 지연한다
        openWakeWord import 와 모델 로드는 느리다. __init__ 에서 하지 않고
        warm_up()/첫 사용 시 한 번만 한다. main 에서 대기 루프 시작 전에 warm_up()
        을 호출해 첫 감지가 지연되지 않게 한다.
    """

    def __init__(
        self,
        *,
        model_path: str,
        device: int | str | None,
        channels: int,
        target_sample_rate: int,
        threshold: float,
        window: int,
        min_hits: int,
        frame_samples: int,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.channels = channels
        self.target_sample_rate = target_sample_rate
        self.threshold = threshold
        self.window = window
        self.min_hits = min_hits
        self.frame_samples = frame_samples
        # 지연 로드되는 openWakeWord 모델 인스턴스. None 이면 아직 안 올렸다는 뜻.
        self._model = None

    def warm_up(self) -> None:
        """모델을 미리 로드한다(첫 감지 지연 방지).

        누가 호출하는가
            main.py 가 대기 루프에 들어가기 전에 한 번. 이렇게 안 하면 첫 "보미야"를
            부르는 순간 모델이 로드되며 감지가 크게 늦어진다(라우터 warm-up 과 같은 이유).
        """
        self._ensure_model()

    def _ensure_model(self):
        """openWakeWord 모델을 아직 안 올렸으면 한 번 올린다.

        openWakeWord 는 웨이크워드 모델(.onnx) 외에 공통 전처리 모델(멜스펙/임베딩)을
        따로 받아야 한다. download_models() 가 없으면 1회 내려받고 있으면 건너뛴다.
        """
        if self._model is not None:
            return self._model

        # 무거운 import 는 이 시점까지 미룬다(테스트/노트북 개발에서 불필요한 로드 방지).
        import openwakeword
        from openwakeword.model import Model

        # 공용 전처리 모델(melspectrogram/embedding/VAD)만 없으면 받는다. 이 셋은 우리
        # 모델이 돌아가는 데 반드시 필요하다. 인자 없이 download_models() 를 부르면
        # alexa/jarvis 같은 '샘플 웨이크워드'까지 전부 받으므로, 매칭되지 않는 이름을
        # 넘겨 그 샘플 다운로드는 건너뛴다(전처리/VAD 는 함수가 항상 확인해 받는다).
        openwakeword.utils.download_models(model_names=["__bomi_features_only__"])
        self._model = Model(wakeword_models=[self.model_path])
        LOGGER.info("wakeword model loaded path=%s", self.model_path)
        return self._model

    def wait_for_wake(self) -> None:
        """'보미야'가 들릴 때까지 마이크를 상시 듣다가, 감지되면 반환한다.

        무엇을 하는가
            장치를 네이티브 SR 로 열고(콜백 캡처), 왼쪽 채널만 16k 로 리샘플해 이어붙인
            뒤 1280 샘플씩 모델에 넣는다. '최근 window 프레임 중 min_hits 개 이상' 이
            임계값을 넘으면 스트림을 닫고 반환한다.

        왜 콜백/네이티브SR/왼쪽채널인가
            일부 장치(ReSpeaker+DirectSound)는 blocking read 로 열면 무음만 나오고,
            16k 로 직접 열면 무음이 되기도 한다. 그래서 네이티브 SR + 콜백으로 받고
            마지막에 16k 로 변환한다. 왼쪽 채널이 하드웨어 처리된(빔포밍) 신호다.
            (sounddevice_backend.capture 와 동일한 이유.)

        누가 호출하는가
            pipeline.run() 루프가 run_once() 직전에. 감지 후 이 함수가 스트림을 닫고
            반환하므로, 곧이어 capture() 가 같은 마이크를 열어도 충돌하지 않는다.

        무엇을 호출하는가
            _ensure_model(), sounddevice InputStream, 그리고 모델의 predict().

        반환값
            None. '감지됐다'는 사실만 알린다(무엇을 말할지는 파이프라인의 몫).

        주의사항
            - Ctrl+C 로 빠져나올 수 있게 queue.get 에 timeout 을 둔다(윈도우에서 timeout
              없는 blocking get 은 인터럽트를 못 받는다).
            - 감지 순간 반환하며 스트림을 닫는다. 대기와 capture 는 '순차로'만 마이크를
              연다(동시에 열지 않는다).
        """
        model = self._ensure_model()

        # 내부 오디오 특징 버퍼를 비운다. 직전 "보미야" 감지의 특징이 남아 있으면, 대화가
        # 끝나고 다시 여기로 왔을 때 그 잔상 때문에 아무도 안 불렀는데 곧바로 재감지된다
        # (종료 직후 대화가 저절로 다시 켜지는 원인). reset() 은 예측 버퍼와 전처리
        # (melspec/embedding) 버퍼를 모두 비운다.
        model.reset()

        device = _resolve_input_device(self.device)
        try:
            native_sr = int(sd.query_devices(device)["default_samplerate"])
        except Exception:
            native_sr = self.target_sample_rate
        if native_sr <= 0:
            native_sr = self.target_sample_rate

        chunk_queue: queue.Queue = queue.Queue()

        def _callback(indata, _frames, _time_info, status):
            if status:
                LOGGER.debug("wakeword audio status=%s", status)
            chunk_queue.put(indata.copy())

        # 최근 window 프레임의 '임계값 초과 여부'를 담는다. 리스트 슬라이싱으로 창을 유지.
        hits: list[bool] = []
        # 16k 로 리샘플한 샘플을 이어 담았다가 1280 샘플씩 떼어 모델에 넣는 버퍼.
        buffer = np.empty(0, dtype=np.int16)

        print("[웨이크워드] '보미야'라고 부르면 시작합니다...")
        with sd.InputStream(
            samplerate=native_sr,
            channels=self.channels,
            dtype="int16",
            device=device,
            blocksize=int(0.1 * native_sr),
            callback=_callback,
        ):
            while True:
                try:
                    chunk = chunk_queue.get(timeout=1.0)
                except queue.Empty:
                    continue  # Ctrl+C 를 받을 수 있도록 잠깐씩 루프를 돈다

                # 왼쪽 채널(처리된 빔)만 모노로 → 16k 로 리샘플 → 버퍼에 이어붙이기
                mono = chunk[:, 0] if chunk.ndim > 1 else chunk
                mono = _resample_int16(mono, native_sr, self.target_sample_rate)
                buffer = np.concatenate([buffer, mono])

                # 1280 샘플(80ms) 프레임을 꺼낼 수 있는 만큼 처리
                while len(buffer) >= self.frame_samples:
                    frame = buffer[: self.frame_samples]
                    buffer = buffer[self.frame_samples :]

                    scores = model.predict(frame)
                    score = max(scores.values())

                    hits.append(score >= self.threshold)
                    if len(hits) > self.window:
                        hits = hits[-self.window :]

                    if sum(hits) >= self.min_hits:
                        LOGGER.info(
                            "wakeword detected score=%.2f hits=%d/%d",
                            score, sum(hits), len(hits),
                        )
                        print(f"[웨이크워드] 감지! (점수 {score:.2f})")
                        return
