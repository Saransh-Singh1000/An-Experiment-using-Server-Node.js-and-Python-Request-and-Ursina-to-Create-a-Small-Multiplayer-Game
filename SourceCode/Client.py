

# Client.py (Ultra-Optimized with Rotating Coins and Colliders)
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import asyncio
import aiohttp
import threading
import time
import uuid
import math
import numpy as np
from collections import deque

# === CONFIG ===
SERVER_URL = 'http://localhost:3000'
PLAYER_UPDATE_INTERVAL = 0.75     # how often we send our position
WORLD_FETCH_INTERVAL = 2.5        # how often we fetch containers+coins
PLAYERS_FETCH_INTERVAL = 0.75
PLAYER_MODEL_PATH = 'Assets/Player.obj'
PLAYER_TEXTURE_PATH = 'Assets/Player.png'
GROUND_TEXTURE_PATH = 'Assets/Grass.png'
BOX_TEXTURE_PATH = 'Assets/SteelCountainer.png'
COIN_MODEL_PATH = 'Assets/Coin.obj'
COIN_TEXTURE_PATH = 'Assets/Coin.png'
CHUNK_SIZE = 50
VIEW_RADIUS = 2
MAX_POOL_PER_CHUNK = 12           # safety cap per chunk to avoid explosion
COIN_LOD_DISTANCE = 80            # beyond this, coins scale down / freeze

# === URSINA APP ===
app = Ursina()


# === IDs & State ===
my_id = str(uuid.uuid4())
other_players = {}
players_lock = threading.Lock()

# === Performance structures ===
active_chunks = {}                # (cx,cz) -> Entity (ground)
chunk_boxes = {}                  # (cx,cz) -> deque[Entity]
chunk_coins = {}                  # (cx,cz) -> deque[Entity]
box_pools = {}                    # (cx,cz) -> deque (recycled boxes)
coin_pools = {}                  # (cx,cz) -> deque (recycled coins)
containers_cache = {}             # server cache of container positions (raw)
coins_cache = {}                  # server cache of coin positions (raw)

# === Utility Helpers ===
def chunk_key(x, z):
    return (math.floor(x / CHUNK_SIZE), math.floor(z / CHUNK_SIZE))

def world_to_chunk_indices_array(xs, zs):
    # vectorized chunk indices for arrays of x,z
    cx = np.floor(np.array(xs) / CHUNK_SIZE).astype(int)
    cz = np.floor(np.array(zs) / CHUNK_SIZE).astype(int)
    return np.vstack((cx, cz)).T

# === Minimal per-frame work: only chunk keep/evict, coin rotation, and sound ===
current_surface = None

def update():
    global current_surface
    # camera vertical control
    camera.rotation_x -= mouse.velocity[1] * 40
    camera.rotation_x = clamp(camera.rotation_x, -90, 90)

    # update chunks only when player moves across chunk boundary to reduce work
    update_chunks_if_needed()

    # Rotate all visible coins smoothly
    for coins in chunk_coins.values():
        for coin in coins:
            coin.rotation_y += 90 * time.dt  # rotate 90 degrees per second

    # sound surface detection (kept minimal)
    hit = raycast(player.world_position + Vec3(0,0.5,0), Vec3(0,-1,0), distance=2, ignore=(player,))
    surface_type = getattr(hit.entity, 'surface_type', None) if hit.hit else None
    is_moving = (held_keys['w'] or held_keys['a'] or held_keys['s'] or held_keys['d']) and player.grounded

    # quick sound logic (unchanged)
    if is_moving:
        if surface_type != current_surface:
            if current_surface == 'grass':
                grass_sound.stop()
            elif current_surface == 'metal':
                metal_sound.stop()
            if surface_type == 'grass':
                grass_sound.play()
            elif surface_type == 'metal':
                metal_sound.play()
            current_surface = surface_type
    else:
        if grass_sound.playing: grass_sound.stop()
        if metal_sound.playing: metal_sound.stop()
        current_surface = None

_last_chunk_center = None
def update_chunks_if_needed():
    global _last_chunk_center
    cx, cz = chunk_key(player.x, player.z)
    center = (cx, cz)
    if center == _last_chunk_center:
        return
    _last_chunk_center = center
    # build visible chunk set
    visible = {(cx + dx, cz + dz) for dx in range(-VIEW_RADIUS, VIEW_RADIUS+1) for dz in range(-VIEW_RADIUS, VIEW_RADIUS+1)}

    # create new chunks
    for key in visible:
        if key not in active_chunks:
            active_chunks[key] = create_chunk(key[0], key[1])

    # unload far chunks
    for key in list(active_chunks.keys()):
        if key not in visible:
            destroy(active_chunks[key])
            del active_chunks[key]
            # recycle chunk objects
            if key in chunk_boxes:
                for ent in chunk_boxes[key]:
                    recycle_box_to_pool(key, ent)
                del chunk_boxes[key]
            if key in chunk_coins:
                for ent in chunk_coins[key]:
                    recycle_coin_to_pool(key, ent)
                del chunk_coins[key]

