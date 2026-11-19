import type { ReactNode } from 'react';
import { useLocation, Link, Outlet, matchPath } from 'react-router-dom';
import {
  AppShell,
  Burger,
  Group,
  NavLink,
  Text,
  Badge,
  Button,
  Skeleton,
  Box,
  ScrollArea,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { SignOutButton } from '@clerk/react';

import { useGetMe } from '@/api/me';
import { ApiError } from '@/apiClient';

/**
 * App shell layout with role-specific navigation, responsive header/navbar,
 * user status, and error handling.
 *
 * The role-specific parts (badge and navigation) only show once GET /me has given the
 * role. The URL is not used to guess it, so a patient who opens a /therapist link never
 * sees therapist navigation, not even briefly.
 */
export default function AppShellLayout({ children }: { children?: ReactNode }) {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const { data: me, error } = useGetMe();

  const role = me?.role;
  // Skeletons until the role is known; if /me fails, a neutral shell (no role-specific
  // parts) next to the error text in the header.
  const isLoadingRole = !role && !error;

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{
        width: 250,
        breakpoint: 'sm',
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Text
              fw={800}
              size="lg"
              c="teal.8"
              component={Link}
              to="/"
              style={{ textDecoration: 'none' }}
            >
              PTAssist
            </Text>
            {isLoadingRole ? (
              <Skeleton height={20} width={70} radius="xl" />
            ) : role === 'therapist' ? (
              <Badge color="blue" variant="light" size="sm">
                Therapist
              </Badge>
            ) : role === 'patient' ? (
              <Badge color="teal" variant="light" size="sm">
                Patient
              </Badge>
            ) : null}
          </Group>

          <Group gap="sm">
            {me && (
              // Hidden on phones, where it would push Sign out off the header.
              <Text size="sm" c="dimmed" visibleFrom="sm">
                Signed in as {me.email}
              </Text>
            )}
            {error && (
              <Text size="sm" c="red">
                {describeError(error)}
              </Text>
            )}
            <SignOutButton redirectUrl="/sign-in">
              <Button variant="default" size="xs">
                Sign out
              </Button>
            </SignOutButton>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <AppShell.Section grow component={ScrollArea}>
          {isLoadingRole ? (
            <Box py="xs">
              <Skeleton height={18} width={120} mb="md" />
              <Skeleton height={36} radius="sm" mb="sm" />
              <Skeleton height={36} radius="sm" mb="sm" />
              <Skeleton height={36} radius="sm" mb="sm" />
            </Box>
          ) : role === 'therapist' ? (
            <Box>
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb="xs">
                Therapist Dashboard
              </Text>
              <NavLink
                component={Link}
                to="/therapist"
                label="Patients"
                description="Patient roster & status"
                active={location.pathname === '/therapist'}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/therapist/plans"
                label="Plan Builder"
                description="Prescribe exercises"
                active={
                  location.pathname === '/therapist/plans' ||
                  // Also while building one patient's plan.
                  matchPath('/therapist/patients/:patientId/plan', location.pathname) !== null
                }
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/therapist/progress"
                label="Progress & Analytics"
                description="Longitudinal compliance"
                active={location.pathname === '/therapist/progress'}
                onClick={close}
              />
            </Box>
          ) : role === 'patient' ? (
            <Box>
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb="xs">
                Patient Portal
              </Text>
              <NavLink
                component={Link}
                to="/patient"
                label="My Plan"
                description="Today's exercises"
                active={location.pathname === '/patient'}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/patient/upload"
                label="Upload Video"
                description="Record & submit session"
                active={location.pathname === '/patient/upload'}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/patient/history"
                label="Results & History"
                description="AI feedback & past logs"
                active={location.pathname === '/patient/history'}
                onClick={close}
              />
            </Box>
          ) : (
            <Text size="sm" c="dimmed">
              Navigation is unavailable until your account loads.
            </Text>
          )}
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>{children ?? <Outlet />}</AppShell.Main>
    </AppShell>
  );
}

/**
 * Explains an error from GET /me, with the API's own message when available.
 */
function describeError(error: Error): string {
  if (!(error instanceof ApiError)) {
    return 'Could not load your account: no answer from the API.';
  }
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  const explanation = typeof detail === 'string' ? `: ${detail}` : '.';
  return `Could not load your account. The API answered ${error.status}${explanation}`;
}
