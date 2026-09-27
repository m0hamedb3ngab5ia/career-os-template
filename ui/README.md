# career-os web UI (frontend)

React + TypeScript app served by `careeros ui` (see `docs/UI.md`). The build lands in
`src/careeros/ui/static/` and is **committed**, so running the app never needs Node.

```sh
cd ui
npm ci
npm run dev          # http://localhost:5173, proxies /api to `careeros ui` on 127.0.0.1:8765
npm test             # Vitest + Testing Library (watch); `npm test -- --run` once
npm run typecheck
npx -p node@22 npm run build   # rebuild the committed bundle; commit src/careeros/ui/static
```

- Node: the major in `../.nvmrc` (22). `npm run build` refuses another major; `CAREEROS_NODE_ANY=1` overrides it
  locally, and CI's bundle check still catches any difference.
- CI (`ui` job) runs typecheck, tests and a fresh build, then fails if `src/careeros/ui/static` differs from what is
  committed.
- Layout: `src/kit/` (design-system components and label tables), `src/app/` (shell, routes), `src/api/` (fetch
  client, live events), `src/features/<screen>/`, `src/styles/tokens.css` (all colours and sizes, light + dark).
- `/kit` shows every component in both themes for checking against the mockup.
