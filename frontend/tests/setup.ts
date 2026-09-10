import { configure } from '@testing-library/dom'
import '@testing-library/jest-dom/vitest'

// jsdom has no real geolocation/camera hardware and no service worker
// container; individual tests stub `navigator.geolocation` /
// `navigator.mediaDevices` themselves (see tests/unit/useGeolocation.test.ts)
// rather than a single blanket mock here, so each test's assumptions about
// what the "device" does are visible at the call site.

// Testing Library's default findBy*/waitFor timeout is 1000ms. The full
// suite runs 25 files' worth of jsdom environments concurrently, and under
// heavy CPU contention (many parallel test files, a busy dev machine) a
// perfectly correct async assertion can occasionally lose the race against
// that fixed timeout — not because anything is broken, but because the
// process didn't get scheduled in time. Raising the ceiling gives real
// slowness room to still pass; it does nothing to hide a genuine failure,
// since a broken assertion still never resolves and still times out either
// way, just later.
configure({ asyncUtilTimeout: 5000 })
