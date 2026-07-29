"""
Run inside Unreal Editor:
  Tools -> Run Python Script -> pick this file

Adds ground, continuous slow sun/sky motion, saves SylvorinWorld map.
"""
import unreal

GROUND_SCALE = 50000  # ~500m starter plane (replace with landscape later)
# ~0.004 deg/sec = one full day in 24 real hours; use slightly faster so you can see it
SUN_PITCH_SPEED = 0.01  # degrees per second — always moving, never jumping


def log(msg):
    unreal.log(f"[Sylvorin Setup] {msg}")


def editor_actors():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if subsystem:
        return subsystem
    log("EditorActorSubsystem missing — using legacy API.")
    return None


def spawn_actor(actor_class, location, rotation):
    subsystem = editor_actors()
    if subsystem:
        return subsystem.spawn_actor_from_class(actor_class, location, rotation)
    return unreal.EditorLevelLibrary.spawn_actor_from_class(actor_class, location, rotation)


def disable_snapping_sky_actors():
    """OpenWorld template may use a time-of-day actor that jumps the sun."""
    snap_names = ("timeofday", "time_of_day", "bp_sky", "skydome", "daynight", "sunsky")
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        label = actor.get_actor_label().lower()
        name = actor.get_name().lower()
        if any(token in label or token in name for token in snap_names):
            actor.set_actor_hidden_in_game(True)
            actor.set_is_temporarily_hidden_in_editor(True)
            log(f"Disabled snap sky actor: {actor.get_actor_label()}")


def spawn_ground():
    plane_mesh = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
    if not plane_mesh:
        log("Could not load Engine plane mesh.")
        return None

    actor = spawn_actor(
        unreal.StaticMeshActor,
        unreal.Vector(0, 0, 0),
        unreal.Rotator(0, 0, 0),
    )
    mesh_comp = actor.static_mesh_component
    mesh_comp.set_static_mesh(plane_mesh)
    actor.set_actor_scale3d(unreal.Vector(GROUND_SCALE / 100, GROUND_SCALE / 100, 1))

    grass = unreal.EditorAssetLibrary.load_asset("/Engine/EngineMaterials/WorldGridMaterial")
    if grass:
        mesh_comp.set_material(0, grass)

    actor.set_actor_label("Sylvorin_Ground")
    log(f"Ground plane created ({GROUND_SCALE}uu wide).")
    return actor


def setup_slow_sun():
    sun = None
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.DirectionalLight):
            sun = actor
            break

    if sun is None:
        sun = spawn_actor(
            unreal.DirectionalLight,
            unreal.Vector(0, 0, 200000),
            unreal.Rotator(-45, 0, 0),
        )

    sun.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.set_actor_label("Sylvorin_Sun_SlowRotate")

    rot_comp = sun.get_component_by_class(unreal.RotatingMovementComponent)
    if rot_comp is None:
        rot_comp = unreal.NewObject(unreal.RotatingMovementComponent, sun)
        sun.add_instance_component(rot_comp)
        rot_comp.register_component()

    root = sun.root_component
    if root:
        rot_comp.set_editor_property("updated_component", root)

    rot_comp.set_editor_property(
        "rotation_rate",
        unreal.Rotator(SUN_PITCH_SPEED, 0, 0),
    )
    rot_comp.set_editor_property("b_rotation_in_local_space", True)
    rot_comp.activate(True)

    log(f"Sun rotates continuously ({SUN_PITCH_SPEED} deg/sec on pitch).")
    return sun


def setup_sky():
    sky = None
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.SkyAtmosphere):
            sky = actor
            break

    if sky is None:
        sky = spawn_actor(
            unreal.SkyAtmosphere,
            unreal.Vector(0, 0, 0),
            unreal.Rotator(0, 0, 0),
        )
        log("Sky Atmosphere spawned.")
    else:
        log("Sky Atmosphere found.")

    sky.set_actor_label("Sylvorin_Sky")

    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.SkyLight):
            actor.set_actor_label("Sylvorin_SkyLight")
            actor.set_mobility(unreal.ComponentMobility.MOVABLE)
            log("Sky Light found.")
            break


def save_map():
    map_path = "/Game/Sylvorin/Maps/SylvorinWorld"
    unreal.EditorAssetLibrary.make_directory("/Game/Sylvorin/Maps")
    unreal.EditorLevelLibrary.save_current_level_as(map_path)
    log(f"Map saved: {map_path}")
    log("Project Settings -> Maps & Modes -> Game Default Map = SylvorinWorld")


def main():
    disable_snapping_sky_actors()
    spawn_ground()
    setup_slow_sun()
    setup_sky()
    save_map()
    log("DONE. Press Play — WASD + mouse, Space jump, slow sky always moving.")


if __name__ == "__main__":
    main()
