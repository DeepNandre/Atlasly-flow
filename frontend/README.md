# Atlasly Frontend

React control-tower source for the Atlasly demo app.

## Source of truth
- Source app: `/Users/deepnandre/Desktop/Atlasly-flow/frontend`
- Built web assets served by the Python runtime: `/Users/deepnandre/Desktop/Atlasly-flow/webapp`
- Backend runtime contract: `/Users/deepnandre/Desktop/Atlasly-flow/scripts/webapp_server.py`

## Commands
- Install deps: `npm install`
- Dev server: `npm run dev`
- Lint: `npm run lint`
- Tests: `npm run test`
- Production build to `/webapp`: `npm run build`

## Notes
- The React app targets the existing Python control-tower runtime. Keep frontend request/response shapes aligned with the backend routes before changing page logic.
- Role switching in the UI uses backend-issued demo sessions from `/api/sessions`; do not reintroduce local-only role simulation.
