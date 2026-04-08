# Angular 15 — Specifiques version

## Stack technique

| Composant | Version |
|-----------|---------|
| Angular | 15.2.10 |
| Node | 18.19.0 |
| TypeScript | ES2022 |
| Tests unit | Jest 29 + jest-preset-angular |
| Tests E2E | Cypress 12 |
| i18n | @ngx-translate/core 14 |
| Auth | @pe-commons/authent 1.2 + jwt-decode 4 |
| Linting | ESLint + @angular-eslint |

## Proxy dev vers backend

`proxy.conf.json` pour `ng serve` — reecrit les appels API vers le backend Quarkus :

```json
{
  "/exp-yb278": {
    "target": "http://localhost:8077",
    "secure": false,
    "changeOrigin": true,
    "pathRewrite": {
      "^/exp-yb278": "/pollinisationnalistements"
    }
  }
}
```

Le nginx Docker fait le meme rewrite via `proxy_pass`.

## Dev replacement

Remplacer le container nginx Docker par `ng serve` local :

```bash
mise dev-<code-angular>
# ou manuellement :
# docker compose stop <service-angular>
# cd <repo-angular> && npm start
```

- La task `dev-<code>` extrait `node_modules` depuis le stage builder Docker si `ng` est absent (layers en cache apres `mise stack`, quasi-instantane). Pas de `npm install` depuis le host (le registry npm PE peut etre indisponible)
- Hot reload automatique a chaque sauvegarde
- Le proxy redirige `/exp-yb278/*` vers le backend Quarkus (localhost:8077)
- Port 4200 identique au container nginx → les tests Behave/Playwright fonctionnent sans changement

## Build Docker

3 stages :
1. **npm config** : copie package.json, installe deps (avec bouchon `@pe-commons/authent`)
2. **Node build** : `npm run build` (Angular CLI prod)
3. **Nginx serve** : copie le `dist/` dans nginx, template de conf pour le reverse proxy

```dockerfile
FROM node:18.19.0-alpine AS builder
# ...
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html/ihm-pollinisationnalistements
COPY nginx-spa.conf.template /etc/nginx/templates/spa.conf.template
```

## Bouchon authent

Le module `@pe-commons/authent` vient du registre npm PE interne (inaccessible en local). Un bouchon est copie manuellement dans `node_modules/@pe-commons/authent/` avant `npm install`.

## environment.ts et bouchon-peam

`ng serve` utilise `environment.ts` (dev), pas `environment.prod.ts` (Docker/dockerize). Pour que le flow OAuth fonctionne avec bouchon-peam en mode dev :

```typescript
// environment.ts
openAMUrl: 'http://localhost:9012',  // bouchon-peam, PAS le vrai SSO
```

Sans ca, l'iframe auth pointe vers le vrai SSO France Travail (`authentification-agent-tis.pe.intra`) qui est inaccessible en local, et l'overlay de login couvre toute la page (z-index 9999).

## Points d'attention

- **baseHref** : `/ihm-<app>/` dans `angular.json` — toutes les routes sont prefixees
- **SPA routing** : nginx configure `try_files $uri $uri/ /ihm-<app>/index.html`
- **CORS** : le backend Quarkus autorise `*` (`quarkus.http.cors.origins=/.*/`)
