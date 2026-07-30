# test_weather_llm.py
from dotenv import load_dotenv
load_dotenv()

from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.weather.client import WeatherClient

weather = WeatherClient()
llm = LLMClient()

data = weather.get_forecast("서울")
response = llm.generate("서울 날씨 알려줘", weather_data=data)
print(response)
