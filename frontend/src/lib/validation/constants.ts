/**
 * Field bounds mirrored from the backend's `app/schemas/fields.py`. Kept
 * here, once, rather than repeated as magic numbers in every form schema —
 * if the backend ever changes one of these, this file (and the OpenAPI
 * regeneration that should prompt someone to check it) is the one place to
 * update. Client-side validation using these is a fast-feedback convenience
 * only; the backend re-validates everything regardless (§27).
 */
export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128
export const NAME_MAX_LENGTH = 255
export const EMPLOYEE_CODE_MAX_LENGTH = 100
export const SLUG_MAX_LENGTH = 100
