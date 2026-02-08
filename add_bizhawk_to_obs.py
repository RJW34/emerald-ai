"""
Add BizHawk window capture to OBS "Active Battles" scene
"""
import obsws_python as obs
import sys
import os

# Fix Unicode encoding for Windows console
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    # Connect to OBS WebSocket (no auth on localhost:4455)
    client = obs.ReqClient(host='127.0.0.1', port=4455)
    
    # Get current scenes to verify "Active Battles" exists
    scenes = client.get_scene_list()
    scene_names = [s['sceneName'] for s in scenes.scenes]
    print(f"Available scenes: {scene_names}")
    
    target_scene = "Active Battles"
    if target_scene not in scene_names:
        print(f"ERROR: Scene '{target_scene}' not found!")
        print("Available scenes:", scene_names)
        sys.exit(1)
    
    # Check if BizHawk source already exists
    try:
        items = client.get_scene_item_list(target_scene)
        for item in items.scene_items:
            if "BizHawk" in item['sourceName'] or "EmuHawk" in item['sourceName']:
                print(f"BizHawk source already exists: {item['sourceName']}")
                print(f"  Item ID: {item['sceneItemId']}")
                print(f"  Enabled: {item.get('sceneItemEnabled', True)}")
                return
    except Exception as e:
        print(f"Warning checking existing items: {e}")
    
    # Create window capture source for EmuHawk
    source_name = "BizHawk Emerald AI"
    
    # Window capture settings for Windows
    settings = {
        "window": "EmuHawk.exe:EmuHawk",  # Partial match for window title
        "capture_mode": "window",
        "priority": 2,  # Match title with executable
    }
    
    try:
        # Create the input (source)
        client.create_input(
            target_scene,
            source_name,
            "game_capture",  # Try game capture first (better performance)
            settings,
            True  # sceneItemEnabled
        )
        print(f"✅ Created game capture source: {source_name}")
    except Exception as e:
        print(f"Game capture failed ({e}), trying window capture...")
        try:
            client.create_input(
                target_scene,
                source_name,
                "window_capture",
                settings,
                True
            )
            print(f"✅ Created window capture source: {source_name}")
        except Exception as e2:
            print(f"❌ Failed to create source: {e2}")
            sys.exit(1)
    
    # Get the newly created item to position it
    items = client.get_scene_item_list(target_scene)
    bizhawk_item = None
    for item in items.scene_items:
        if item['sourceName'] == source_name:
            bizhawk_item = item
            break
    
    if not bizhawk_item:
        print("Warning: Could not find newly created item to position it")
        return
    
    item_id = bizhawk_item['sceneItemId']
    
    # Position it bottom-center (assuming 1920x1080 canvas)
    # BizHawk GBA is 240x160, scale to ~480x320
    transform = {
        "positionX": 720,  # Center horizontally: (1920 - 480) / 2
        "positionY": 700,  # Bottom area: 1080 - 320 - 60
        "scaleX": 2.0,
        "scaleY": 2.0,
        "alignment": 5,  # Center alignment
    }
    
    client.set_scene_item_transform(target_scene, item_id, transform)
    print(f"✅ Positioned BizHawk at bottom-center")
    print(f"   Position: ({transform['positionX']}, {transform['positionY']})")
    print(f"   Scale: {transform['scaleX']}x")
    
    print("\n✅ BizHawk added to OBS successfully!")

if __name__ == "__main__":
    main()
