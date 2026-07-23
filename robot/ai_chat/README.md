# BOMI AI Chat

돌봄 로봇의 음성 대화(STT → LLM → TTS) 파이프라인을 담당하는 Python 프로젝트다. 사용자의 발화를 텍스트로 변환하고, 발화 내용에 따라 로컬 모델(Jetson)과 API 모델(Gemini) 중 하나로 라우팅하여 응답을 생성한 뒤 음성으로 재생한다.

## 현재 구현 범위

STT-LLM-TTS 순차 파이프라인, 로컬/API 하이브리드 LLM 라우팅, 날씨 조회 연동, 노트북 마이크/스피커 기반 오디오 입출력이 구현되어 있다. 젯슨 오린 나노 배포 및 실기기 테스트는 진행 중이다.

## 디렉터리 구조

```text
src/audio_io/   마이크/스피커 입출력 (노트북/로봇 구현체)
src/llm/        로컬(Ollama)/API(Gemini) LLM 클라이언트 및 라우팅 로직
src/stt/        RTZR Sommers 기반 STT 클라이언트
src/tts/        TTS 클라이언트
src/weather/    기상청 API 연동
src/pipeline.py STT → LLM → TTS 파이프라인
src/main.py     진입점 (노트북 모드)
tests/          LLM 라우팅/응답 품질 테스트
```

## 빠른 시작

지원 Python 버전은 3.10 이상 3.13 미만이다. 저장소를 복제한 뒤 프로젝트 루트(`ai_chat/`)에서 가상환경을 생성하고 활성화한다.

Windows PowerShell:

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install -e .
```

Linux 또는 Jetson:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -e .
```

## 환경 변수

프로젝트 루트에 `.env` 파일을 만들고 노션 자료/학습 > 공통 > AI_CHAT API key값을 설정한다.

## 로컬 LLM(Ollama) 설정

로컬 모델은 Ollama를 통해 실행한다. 최초 1회 아래 명령으로 모델을 받아둔다.

```bash
ollama pull exaone3.5:2.4b
```

Ollama가 백그라운드 서비스(`localhost:11434`)로 떠 있어야 하며, 설치되어 있지 않다면 [ollama.com](https://ollama.com)에서 설치한다.

## 실행

```bash
python -m src.main
```

마이크 입력을 받아 STT → 라우팅 판단 → LLM 응답 생성 → TTS 재생까지 한 번 실행한다.

## LLM 라우팅 기준

1. 날씨/시간/날짜 등 정형 정보 조회는 판단 없이 바로 로컬로 처리한다.
2. 그 외 발화는 문장 임베딩(`ko-sroberta-multitask`) 유사도로 판단한다. 개인 맥락(가족, 과거 대화 회상)이나 정서/건강 관련 표현과 유사도가 threshold 이상이면 API로, 그 외는 로컬로 라우팅한다.

## 테스트

STT/TTS 없이 LLM 라우팅과 로컬/API 응답을 나란히 비교할 수 있다.

```bash
python test_llm.py
```

## 후속 작업

젯슨 오린 나노 실기기 배포, 라우팅 threshold 튜닝, 로컬 모델 응답 길이/품질 보정이 남아 있다.