import * as THREE from 'three';

export function createTerrain(scene) {
  const size = 120;
  const segments = 60;
  const geometry = new THREE.PlaneGeometry(size, size, segments, segments);
  const positions = geometry.attributes.position;

  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const y = positions.getY(i);
    const height = Math.sin(x * 0.08) * Math.cos(y * 0.08) * 2
      + Math.sin(x * 0.15 + 1) * Math.cos(y * 0.12) * 1
      + Math.random() * 0.3;
    positions.setZ(i, height);
  }
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    color: '#3a6b3a',
    roughness: 0.9,
    metalness: 0.1,
    flatShading: true,
  });

  const terrain = new THREE.Mesh(geometry, material);
  terrain.rotation.x = -Math.PI / 2;
  terrain.receiveShadow = true;
  scene.add(terrain);

  return terrain;
}

export function getTerrainHeight(x, z, terrain) {
  const raycaster = new THREE.Raycaster(
    new THREE.Vector3(x, 50, z),
    new THREE.Vector3(0, -1, 0)
  );
  const hits = raycaster.intersectObject(terrain);
  return hits.length > 0 ? hits[0].point.y : 0;
}

function createTree(x, z, terrain) {
  const group = new THREE.Group();
  const trunkGeo = new THREE.CylinderGeometry(0.15, 0.25, 2, 6);
  const trunkMat = new THREE.MeshStandardMaterial({ color: '#5c4033' });
  const trunk = new THREE.Mesh(trunkGeo, trunkMat);
  trunk.position.y = 1;
  trunk.castShadow = true;
  group.add(trunk);

  const leavesGeo = new THREE.ConeGeometry(1.2, 2.5, 7);
  const leavesMat = new THREE.MeshStandardMaterial({ color: '#2d5a2d' });
  const leaves = new THREE.Mesh(leavesGeo, leavesMat);
  leaves.position.y = 3;
  leaves.castShadow = true;
  group.add(leaves);

  const y = getTerrainHeight(x, z, terrain);
  group.position.set(x, y, z);
  return group;
}

function createRock(x, z, terrain) {
  const geo = new THREE.DodecahedronGeometry(0.5 + Math.random() * 0.5, 0);
  const mat = new THREE.MeshStandardMaterial({ color: '#6a6a6a', flatShading: true });
  const rock = new THREE.Mesh(geo, mat);
  const y = getTerrainHeight(x, z, terrain);
  rock.position.set(x, y + 0.3, z);
  rock.rotation.set(Math.random(), Math.random(), Math.random());
  rock.castShadow = true;
  return rock;
}

function createBuilding(x, z, terrain, type = 'tent') {
  const group = new THREE.Group();
  if (type === 'tent') {
    const poleGeo = new THREE.CylinderGeometry(0.05, 0.05, 3, 4);
    const poleMat = new THREE.MeshStandardMaterial({ color: '#8b7355' });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.y = 1.5;
    group.add(pole);

    const canvasGeo = new THREE.ConeGeometry(2, 2.5, 4);
    const canvasMat = new THREE.MeshStandardMaterial({ color: '#c9a227', side: THREE.DoubleSide });
    const canvas = new THREE.Mesh(canvasGeo, canvasMat);
    canvas.position.y = 2;
    canvas.rotation.y = Math.PI / 4;
    canvas.castShadow = true;
    group.add(canvas);
  } else {
    const baseGeo = new THREE.BoxGeometry(4, 3, 4);
    const baseMat = new THREE.MeshStandardMaterial({ color: '#8b7355' });
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.position.y = 1.5;
    base.castShadow = true;
    group.add(base);

    const roofGeo = new THREE.ConeGeometry(3, 2, 4);
    const roofMat = new THREE.MeshStandardMaterial({ color: '#5c4033' });
    const roof = new THREE.Mesh(roofGeo, roofMat);
    roof.position.y = 4;
    roof.rotation.y = Math.PI / 4;
    roof.castShadow = true;
    group.add(roof);
  }

  const y = getTerrainHeight(x, z, terrain);
  group.position.set(x, y, z);
  return group;
}

export class World {
  constructor(scene) {
    this.scene = scene;
    this.terrain = null;
    this.decorations = [];
    this.spawnPoints = [];
    this.npcPositions = [];
  }

  build() {
    this.terrain = createTerrain(this.scene);

    const treePositions = [
      [-15, -10], [-20, 5], [-8, 15], [12, -18], [25, -8],
      [30, 12], [18, 22], [-25, -20], [-30, 8], [5, 30],
      [-10, -25], [35, -15], [-35, -5], [15, -30], [-5, 35],
      [40, 5], [-40, 15], [22, 35], [-18, 30], [8, -35],
    ];

    treePositions.forEach(([x, z]) => {
      const tree = createTree(x, z, this.terrain);
      this.scene.add(tree);
      this.decorations.push(tree);
    });

    const rockPositions = [
      [-12, -5], [8, 10], [-5, -15], [20, -5], [-18, 12],
      [15, 18], [-25, -12], [10, -22], [-8, 25], [28, 8],
    ];

    rockPositions.forEach(([x, z]) => {
      const rock = createRock(x, z, this.terrain);
      this.scene.add(rock);
      this.decorations.push(rock);
    });

    const camp = createBuilding(0, 0, this.terrain, 'tent');
    this.scene.add(camp);
    this.decorations.push(camp);

    const inn = createBuilding(-8, -3, this.terrain, 'house');
    this.scene.add(inn);
    this.decorations.push(inn);

    this.npcPositions.push({ x: -6, z: -2, name: 'Captain Aldric' });

    this.spawnPoints = [
      { x: 15, z: -12, type: 'wolf' },
      { x: 22, z: -8, type: 'wolf' },
      { x: -18, z: 10, type: 'wolf' },
      { x: 30, z: 5, type: 'wolf' },
      { x: -25, z: -15, type: 'wolf' },
      { x: 35, z: -10, type: 'bandit' },
      { x: -30, z: 5, type: 'bandit' },
      { x: 10, z: 25, type: 'boar' },
      { x: -15, z: 20, type: 'boar' },
      { x: 25, z: 15, type: 'boar' },
      { x: -20, z: -18, type: 'boar' },
      { x: 5, z: -20, type: 'wolf' },
    ];

    const skyColor = new THREE.Color('#87ceeb');
    this.scene.background = skyColor;
    this.scene.fog = new THREE.Fog(skyColor, 40, 80);

    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    this.scene.add(ambient);

    const sun = new THREE.DirectionalLight(0xfff5e0, 1.2);
    sun.position.set(30, 50, 20);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 100;
    sun.shadow.camera.left = -50;
    sun.shadow.camera.right = 50;
    sun.shadow.camera.top = 50;
    sun.shadow.camera.bottom = -50;
    this.scene.add(sun);
  }

  getHeightAt(x, z) {
    return getTerrainHeight(x, z, this.terrain);
  }
}
