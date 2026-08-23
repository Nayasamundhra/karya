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

export type QRChallengeResponse = Schemas['QRChallengeResponse']
export type PresenceVerificationRequest = Schemas['PresenceVerificationRequest']
export type PresenceVerificationResponse = Schemas['PresenceVerificationResponse']

export type AttendanceActionRequest = Schemas['AttendanceActionRequest']
export type AttendanceActionResponse = Schemas['AttendanceActionResponse']
export type AttendanceTodayResponse = Schemas['AttendanceTodayResponse']
export type AttendanceDayResponse = Schemas['AttendanceDayResponse']
export type AttendanceHistoryResponse = Schemas['AttendanceHistoryResponse']
export type TeamAttendanceResponse = Schemas['TeamAttendanceResponse']

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
export const ASSIGNABLE_ROLES: readonly UserRole[] = ['TENANT_ADMIN', 'MANAGER', 'STAFF']
