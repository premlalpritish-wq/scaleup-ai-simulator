// Base URL of the Python execution service.
//
// Empty string means "same origin": correct when this page is served by
// api/app.py (`python -m api.app`), which serves /research/ and /api/research/*
// from the same host.
//
// On a static-only host (GitHub Pages, a static site service) set this to the
// HTTPS origin of the Python service in the deployment's build step, for example
//   window.SCALEUP_RESEARCH_API_BASE = "https://scaleup-ai-api.onrender.com";
// The page never carries an API key: the service needs none.
window.SCALEUP_RESEARCH_API_BASE = "";
