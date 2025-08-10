


from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import requests, threading, time, uuid, math

# === CONFIG ===
SERVER_URL = 'http://localhost:3000'
PLAYER_UPDATE_INTERVAL = 1.0
PLAYER_MODEL_PATH = 'Assets/Player.obj'
PLAYER_TEXTURE_PATH = 'Assets/Player.png'
GROUND_TEXTURE_PATH = 'Assets/Grass.png'
BOX_TEXTURE_PATH = 'Assets/SteelCountainer.png'
CHUNK_SIZE = 50
VIEW_RADIUS = 2

# === URSINA GAME ===
app = Ursina()  # Must be created BEFORE any Entity or Audio!

# === UNIQUE PLAYER ID ===
my_id = str(uuid.uuid4())
other_players = {}

# === UTILITY: Get Model Height ===
def get_model_height(path):
    temp = Entity(model=path)
    height = temp.bounds.size.y
    destroy(temp)
    return height

# === SOUND SETUP ===
grass_sound = Audio('Assets/WalkingOnGrass.mp3', loop=True, autoplay=False, volume=1)
metal_sound = Audio('Assets/WalkingOnMetal.mp3', loop=True, autoplay=False, volume=1)
current_surface = None

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

# === CHUNK SYSTEM ===
active_chunks = {}
chunk_boxes = {}  # Containers per chunk: {(cx, cz): [Entity, ...]}

def chunk_key(x, z):
    return (math.floor(x / CHUNK_SIZE), math.floor(z / CHUNK_SIZE))

# === LOAD CONTAINERS FROM SERVER ===
def fetch_containers():
    global chunk_boxes
    while True:
        try:
            res = requests.get(f'{SERVER_URL}/containers')
            data = res.json()  # { "cx,cz": [ {x,y,z}, ... ] }

            # For each chunk, place containers if not already present
            for key, positions in data.items():
                cx, cz = map(int, key.split(','))
                if (cx, cz) not in chunk_boxes:
                    chunk_boxes[(cx, cz)] = []
                    for pos in positions:
                        box = Entity(
                            model='cube',
                            texture=BOX_TEXTURE_PATH,
                            scale=(4, 2, 3),
                            position=(pos['x'], pos['y'], pos['z']),
                            collider='box',
                            color=color.white
                        )
                        box.surface_type = 'metal'
                        chunk_boxes[(cx, cz)].append(box)

            # Remove container entities for chunks no longer sent by server
            keys_to_remove = []
            for ck in list(chunk_boxes.keys()):
                if f"{ck[0]},{ck[1]}" not in data:
                    for box in chunk_boxes[ck]:
                        destroy(box)
                    keys_to_remove.append(ck)
            for k in keys_to_remove:
                del chunk_boxes[k]

        except Exception as e:
            print('Container Fetch Error:', e)
        time.sleep(5)  # fetch every 5 seconds

# === CHUNK CREATION WITHOUT CONTAINERS ===
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
    chunk.surface_type = 'grass'
    return chunk

def update_chunks():
    cx, cz = chunk_key(player.x, player.z)
    for dx in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
        for dz in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
            key = (cx + dx, cz + dz)
            if key not in active_chunks:
                active_chunks[key] = create_chunk(*key)

    to_remove = []
    for key in list(active_chunks.keys()):
        if abs(key[0] - cx) > VIEW_RADIUS + 1 or abs(key[1] - cz) > VIEW_RADIUS + 1:
            to_remove.append(key)

    for key in to_remove:
        destroy(active_chunks[key])
        del active_chunks[key]

        # Unload containers for this chunk
        if key in chunk_boxes:
            for box in chunk_boxes[key]:
                destroy(box)
            del chunk_boxes[key]

# === VERTICAL CAMERA MOVEMENT + CHUNK UPDATE + SURFACE SOUND ===
def update():
    global current_surface

    camera.rotation_x -= mouse.velocity[1] * 40
    camera.rotation_x = clamp(camera.rotation_x, -90, 90)
    update_chunks()

    # Detect surface type under player using surface_type attribute
    hit_info = raycast(player.world_position + Vec3(0, 0.5, 0), Vec3(0, -1, 0), distance=2, ignore=(player,))
    surface_type = None
    if hit_info.hit and hasattr(hit_info.entity, 'surface_type'):
        surface_type = hit_info.entity.surface_type

    # Determine if moving on ground
    is_moving = (held_keys['w'] or held_keys['a'] or held_keys['s'] or held_keys['d']) and player.grounded
    if is_moving:
        if surface_type != current_surface:
            # Stop old sound
            if grass_sound.playing:
                grass_sound.stop()
            if metal_sound.playing:
                metal_sound.stop()

            # Play new sound
            if surface_type == 'grass':
                grass_sound.play()
            elif surface_type == 'metal':
                metal_sound.play()

            current_surface = surface_type
        else:
            # If same surface, but sound not playing, play again
            if surface_type == 'grass' and not grass_sound.playing:
                grass_sound.play()
            elif surface_type == 'metal' and not metal_sound.playing:
                metal_sound.play()
    else:
        # Stop all sounds if not moving
        if grass_sound.playing:
            grass_sound.stop()
        if metal_sound.playing:
            metal_sound.stop()
        current_surface = None

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

Sky()
update_chunks()

threading.Thread(target=update_position, daemon=True).start()
threading.Thread(target=fetch_players, daemon=True).start()
threading.Thread(target=fetch_containers, daemon=True).start()

app.run()
