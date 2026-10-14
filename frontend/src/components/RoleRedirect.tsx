import { Navigate } from 'react-router-dom';
import { Alert, Center, Loader } from '@mantine/core';
import { useRole } from '@/hooks/useRole';

export default function RoleRedirect() {
  const { role, isLoading, isError } = useRole();
  if (isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (isError || !role) {
    return <Alert color="red">Couldn't load your account.</Alert>;
  }
  return <Navigate to={role === 'therapist' ? '/therapist' : '/patient'} replace />;
}