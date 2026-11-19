import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@mantine/core/styles.css';
import App from './App';

import { ApiError } from '@/apiClient';

/**
 * Decides whether to retry a failed API query. Client errors (4xx, such as 401 or 403)
 * are not retried so redirects and error states respond immediately. Server and network
 * errors are retried up to 3 times.
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
    return false;
  }
  return failureCount < 3;
}

// One shared cache for every API hook in src/api/ (see src/apiClient.ts).
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: shouldRetryQuery,
    },
  },
});

const rootElement = document.getElementById('root');
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <MantineProvider defaultColorScheme="light">
          <App />
        </MantineProvider>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
