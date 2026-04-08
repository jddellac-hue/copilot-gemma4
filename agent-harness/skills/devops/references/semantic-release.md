# Semantic Release — Référence complète

## Configuration Node.js

### `.releaserc.json` complet

```json
{
  "branches": [
    "main",
    "next",
    { "name": "beta", "prerelease": true },
    { "name": "alpha", "prerelease": true }
  ],
  "tagFormat": "v${version}",
  "plugins": [
    ["@semantic-release/commit-analyzer", {
      "preset": "angular",
      "releaseRules": [
        { "type": "docs", "scope": "README", "release": "patch" },
        { "type": "refactor", "release": "patch" },
        { "type": "perf", "release": "patch" },
        { "type": "build", "scope": "deps", "release": "patch" },
        { "scope": "no-release", "release": false }
      ],
      "parserOpts": {
        "noteKeywords": ["BREAKING CHANGE", "BREAKING CHANGES"]
      }
    }],
    ["@semantic-release/release-notes-generator", {
      "preset": "conventionalcommits",
      "presetConfig": {
        "types": [
          { "type": "feat", "section": "Features" },
          { "type": "fix", "section": "Bug Fixes" },
          { "type": "perf", "section": "Performance" },
          { "type": "refactor", "section": "Refactoring" },
          { "type": "docs", "section": "Documentation" },
          { "type": "build", "section": "Build" },
          { "type": "ci", "section": "CI/CD", "hidden": true },
          { "type": "test", "section": "Tests", "hidden": true },
          { "type": "chore", "section": "Miscellaneous", "hidden": true }
        ]
      }
    }],
    ["@semantic-release/changelog", {
      "changelogFile": "CHANGELOG.md",
      "changelogTitle": "# Changelog"
    }],
    ["@semantic-release/npm"],
    ["@semantic-release/git", {
      "assets": ["CHANGELOG.md", "package.json"],
      "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
    }],
    ["@semantic-release/github"]
  ]
}
```

**Ordre des plugins** : L'ordre compte. `changelog` doit précéder `git` pour que le fichier CHANGELOG.md soit inclus dans le commit.

## Configuration Python

### `pyproject.toml`

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
commit_parser = "conventional"
build_command = "python -m build --sdist --wheel ."
tag_format = "v{version}"

[tool.semantic_release.commit_parser_options]
minor_tags = ["feat"]
patch_tags = ["fix", "perf"]
parse_squash_commits = true
ignore_merge_commits = true

[tool.semantic_release.branches.main]
match = "main"

[tool.semantic_release.branches.rc]
match = "rc"
prerelease = true
prerelease_token = "rc"

[tool.semantic_release.changelog]
exclude_commit_patterns = [
    "chore\\(release\\):",
    "Merge branch",
]

[tool.semantic_release.remote]
type = "github"
token = { env = "GH_TOKEN" }
```

## Commitlint + Husky

### Installation

```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional husky
npx husky init
echo 'npx --no -- commitlint --edit $1' > .husky/commit-msg
```

### `commitlint.config.mjs`

```javascript
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', [
      'feat', 'fix', 'docs', 'style', 'refactor',
      'perf', 'test', 'build', 'ci', 'chore', 'revert'
    ]],
    'scope-empty': [0],
    'subject-case': [2, 'never', ['upper-case', 'pascal-case', 'start-case']],
    'subject-empty': [2, 'never'],
    'subject-max-length': [2, 'always', 72],
    'type-case': [2, 'always', 'lower-case'],
    'type-empty': [2, 'never'],
    'body-max-line-length': [2, 'always', 100],
    'body-leading-blank': [2, 'always'],
    'footer-leading-blank': [2, 'always'],
    'header-max-length': [2, 'always', 100],
  },
};
```

**Niveaux de sévérité :** 0 = désactivé, 1 = warning, 2 = erreur (bloque le commit)

### lint-staged (bonus)

```bash
npm install --save-dev lint-staged
```

**`.husky/pre-commit` :**
```bash
npx lint-staged
```

**`package.json` :**
```json
{
  "lint-staged": {
    "*.{js,ts,tsx}": ["eslint --fix", "prettier --write"],
    "*.py": ["ruff check --fix", "ruff format"],
    "*.{json,md,yml}": ["prettier --write"]
  }
}
```

## GitHub Actions

### Release pipeline Node.js

```yaml
name: Release
on:
  push:
    branches: [main, next]

permissions:
  contents: write
  issues: write
  pull-requests: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npm run lint
      - run: npm test

  release:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npx semantic-release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

### Release pipeline Python

```yaml
name: Release
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest

  release:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install python-semantic-release build
      - run: semantic-release version
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - run: semantic-release publish
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Plugins utiles

### Officiels

| Plugin | Usage |
|--------|-------|
| `@semantic-release/commit-analyzer` | Détermine le type de bump (défaut) |
| `@semantic-release/release-notes-generator` | Génère le changelog (défaut) |
| `@semantic-release/npm` | Publie sur npm (défaut) |
| `@semantic-release/github` | Crée la GitHub Release (défaut) |
| `@semantic-release/changelog` | Écrit CHANGELOG.md |
| `@semantic-release/git` | Commit les artefacts de release |
| `@semantic-release/exec` | Commandes shell arbitraires |

### Communautaires

| Plugin | Usage |
|--------|-------|
| `semantic-release-pypi` | Publier sur PyPI |
| `semantic-release-docker` | Build et push images Docker |
| `semantic-release-slack-bot` | Notifications Slack |

## Règles de bump

| Pattern de commit | Bump |
|-------------------|------|
| `BREAKING CHANGE:` dans footer ou `!` après type | MAJOR |
| `feat:` ou `feat(scope):` | MINOR |
| `fix:` ou `perf:` | PATCH |
| Tous les autres (docs, style, refactor...) | Pas de release |

## Changelog généré — exemple

```markdown
# Changelog

## [2.1.0](https://github.com/org/repo/compare/v2.0.0...v2.1.0) (2026-02-14)

### Features

* **auth:** ajouter le support OAuth2 ([abc1234](https://github.com/org/repo/commit/abc1234))
* **search:** ajouter l'autocomplétion ([def5678](https://github.com/org/repo/commit/def5678))

### Bug Fixes

* **bfs:** corriger le calcul pour les graphes cycliques ([fed8765](https://github.com/org/repo/commit/fed8765))

### Performance

* **graph:** optimiser le rendu avec requestAnimationFrame ([cba4321](https://github.com/org/repo/commit/cba4321))
```
