import requests

# API endpoint
url = 'https://core-saas.voicegenie.ai/api/v1/pushCallToCampaign'

# Request headers
headers = {
    'Content-Type': 'application/json'
}

# Request payload
payload = {
    "token": "4b6a5478c86c964c34dbbcabee96b704",
    "workspaceId": "677168f9daa73ba3c5f62430",
    "campaignId": "34dfc424-f145-4319-972c-87cb1c366eeb",
    "customerNumber": "+233553792221",
    "customerInformation": {
        "first_name": "john",
        "last_name": "wick"
    }
}

# Make the POST request
response = requests.post(url, headers=headers, json=payload)

# Check the response
if response.status_code == 200:
    print("Success:", response.json())
else:
    print("Error:", response.status_code)
    print("Response:", response.text)