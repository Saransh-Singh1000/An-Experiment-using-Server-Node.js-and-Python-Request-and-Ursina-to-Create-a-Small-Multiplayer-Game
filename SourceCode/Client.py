






# Client.py
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import requests, threading, time, uuid

# === CONFIG ===
SERVER_URL = 'http://localhost:3000'
PLAYER_UPDATE_INTERVAL = 1.0
PLAYER_MODEL_PATH = 'Assets/Player.obj'
PLAYER_TEXTURE_PATH = 'Assets/Player.png'
other_players = {}

# === UNIQUE PLAYER ID ===
my_id = str(uuid.uuid4())  # ✅ Unique per client, avoids IP issues

# === UTILITY: Get Model Height ===
def get_model_height(path):
    temp = Entity(model=path)
    height = temp.bounds.size.y  # ✅ Full height of the model
    destroy(temp)
    return height

# === NETWORK: SEND POSITION ===
def update_position():
    while True:
        try:
            requests.post(SERVER_URL, json={
                'id': my_id,
                'x': round(player.x, 2),
                'y': round(player.y, 2),
                'z': round(player.z, 2)
            })
        except Exception as e:
            print('Update Error:', e)
        time.sleep(PLAYER_UPDATE_INTERVAL)

# === NETWORK: FETCH REMOTE PLAYERS ===
def fetch_players():
    while True:
        try:
            res = requests.get(SERVER_URL)
            players = res.json()
            for pid, pos in players.items():
                if pid == my_id:
                    continue  # Skip local player
                if pid not in other_players:
                    other_players[pid] = Entity(
                        model=PLAYER_MODEL_PATH,
                        texture=PLAYER_TEXTURE_PATH,
                        scale=1.5,
                        position=(pos['x'], pos['y'] + player_height / 2 + 0.1, pos['z']),
                        collider='box',
                        double_sided=True
                    )
                else:
                    p = other_players[pid]
                    p.x = pos['x']
                    p.y = pos['y'] + player_height / 2 + 0.1
                    p.z = pos['z']
        except Exception as e:
            print('Fetch Error:', e)
        time.sleep(PLAYER_UPDATE_INTERVAL)

# === URSINA GAME ===
app = Ursina()

# Calculate model height for proper placement
player_height = get_model_height(PLAYER_MODEL_PATH) * 1.5  # Account for scale

# Local player (only rendered and controlled locally)
player = FirstPersonController(
    model=PLAYER_MODEL_PATH,
    texture=PLAYER_TEXTURE_PATH,
    position=(0, player_height / 2 + 0.1, 0),
    collider='box',
)
player.scale = 1.5  # ✅ Match remote player scale
player.gravity = 1

# ✅ Lift camera based on model height + 1.5
camera.parent = player
camera.position = (0, player_height + 0, 0)

Sky()
ground = Entity(
    model='plane',
    scale=100,
    texture='white_cube',
    texture_scale=(100, 100),
    collider='box',
    color=color.green
)

# ESC toggles mouse lock
mouse_locked = True
mouse.locked = True
def input(key):
    global mouse_locked
    if key == 'escape':
        mouse_locked = not mouse_locked
        mouse.locked = mouse_locked
        mouse.visible = not mouse_locked

# Start networking threads
threading.Thread(target=update_position, daemon=True).start()
threading.Thread(target=fetch_players, daemon=True).start()

app.run()