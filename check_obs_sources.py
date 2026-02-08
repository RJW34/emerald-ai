"""Check what sources exist in OBS Active Battles scene"""
import obsws_python as obs

client = obs.ReqClient(host='127.0.0.1', port=4455)

# List all scenes
scenes = client.get_scene_list()
print("Available scenes:")
for s in scenes.scenes:
    print(f"  - {s['sceneName']}")

# Check Active Battles scene items
print("\nActive Battles scene items:")
items = client.get_scene_item_list("Active Battles")
for item in items.scene_items:
    print(f"  - {item['sourceName']} (ID: {item['sceneItemId']}, Enabled: {item.get('sceneItemEnabled', True)})")
