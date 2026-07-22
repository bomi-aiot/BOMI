from dotenv import load_dotenv
load_dotenv()

from src.llm.client import LLMClient

llm = LLMClient()
print(llm.generate("오늘 몇 시야?"))