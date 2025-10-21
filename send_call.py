import requests
import json

# Configuration
API_URL = "https://7202f67a7956.ngrok-free.app/start_call"  # Replace with your actual endpoint
TO_NUMBER = "+13074878591"  # Replace with target phone number (E.164 format)
AGENT_ID = "1"  # The agent ID from your mockAPI

# Request payload
payload = {
    "to_number": TO_NUMBER,
    "agent_id": AGENT_ID
}

# Headers
headers = {
    "Content-Type": "application/json"
}

try:
    # Make the POST request
    response = requests.post(
        API_URL,
        data=json.dumps(payload),
        headers=headers
    )

    # Print formatted response
    print("Status Code:", response.status_code)
    print("Response:", json.dumps(response.json(), indent=2))

except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")