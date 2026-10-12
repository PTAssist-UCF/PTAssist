import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@mantine/core/styles.css';
import App from './App';

// One shared cache for every API hook in src/api/ (see src/apiClient.ts). It uses
// TanStack Query's defaults: a failed request is retried 3 times. The 401 handling
// (SCRUM-56) decides whether to skip retries for 4xx answers.
const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <MantineProvider defaultColorScheme="light">
        <App />
      </MantineProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
