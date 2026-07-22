from dotenv import load_dotenv
import os, requests

load_dotenv()

resp = requests.post(
    'https://openapi.vito.ai/v1/authenticate',
    data={
        'client_id': os.getenv('RTZR_CLIENT_ID'),
        'client_secret': os.getenv('RTZR_CLIENT_SECRET'),
    }
)

print(resp.status_code)
print(resp.json())