/**
 * Convenience aliases over the generated OpenAPI types.
 *
 * `src/types/api.generated.ts` is produced by `npm run generate:api-types`
 * (see that script and `docs/api-types.md`) directly from the backend's
 * `/openapi.json` — it is never hand-edited. Everything in this file is a
 * thin, readable name for a `components["schemas"][...]` type, so the rest
 * of the app imports `LoginRequest` instead of reaching into the generated
 * structure at every call site.
 */
import type { components } from '@/types/api.generated'

export type Schemas = components['schemas']

export type LoginRequest = Schemas['LoginRequest']
export type RefreshTokenRequest = Schemas['RefreshTokenRequest']
export type TokenResponse = Schemas['TokenResponse']
export type UserResponse = Schemas['UserResponse']
export type UserDetailResponse = Schemas['UserDetailResponse']
export type UserListResponse = Schemas['UserListResponse']
export type UserCreateRequest = Schemas['UserCreateRequest']
export type UserUpdateRequest = Schemas['UserUpdateRequest']
export type SelfUpdateRequest = Schemas['SelfUpdateRequest']
export type RoleUpdateRequest = Schemas['RoleUpdateRequest']
export type PasswordChangeRequest = Schemas['PasswordChangeRequest']
export type PasswordChangeResponse = Schemas['PasswordChangeResponse']
export type UserAuditResponse = Schemas['UserAuditResponse']

export type TenantResponse = Schemas['TenantResponse']
export type TenantUpdateRequest = Schemas['TenantUpdateRequest']

export type AttendanceLocationResponse = Schemas['AttendanceLocationResponse']
export type AttendanceLocationCreateRequest = Schemas['AttendanceLocationCreateRequest']
export type AttendanceLocationUpdateRequest = Schemas['AttendanceLocationUpdateRequest']

export type TenantOnboardingRequest = Schemas['TenantOnboardingRequest']
export type TenantOnboardingResponse = Schemas['TenantOnboardingResponse']
export type EmailVerificationRequest = Schemas['EmailVerificationRequest']
export type ResendVerificationRequest = Schemas['ResendVerificationRequest']
export type ResendVerificationResponse = Schemas['ResendVerificationResponse']

export type DisplayTokenCreateRequest = Schemas['DisplayTokenCreateRequest']
export type DisplayTokenCreateResponse = Schemas['DisplayTokenCreateResponse']
export type DisplayTokenResponse = Schemas['DisplayTokenResponse']
export type DisplayTokenListResponse = Schemas['DisplayTokenListResponse']

export type QRChallengeResponse = Schemas['QRChallengeResponse']
export type PresenceVerificationRequest = Schemas['PresenceVerificationRequest']
export type PresenceVerificationResponse = Schemas['PresenceVerificationResponse']

export type AttendanceActionRequest = Schemas['AttendanceActionRequest']
export type AttendanceActionResponse = Schemas['AttendanceActionResponse']
export type AttendanceTodayResponse = Schemas['AttendanceTodayResponse']
export type AttendanceDayResponse = Schemas['AttendanceDayResponse']
export type AttendanceHistoryResponse = Schemas['AttendanceHistoryResponse']
export type AttendanceSessionResponse = Schemas['AttendanceSessionResponse']
export type TeamAttendanceResponse = Schemas['TeamAttendanceResponse']
export type TeamAttendanceMember = Schemas['TeamAttendanceMember']
export type TeamAttendanceSummary = Schemas['TeamAttendanceSummary']

export type UserRole = Schemas['UserRole']
export type UserStatus = Schemas['UserStatus']
export type AttendanceState = Schemas['AttendanceState']
export type DayStatus = Schemas['DayStatus']
export type FailureReason = Schemas['FailureReason']

/** The four roles that exist. `UserResponse.role` is typed `string` by the
 * backend on purpose (see `app/schemas/user.py`) — this is what lets the
 * frontend narrow it back safely instead of trusting the string blindly. */
export const USER_ROLES: readonly UserRole[] = ['SUPER_ADMIN', 'TENANT_ADMIN', 'MANAGER', 'STAFF']

export function isUserRole(value: string): value is UserRole {
  return (USER_ROLES as readonly string[]).includes(value)
}

/** Roles a tenant administrator may assign. SUPER_ADMIN is a platform role —
 * the backend rejects assigning it with a 422, so it is never offered here. */
export const ASSIGNABLE_ROLES = ['TENANT_ADMIN', 'MANAGER', 'STAFF'] as const
