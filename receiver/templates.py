"""WALIBRA 0.4.0 template and scene-transition helpers; pure Python."""
import copy, json, os

TRANSITIONS = ("none", "fade", "slide_left", "slide_right", "slide_up", "slide_down", "zoom")
def load_templates(path=None):
    path = path or os.path.join(os.path.dirname(__file__), "template_catalog.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = []
    for item in data.get("templates", []):
        zones = []
        for z in item.get("zones", []):
            x,y,w,h = (float(z[k]) for k in ("x","y","w","h"))
            if not all(0 <= v <= 1 for v in (x,y,w,h)) or w <= 0 or h <= 0 or x+w > 1.0001 or y+h > 1.0001:
                raise ValueError("Invalid template zone: %s" % z.get("id"))
            zones.append(dict(id=str(z["id"]), x=x, y=y, w=w, h=h))
        if not zones: raise ValueError("Template must contain at least one zone")
        result.append(dict(id=str(item["id"]), name=str(item["name"]), description=str(item.get("description","")), zones=zones))
    return result

def template_scene(template_id, path=None):
    item = next((x for x in load_templates(path) if x["id"] == template_id), None)
    if item is None: raise KeyError(template_id)
    return {"template_id": item["id"], "name": item["name"], "zones": copy.deepcopy(item["zones"])}

def normalize_transition(value):
    return value if value in TRANSITIONS else "none"

def transition_options(scene):
    scene = scene if isinstance(scene, dict) else {}
    return {"transition_in": normalize_transition(scene.get("transition_in")),
            "transition_out": normalize_transition(scene.get("transition_out")),
            "transition_ms": max(100, min(3000, int(scene.get("transition_ms", 500) or 500)))}
