import { useCallback, useSyncExternalStore } from 'react'

import { getAppliedTheme, setTheme, subscribeToTheme, type Theme } from '@/lib/theme/theme'

export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void; toggleTheme: () => void } {
  const theme = useSyncExternalStore(subscribeToTheme, getAppliedTheme, () => 'light' as const)
  const toggleTheme = useCallback(() => setTheme(getAppliedTheme() === 'dark' ? 'light' : 'dark'), [])
  return { theme, setTheme, toggleTheme }
}
