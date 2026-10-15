import type { ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Alert, Code, Container } from '@mantine/core';
import { ClerkProvider } from '@clerk/react';

import { env } from '@/config/env';
import ApiAuth from '@/components/ApiAuth';
import RequireSignIn from '@/components/RequireSignIn';
import SignInPage from './pages/SignInPage';
import SignUpPage from './pages/SignUpPage';
import PatientPage from './pages/patient/PatientPage';
import TherapistPage from './pages/therapist/TherapistPage';
import RoleRedirect from '@/components/RoleRedirect';
import RoleRoute from '@/components/RoleRoute';

export default function App() {
  // Without a publishable key (pk_test_...), Clerk never loads and every page would show a
  // spinner, so say what is missing instead. This also catches the secret key
  // (sk_test_...) put here by mistake.
  if (!env.clerkPublishableKey.startsWith('pk_')) {
    return <MissingClerkKey />;
  }

  return (
    <BrowserRouter>
      <ClerkWithRouter publishableKey={env.clerkPublishableKey}>
        <ApiAuth>
          <Routes>
            {/* Clerk's forms. Their later steps live under these paths, hence the "/*". */}
            <Route path="/sign-in/*" element={<SignInPage />} />
            <Route path="/sign-up/*" element={<SignUpPage />} />
            {/* Every page inside this route needs a signed-in user. */}
            <Route element={<RequireSignIn />}>
              {/* Sends each user to their own side, based on the role from /me. */}
              <Route path="/" element={<RoleRedirect />} />
              <Route
                path="/patient"
                element={
                  <RoleRoute role="patient">
                    <PatientPage />
                  </RoleRoute>
                }
              />
              <Route
                path="/therapist"
                element={
                  <RoleRoute role="therapist">
                    <TherapistPage />
                  </RoleRoute>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </ApiAuth>
      </ClerkWithRouter>
    </BrowserRouter>
  );
}

/**
 * Clerk (sign-in), set up to change pages through React Router. Without routerPush and
 * routerReplace, each of Clerk's page changes would reload the whole app.
 */
function ClerkWithRouter({
  publishableKey,
  children,
}: {
  publishableKey: string;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <ClerkProvider
      publishableKey={publishableKey}
      routerPush={(to) => navigate(to)}
      routerReplace={(to) => navigate(to, { replace: true })}
      // Our own pages for Clerk's forms, instead of Clerk's hosted pages.
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/sign-in"
    >
      {children}
    </ClerkProvider>
  );
}

function MissingClerkKey() {
  return (
    <Container size="sm" py="xl">
      <Alert color="red" title="Sign-in is not set up">
        Set <Code>VITE_CLERK_PUBLISHABLE_KEY</Code> in <Code>frontend/.env</Code> to our Clerk
        publishable key, which starts with <Code>pk_test_</Code> (see{' '}
        <Code>frontend/.env.example</Code>). Then restart <Code>npm run dev</Code>.
      </Alert>
    </Container>
  );
}