# === Pool helpers ===
def ensure_pool_for(key):
    if key not in box_pools:
        box_pools[key] = deque()
    if key not in coin_pools:
        coin_pools[key] = deque()

def get_box_from_pool(key):
    ensure_pool_for(key)
    if box_pools[key]:
        ent = box_pools[key].pop()
        ent.enable()
        return ent
    return None

def get_coin_from_pool(key):
    ensure_pool_for(key)
    if coin_pools[key]:
        ent = coin_pools[key].pop()
        ent.enable()
        return ent
    return None

def recycle_box_to_pool(key, ent):
    ensure_pool_for(key)
    ent.disable()
    if len(box_pools[key]) < MAX_POOL_PER_CHUNK:
        box_pools[key].append(ent)
    else:
        destroy(ent)

def recycle_coin_to_pool(key, ent):
    ensure_pool_for(key)
    ent.disable()
    if len(coin_pools[key]) < MAX_POOL_PER_CHUNK:
        coin_pools[key].append(ent)
    else:
        destroy(ent)

# === Chunk / world entity creation ===
def create_chunk(cx, cz):
    world_x, world_z = cx * CHUNK_SIZE, cz * CHUNK_SIZE
    chunk = Entity(
        model='plane',
        scale=(CHUNK_SIZE, 1, CHUNK_SIZE),
        position=(world_x + CHUNK_SIZE/2, -0.5, world_z + CHUNK_SIZE/2),
        texture=GROUND_TEXTURE_PATH,
        texture_scale=(CHUNK_SIZE, CHUNK_SIZE),
        collider='box',
        color=color.green
    )
    chunk.surface_type = 'grass'
    return chunk

# === Entity creation with pooling ===
def spawn_container_entity(key, pos):
    # try pool
    ent = get_box_from_pool(key)
    if ent is None:
        ent = Entity(model='cube', texture=BOX_TEXTURE_PATH, scale=(4,2,3), collider='box', color=color.white, double_sided=True)
        ent.surface_type = 'metal'
    ent.position = (pos['x'], pos['y'], pos['z'])
    ent.enable()
    return ent

def spawn_coin_entity(key, pos):
    ent = get_coin_from_pool(key)
    if ent is None:
        ent = Entity(
            model=COIN_MODEL_PATH,
            texture=COIN_TEXTURE_PATH,
            scale=1,
            collider='box',   # Added box collider
            double_sided=True
        )
    ent.position = (pos['x'], pos['y'], pos['z'])
    ent.enable()
    return ent

