import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { useRole } from '@/hooks/useRole';

export default function RoleRoute({
  role,
  children,
}: {
  role: 'patient' | 'therapist';
  children: ReactNode;
}) {
  const { role: myRole, isLoading } = useRole();
  if (isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (myRole !== role) return <Navigate to="/" replace />;
  return <>{children}</>;
}