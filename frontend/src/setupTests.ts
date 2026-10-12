/**
 * Runs before every test file (vite.config.ts, test.setupFiles).
 *
 * Tests run in jsdom, a simulated browser that lacks some browser features. Mantine
 * needs window.matchMedia (to read the light/dark preference), so this adds a stand-in
 * that matches nothing. Mantine's testing guide recommends the same. It lists a few more
 * stand-ins (ResizeObserver, scrollIntoView): add them here when a test needs them.
 */
window.matchMedia = (query: string): MediaQueryList => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
});
