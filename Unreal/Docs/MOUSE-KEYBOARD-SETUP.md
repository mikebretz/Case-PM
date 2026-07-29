# Mouse + keyboard controls (PC game)

## Default controls (after setup)

| Input | Action |
|-------|--------|
| **W A S D** | Move |
| **Mouse** | Look / turn camera |
| **Space** | Jump |
| **Shift** | Sprint (Third Person template) |

On-screen **virtual joysticks are disabled** in project config.

## If it still feels like a gamepad

You added the **Third Person** content pack — it uses **Enhanced Input**.

1. In Content Browser open: `Content/ThirdPerson/Input/IMC_Default`
2. Open `IA_Look` — confirm **Mouse XY2D** is bound (not only gamepad stick)
3. Open `IA_Move` — confirm **WASD** keys are bound
4. Select your player Blueprint (`BP_ThirdPersonCharacter`)
5. Details → **Input** → **Default Mapping Contexts** = `IMC_Default`
6. **Project Settings → Input** → disable **Always Show Touch Interface**

## Play test

Press **Play** (Alt+P). Click in the game window so mouse capture works.
