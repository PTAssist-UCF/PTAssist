import { defineConfig } from 'orval';

// Orval reads the backend's API description and writes typed TanStack Query hooks into
// src/api/ (one file per API area, for example src/api/me.ts with useGetMe()).
// Regenerate with `npm run generate:api` while the backend runs on localhost:8000.
// If it fails, src/api/ is left empty: `git restore src/api`, start the backend, retry.
// Never edit src/api/ by hand: every run deletes it and writes it again.
export default defineConfig({
  ptassist: {
    input: {
      target: 'http://localhost:8000/openapi.json',
    },
    output: {
      mode: 'tags',
      target: 'src/api',
      schemas: 'src/api/model',
      client: 'react-query',
      clean: true,
      formatter: 'prettier',
      override: {
        // Every generated hook sends its request through apiFetch, which adds the API's
        // address and the signed-in user's token.
        mutator: {
          path: 'src/apiClient.ts',
          name: 'apiFetch',
        },
        // Hooks return the response body itself (me.role), not { data, status, headers }.
        fetch: {
          includeHttpResponseReturnType: false,
        },
      },
    },
  },
});
