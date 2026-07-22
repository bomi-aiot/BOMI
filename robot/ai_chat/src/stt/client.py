"""RTZR Sommers API를 이용한 STT(Speech-to-Text) 클라이언트."""

import os
import time
import requests


class STTClient:
    """오디오를 텍스트로 변환하는 RTZR API 클라이언트."""

    def __init__(self):
        self.client_id = os.getenv("RTZR_CLIENT_ID")
        self.client_secret = os.getenv("RTZR_CLIENT_SECRET")
        self._token = None

    def _get_token(self) -> str:
        resp = requests.post(
            "https://openapi.vito.ai/v1/authenticate",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def transcribe(self, audio: bytes) -> str:
        """오디오 바이트를 받아서 인식된 텍스트를 반환한다."""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1) 오디오 업로드 + 처리 요청
        resp = requests.post(
            "https://openapi.vito.ai/v1/transcribe",
            headers=headers,
            files={"file": ("audio.wav", audio)},
            data={"config": '{"model_name": "sommers", "language": "ko"}'},
        )
        resp.raise_for_status()
        transcribe_id = resp.json()["id"]

        # 2) 완료될 때까지 폴링
        while True:
            result_resp = requests.get(
                f"https://openapi.vito.ai/v1/transcribe/{transcribe_id}",
                headers=headers,
            )
            result_resp.raise_for_status()
            result = result_resp.json()

            if result["status"] == "completed":
                utterances = result["results"]["utterances"]
                return " ".join(u["msg"] for u in utterances)
            elif result["status"] == "failed":
                raise RuntimeError(f"STT 실패: {result}")

            time.sleep(0.5)