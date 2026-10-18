import { useGetMe } from '@/api/me';

export function useRole() {
  const { data, isLoading, isError } = useGetMe();
  return { role: data?.role, isLoading, isError };
}
