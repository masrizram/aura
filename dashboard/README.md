# AURA Dashboard

React single-page application for visualizing the AURA audit engine state. Provides a professional dark-themed monitoring dashboard for audit findings, convergence gates, metrics, and timeline data.

## Quick Start

```bash
cd dashboard
npm install
npm start
```

The dashboard starts at `http://localhost:3000` with hot reload.

## Data Source

The dashboard reads JSON files from `.aura/state/` via a backend API. By default it proxies API requests to `http://localhost:3001`. 

To serve the data for development:

```powershell
# Simple static file server for .aura/state/
cd C:\laraenv\www\aura
npx serve .aura -l 3001 --cors
```

Alternatively, embed the state files directly:

```json
// In dashboard/package.json, change proxy to point at your API server
"proxy": "http://localhost:3001"
```

## Production Build

```bash
cd dashboard
npm run build
```

Output goes to `dashboard/build/`. Serve these static files from any web server:

```bash
npx serve build
```

## CI/CD Integration

Add to your CI pipeline:

```yaml
# GitHub Actions example
- name: Build Dashboard
  run: |
    cd dashboard
    npm ci
    npm run build

- name: Deploy Dashboard
  run: |
    cp -r dashboard/build/* /var/www/aura-dashboard/
```

## Data Files Used

| File | Source |
|------|--------|
| `.aura/state/convergence.json` | Convergence state, gates, dimension scores |
| `.aura/state/findings.json` | All audit findings with evidence |
| `.aura/state/cycle.json` | Current cycle metadata |
| `.aura/state/tooling-evidence.json` | Tool execution evidence registry |

## Tab Reference

| Tab | Content |
|-----|---------|
| **Overview** | Engine status, classification, score, stats, reason |
| **Convergence Gates** | 12-gate matrix with pass/fail visualization |
| **Findings** | Searchable, filterable findings with expandable detail rows |
| **Metrics** | Radar chart, score trend, status distribution, dimension bars |
| **Timeline** | Cycle history, burndown chart, score progression |
| **Evidence** | Evidence registry browser with hash verification status |