






# Client.py
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import requests, threading, time, socket

SERVER_URL = 'http://localhost:3000'
PLAYER_UPDATE_INTERVAL = 0.0
other_players = {}

# Get local IP for unique ID
def get_my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except:
        return '127.0.0.1'
    finally:
        s.close()

my_ip = get_my_ip()

def update_position():
    while True:
        try:
            requests.post(SERVER_URL, json={
                'x': round(player.x, 2),
                'y': round(player.y, 2),
                'z': round(player.z, 2)
            })
        except Exception as e:
            print('Update Error:', e)
        time.sleep(PLAYER_UPDATE_INTERVAL)

def fetch_players():
    while True:
        try:
            res = requests.get(SERVER_URL)
            players = res.json()
            for ip, pos in players.items():
                if ip == my_ip:
                    continue
                if ip not in other_players:
                    other_players[ip] = Entity(model='cube', color=color.red, scale=(1, 2, 1))
                other_players[ip].x = pos['x']
                other_players[ip].y = pos['y']
                other_players[ip].z = pos['z']
        except Exception as e:
            print('Fetch Error:', e)
        time.sleep(PLAYER_UPDATE_INTERVAL)

# Ursina Game
app = Ursina()
player = FirstPersonController()
player.gravity = 0

Sky()
ground = Entity(model='plane', scale=100, texture='white_cube', texture_scale=(100,100), collider='box', color=color.green)

# ESC key to toggle mouse lock
mouse_locked = True
mouse.locked = True

def input(key):
    global mouse_locked
    if key == 'escape':
        mouse_locked = not mouse_locked
        mouse.locked = mouse_locked
        mouse.visible = not mouse_locked

# Start networking
threading.Thread(target=update_position, daemon=True).start()
threading.Thread(target=fetch_players, daemon=True).start()

app.run()
