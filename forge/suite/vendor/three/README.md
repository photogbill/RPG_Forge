# three.js, kept inside the forge (BUILD 36)

The 3D workshop's viewer (forge/suite/viewer.html) draws models with three.js. It is kept here, in the repository,
so the viewer never fetches anything from the internet at run time.

- three.js r170 (npm package `three@0.170.0`), MIT licence — see LICENSE.txt (Copyright © 2010-2024 three.js authors)
- files: build/three.module.min.js -> three.module.min.js; examples/jsm/loaders/GLTFLoader.js,
  examples/jsm/controls/OrbitControls.js, examples/jsm/utils/BufferGeometryUtils.js (unchanged)
- served by the suite at /suite/vendor/three/<file>; the viewer's import map points `three` at three.module.min.js
