from bomi_ai_chat.audio_io.laptop import LaptopMicInput, LaptopSpeakerOutput

mic = LaptopMicInput(duration_seconds=3)
speaker = LaptopSpeakerOutput()

audio = mic.capture()
speaker.play(audio)
