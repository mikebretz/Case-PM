import * as THREE from 'three';

export class InputManager {
  constructor(canvas) {
    this.keys = {};
    this.mouse = { x: 0, y: 0, buttons: {} };
    this.canvas = canvas;

    window.addEventListener('keydown', (e) => {
      this.keys[e.code] = true;
      if (['Tab', 'Space'].includes(e.code)) e.preventDefault();
    });
    window.addEventListener('keyup', (e) => { this.keys[e.code] = false; });

    canvas.addEventListener('mousedown', (e) => {
      this.mouse.buttons[e.button] = true;
      this._updateMouse(e);
    });
    canvas.addEventListener('mouseup', (e) => {
      this.mouse.buttons[e.button] = false;
    });
    canvas.addEventListener('mousemove', (e) => this._updateMouse(e));
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  _updateMouse(e) {
    this.mouse.x = e.clientX;
    this.mouse.y = e.clientY;
  }

  isKeyDown(code) { return this.keys[code] || false; }
  isMouseDown(button = 0) { return this.mouse.buttons[button] || false; }

  getMovementVector() {
    let x = 0, z = 0;
    if (this.isKeyDown('KeyW') || this.isKeyDown('ArrowUp')) z -= 1;
    if (this.isKeyDown('KeyS') || this.isKeyDown('ArrowDown')) z += 1;
    if (this.isKeyDown('KeyA') || this.isKeyDown('ArrowLeft')) x -= 1;
    if (this.isKeyDown('KeyD') || this.isKeyDown('ArrowRight')) x += 1;
    const len = Math.sqrt(x * x + z * z);
    if (len > 0) { x /= len; z /= len; }
    return { x, z };
  }
}

export function createRaycaster(camera, mouseX, mouseY, canvas) {
  const raycaster = new THREE.Raycaster();
  const rect = canvas.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    ((mouseX - rect.left) / rect.width) * 2 - 1,
    -((mouseY - rect.top) / rect.height) * 2 + 1
  );
  raycaster.setFromCamera(mouse, camera);
  return raycaster;
}
