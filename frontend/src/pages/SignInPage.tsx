import { Center } from '@mantine/core';
import { SignIn } from '@clerk/react';

import AuthLoading from '@/components/AuthLoading';

/**
 * Clerk's sign-in form. With routing="path", its later steps get their own addresses
 * under /sign-in (for example /sign-in/factor-one), which is why App.tsx routes
 * "/sign-in/*" here. A link on the form leads to /sign-up for new users.
 * Until Clerk has loaded, the fallback shows instead of the form.
 */
export default function SignInPage() {
  return (
    <Center mih="100vh" p="md">
      <SignIn routing="path" path="/sign-in" fallback={<AuthLoading />} />
    </Center>
  );
}
