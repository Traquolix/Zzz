# Frontend

React single-page application for real-time traffic monitoring. Displays live vehicle detections on a Mapbox GL map, manages traffic incidents, and provides historical analytics dashboards.

## Stack

- **React 19** + TypeScript (strict mode)
- **Vite** — build and dev server with HMR
- **Mapbox GL JS** — interactive map with fiber overlays and vehicle markers
- **Zustand** — state management
- **Tailwind CSS v4** + **shadcn/ui** — styling and components
- **i18n** — French and English (`src/i18n/en.json`, `src/i18n/fr.json`)

## Key Files

```
frontend/
├── index.html
├── vite.config.ts
├── package.json
├── tailwind.config.ts
├── src/
│   ├── main.tsx                        # App entry point
│   ├── App.tsx                         # Root component, routing
│   ├── context/
│   │   └── RealtimeProvider.tsx        # WebSocket connection + data streaming
│   ├── pages/
│   │   ├── Dashboard/                  # Main monitoring dashboard
│   │   ├── Prototype/                  # Map-centric prototype view
│   │   ├── Login/                      # Authentication
│   │   └── ...
│   ├── hooks/                          # Custom React hooks
│   ├── stores/                         # Zustand stores
│   ├── components/                     # Shared UI components
│   ├── i18n/                           # Translation files
│   │   ├── en.json
│   │   └── fr.json
│   └── lib/                            # Utilities
└── public/                             # Static assets
```

## Real-Time Data

The frontend connects to the backend via WebSocket (`/ws/`). The `RealtimeProvider` handles:

1. JWT authentication over the WebSocket
2. Channel subscriptions (`detections`, `counts`, `incidents`, `fibers`)
3. Automatic reconnection with exponential backoff
4. Data distribution to Zustand stores

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8001` | Backend API base URL |
| `VITE_WS_URL` | `ws://localhost:8001/ws/` | WebSocket endpoint |
| `VITE_MAPBOX_TOKEN` | (required) | Mapbox GL access token |
| `VITE_BASE_URL` | `/` | Base path (set to `/preprod/` for preprod deploy) |

## Running

```bash
# Development (with HMR)
cd services/platform/frontend
npm install
npm run dev              # http://localhost:5173

# Production build
npm run build            # Output in dist/
npm run preview          # Preview production build locally

# Lint and type check
npm run lint             # ESLint
npx tsc --noEmit         # TypeScript check
```

## Conventions

- All user-visible strings go in `src/i18n/en.json` and `src/i18n/fr.json`
- Components use shadcn/ui as the base layer
- Test files colocated next to components: `Component.test.tsx`
- Styling via Tailwind utility classes only — no custom CSS files
