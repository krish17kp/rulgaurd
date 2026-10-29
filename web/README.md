# RULGuard web

Animated landing site + demo for RULGuard. Static build (Vite + React + Tailwind v4 + Motion + Lenis), no backend required yet.
The older Next.js app with the Python API wiring lives in `../frontend/` and is untouched.

## Run locally

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

All numbers on the page are real. They come from `src/data.json`, generated from the repo's metrics:

```bash
python3 web/scripts/build_data.py   # run from repo root after re-running evaluation
```

## Deploy to the Hostinger VPS (when ready)

```bash
npm run build                                  # -> web/dist (plain static files)
rsync -avz --delete dist/ user@VPS_IP:/var/www/rulguard/
```

nginx site (`/etc/nginx/sites-available/rulguard`):

```nginx
server {
    server_name your-domain.com;
    root /var/www/rulguard;
    index index.html;

    location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }
    location / { try_files $uri /index.html; }

    # later: the FastAPI backend (../frontend/api/index.py) behind the same domain
    # location /api/ { proxy_pass http://127.0.0.1:8000; client_max_body_size 200m; }
}
```

Then `sudo ln -s /etc/nginx/sites-available/rulguard /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx`, and `sudo certbot --nginx -d your-domain.com` for HTTPS.

## Connecting the backend later

The upload box in `src/components/Analyzer.tsx` currently stops at the applicability step and shows an "analysis server isn't connected" notice.
Swap the `go(file)` timer for a `fetch('/api/...')` call to the same endpoints `../frontend/src/lib/api.ts` already uses.
