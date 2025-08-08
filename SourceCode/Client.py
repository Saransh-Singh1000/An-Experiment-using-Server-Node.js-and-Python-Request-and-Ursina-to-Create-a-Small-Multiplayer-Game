






from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import requests, threading, time, uuid, math
from random import uniform

# === CONFIG ===
SERVER_URL = 'http://localhost:3000'
PLAYER_UPDATE_INTERVAL = 1.0
PLAYER_MODEL_PATH = 'Assets/Player.obj'
PLAYER_TEXTURE_PATH = 'Assets/Player.png'
GROUND_TEXTURE_PATH = 'Assets/Grass.png'
BOX_TEXTURE_PATH = 'Assets/SteelCountainer.png'
CHUNK_SIZE = 50
VIEW_RADIUS = 2

# === UNIQUE PLAYER ID ===
my_id = str(uuid.uuid4())
other_players = {}

# === UTILITY: Get Model Height ===
def get_model_height(path):
    temp = Entity(model=path)
    height = temp.bounds.size.y
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

# === NETWORK: FETCH REMOTE PLAYERS WITH CULLING ===
def fetch_players():
    while True:
        try:
            res = requests.get(SERVER_URL)
            players = res.json()

            cx, cz = chunk_key(player.x, player.z)
            active_ids = set()

            for pid, pos in players.items():
                if pid == my_id:
                    continue

                px, pz = pos['x'], pos['z']
                pcx, pcz = chunk_key(px, pz)

                if abs(pcx - cx) <= VIEW_RADIUS and abs(pcz - cz) <= VIEW_RADIUS:
                    adjusted_y = pos['y'] + scaled_height / 2 + 0.1
                    active_ids.add(pid)

                    if pid not in other_players:
                        other_players[pid] = Entity(
                            model=PLAYER_MODEL_PATH,
                            texture=PLAYER_TEXTURE_PATH,
                            scale=player_scale,
                            position=(px, adjusted_y, pz),
                            collider='box',
                            double_sided=True
                        )
                    else:
                        p = other_players[pid]
                        p.x = px
                        p.y = adjusted_y
                        p.z = pz

            for pid in list(other_players.keys()):
                if pid not in active_ids:
                    destroy(other_players[pid])
                    del other_players[pid]

        except Exception as e:
            print('Fetch Error:', e)
        time.sleep(PLAYER_UPDATE_INTERVAL)

# === URSINA GAME ===
app = Ursina()

# Calculate model height and scale
raw_model_height = get_model_height(PLAYER_MODEL_PATH)
player_scale = 1.0
scaled_height = raw_model_height * player_scale

# Local player controller
player = FirstPersonController(
    position=(0, scaled_height / 2 + 0.1, 0),
    collider='box',
)
player.gravity = 1
player.height = scaled_height

# Attach visual model manually
player_model = Entity(
    parent=player,
    model=PLAYER_MODEL_PATH,
    texture=PLAYER_TEXTURE_PATH,
    scale=player_scale,
    position=(0, 0, 0),
    double_sided=True
)

# Camera setup using scaled height
camera.parent = player
camera.position = (0, scaled_height + 0.2, 0)
camera.rotation = (0, 0, 0)

# ESC toggles mouse lock
mouse_locked = True
mouse.locked = True

def input(key):
    global mouse_locked
    if key == 'escape':
        mouse_locked = not mouse_locked
        mouse.locked = mouse_locked
        mouse.visible = not mouse_locked

# === CHUNK SYSTEM ===
active_chunks = {}
chunk_boxes = {}

def chunk_key(x, z):
    return (math.floor(x / CHUNK_SIZE), math.floor(z / CHUNK_SIZE))

# === SPAWN RANDOM RECTANGULAR BOXES IN CHUNK ===
def spawn_random_boxes_in_chunk(cx, cz, count=5):
    boxes = []
    for _ in range(count):
        x = uniform(cx * CHUNK_SIZE, (cx + 1) * CHUNK_SIZE)
        z = uniform(cz * CHUNK_SIZE, (cz + 1) * CHUNK_SIZE)
        y = 0.5  # Slightly above ground

        box = Entity(
            model='cube',
            texture=BOX_TEXTURE_PATH,
            scale=(4, 2, 3),  # Rectangular shape
            position=(x, y, z),
            collider='box',
            color=color.white
        )
        boxes.append(box)
    return boxes

# === CHUNK CREATION WITH BOXES ===
def create_chunk(cx, cz):
    world_x = cx * CHUNK_SIZE
    world_z = cz * CHUNK_SIZE
    chunk = Entity(
        model='plane',
        scale=(CHUNK_SIZE, 1, CHUNK_SIZE),
        position=(world_x + CHUNK_SIZE / 2, -0.5, world_z + CHUNK_SIZE / 2),
        texture=GROUND_TEXTURE_PATH,
        texture_scale=(CHUNK_SIZE, CHUNK_SIZE),
        collider='box',
        color=color.green
    )
    chunk_boxes[(cx, cz)] = spawn_random_boxes_in_chunk(cx, cz)
    return chunk

def update_chunks():
    cx, cz = chunk_key(player.x, player.z)
    for dx in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
        for dz in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
            key = (cx + dx, cz + dz)
            if key not in active_chunks:
                active_chunks[key] = create_chunk(*key)

    to_remove = []
    for key in active_chunks:
        if abs(key[0] - cx) > VIEW_RADIUS + 1 or abs(key[1] - cz) > VIEW_RADIUS + 1:
            to_remove.append(key)

    for key in to_remove:
        destroy(active_chunks[key])
        del active_chunks[key]

        # Unload boxes
        if key in chunk_boxes:
            for box in chunk_boxes[key]:
                destroy(box)
            del chunk_boxes[key]

# === VERTICAL CAMERA MOVEMENT + CHUNK UPDATE ===
def update():
    camera.rotation_x -= mouse.velocity[1] * 40
    camera.rotation_x = clamp(camera.rotation_x, -90, 90)
    update_chunks()

Sky()
update_chunks()

threading.Thread(target=update_position, daemon=True).start()
threading.Thread(target=fetch_players, daemon=True).start()

app.run()