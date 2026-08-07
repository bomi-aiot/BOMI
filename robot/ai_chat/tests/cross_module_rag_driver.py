"""Spring Boot와 실제 HTTP로 대화/RAG 계약을 잇는 교차 모듈 E2E 드라이버.

이 파일은 단독 pytest가 아니다. 백엔드의
``CrossModuleRagEndToEndIntegrationTest``가 별도 Python 프로세스로 실행한다.
외부 생성·TTS API는 결정적 대역으로 고정하되, 문맥 조회·대화 적재·사실 후보 제출은
실제 ``Backend*Client``를 사용한다. 따라서 JSON 직렬화와 HTTP 경계를 건너는 계약까지
검증하면서도 과금은 발생하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from bomi_ai_chat.backend_client import (
    BackendContextClient,
    BackendConversationClient,
    BackendFactClient,
)
from bomi_ai_chat.config import Settings, clear_settings_cache
from bomi_ai_chat.graph import build, handlers, output
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph.build import build_graph
from bomi_ai_chat.graph.turn import run_user_turn
from bomi_ai_chat.jobs.ticks import extraction_flush
from bomi_ai_chat.localstore import db


class RecordingResponseLlm:
    """실제 프롬프트를 보존하고 네트워크 없이 짧은 한국어 응답을 만든다."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, weather_data=None) -> str:
        self.prompts.append(prompt)
        return "확인한 내용을 바탕으로 함께 이야기해 볼게요."


class DeterministicExtractionLlm:
    """뜨개질 발화만 HOBBY 사실로 추출한다."""

    def generate(self, prompt: str, weather_data=None) -> str:
        if "뜨개질" not in prompt:
            return "[]"
        return json.dumps(
            [{"factType": "HOBBY", "content": "요즘 뜨개질을 자주 한다"}],
            ensure_ascii=False,
        )


class CompletedHandle:
    def cancel(self) -> None:
        return None

    def remaining_sentences(self) -> list[str]:
        return []

    @property
    def is_done(self) -> bool:
        return True


class RecordingPlayer:
    """TTS 네트워크 대신 emit 단계의 비동기 호출 계약만 지킨다."""

    def __init__(self) -> None:
        self.spoken: list[list[str]] = []

    def speak_async(self, sentences) -> CompletedHandle:
        self.spoken.append(list(sentences))
        return CompletedHandle()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"필수 환경변수가 없습니다: {name}")
    return value


def _compact_state(state: dict) -> dict:
    retrieval = dict(state.get("retrieval_status") or {})
    return {
        "intent": state.get("intent"),
        "conversationId": state.get("conversation_id"),
        "lastMessageId": state.get("last_message_id"),
        "retrieval": retrieval,
        "memoryCount": len((state.get("ctx") or {}).get("memories") or []),
        "summaryCount": len((state.get("ctx") or {}).get("relevantSummaries") or []),
        "documentCount": len((state.get("ctx") or {}).get("documents") or []),
    }


def _run_phase(phase: str) -> dict:
    senior_id = _required_env("SENIOR_ID")
    localstore = Path(_required_env("LOCALSTORE_DIR"))
    localstore.mkdir(parents=True, exist_ok=True)

    # recall 단계는 새 사실 추출을 만들 필요가 없다. conversation 단계에서만 큐잉과
    # flush를 실제로 태운다. 설정 캐시를 비워 환경변수 변경이 확실히 반영되게 한다.
    os.environ["EXTRACTION_ENABLED"] = "true" if phase == "conversation" else "false"
    clear_settings_cache()
    db.close_all()

    settings = Settings.from_env(load_env_file=False)
    response_llm = RecordingResponseLlm()
    player = RecordingPlayer()
    context_node.set_client(BackendContextClient(settings=settings))
    handlers.set_llm(response_llm)
    output.set_player(player)
    build.set_conversation_client(BackendConversationClient(settings=settings))

    checkpoint = localstore / f"checkpoint-{phase}.sqlite"
    app = build_graph(checkpoint_path=str(checkpoint))

    try:
        if phase == "conversation":
            information = run_user_turn(app, senior_id, "복지제도 알려줘")
            hobby = run_user_turn(app, senior_id, "요즘 뜨개질을 자주 해요")
            flushed = extraction_flush(
                senior_id,
                llm=DeterministicExtractionLlm(),
                fact_client=BackendFactClient(settings=settings),
            )
            return {
                "phase": phase,
                "turns": [_compact_state(information), _compact_state(hobby)],
                "prompts": response_llm.prompts,
                "spoken": player.spoken,
                "extraction": flushed,
            }

        recall = run_user_turn(app, senior_id, "제가 뜨개질을 좋아한다고 했나요?")
        return {
            "phase": phase,
            "turns": [_compact_state(recall)],
            "prompts": response_llm.prompts,
            "spoken": player.spoken,
        }
    finally:
        context_node.set_client(None)
        handlers.set_llm(None)
        output.set_player(None)
        build.set_conversation_client(None)
        db.close_all()
        clear_settings_cache()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("conversation", "recall"), required=True)
    args = parser.parse_args()
    print(json.dumps(_run_phase(args.phase), ensure_ascii=False))


if __name__ == "__main__":
    main()
