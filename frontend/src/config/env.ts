/**
 * Frontend environment configuration.
 * Reads environment variables provided by Vite (VITE_*).
 */
export const env = {
  apiUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  clerkPublishableKey: import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || '',
} as const;
