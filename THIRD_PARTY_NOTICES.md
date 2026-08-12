# Third-party notices

## Repository license scope

Original software and original documentation in this repository are Copyright (c) 2026
beibeifeng and are distributed under the MIT License in `LICENSE.md`. That license does not
relicense the third-party components, data, images, video, marks, or model-derived material
identified below.

## Three.js r167

- Project: https://threejs.org/
- Source used: `three@0.167.1/build/three.module.js`
- License: MIT
- Vendored license: `app/vendor/three/LICENSE`
- Vendored file SHA-256: `5289ca2dfde8572bd7715b9fa2ca929db12bae87e9a2cb53e431662df7039506`

## Starship Block 3 model-derived geometry

- Creator: Clarence365
- Source: https://sketchfab.com/3d-models/spacex-starship-block-3-6f6c6f88a3eb4b4d822fdca66733fbb2
- License declared by the source metadata: CC BY 4.0
- Use in this repository: simplified, proportion-locked browser geometry in `app/hud/assets/vehicle-models.json`
- Modification notice: the source geometry was simplified, converted, and adapted for browser rendering
- License link: https://creativecommons.org/licenses/by/4.0/

## Broadcast and telemetry-derived material

The public repository does not distribute Flight imagery, broadcast-derived HUD frames, the
Flight 13 public-feed replay data, or the private evidence bundle. Its included
`app/viewer-data.json` is generated synthetic demonstration data and is not a Flight 13
measurement. Flight imagery, telemetry-derived material, marks, and names remain subject to
rights independent of the repository code. No license grant for those materials is implied by
this notice or by `LICENSE.md`.
