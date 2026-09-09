import { useQuery } from '@tanstack/react-query'

import * as displayApi from '@/lib/api/endpoints/display'

/**
 * Keeps one QR challenge on screen, always fetched a few seconds before the
 * current one expires — never left showing an already-lapsed code waiting
 * for the next tick, and briefly overlapping with the previous code exactly
 * the way the backend's own issuance comment describes ("the display fetches
 * the next code slightly before the current one lapses").
 *
 * `refetchInterval` (not a hand-rolled `setTimeout` loop) keeps this on
 * React Query's own scheduling/cleanup and gives the kiosk "recover
 * gracefully from network failures" for free: a failed fetch leaves the
 * previous QR on screen (`data` is untouched by a failed refetch) and the
 * next scheduled attempt tries again regardless of whether this one failed.
 */
export function useDisplayQrChallenge(displayToken: string | null) {
  return useQuery({
    queryKey: ['display', 'qr-challenge', displayToken],
    queryFn: ({ signal }) => {
      if (!displayToken) throw new Error('No display token configured')
      return displayApi.createQrChallengeForDisplay(displayToken, signal)
    },
    enabled: displayToken !== null,
    staleTime: 0,
    retry: 2,
    refetchIntervalInBackground: true,
    refetchInterval: (query) => {
      const data = query.state.data
      // No successful fetch yet (or none survived) — retry soon rather than
      // waiting out a full QR lifetime with a blank screen.
      if (!data) return 5_000
      const marginSeconds = Math.min(5, Math.max(1, Math.floor(data.expires_in / 4)))
      return Math.max(1_000, (data.expires_in - marginSeconds) * 1000)
    },
  })
}
