import { useGetMe } from '@/api/me';

export function useRole() {
  const { data, isLoading, isError, error } = useGetMe();
  return { role: data?.role, isLoading, isError, error };
}
