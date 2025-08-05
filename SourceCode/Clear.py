# clear_server.py
import requests

response = requests.post("http://localhost:3000/clear")
print("Server says:", response.text)