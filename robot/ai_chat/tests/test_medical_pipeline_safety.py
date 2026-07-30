"""불확실한 의료 상세 정보가 파이프라인의 TTS 입력에 도달하지 않는지 검증한다."""

import importlib
import sys
from types import ModuleType

from bomi_ai_chat.llm import medical_flow


class StubAudioInput:
    def capture(self):
        return b"wav"


class StubAudioOutput:
    def __init__(self):
        self.played = []

    def play(self, audio):
        self.played.append(audio)


class StubSTT:
    def transcribe(self, audio):
        return "서울대병원 어디야"


class RecordingTTS:
    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return b"spoken-wav"


def function_call(name, args):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": name,
                                "args": args,
                            }
                        }
                    ]
                }
            }
        ]
    }


def test_partial_facility_details_never_reach_tts(
    monkeypatch,
    settings_factory,
):
    fake_router = ModuleType("bomi_ai_chat.llm.router")
    fake_router.is_medical_query = lambda text: True
    monkeypatch.setitem(
        sys.modules,
        "bomi_ai_chat.llm.router",
        fake_router,
    )

    import bomi_ai_chat.pipeline as pipeline_module

    pipeline_module = importlib.reload(pipeline_module)
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "find_medical_facility",
            {"facility_type": "병원", "facility_name": "서울대병원"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_hospitals",
        lambda **kwargs: [
            {
                "yadm_nm": "서울대효병원",
                "addr": "TTS로 전달되면 안 되는 주소",
                "cl_cd_nm": "병원",
            }
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "handle_medical_query",
        medical_flow.handle_medical_query,
    )

    audio_output = StubAudioOutput()
    pipeline = pipeline_module.ConversationPipeline(
        StubAudioInput(),
        audio_output,
        settings_factory(),
    )
    pipeline.stt = StubSTT()
    pipeline.tts = RecordingTTS()

    pipeline.run_once()

    assert len(pipeline.tts.texts) == 1
    assert "서울대효병원을 찾으신 건가요?" in pipeline.tts.texts[0]
    assert "TTS로 전달되면 안 되는 주소" not in pipeline.tts.texts[0]
    assert audio_output.played == [b"spoken-wav"]
