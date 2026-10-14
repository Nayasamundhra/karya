/**
 * Class overrides that turn the app's stock `Input` into the public-page
 * (login / sign up) field: white, 12px-rounded, purple focus ring. Passed as
 * `className` rather than adding a variant to `Input`, because only these two
 * forms use it and the signed-in app's inputs are not being restyled yet.
 */
export const brandInputClass =
  'min-h-12 rounded-xl border-brand-indigo/20 bg-white text-base shadow-xs ' +
  'placeholder:text-brand-indigo/40 focus-visible:ring-brand-purple'

/** The small uppercase "section label" used above headings on public pages. */
export const eyebrowClass = 'text-[11px] font-semibold uppercase tracking-[0.2em]'