# === Async networking (aiohttp) running in background thread ===
async def network_loop():
    timeout = aiohttp.ClientTimeout(total=5.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # schedule repeated tasks
        last_world_fetch = 0.0
        last_players_fetch = 0.0
        last_send = 0.0
        while True:
            now = time.time()

            # send my position (batched, lower-overhead)
            if now - last_send >= PLAYER_UPDATE_INTERVAL:
                last_send = now
                payload = {'id': my_id, 'x': round(player.x,2), 'y': round(player.y,2), 'z': round(player.z,2)}
                asyncio.create_task(post_position(session, payload))

            # fetch other players more frequently (positions are small)
            if now - last_players_fetch >= PLAYERS_FETCH_INTERVAL:
                last_players_fetch = now
                asyncio.create_task(fetch_players(session))

            # fetch world data (containers + coins) less frequently and in batch
            if now - last_world_fetch >= WORLD_FETCH_INTERVAL:
                last_world_fetch = now
                # parallel fetch
                asyncio.create_task(fetch_world(session))

            await asyncio.sleep(0.06)  # small sleep to yield to the loop

async def post_position(session, payload):
    try:
        await session.post(SERVER_URL, json=payload)
    except Exception as e:
        # ignore transient errors but print once in a while
        if int(time.time()) % 10 == 0:
            print('Post pos error:', e)

async def fetch_players(session):
    try:
        async with session.get(SERVER_URL) as resp:
            if resp.status == 200:
                data = await resp.json()
                # quickly update other_players dict in thread-safe manner
                with players_lock:
                    # we will only keep remote players within visible radius (coarse culling)
                    pxs, pzs, ids = [], [], []
                    for pid, p in data.items():
                        if pid == my_id: continue
                        pxs.append(p['x']); pzs.append(p['z']); ids.append(pid)
                    if pxs:
                        arr = np.vstack((pxs, pzs)).T
                    else:
                        arr = np.empty((0,2))
                    # update other_players with minimal work in main thread via function-call
                    invoke_on_main_thread(lambda: update_other_players(ids, pxs, pzs))
    except Exception as e:
        if int(time.time()) % 10 == 0:
            print('Fetch players error:', e)

def update_other_players(ids, xs, zs):
    # invoked in main thread via ursina's invoke or direct call
    cx, cz = chunk_key(player.x, player.z)
    for idx, pid in enumerate(ids):
        px, pz = xs[idx], zs[idx]
        pcx, pcz = chunk_key(px, pz)
        if abs(pcx - cx) <= VIEW_RADIUS and abs(pcz - cz) <= VIEW_RADIUS:
            adjusted_y = 0.0 + 0.1  # server y may be small; we avoid heavy get_model_height calls here
            if pid not in other_players:
                other_players[pid] = Entity(model=PLAYER_MODEL_PATH, texture=PLAYER_TEXTURE_PATH, scale=1.0,
                                           position=(px, adjusted_y, pz), collider='box', double_sided=True)
            else:
                p = other_players[pid]
                p.x, p.y, p.z = px, adjusted_y, pz
    # remove far players
    for pid in list(other_players.keys()):
        # if player vanished server-side or moved far
        if pid not in ids:
            destroy(other_players[pid]); del other_players[pid]

async def fetch_world(session):
    try:
        # parallel GET for containers and coins
        async with session.get(f'{SERVER_URL}/containers') as rc:
            containers_data = await rc.json() if rc.status == 200 else {}
        async with session.get(f'{SERVER_URL}/coins') as rco:
            coins_data = await rco.json() if rco.status == 200 else {}

        # store caches (cheap copy)
        # convert keys to tuple ints for quick comparisons
        new_containers = {}
        for k, v in containers_data.items():
            new_containers[tuple(map(int, k.split(',')))] = v
        new_coins = {}
        for k, v in coins_data.items():
            new_coins[tuple(map(int, k.split(',')))] = v

        # apply to main thread
        invoke_on_main_thread(lambda: apply_world_updates(new_containers, new_coins))
    except Exception as e:
        if int(time.time()) % 10 == 0:
            print('Fetch world error:', e)

def apply_world_updates(containers_dict, coins_dict):
    # caches for future diffs
    global containers_cache, coins_cache
    containers_cache = containers_dict
    coins_cache = coins_dict

    cx, cz = chunk_key(player.x, player.z)
    visible_chunks = {(cx + dx, cz + dz) for dx in range(-VIEW_RADIUS, VIEW_RADIUS+1) for dz in range(-VIEW_RADIUS, VIEW_RADIUS+1)}

    # spawn containers for visible chunks
    for ck in visible_chunks:
        # containers
        if ck in containers_cache and ck not in chunk_boxes:
            positions = containers_cache[ck]
            chunk_boxes[ck] = deque()
            ensure_pool_for(ck)
            for pos in positions:
                ent = get_box_from_pool(ck)
                if ent is None:
                    ent = Entity(model='cube', texture=BOX_TEXTURE_PATH, scale=(4,2,3), collider='box', double_sided=True)
                    ent.surface_type = 'metal'
                ent.position = (pos['x'], pos['y'], pos['z'])
                ent.enable()
                chunk_boxes[ck].append(ent)
        # coins
        if ck in coins_cache and ck not in chunk_coins:
            positions = coins_cache[ck]
            chunk_coins[ck] = deque()
            ensure_pool_for(ck)
            for pos in positions:
                ent = get_coin_from_pool(ck)
                if ent is None:
                    ent = Entity(model=COIN_MODEL_PATH, texture=COIN_TEXTURE_PATH, scale=1, collider='box', double_sided=True)
                ent.position = (pos['x'], pos['y'], pos['z'])
                ent.enable()
                chunk_coins[ck].append(ent)

    # remove chunks that are not visible (we already handle removal in update_chunks_if_needed)
    # but also ensure we recycle any chunk entities that might remain
    # (this is defensive -- most cleanup is handled on chunk unload)
    for ck in list(chunk_boxes.keys()):
        if ck not in visible_chunks:
            for ent in chunk_boxes[ck]:
                recycle_box_to_pool(ck, ent)
            del chunk_boxes[ck]
    for ck in list(chunk_coins.keys()):
        if ck not in visible_chunks:
            for ent in chunk_coins[ck]:
                recycle_coin_to_pool(ck, ent)
            del chunk_coins[ck]

# === small utility to safely call from async to main thread ===
def invoke_on_main_thread(fn, *args, **kwargs):
    # Ursina's invoke executes in the main thread after delay=0
    invoke(fn, *args, delay=0)

# === Player setup (kept similar to before but minimal height calc) ===
def get_model_height(path):
    temp = Entity(model=path)
    h = temp.bounds.size.y
    destroy(temp)
    return h

raw_model_height = get_model_height(PLAYER_MODEL_PATH)
player_scale = 1.0
scaled_height = raw_model_height * player_scale

player = FirstPersonController(position=(0, scaled_height/2 + 0.1, 0), collider='box')
player.gravity = 1
player.height = scaled_height

player_model = Entity(parent=player, model=PLAYER_MODEL_PATH, texture=PLAYER_TEXTURE_PATH, scale=player_scale)
camera.parent = player
camera.position = (0, scaled_height + 0.2, 0)
mouse.locked = True

# === Sound (unchanged minimal) ===
grass_sound = Audio('Assets/WalkingOnGrass.mp3', loop=True, autoplay=False, volume=0.9)
metal_sound = Audio('Assets/WalkingOnMetal.mp3', loop=True, autoplay=False, volume=0.9)

# === Start async networking in background thread ===
def start_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(network_loop())

threading.Thread(target=start_async_loop, daemon=True).start()

# initial chunk load
update_chunks_if_needed()

Sky()

app.run()
