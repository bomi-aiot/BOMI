"""ai_chat 진입점 (노트북 모드)."""

from dotenv import load_dotenv

load_dotenv()

from src.pipeline import ConversationPipeline
from src.audio_io.laptop import LaptopMicInput, LaptopSpeakerOutput


def main():
    pipeline = ConversationPipeline(
        audio_in=LaptopMicInput(),
        audio_out=LaptopSpeakerOutput(),
    )
    pipeline.run_once()


if __name__ == "__main__":
    main()