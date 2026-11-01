import { Navigate, useLocation } from 'react-router-dom';
import { Alert, Center, Loader } from '@mantine/core';
import { useRole } from '@/hooks/useRole';
import { ApiError } from '@/apiClient';

export default function RoleRedirect() {
  const { role, isLoading, isError, error } = useRole();
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
  if (isError || !role) {
    return <Alert color="red">Couldn't load your account.</Alert>;
  }
  return <Navigate to={role === 'therapist' ? '/therapist' : '/patient'} replace />;
}
