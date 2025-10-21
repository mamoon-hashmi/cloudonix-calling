import requests

url = "https://api.cloudonix.io/customers/self/domains/stream-pgigtg.cloudonix.net/sessions/acf791116d046eb0ce6f654c6888d6d1"

headers = {"Authorization": "Bearer XI3A86BD6F0C79476CBBB835770DC42401"}  # replace with your real token

response = requests.delete(url, headers=headers)

if response.status_code == 204:
    print("✅ Session deleted successfully.")
elif response.status_code == 404:
    print("❌ Session not found.")
else:
    print("Status:", response.status_code)
    print("Response text:", response.text)
