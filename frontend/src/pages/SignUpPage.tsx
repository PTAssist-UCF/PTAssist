import { Center } from '@mantine/core';
import { SignUp } from '@clerk/react';

import AuthLoading from '@/components/AuthLoading';

/**
 * Clerk's sign-up form, for new users. The API creates every new user as a patient on
 * their first request. Like the sign-in page, its later steps live under /sign-up, and
 * the fallback shows until Clerk has loaded.
 */
export default function SignUpPage() {
  return (
    <Center mih="100vh" p="md">
      <SignUp routing="path" path="/sign-up" fallback={<AuthLoading />} />
    </Center>
  );
}
