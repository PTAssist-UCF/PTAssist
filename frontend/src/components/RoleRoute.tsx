import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { useRole } from '@/hooks/useRole';
import { ApiError } from '@/apiClient';

export default function RoleRoute({
  role,
  children,
}: {
  role: 'patient' | 'therapist';
  children: ReactNode;
}) {
  const { role: myRole, isLoading, error } = useRole();
  const location = useLocation();

  if (isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (error instanceof ApiError && error.status === 401) {
    const here = location.pathname + location.search + location.hash;
    return <Navigate to={`/sign-in?redirect_url=${encodeURIComponent(here)}`} replace />;
  }
  if (myRole !== role) return <Navigate to="/" replace />;
  return <>{children}</>;
}
