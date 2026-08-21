import '@testing-library/jest-dom/vitest'

// jsdom has no real geolocation/camera hardware and no service worker
// container; individual tests stub `navigator.geolocation` /
// `navigator.mediaDevices` themselves (see tests/unit/useGeolocation.test.ts)
// rather than a single blanket mock here, so each test's assumptions about
// what the "device" does are visible at the call site.
